from fastapi import FastAPI
from fastapi.testclient import TestClient

from minecraft_mods.catalog import Catalog, JarLink, ModEntry
from minecraft_mods.search import select_mods
from orchestrator.home import home_payload


def _mod(name: str, loaders: list[str], minecraft: str = "1.21.1") -> ModEntry:
    return ModEntry(
        repo=name.casefold() + "-mod",
        name=name,
        description_en=name + " does a thing",
        description_ru="описание " + name,
        github_url="https://github.com/Nergan/" + name.casefold(),
        license_id="MIT",
        license_name="MIT License",
        license_url="https://example.invalid/license",
        version="1.0.0",
        minecraft=minecraft,
        loaders=loaders,
        mod_jars=[JarLink(name=name.casefold() + ".jar", url="https://example.invalid/a.jar", loaders=loaders)],
        dependency_jars=[],
        jars_classified=True,
        has_release=True,
        modrinth_state="linked",
        modrinth_url="https://modrinth.com/mod/" + name.casefold(),
        modrinth_status="approved",
    )


def test_home_document_names_the_projects_and_the_contacts():
    payload = home_payload(9)
    assert payload["title"] == "nargan's projects"
    assert payload["visitors"] == 9
    assert payload["links"]["github"]["url"] == "https://github.com/Nergan"
    assert payload["links"]["telegram"]["url"] == "https://t.me/kiry_vampy"
    assert "пет-проектов" in payload["welcome"]["ru"]
    ids = [project["id"] for project in payload["projects"]]
    remote = "yellow" + "_mirror"
    assert ids[0] == "evenfest"
    assert remote in ids
    assert "dnd" in ids
    assert "minecraft_mods" in ids
    assert "age" not in ids
    assert payload["projects"][-1]["href"] == "/soon"
    hidden = home_payload(9, only=frozenset())
    assert hidden["projects"] == []


def test_the_public_profile_leaves_a_stopped_project_off_the_landing():
    from pathlib import Path

    from orchestrator.config import load_runtime_config

    root = Path(__file__).resolve().parents[1]
    config = load_runtime_config(root, profile="hf", isolation="isolated")
    running = frozenset(project.project_id for project in config.projects.values() if project.run)
    ids = [project["id"] for project in home_payload(0, only=running)["projects"]]
    assert "yellow" + "_mirror" not in ids
    assert "dnd" in ids
    assert "formular" in ids


def test_the_hub_serves_that_document_at_the_api_root():
    from orchestrator.app import app

    paths = [getattr(route, "path", "") for route in app.routes]
    assert "/api" in paths
    assert "/api/status" in paths


def test_druid_search_returns_the_same_cards_as_the_page():
    from dnd.main import router

    app = FastAPI()
    app.include_router(router, prefix="/dnd")
    with TestClient(app) as client:
        index = client.get("/dnd/api")
        assert index.status_code == 200
        assert index.json()["beasts"] == "/dnd/api/beasts"
        found = client.get("/dnd/api/beasts", params={"q": "\u0441\u043a\u043e\u0440\u043e\u0441", "lang": "ru"})
        assert found.status_code == 200
        body = found.json()
        assert body["sort"] == ["speed"]
        assert body["count"] == body["count"] and body["count"] > 100
        assert body["beasts"][0]["n_en"] == "Giant eagle"
        assert "categories" in body["beasts"][0]
        eel = client.get("/dnd/api/beasts", params={"q": "space eel", "cat": "lvl4"})
        assert eel.json()["count"] == 0
        refused = client.get("/dnd/api/beasts", params={"cat": "nope"})
        assert refused.status_code == 400


def test_mod_search_filters_loader_name_and_version(monkeypatch):
    fabric = _mod("Apple", ["Fabric"])
    forge = _mod("Berry Forge Friend", ["Forge"], minecraft="1.20.1")
    assert [mod.name for mod in select_mods([forge, fabric], loader="Fabric")] == ["Apple"]
    assert [mod.name for mod in select_mods([fabric, forge], q="ber")] == ["Berry Forge Friend"]
    assert [mod.name for mod in select_mods([fabric, forge], minecraft="1.20")] == ["Berry Forge Friend"]
    assert select_mods([fabric, forge], license_name="gpl") == []

    from minecraft_mods import minecraft_mods

    def fake_catalog():
        return Catalog(mods=[fabric, forge])

    monkeypatch.setattr(minecraft_mods, "get_catalog", fake_catalog)
    app = FastAPI()
    app.include_router(minecraft_mods.router, prefix="/mods")
    with TestClient(app) as client:
        found = client.get("/mods/api/mods", params={"q": "apple", "loader": "fabric"})
        assert found.status_code == 200
        body = found.json()
        assert body["count"] == 1
        card = body["mods"][0]
        assert card["name"] == "Apple"
        assert card["description_en"].startswith("Apple")
        assert card["mod_jars"][0]["name"] == "apple.jar"
        assert card["download"] == "/mods/apple-mod/jars.zip"
        assert card["github_url"].endswith("/apple")


class _Docs:
    def __init__(self):
        self.rows = []

    async def create_index(self, *args, **kwargs):
        return None

    async def find_one(self, query):
        for row in self.rows:
            if all(row.get(key) == value for key, value in query.items()):
                return dict(row)
        return None

    async def insert_one(self, doc):
        self.rows.append(dict(doc))
        return type("Result", (), {"inserted_id": "1"})()


def test_a_markbin_document_can_be_created_and_read_back(monkeypatch):
    import markbin.markbin as markbin

    monkeypatch.setattr(markbin, "codes_collection", _Docs())
    app = FastAPI()
    app.include_router(markbin.router, prefix="/markbin")
    with TestClient(app) as client:
        created = client.post("/markbin/api/docs", json={"content": "hello **there**", "ttl_seconds": 60})
        assert created.status_code == 201
        saved = created.json()
        assert saved["href"] == "/markbin/api/docs/" + saved["id"]
        assert "expires_at" in saved
        read = client.get(saved["href"])
        assert read.status_code == 200
        assert read.json()["content"] == "hello **there**"
        again = client.post("/markbin/api/save", json={"content": "hello **there**", "ttl_seconds": 60})
        assert again.status_code == 200
        assert again.json()["uuid"] == saved["id"]
        missing = client.get("/markbin/api/docs/missing")
        assert missing.status_code == 404


def test_evenfest_pages_are_readable_as_json(monkeypatch):
    import evenfest.evenfest as evenfest

    async def fake_config():
        return {
            "menu": [{"title": "News", "url": "news", "icon": "bi-newspaper"}],
            "content": {"news": "<p>Festival day</p>", "about": ""},
        }

    monkeypatch.setattr(evenfest, "get_config", fake_config)
    app = FastAPI()
    app.include_router(evenfest.router, prefix="/evenfest")
    with TestClient(app) as client:
        listing = client.get("/evenfest/api/pages")
        assert listing.status_code == 200
        ids = [page["id"] for page in listing.json()["pages"]]
        assert "news" in ids
        assert "about" in ids
        assert "base" not in ids
        news = client.get("/evenfest/api/pages/news")
        assert news.status_code == 200
        body = news.json()
        assert body["content"] == "<p>Festival day</p>"
        assert body["heading"]
        assert body["menu"][0]["title"] == "News"
        missing = client.get("/evenfest/api/pages/not-a-page")
        assert missing.status_code == 404
        page = client.get("/evenfest/news")
        assert page.status_code == 200
        assert "Festival day" in page.text
