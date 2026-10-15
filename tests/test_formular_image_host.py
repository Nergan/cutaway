import io
import urllib.error

import pytest

from formular.core.image_host import CLIENT_ID_ENV, image_link, reset_upload_state, upload_image


@pytest.fixture(autouse=True)
def _clean_upload_state(monkeypatch):
    monkeypatch.delenv(CLIENT_ID_ENV, raising=False)
    reset_upload_state()
    yield
    reset_upload_state()


def test_a_successful_upload_returns_only_the_picture_address():
    assert image_link(
        {
            "success": True,
            "data": {"link": "https://i.imgur.com/abc.jpg", "deletehash": "secret"},
        }
    ) == "https://i.imgur.com/abc.jpg"
    assert image_link({"success": True, "data": {"link": "https://example.test/a.jpg"}}) is None
    assert image_link({"success": False, "status": 403, "data": {"error": "over capacity"}}) is None


def test_without_a_client_id_nothing_is_uploaded(monkeypatch):
    def fail(request, **kwargs):
        raise AssertionError(request.full_url)

    monkeypatch.setattr("formular.core.image_host.safe_urlopen", fail)
    assert upload_image(b"picture", "jpg") is None


def test_a_spent_quota_skips_the_upload(monkeypatch):
    monkeypatch.setenv(CLIENT_ID_ENV, "public-client")
    calls = []

    def fake(request, **kwargs):
        calls.append(request.full_url)
        return (
            b'{"success":true,"data":{"UserRemaining":9,"ClientRemaining":12000,"UserReset":4102444800}}'
        )

    monkeypatch.setattr("formular.core.image_host.safe_urlopen", fake)
    assert upload_image(b"picture", "jpg") is None
    assert upload_image(b"again", "jpg") is None
    assert calls == ["https://api.imgur.com/3/credits"]


def test_a_capacity_refusal_does_not_retry(monkeypatch):
    monkeypatch.setenv(CLIENT_ID_ENV, "public-client")
    calls = []

    def fake(request, **kwargs):
        calls.append(request.full_url)
        if request.full_url.endswith("/credits"):
            return b'{"success":true,"data":{"UserRemaining":100,"ClientRemaining":100}}'
        raise urllib.error.HTTPError(
            request.full_url,
            403,
            "Forbidden",
            None,
            io.BytesIO(
                b'{"data":{"error":"Imgur is temporarily over capacity. Please try again later."},"success":false,"status":403}'
            ),
        )

    monkeypatch.setattr("formular.core.image_host.safe_urlopen", fake)
    assert upload_image(b"picture", "jpg") is None
    assert upload_image(b"again", "jpg") is None
    assert calls == ["https://api.imgur.com/3/credits", "https://api.imgur.com/3/image"]


def test_one_bad_picture_does_not_block_the_next(monkeypatch):
    monkeypatch.setenv(CLIENT_ID_ENV, "public-client")
    calls = []

    def fake(request, **kwargs):
        calls.append(request.full_url)
        if request.full_url.endswith("/credits"):
            return b'{"success":true,"data":{"UserRemaining":100,"ClientRemaining":100}}'
        if calls.count("https://api.imgur.com/3/image") == 1:
            raise urllib.error.HTTPError(
                request.full_url,
                400,
                "Bad Request",
                None,
                io.BytesIO(b'{"data":{"error":"Image format not supported"},"success":false,"status":400}'),
            )
        return b'{"success":true,"status":200,"data":{"link":"https://i.imgur.com/ok.jpg"}}'

    monkeypatch.setattr("formular.core.image_host.safe_urlopen", fake)
    assert upload_image(b"bad", "jpg") is None
    assert upload_image(b"good", "png") == "https://i.imgur.com/ok.jpg"
