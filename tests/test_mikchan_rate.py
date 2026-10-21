from fastapi import FastAPI
from fastapi.testclient import TestClient

from mikchan_rate.mikchan_rate import EMBED, router
from orchestrator.home import home_payload


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/mikchan-rate")
    return TestClient(app)


def test_the_page_embeds_the_dashboard_frame():
    page = _client().get("/mikchan-rate")
    assert page.status_code == 200
    assert "text/html" in page.headers["content-type"]
    assert f'src="{EMBED}"' in page.text
    assert 'title="Курс макарок"' in page.text
    assert 'data.source !== "mikchan-rate"' in page.text
    assert "<main hidden>" in page.text
    assert "Не удалось показать курс" in page.text


def test_the_rate_page_stays_off_the_home_cards():
    projects = home_payload(0)["projects"]
    assert "mikchan_rate" not in [project["id"] for project in projects]
    assert "/mikchan-rate" not in [project["href"] for project in projects]
