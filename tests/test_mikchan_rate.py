from fastapi import FastAPI
from fastapi.testclient import TestClient

import mikchan_rate.mikchan_rate as rate
from mikchan_rate.mikchan_rate import FAVICON, prepare_embed, router
from orchestrator.home import home_payload


EMBED = """<!DOCTYPE html>
<html lang="ru">
<head>
  <link rel="icon" href="/favicon.svg" type="image/svg+xml">
  <link rel="stylesheet" href="/styles.css">
</head>
<body>
  <footer class="footer">
    <span id="latest"></span>
    <a class="embed-open" href="/" target="_blank" rel="noopener">открыть график</a>
  </footer>
  <script type="module" src="/chart.js"></script>
</body>
</html>
"""


def setup_function() -> None:
    rate._cached_html = ""
    rate._cached_at = 0.0


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/mikchan-rate")
    return TestClient(app)


def test_the_embed_copy_drops_the_open_chart_link_and_keeps_dashboard_files():
    prepared = prepare_embed(EMBED)
    assert "открыть график" not in prepared
    assert "embed-open" not in prepared
    assert f'<base href="{rate.ORIGIN}/">' in prepared
    assert '<script src="/chart.js"></script>' in prepared
    assert "type=\"module\"" not in prepared
    assert 'href="/favicon.svg"' in prepared
    assert 'source: "mikchan-rate"' in prepared
    assert 'class="is-embed"' in prepared


def test_the_page_uses_the_dashboard_icon_and_hides_the_open_chart_link(monkeypatch):
    monkeypatch.setattr(rate, "fetch_embed_html", lambda: EMBED)
    page = _client().get("/mikchan-rate")
    assert page.status_code == 200
    assert "text/html" in page.headers["content-type"]
    assert f'rel="icon" href="{FAVICON}"' in page.text
    assert "открыть график" not in page.text
    assert "embed-open" not in page.text
    assert 'sandbox="allow-scripts"' in page.text
    assert 'title="Курс макарок"' in page.text
    assert "<main hidden>" in page.text


def test_a_failed_embed_copy_is_an_error_page(monkeypatch):
    def fail() -> str:
        raise rate.UpstreamError("Страница курса не отвечает.")

    monkeypatch.setattr(rate, "fetch_embed_html", fail)
    page = _client().get("/mikchan-rate")
    assert page.status_code == 424
    assert "Не удалось показать курс" in page.text
    assert f'rel="icon" href="{FAVICON}"' in page.text


def test_the_rate_page_stays_off_the_home_cards():
    projects = home_payload(0)["projects"]
    assert "mikchan_rate" not in [project["id"] for project in projects]
    assert "/mikchan-rate" not in [project["href"] for project in projects]
