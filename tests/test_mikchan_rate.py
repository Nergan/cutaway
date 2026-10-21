import urllib.error

from fastapi import FastAPI
from fastapi.testclient import TestClient

from mikchan_rate.mikchan_rate import Upstream, UpstreamError, fetch_upstream, router
from orchestrator.home import home_payload


PAGE = """<!DOCTYPE html>
<html><head>
<link rel="stylesheet" href="/styles.css">
</head><body>
<script type="module" src="/chart.js"></script>
</body></html>
"""
SCRIPT = 'fetch("/api/rates", { cache: "no-store" });\n'


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/mikchan-rate")
    return TestClient(app)


def test_the_dashboard_is_served_from_the_hub_prefix(monkeypatch):
    def fake(url: str) -> Upstream:
        if url.endswith("/chart.js"):
            return Upstream(200, "text/javascript; charset=utf-8", SCRIPT.encode())
        if url.endswith("/api/rates"):
            return Upstream(200, "application/json", b'{"history":[],"note":"/api/rates"}')
        assert url == "https://mikchan-dashboard-worker.makarka7923.workers.dev/"
        return Upstream(200, "text/html; charset=utf-8", PAGE.encode())

    monkeypatch.setattr("mikchan_rate.mikchan_rate.fetch_upstream", fake)
    client = _client()

    page = client.get("/mikchan-rate")
    assert page.status_code == 200
    assert "text/html" in page.headers["content-type"]
    assert 'href="/mikchan-rate/styles.css"' in page.text
    assert 'src="/mikchan-rate/chart.js"' in page.text
    assert "x-frame-options" not in page.headers

    script = client.get("/mikchan-rate/chart.js")
    assert script.status_code == 200
    assert 'fetch("/mikchan-rate/api/rates"' in script.text

    rates = client.get("/mikchan-rate/api/rates")
    assert rates.status_code == 200
    assert rates.json()["note"] == "/api/rates"


def test_a_failed_dashboard_is_an_error_page(monkeypatch):
    def fake(url: str) -> Upstream:
        if url.endswith("/api/rates"):
            return Upstream(503, "text/plain", b"down")
        return Upstream(503, "text/html", b"<html>upstream exploded</html>")

    monkeypatch.setattr("mikchan_rate.mikchan_rate.fetch_upstream", fake)
    client = _client()

    page = client.get("/mikchan-rate")
    assert page.status_code == 502
    assert "Не удалось показать курс" in page.text
    assert "ответила ошибкой 503" in page.text
    assert "upstream exploded" not in page.text
    assert "Traceback" not in page.text

    rates = client.get("/mikchan-rate/api/rates")
    assert rates.status_code == 503
    assert rates.content == b""


def test_an_unreachable_dashboard_is_an_error_page(monkeypatch):
    class _Opener:
        def open(self, *_args, **_kwargs):
            raise urllib.error.URLError("timed out")

    monkeypatch.setattr("mikchan_rate.mikchan_rate.validate_outbound_url", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("mikchan_rate.mikchan_rate.urllib.request.build_opener", lambda *_args, **_kwargs: _Opener())
    try:
        fetch_upstream("https://mikchan-dashboard-worker.makarka7923.workers.dev/")
    except UpstreamError as error:
        assert error.message == "Страница курса не отвечает."
        assert error.status == 502
    else:
        raise AssertionError("expected an error page cause")

    def fake(_url: str) -> Upstream:
        raise UpstreamError("Страница курса не отвечает.")

    monkeypatch.setattr("mikchan_rate.mikchan_rate.fetch_upstream", fake)
    page = _client().get("/mikchan-rate")
    assert page.status_code == 502
    assert "не отвечает" in page.text
    assert "timed out" not in page.text


def test_the_rate_page_stays_off_the_home_cards():
    ids = [project["id"] for project in home_payload(0)["projects"]]
    assert "mikchan_rate" not in ids
    assert "/mikchan-rate" not in [project["href"] for project in home_payload(0)["projects"]]
