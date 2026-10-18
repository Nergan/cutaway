import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import formular.api.endpoints as api
from formular.formular import router

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(api, "TEMP_DIR", tmp_path)
    api.UPLOAD_RATE._hits.clear()
    api.CHUNK_RATE._hits.clear()
    tmp_path.mkdir(parents=True, exist_ok=True)
    app = FastAPI()
    app.include_router(router, prefix="/formular")
    with TestClient(app) as running:
        yield running


def test_the_index_names_the_file_budget(client: TestClient):
    response = client.get("/formular/api")
    assert response.status_code == 200
    body = response.json()
    assert body["max_file_bytes"] <= body["max_upload_bytes"]
    assert body["chunk_bytes"] <= body["max_file_bytes"]
    assert body["max_stored_bytes"] >= body["max_file_bytes"]
    assert body["create_files"] == "POST /formular/api/files"
    assert body["create_conversion"] == "POST /formular/api/files/{id}/conversions"


def test_a_text_file_can_be_created_and_read_back(client: TestClient):
    pytest.importorskip("magic")
    created = client.post(
        "/formular/api/files",
        files=[("files", ("note.txt", b"hello", "text/plain"))],
    )
    assert created.status_code == 201
    stored = created.json()["files"][0]
    assert stored["format"] == "txt"
    assert stored["size"] == 5
    assert "md" in stored["allowed_targets"]
    assert stored["ai_targets"]["mp3"] == "speak"
    assert "md" not in stored["ai_targets"]

    fetched = client.get(f"/formular/api/files/{stored['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["filename"] == "note.txt"

    legacy = client.post(
        "/formular/api/upload",
        files=[("files", ("other.txt", b"x", "text/plain"))],
    )
    assert legacy.status_code == 200
    assert legacy.json()["files"][0]["id"]


def test_a_picture_is_not_offered_as_speech(client: TestClient):
    pytest.importorskip("magic")
    png = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
        "890000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
    )
    created = client.post(
        "/formular/api/files",
        files=[("files", ("ava.png", png, "image/png"))],
    )
    assert created.status_code == 201
    stored = created.json()["files"][0]
    assert stored["format"] == "png"
    assert "pdf" in stored["allowed_targets"]
    assert "jpg" in stored["allowed_targets"]
    for audio in ("mp3", "wav", "ogg"):
        assert audio not in stored["allowed_targets"]
        assert audio not in stored["ai_targets"]


def test_an_oversized_request_names_both_sizes(client: TestClient, monkeypatch):
    monkeypatch.setattr(api, "MAX_UPLOAD_BYTES", 32)
    response = client.post(
        "/formular/api/files",
        files=[("files", ("note.txt", b"hello", "text/plain"))],
    )
    assert response.status_code == 413
    detail = response.json()["detail"]
    assert detail.startswith("This request is ")
    assert "The maximum is 32 B." in detail


def test_a_file_past_the_budget_names_the_file(client: TestClient, monkeypatch):
    monkeypatch.setattr(api, "file_budget", lambda: 4)
    response = client.post(
        "/formular/api/files",
        files=[("files", ("note.txt", b"hello!", "text/plain"))],
    )
    assert response.status_code == 201
    assert response.json()["files"][0]["error"] == "note.txt is 6 B. The maximum is 4 B."


def test_a_file_past_one_request_is_assembled_from_pieces(client: TestClient, monkeypatch):
    pytest.importorskip("magic")
    monkeypatch.setattr(api, "MAX_UPLOAD_BYTES", 8)
    monkeypatch.setattr(api, "MAX_STORED_BYTES", 12)
    payload = b"abcdefghijkl"
    opened = client.post("/formular/api/uploads", json={"filename": "note.txt", "size": len(payload)})
    assert opened.status_code == 201
    info = opened.json()
    assert info["chunk_bytes"] == 8
    file_id = info["id"]
    for index, start in enumerate(range(0, len(payload), 8)):
        piece = client.put(f"/formular/api/uploads/{file_id}/{index}", content=payload[start:start + 8])
        assert piece.status_code == 200

    finished = client.post(f"/formular/api/uploads/{file_id}/complete")
    assert finished.status_code == 200
    stored = finished.json()["files"][0]
    assert stored["format"] == "txt"
    assert stored["size"] == 12
    assert (api.TEMP_DIR / stored["id"] / "input" / "note.txt").read_bytes() == payload
    again = client.post(f"/formular/api/uploads/{file_id}/complete")
    assert again.status_code == 200
    assert again.json()["files"][0]["id"] == stored["id"]


def test_a_gap_is_not_assembled(client: TestClient, monkeypatch):
    monkeypatch.setattr(api, "MAX_UPLOAD_BYTES", 8)
    monkeypatch.setattr(api, "MAX_STORED_BYTES", 12)
    opened = client.post("/formular/api/uploads", json={"filename": "note.txt", "size": 12})
    file_id = opened.json()["id"]
    assert client.put(f"/formular/api/uploads/{file_id}/0", content=b"abcdefgh").status_code == 200
    missing = client.post(f"/formular/api/uploads/{file_id}/complete")
    assert missing.status_code == 400
    assert missing.json()["detail"] == "Upload is missing a piece."


def test_an_upload_past_the_stored_budget_is_refused(client: TestClient, monkeypatch):
    monkeypatch.setattr(api, "MAX_UPLOAD_BYTES", 8)
    monkeypatch.setattr(api, "MAX_STORED_BYTES", 12)
    refused = client.post("/formular/api/uploads", json={"filename": "clip.mp4", "size": 13})
    assert refused.status_code == 413
    assert refused.json()["detail"] == "clip.mp4 is 13 B. The maximum is 12 B."


def test_jpeg_and_png_drop_only_metadata():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    script = ROOT / "formular" / "static" / "js" / "shrink.js"
    completed = subprocess.run(
        [node, "-e", SHRINK_CHECK, str(script)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr


SHRINK_CHECK = r"""
const { shrinkJpeg, shrinkPng } = require(process.argv[1]);
const jpeg = Uint8Array.from([
  0xff, 0xd8,
  0xff, 0xe1, 0x00, 0x08, 0x45, 0x78, 0x69, 0x66, 0x00, 0x00,
  0xff, 0xfe, 0x00, 0x05, 0x68, 0x69, 0x21,
  0xff, 0xe2, 0x00, 0x04, 0x49, 0x43,
  0xff, 0xd9,
]);
const packedJpeg = shrinkJpeg(jpeg);
if (!packedJpeg) throw new Error('jpeg was not reduced');
if (packedJpeg.length >= jpeg.length) throw new Error('jpeg did not get smaller');
const jpegText = Buffer.from(packedJpeg).toString('latin1');
if (jpegText.includes('Exif')) throw new Error('exif survived');
if (!jpegText.includes('IC')) throw new Error('color profile was removed');
if (packedJpeg[0] !== 0xff || packedJpeg[1] !== 0xd8) throw new Error('missing soi');
if (packedJpeg.at(-2) !== 0xff || packedJpeg.at(-1) !== 0xd9) throw new Error('missing eoi');

const signature = [137, 80, 78, 71, 13, 10, 26, 10];
const ihdr = [0, 0, 0, 13, 73, 72, 68, 82, 0, 0, 0, 1, 0, 0, 0, 1, 8, 2, 0, 0, 0, 0, 0, 0, 0];
const text = [0, 0, 0, 4, 116, 69, 88, 116, 104, 105, 0, 0, 0, 0, 0, 0];
const iend = [0, 0, 0, 0, 73, 69, 78, 68, 0, 0, 0, 0];
const png = Uint8Array.from([...signature, ...ihdr, ...text, ...iend]);
const packedPng = shrinkPng(png);
if (!packedPng || packedPng.length >= png.length) throw new Error('png was not reduced');
const pngText = Buffer.from(packedPng).toString('latin1');
if (pngText.includes('tEXt')) throw new Error('text chunk survived');
if (!pngText.includes('IHDR') || !pngText.includes('IEND')) throw new Error('image chunks were removed');
if (shrinkJpeg(Uint8Array.from([0xff, 0xd8, 0xff, 0xd9])) !== null) throw new Error('plain jpeg changed');
"""


def test_a_missing_file_cannot_be_converted(client: TestClient):
    response = client.post(
        "/formular/api/files/not-a-uuid/conversions",
        json={"to": "md"},
    )
    assert response.status_code == 400
