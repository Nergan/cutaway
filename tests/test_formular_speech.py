"""Speech catalog and conversion routing. These tests never download weights."""

from __future__ import annotations

from pathlib import Path

import pytest

from formular.core.speech import (
    LANGUAGE_VOICES,
    SpeechError,
    VOICES,
    _letter_metadata_blob,
    _mark_letter_model,
    get_voice,
    kind,
    model_file_url,
    prepare_text,
    public_headers,
    trim_cache,
    voice_for,
    voice_from_opts,
    voices_for_text,
)
from formular.core.speech_lang import segment_languages

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


def test_speech_path_prefers_a_direct_conversion_and_still_reaches_text():
    from formular.core.graph import (
        DIRECT_EDGES,
        ai_targets_for,
        find_shortest_path,
        hop_kind,
        targets_for,
    )

    assert find_shortest_path("mp3", "wav") == ["mp3", "wav"]
    assert find_shortest_path("mp4", "ogg") == ["mp4", "ogg"]
    assert find_shortest_path("docx", "pdf") == ["docx", "pdf"]
    assert find_shortest_path("docx", "mp3") == ["docx", "txt", "mp3"]
    assert find_shortest_path("pdf", "wav") == ["pdf", "txt", "wav"]
    assert find_shortest_path("mp4", "md") == ["mp4", "txt", "md"]
    assert find_shortest_path("mp4", "pdf") == ["mp4", "txt", "pdf"]
    assert find_shortest_path("gif", "txt") == ["gif", "mp4", "txt"]
    assert find_shortest_path("gif", "pdf") == ["gif", "mp4", "txt", "pdf"]
    assert find_shortest_path("gif", "html") == ["gif", "mp4", "txt", "html"]
    assert find_shortest_path("gif", "mp3") == ["gif", "mp4", "mp3"]
    assert find_shortest_path("gif", "png") == ["gif", "png"]
    assert find_shortest_path("gif", "md") == ["gif", "mp4", "txt", "md"]
    assert find_shortest_path("webm", "pdf") == ["webm", "txt", "pdf"]
    assert find_shortest_path("jpg", "mp3") == ["jpg", "pdf", "txt", "mp3"]
    assert find_shortest_path("webm", "json") == ["webm", "txt", "json"]
    assert find_shortest_path("csv", "ogg") == ["csv", "pdf", "txt", "ogg"]
    assert find_shortest_path("zip", "txt") is None

    assert ai_targets_for("mp4")["txt"] == "transcribe"
    assert ai_targets_for("mp4")["pdf"] == "transcribe"
    assert "mp3" not in ai_targets_for("mp4")
    assert ai_targets_for("docx")["mp3"] == "speak"
    assert "pdf" not in ai_targets_for("docx")
    assert ai_targets_for("jpg")["wav"] == "speak"
    assert "txt" not in targets_for("jpg")
    assert "pdf" in targets_for("mp3")
    assert ai_targets_for("mp3")["pdf"] == "transcribe"
    assert targets_for("zip") == ["7z", "tar", "gz"]
    assert "both" not in ai_targets_for("gif").values()

    for source, targets in ((name, targets_for(name)) for name in set(DIRECT_EDGES) | {"txt"}):
        for target in targets:
            if target == source:
                continue
            path = find_shortest_path(source, target)
            assert path is not None and path[0] == source and path[-1] == target
            kinds = []
            for left, right in zip(path, path[1:]):
                kind_name = hop_kind(left, right)
                assert kind_name or right in DIRECT_EDGES.get(left, ())
                if kind_name:
                    kinds.append(kind_name)
            assert "speak" not in kinds or "transcribe" not in kinds
            marked = ai_targets_for(source).get(target)
            if kinds:
                assert marked == kinds[0]
            else:
                assert marked is None


def test_text_is_split_by_language_and_keeps_every_character():
    samples = {
        "en": "This is a test for the new voice.",
        "de": "Das ist nicht gut und auch wichtig.",
        "fr": "Les amis sont dans la maison avec nous.",
        "es": "Los amigos están aquí para comer.",
        "nl": "Het is niet voor mij en ook niet voor hem.",
        "sv": "Det är inte ett problem för mig.",
        "ru": "Это русский текст, и он не украинский.",
        "uk": "Це український текст, і він не російський.",
    }
    for lang, sentence in samples.items():
        pieces = segment_languages(sentence)
        assert [item[0] for item in pieces] == [lang]
        assert "".join(item[1] for item in pieces) == sentence

    mixed = "This is a test. Das ist nicht gut. Це український текст."
    pieces = segment_languages(mixed)
    assert [item[0] for item in pieces] == ["en", "de", "uk"]
    assert "".join(item[1] for item in pieces) == mixed

    inline = "Hello Привет"
    pieces = segment_languages(inline)
    assert [item[0] for item in pieces] == ["en", "ru"]
    assert "".join(item[1] for item in pieces) == inline


def test_language_voices_follow_gender_and_stay_permissive():
    norman = get_voice("norman")
    cori = get_voice("cori")
    assert voice_for(norman, "en").id == "norman"
    assert voice_for(norman, "ru").id == "norman"
    assert voice_for(norman, "de").id == "de-mls"
    assert voice_for(norman, "nl").id == "nl-rdh"
    assert voice_for(cori, "nl").id == "nl-nathalie"
    assert voice_for(norman, "uk").sid == 1
    assert voice_for(cori, "uk").sid == 0
    assert voice_for(cori, "es").id == "es-carlfm"
    spoken = voices_for_text(norman, "This is a test. Das ist nicht gut.")
    assert [voice.id for voice in spoken] == ["norman", "de-mls"]
    for voice in LANGUAGE_VOICES:
        lowered = voice.license.lower()
        assert "nc" not in lowered
        assert "sa" not in lowered
        assert model_file_url(voice.repo, voice.onnx).startswith("https://huggingface.co/")


def test_ukrainian_voice_reads_letters_and_the_mark_is_written_once():
    assert voice_for(get_voice("norman"), "uk").characters
    assert voice_for(get_voice("cori"), "uk").characters
    assert all(voice.characters for voice in LANGUAGE_VOICES if voice.lang == "uk")
    assert all(not voice.characters for voice in list(VOICES) + list(LANGUAGE_VOICES) if voice.lang != "uk")
    blob = _letter_metadata_blob()
    assert b"characters" in blob
    path = ROOT / ".pytest-tmp" / "letter-mark.bin"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"model")
    note = path.with_name(path.name + ".letters")
    note.unlink(missing_ok=True)
    _mark_letter_model(path)
    marked = path.read_bytes()
    _mark_letter_model(path)
    assert path.read_bytes() == marked
    assert marked.endswith(blob)


def test_spoken_headers_name_every_language_voice():
    source = ROOT / ".pytest-tmp" / "speech-note.txt"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("This is a test. Das ist nicht gut.", encoding="utf-8")
    headers = public_headers("speak", '{"voice":"ljspeech"}', source)
    assert "ljspeech-high" in headers["X-AI-Model"]
    assert "de_DE-mls-medium" in headers["X-AI-Model"]
    assert "CC-BY-4.0" in headers["X-AI-License"]
    assert "public-domain" in headers["X-AI-License"]


def test_backup_catalog_offers_transcripts_and_speech():
    from formular.core.graph import ai_targets_for, targets_for

    for source in ("mp3", "wav", "ogg", "mp4", "webm"):
        assert "txt" in targets_for(source)
        assert ai_targets_for(source)["txt"] == "transcribe"
    for target in ("mp3", "wav", "ogg"):
        assert target in targets_for("txt")
        assert ai_targets_for("txt")[target] == "speak"
    for source in ("docx", "pdf", "html", "md", "epub", "csv"):
        assert "mp3" in targets_for(source)
        assert ai_targets_for(source)["mp3"] == "speak"
    endpoints = (ROOT / "formular" / "api" / "endpoints.py").read_text(encoding="utf-8")
    assert "speech.convert" in endpoints
    assert "X-AI-Operation" in (ROOT / "formular" / "core" / "speech.py").read_text(encoding="utf-8")
