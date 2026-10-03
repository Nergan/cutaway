"""Speech to text and text to speech.

Weights stay in the runtime temp directory and are fetched from Hugging Face
when a task needs them. The speech engine is imported only when a task runs.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import threading
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

_TRANSCRIBE_SOURCES = frozenset({"mp3", "wav", "ogg", "mp4", "webm"})
_SPEAK_TARGETS = frozenset({"mp3", "wav", "ogg"})
_MAX_TEXT_CHARS = 4000
_MAX_TEXT_BYTES = 1_000_000
_MAX_AUDIO_SECONDS = 180
_MAX_FILE_BYTES = 160 * 1024 * 1024
_WHISPER_REPO = "csukuangfj/sherpa-onnx-whisper-tiny"
_ESPEAK_REPO = "csukuangfj/vits-piper-en_US-norman-medium"
_SAMPLE = "This is a sample of the voice."
_LOCK = threading.Lock()


class SpeechError(Exception):
    def __init__(self, message: str, status: int = 422):
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class Voice:
    id: str
    label: str
    gender: str
    lang: str
    repo: str
    onnx: str
    license: str
    sample: str = _SAMPLE


# Public-domain datasets, trained from scratch or from another public-domain voice.
VOICES = (
    Voice(
        "norman",
        "Norman",
        "male",
        "en",
        "csukuangfj/vits-piper-en_US-norman-medium",
        "en_US-norman-medium.onnx",
        "public-domain",
    ),
    Voice(
        "john",
        "John",
        "male",
        "en",
        "csukuangfj/vits-piper-en_US-john-medium",
        "en_US-john-medium.onnx",
        "public-domain",
    ),
    Voice(
        "ljspeech",
        "LJ Speech",
        "female",
        "en",
        "csukuangfj/vits-piper-en_US-ljspeech-high",
        "en_US-ljspeech-high.onnx",
        "public-domain",
    ),
    Voice(
        "cori",
        "Cori",
        "female",
        "en-GB",
        "csukuangfj/vits-piper-en_GB-cori-medium",
        "en_GB-cori-medium.onnx",
        "public-domain",
    ),
)


def kind(source: str, target: str) -> str | None:
    if source in _TRANSCRIBE_SOURCES and target == "txt":
        return "transcribe"
    if source == "txt" and target in _SPEAK_TARGETS:
        return "speak"
    return None


def get_voice(voice_id: str) -> Voice:
    for voice in VOICES:
        if voice.id == voice_id:
            return voice
    raise SpeechError("Unknown voice.", 404)


def voice_from_opts(raw: str | None) -> Voice:
    voice_id = "norman"
    if raw:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise SpeechError("Voice options are not valid.", 422) from exc
        if isinstance(payload, dict) and payload.get("voice"):
            voice_id = str(payload["voice"])
    return get_voice(voice_id)


def prepare_text(raw: str) -> str:
    text = raw.replace("\x00", "").strip()
    if not text:
        raise SpeechError("The text file is empty.", 422)
    if len(text) > _MAX_TEXT_CHARS:
        raise SpeechError("Text longer than 4000 characters is not spoken.", 422)
    return text


def public_voices() -> list[dict[str, str | bool]]:
    return [
        {
            "id": voice.id,
            "label": voice.label,
            "gender": voice.gender,
            "lang": voice.lang,
            "license": voice.license,
            "ai": True,
        }
        for voice in VOICES
    ]


def public_headers(operation: str, audio_opts: str | None = None) -> dict[str, str]:
    headers = {"X-Content-Type-Options": "nosniff"}
    if operation == "transcribe":
        headers["X-AI-Operation"] = "speech.transcribe"
        headers["X-AI-Model"] = _WHISPER_REPO
        headers["X-AI-License"] = "MIT"
        return headers
    voice = voice_from_opts(audio_opts)
    headers["X-AI-Operation"] = "speech.speak"
    headers["X-AI-Model"] = voice.repo
    headers["X-AI-License"] = voice.license
    return headers


def model_file_url(repo: str, relative: str) -> str:
    return f"https://huggingface.co/{repo}/resolve/main/{quote(relative, safe='/')}"


def cache_root() -> Path:
    override = os.environ.get("FORMULAR_MODEL_CACHE")
    root = Path(override) if override else Path(tempfile.gettempdir()) / "formular_models"
    root.mkdir(parents=True, exist_ok=True)
    return root


def trim_cache() -> None:
    root = cache_root()
    cap = int(os.environ.get("FORMULAR_MODEL_CACHE_BYTES", str(700 * 1024 * 1024)))

    def total() -> int:
        return sum(
            path.stat().st_size
            for path in root.rglob("*")
            if path.is_file() and not path.name.endswith(".part")
        )

    if total() <= cap:
        return
    samples = root / "samples"
    if samples.is_dir():
        oldest = sorted(
            (path for path in samples.iterdir() if path.is_file()),
            key=lambda path: path.stat().st_mtime,
        )
        for path in oldest:
            path.unlink(missing_ok=True)
            if total() <= cap:
                return


def convert(operation: str, source: Path, dest: Path, target: str, audio_opts: str | None) -> None:
    if operation == "transcribe":
        with _LOCK, _busy():
            text = _transcribe(source)
        dest.write_text(text + ("\n" if text else ""), encoding="utf-8")
        return
    if operation == "speak":
        voice = voice_from_opts(audio_opts)
        spoken = _read_text(source)
        with _LOCK, _busy():
            _speak(voice, spoken, dest, target)
        return
    raise SpeechError("Unsupported speech conversion.", 422)


def sample_path(voice_id: str) -> Path:
    voice = get_voice(voice_id)
    dest = cache_root() / "samples" / f"{voice.id}.wav"
    if dest.is_file() and dest.stat().st_size > 44:
        return dest
    with _LOCK, _busy():
        if dest.is_file() and dest.stat().st_size > 44:
            return dest
        dest.parent.mkdir(parents=True, exist_ok=True)
        _tts_to_wav(voice, voice.sample, dest)
    return dest


def _read_text(path: Path) -> str:
    size = path.stat().st_size
    if size > _MAX_TEXT_BYTES:
        raise SpeechError("The text file is too large to speak.", 413)
    return prepare_text(path.read_text(encoding="utf-8", errors="replace"))


def _touch_busy() -> None:
    marker = os.environ.get("CUTAWAY_BUSY_FILE")
    if not marker:
        return
    try:
        Path(marker).touch()
    except OSError:
        return


@contextmanager
def _busy():
    stop = threading.Event()

    def pulse() -> None:
        while not stop.wait(15):
            _touch_busy()

    _touch_busy()
    thread = threading.Thread(target=pulse, daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()


def _sherpa():
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    try:
        import sherpa_onnx
    except ImportError as exc:
        raise SpeechError("The speech engine is not installed on this server.", 503) from exc
    return sherpa_onnx


def _fetch(url: str, dest: Path, *, trim: bool = True) -> None:
    from shared_network import NetworkPolicyError, SafeRedirectHandler, validate_outbound_url

    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_name(dest.name + ".part")
    opener = urllib.request.build_opener(SafeRedirectHandler())
    request = urllib.request.Request(url, headers={"User-Agent": "formular"})
    for attempt in range(6):
        try:
            validate_outbound_url(url)
        except NetworkPolicyError as exc:
            if "budget" in str(exc).lower() and attempt < 5:
                time.sleep(2)
                continue
            raise SpeechError(f"The download was blocked by the network policy. {exc}", 502) from exc
        try:
            with opener.open(request, timeout=180) as response, partial.open("wb") as handle:
                total = 0
                while True:
                    chunk = response.read(256 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > _MAX_FILE_BYTES:
                        raise SpeechError("The model file is larger than allowed.", 413)
                    handle.write(chunk)
                    _touch_busy()
            break
        except SpeechError:
            partial.unlink(missing_ok=True)
            raise
        except urllib.error.HTTPError as exc:
            partial.unlink(missing_ok=True)
            if exc.code in {429, 503} and attempt < 5:
                time.sleep(1 + attempt)
                continue
            raise SpeechError("The model file could not be downloaded.", 503) from exc
        except Exception as exc:
            partial.unlink(missing_ok=True)
            raise SpeechError("The model file could not be downloaded.", 503) from exc
    partial.replace(dest)
    if trim:
        trim_cache()


def _ensure_file(repo: str, relative: str, dest: Path, size: int | None = None, *, trim: bool = True) -> Path:
    if dest.is_file():
        current = dest.stat().st_size
        if current > 0 and (size is None or current == size):
            return dest
    _fetch(model_file_url(repo, relative), dest, trim=trim)
    return dest


def _tree(repo: str) -> list[dict]:
    url = f"https://huggingface.co/api/models/{repo}/tree/main?recursive=1"
    listing = cache_root() / "lists" / (repo.replace("/", "__") + ".json")
    if not listing.is_file():
        _fetch(url, listing)
    try:
        payload = json.loads(listing.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        listing.unlink(missing_ok=True)
        raise SpeechError("The model file list could not be read.", 503) from exc
    if not isinstance(payload, list):
        raise SpeechError("The model file list could not be read.", 503)
    return payload


def _ensure_espeak() -> Path:
    from concurrent.futures import ThreadPoolExecutor

    root = cache_root() / "espeak-ng-data"
    marker = root / ".complete"
    if marker.is_file():
        return root
    pending = []
    for item in _tree(_ESPEAK_REPO):
        relative = str(item.get("path") or "")
        if item.get("type") != "file" or not relative.startswith("espeak-ng-data/"):
            continue
        pending.append((relative, item.get("size")))

    def fetch_one(item: tuple[str, int | None]) -> None:
        relative, size = item
        _ensure_file(_ESPEAK_REPO, relative, cache_root() / relative, size, trim=False)

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(fetch_one, pending))
    trim_cache()
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("ok", encoding="utf-8")
    return root


def _ensure_voice_files(voice: Voice) -> tuple[Path, Path]:
    folder = cache_root() / "voices" / voice.id
    model = _ensure_file(voice.repo, voice.onnx, folder / voice.onnx)
    tokens = _ensure_file(voice.repo, "tokens.txt", folder / "tokens.txt")
    return model, tokens


def _ensure_whisper() -> tuple[Path, Path, Path]:
    folder = cache_root() / "whisper"
    encoder = _ensure_file(_WHISPER_REPO, "tiny-encoder.int8.onnx", folder / "tiny-encoder.int8.onnx")
    decoder = _ensure_file(_WHISPER_REPO, "tiny-decoder.int8.onnx", folder / "tiny-decoder.int8.onnx")
    tokens = _ensure_file(_WHISPER_REPO, "tiny-tokens.txt", folder / "tiny-tokens.txt")
    return encoder, decoder, tokens


def _tts_to_wav(voice: Voice, text: str, dest: Path) -> None:
    sherpa = _sherpa()
    espeak = _ensure_espeak()
    model, tokens = _ensure_voice_files(voice)
    config = sherpa.OfflineTtsConfig(
        model=sherpa.OfflineTtsModelConfig(
            vits=sherpa.OfflineTtsVitsModelConfig(
                model=str(model),
                lexicon="",
                tokens=str(tokens),
                data_dir=str(espeak),
            ),
            num_threads=1,
            provider="cpu",
        )
    )
    engine = sherpa.OfflineTts(config)
    try:
        audio = engine.generate(text, sid=0, speed=1.0)
        samples = audio.samples
        if samples is None or len(samples) == 0:
            raise SpeechError("The voice produced no audio.", 422)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not sherpa.write_wave(str(dest), samples, audio.sample_rate):
            raise SpeechError("The voice audio could not be stored.", 500)
    finally:
        del engine


def _speak(voice: Voice, text: str, dest: Path, target: str) -> None:
    if target == "wav":
        _tts_to_wav(voice, text, dest)
        return
    if target not in _SPEAK_TARGETS:
        raise SpeechError("Unsupported audio format.", 422)
    wav = dest.with_name(dest.stem + ".speech.wav")
    try:
        _tts_to_wav(voice, text, wav)
        _encode(wav, dest, target)
    finally:
        wav.unlink(missing_ok=True)


def _transcribe(source: Path) -> str:
    wav = source.with_name(source.stem + ".speech16.wav")
    try:
        _extract_speech(source, wav)
        sherpa = _sherpa()
        encoder, decoder, tokens = _ensure_whisper()
        recognizer = sherpa.OfflineRecognizer.from_whisper(
            encoder=str(encoder),
            decoder=str(decoder),
            tokens=str(tokens),
            language="",
            task="transcribe",
            num_threads=1,
            decoding_method="greedy_search",
            provider="cpu",
        )
        rate, samples = _float_samples(wav)
        stream = recognizer.create_stream()
        stream.accept_waveform(rate, samples)
        recognizer.decode_stream(stream)
        return (stream.result.text or "").strip()
    finally:
        wav.unlink(missing_ok=True)


def _float_samples(path: Path):
    import wave

    import numpy as np

    with wave.open(str(path), "rb") as handle:
        rate = handle.getframerate()
        channels = handle.getnchannels()
        width = handle.getsampwidth()
        count = handle.getnframes()
        frames = handle.readframes(count)
    if channels != 1 or width != 2 or rate != 16000:
        raise SpeechError("The audio could not be prepared.", 422)
    if count > 16000 * _MAX_AUDIO_SECONDS:
        raise SpeechError("Audio longer than 3 minutes is not transcribed.", 422)
    samples = np.frombuffer(frames, dtype="<i2").astype(np.float32)
    samples /= np.float32(32768.0)
    return rate, samples


def _duration_seconds(stderr: str) -> float | None:
    match = re.search(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)", stderr)
    if match is None:
        return None
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def _extract_speech(source: Path, wav: Path) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise SpeechError("Audio tools are unavailable.", 503)
    probed = _run([ffmpeg, "-hide_banner", "-i", str(source)], timeout=60)
    stderr = probed.stderr.decode("utf-8", "replace")
    if "Audio:" not in stderr:
        raise SpeechError("This file has no audio to transcribe.", 422)
    duration = _duration_seconds(stderr)
    if duration is not None and duration > _MAX_AUDIO_SECONDS:
        raise SpeechError("Audio longer than 3 minutes is not transcribed.", 422)
    wav.parent.mkdir(parents=True, exist_ok=True)
    extracted = _run(
        [
            ffmpeg,
            "-hide_banner",
            "-y",
            "-i",
            str(source),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-t",
            str(_MAX_AUDIO_SECONDS),
            str(wav),
        ],
        timeout=300,
    )
    if extracted.returncode != 0 or not wav.is_file() or wav.stat().st_size < 1000:
        raise SpeechError("This file has no audio to transcribe.", 422)


def _encode(wav: Path, dest: Path, target: str) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise SpeechError("Audio tools are unavailable.", 503)
    codec = "libmp3lame" if target == "mp3" else "libvorbis"
    encoded = _run(
        [ffmpeg, "-hide_banner", "-y", "-i", str(wav), "-vn", "-c:a", codec, str(dest)],
        timeout=300,
    )
    if encoded.returncode != 0 or not dest.is_file() or dest.stat().st_size < 100:
        raise SpeechError("The spoken audio could not be encoded.", 422)


def _run(args: list[str], timeout: float):
    import asyncio

    from shared_runtime import SubprocessFailure, run_process

    try:
        return asyncio.run(
            run_process(
                args,
                timeout=timeout,
                capture_stderr=True,
                check=False,
                allowed_returncodes=frozenset({0, 1}),
                background=True,
            )
        )
    except FileNotFoundError as exc:
        raise SpeechError("Audio tools are unavailable.", 503) from exc
    except SubprocessFailure as exc:
        if "timed out" in str(exc):
            raise SpeechError("Speech conversion timed out.", 504) from exc
        raise SpeechError("Audio conversion failed.", 422) from exc
