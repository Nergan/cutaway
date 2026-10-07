import hashlib

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import toadcode.toadcode as api


@pytest.fixture(scope="module")
def client():
    previous = api.codes_collection
    api.codes_collection = api.MemoryCollection()
    app = FastAPI()
    app.include_router(api.router, prefix="/toadcode")
    with TestClient(app) as running:
        yield running
    api.codes_collection = previous


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_publish_hash_matches_the_previous_digest():
    files = [{"path": "a.txt", "content": "hi", "is_dir": False}]
    digest = hashlib.sha256()
    digest.update(b"a.txt")
    digest.update(b"hi")
    digest.update(b"False")
    assert api._content_hash(files) == digest.hexdigest()


def test_rest_workspace_can_be_created_read_edited_and_removed(client: TestClient):
    created = client.post(
        "/toadcode/api/repos",
        json={"files": [
            {"path": "a.txt", "content": "alpha", "is_dir": False},
            {"path": "box", "is_dir": True, "content": ""},
            {"path": "box/b.txt", "content": "beta", "is_dir": False},
        ]},
    )
    assert created.status_code == 201
    body = created.json()
    token = body["token"]
    repo_id = body["id"]
    assert body["editable"] is True
    assert [item["path"] for item in body["files"]] == ["a.txt", "box/", "box/b.txt"]

    same = client.post(
        "/toadcode/api/repos",
        json={"files": [{"path": "a.txt", "content": "alpha", "is_dir": False}]},
    )
    assert same.status_code == 201
    assert same.json()["id"] != repo_id

    fetched = client.get(f"/toadcode/api/repos/{repo_id}")
    assert fetched.status_code == 200
    assert fetched.json()["files"][0]["content"] == "alpha"
    assert "token" not in fetched.json()

    one = client.get(f"/toadcode/api/repos/{repo_id}/files/box/b.txt")
    assert one.status_code == 200
    assert one.json()["content"] == "beta"

    written = client.put(
        f"/toadcode/api/repos/{repo_id}/files/notes/today.txt",
        headers=_auth(token),
        json={"content": "ship it"},
    )
    assert written.status_code == 200
    assert any(item["path"] == "notes/today.txt" and item["content"] == "ship it" for item in written.json()["files"])

    removed = client.delete(
        f"/toadcode/api/repos/{repo_id}/files/box",
        headers=_auth(token),
    )
    assert removed.status_code == 200
    assert [item["path"] for item in removed.json()["files"]] == ["a.txt", "notes/today.txt"]

    replaced = client.put(
        f"/toadcode/api/repos/{repo_id}",
        headers=_auth(token),
        json={"files": [{"path": "only.txt", "content": "one", "is_dir": False}]},
    )
    assert [item["path"] for item in replaced.json()["files"]] == ["only.txt"]

    page = client.get(f"/toadcode/{repo_id}")
    assert page.status_code == 200
    assert "only.txt" in page.text
    assert "readonly" in page.text

    deleted = client.delete(f"/toadcode/api/repos/{repo_id}", headers=_auth(token))
    assert deleted.status_code == 204
    assert client.get(f"/toadcode/api/repos/{repo_id}").status_code == 404


def test_published_page_save_stays_readable_and_read_only(client: TestClient):
    payload = {"id": "page-one", "files": [{"path": "keep.txt", "content": "same", "is_dir": False}]}
    first = client.post("/toadcode/api/save", json=payload)
    second = client.post("/toadcode/api/save", json={**payload, "id": "page-two"})
    assert first.status_code == 200
    assert first.json()["id"] == "page-one"
    assert second.json()["id"] == "page-one"

    fetched = client.get("/toadcode/api/repos/page-one")
    assert fetched.status_code == 200
    assert fetched.json()["editable"] is False
    assert fetched.json()["files"][0]["content"] == "same"

    denied = client.put(
        "/toadcode/api/repos/page-one/files/keep.txt",
        headers=_auth("nope"),
        json={"content": "changed"},
    )
    assert denied.status_code == 403
    assert client.get("/toadcode/api/repos/page-one/files/keep.txt").json()["content"] == "same"


def test_a_wrong_token_and_a_bad_path_are_rejected(client: TestClient):
    created = client.post("/toadcode/api/repos", json={"files": []}).json()
    wrong = client.put(
        f"/toadcode/api/repos/{created['id']}/files/a.txt",
        headers=_auth("not-the-token"),
        json={"content": "no"},
    )
    assert wrong.status_code == 401

    escaped = client.post(
        "/toadcode/api/repos",
        json={"files": [{"path": "../secret.txt", "content": "no", "is_dir": False}]},
    )
    assert escaped.status_code == 400

    missing = client.get("/toadcode/not-a-repo", follow_redirects=False)
    assert missing.status_code in (302, 307)

    index = client.get("/toadcode/api")
    assert index.status_code == 200
    assert index.json()["create"] == "POST /toadcode/api/repos"
