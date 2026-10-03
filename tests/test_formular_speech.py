"""Speech catalog and conversion routing. These tests never download weights."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from formular.core.speech import (
    SpeechError,
    VOICES,
    get_voice,
    kind,
    model_file_url,
    prepare_text,
    public_headers,
    trim_cache,
    voice_from_opts,
)

ROOT = Path(__file__).resolve().parents[1]


def test_speech_routes_only_the_two_operations():
    assert kind("mp3", "txt") == "transcribe"
    assert kind("wav", "txt") == "transcribe"
    assert kind("ogg", "txt") == "transcribe"
    assert kind("mp4", "txt") == "transcribe"
    assert kind("webm", "txt") == "transcribe"
    assert kind("gif", "txt") is None
    assert kind("txt", "mp3") == "speak"
    assert kind("txt", "wav") == "speak"
    assert kind("txt", "ogg") == "speak"
    assert kind("txt", "pdf") is None
    assert kind("mp3", "wav") is None


def test_voices_are_two_male_and_two_female_without_noncommercial_licenses():
    assert [voice.id for voice in VOICES] == ["norman", "john", "ljspeech", "cori"]
    assert [voice.gender for voice in VOICES] == ["male", "male", "female", "female"]
    for voice in VOICES:
        lowered = voice.license.lower()
        assert "nc" not in lowered
        assert "sa" not in lowered
        assert voice.license == "public-domain"
        url = model_file_url(voice.repo, voice.onnx)
        assert url.startswith("https://huggingface.co/")
        assert ".." not in url


def test_voice_option_rejects_unknown_and_broken_json():
    assert voice_from_opts(None).id == "norman"
    assert voice_from_opts('{"voice":"cori"}').id == "cori"
    with pytest.raises(SpeechError) as unknown:
        voice_from_opts('{"voice":"ruslan"}')
    assert unknown.value.status == 404
    with pytest.raises(SpeechError) as broken:
        voice_from_opts("{")
    assert broken.value.status == 422
    with pytest.raises(SpeechError):
        get_voice("../etc")


def test_spoken_text_rejects_empty_and_long_input():
    assert prepare_text("  Hello.  ") == "Hello."
    with pytest.raises(SpeechError) as empty:
        prepare_text(" \x00 ")
    assert empty.value.status == 422
    with pytest.raises(SpeechError) as long:
        prepare_text("a" * 4001)
    assert long.value.status == 422


def test_result_headers_name_the_ai_operation():
    transcript = public_headers("transcribe")
    assert transcript["X-AI-Operation"] == "speech.transcribe"
    assert transcript["X-AI-License"] == "MIT"
    assert transcript["X-Content-Type-Options"] == "nosniff"
    spoken = public_headers("speak", '{"voice":"ljspeech"}')
    assert spoken["X-AI-Operation"] == "speech.speak"
    assert spoken["X-AI-Model"].endswith("ljspeech-high")
    assert spoken["X-AI-License"] == "public-domain"


def test_cache_trims_samples_before_it_grows_without_a_limit(monkeypatch):
    folder = ROOT / ".pytest-tmp" / "speech-cache"
    if folder.exists():
        for path in sorted(folder.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()
    folder.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("FORMULAR_MODEL_CACHE", str(folder))
    monkeypatch.setenv("FORMULAR_MODEL_CACHE_BYTES", "100")
    samples = folder / "samples"
    samples.mkdir()
    (samples / "old.wav").write_bytes(b"x" * 80)
    (folder / "keep.bin").write_bytes(b"y" * 80)
    trim_cache()
    assert not (samples / "old.wav").exists()
    assert (folder / "keep.bin").is_file()


def _conversions() -> dict[str, list[str]]:
    module = ast.parse((ROOT / "formular" / "core" / "detector.py").read_text(encoding="utf-8"))
    for node in module.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "ALLOWED_CONVERSIONS" for target in node.targets
        ):
            return ast.literal_eval(node.value)
    raise AssertionError("ALLOWED_CONVERSIONS was not found")


def test_backup_catalog_offers_transcripts_and_speech():
    conversions = _conversions()
    for source in ("mp3", "wav", "ogg", "mp4", "webm"):
        assert "txt" in conversions[source]
    for target in ("mp3", "wav", "ogg"):
        assert target in conversions["txt"]
    endpoints = (ROOT / "formular" / "api" / "endpoints.py").read_text(encoding="utf-8")
    assert "speech.convert" in endpoints
    assert "X-AI-Operation" in (ROOT / "formular" / "core" / "speech.py").read_text(encoding="utf-8")
