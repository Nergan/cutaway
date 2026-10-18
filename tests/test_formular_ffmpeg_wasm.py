"""The browser media path names the official ffmpeg.wasm core and the same pairs the server already sends to ffmpeg."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_direct_media_names_the_official_single_thread_core():
    script = (ROOT / "formular" / "tools" / "fetch_ffmpeg_wasm.py").read_text(encoding="utf-8")
    page = (ROOT / "formular" / "static" / "js" / "ffmpeg_media.js").read_text(encoding="utf-8")
    card = (ROOT / "formular" / "static" / "js" / "card.js").read_text(encoding="utf-8")
    assert "@ffmpeg/core/-/core-0.12.6.tgz" in script
    assert "@ffmpeg/ffmpeg/-/ffmpeg-0.12.10.tgz" in script
    assert "tryFfmpegWasm" in page
    assert "tryFfmpegWasm" in card
    media = page.split("const MEDIA = new Set([", 1)[1].split("])", 1)[0]
    for ext in ("mp4", "webm", "mp3", "wav", "ogg", "gif"):
        assert f"'{ext}'" in media
    assert "png" not in media
    assert "jpg" not in media
