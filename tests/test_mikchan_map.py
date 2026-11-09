from fastapi import FastAPI
from fastapi.testclient import TestClient

from mikchan_map.biomes import filter_biomes, sample_grid
from mikchan_map.convert import load_done, should_upload
from mikchan_map.markers import check_suggestion, color_hex, filter_markers, parse_waypoints
from mikchan_map.mikchan_map import cloud_name, router
from mikchan_map.xaero_cache import parse_cache
from orchestrator.home import home_payload


def _i32(value: int) -> bytes:
    return value.to_bytes(4, "big", signed=True)


def _leaf() -> bytes:
    raw = bytearray(16384)
    raw[0:4] = bytes((20, 140, 40, 200))
    raw[4:8] = bytes((255, 0, 0, 0))
    raw[8:12] = bytes((90, 121, 60, 0))
    return _region(0x00030018, raw)


def _region(version: int, raw: bytes) -> bytes:
    return b"".join(
        (
            _i32(version),
            b"\x00" * 20,
            bytes((0,)),
            _i32(1),
            bytes((0xFF,)),
            _i32(0),
            bytes((0,)),
            bytes(raw),
            bytes((0,)),
            b"\x00" * (1024 * 8 * 2),
            _i32(0),
            bytes((0xFF,)),
        )
    )


def _utf(text: str) -> bytes:
    raw = text.encode()
    return len(raw).to_bytes(2, "big") + raw


def _biome_cell(local: int) -> bytes:
    step = local + 1
    shorts = (0, 128 * step, 1024 * step, 8192 * step + 1)
    return b"".join(item.to_bytes(2, "big") for item in shorts)


def test_cache_reads_a_biome_palette_and_a_two_block_grid():
    blob = bytearray(8192)
    blob[0:8] = _biome_cell(0)
    blob[8:16] = _biome_cell(1)
    data = b"".join(
        (
            _i32(0x00030018),
            b"\x00" * 20,
            bytes((0,)),
            _i32(1),
            bytes((0xFF,)),
            _i32(2),
            bytes((0,)),
            _utf("minecraft:plains"),
            bytes((0,)),
            _utf("minecraft:forest"),
            bytes((0,)),
            b"\x00" * 16384,
            bytes((0,)),
            b"\x00" * (1024 * 8 * 2),
            _i32(2),
            _i32(0),
            b"\x00\x00",
            _i32(1),
            b"\x00\x00",
            bytes((1,)),
            bytes(blob),
            bytes((0xFF,)),
        )
    )
    image = parse_cache(data, leaf=True, level=0)
    assert image.biome_names[:2] == ("minecraft:plains", "minecraft:forest")
    assert image.biomes[0] == 1
    assert image.biomes[1] == 2
    assert sample_grid(list(image.biome_names), image.biomes, 1, 0, 0, 0) == "minecraft:plains"
    assert sample_grid(list(image.biome_names), image.biomes, 3, 0, 0, 0) == "minecraft:forest"
    single = b"".join(
        (
            _i32(0x00030018),
            b"\x00" * 20,
            bytes((0,)),
            _i32(1),
            bytes((0xFF,)),
            _i32(1),
            bytes((0,)),
            _utf("minecraft:river"),
            bytes((0,)),
            b"\x00" * 16384,
            bytes((0,)),
            b"\x00" * (1024 * 8 * 2),
            _i32(1),
            _i32(0),
            b"\x00\x00",
            bytes((0,)),
            bytes((0xFF,)),
        )
    )
    filled = parse_cache(single, leaf=True, level=0)
    assert filled.biomes[0] == 1
    assert filled.biomes[31] == 1
    assert filled.biomes[32] == 0
    assert filled.biomes[256] == 1


def test_cache_keeps_dark_surface_pixels_and_drops_the_red_hole():
    image = parse_cache(_leaf(), leaf=True, level=0)
    assert image.major == 3 and image.minor == 24
    assert image.rgba[0:4] == bytes((20, 140, 40, 255))
    assert image.rgba[4:8] == bytes(4)
    assert image.rgba[8:12] == bytes((90, 121, 60, 255))
    assert image.opaque_pixels() == 2
    older = bytearray(16384)
    older[0:4] = bytes((200, 20, 140, 40))
    older[4:8] = bytes((0, 255, 0, 0))
    older[8:12] = bytes((0, 90, 121, 60))
    image = parse_cache(_region(0x00020018, bytes(older)), leaf=True, level=0)
    assert image.major == 2
    assert image.rgba[0:4] == bytes((20, 140, 40, 255))
    assert image.rgba[4:8] == bytes(4)
    assert image.rgba[8:12] == bytes((90, 121, 60, 255))
    assert image.opaque_pixels() == 2


def test_upload_notes_keep_an_unstamped_tile_until_the_cache_changes(tmp_path):
    notes = tmp_path / "uploaded.txt"
    notes.write_text("overworld 0 1 2\noverworld 0 3 4 50\n", encoding="utf-8")
    done = load_done(notes)
    assert done["overworld 0 1 2"] == 0
    assert done["overworld 0 3 4"] == 50
    assert should_upload(0, 80, True) is False
    assert should_upload(0, 80, False) is True
    assert should_upload(50, 40, False) is False
    assert should_upload(None, 80, False) is True


def test_waypoint_lines_keep_color_and_colons_and_skip_disabled():
    text = "\n".join(
        (
            "waypoint:склад:📦:-10:64:-20:4:false:0:gui.xaero_default:false:0:0:false",
            "waypoint:a:b:c:1:2:3:0:false:0:set:false:0:0:false",
            "waypoint:скрыто:s:1:2:3:0:true:0:set:false:0:0:false",
        )
    )
    markers = parse_waypoints(text)
    assert markers[0]["name"] == "склад"
    assert markers[0]["initials"] == "📦"
    assert markers[0]["color"] == color_hex(4) == "#AA0000"
    assert markers[1]["name"] == "a:b"
    assert [marker["name"] for marker in markers] == ["склад", "a:b"]


def test_suggestion_checks_reject_a_nameless_marker_and_a_far_coordinate():
    assert check_suggestion({"kind": "add", "dimension": "overworld", "x": 1, "z": 2, "name": "дом"})["name"] == "дом"
    assert check_suggestion({"kind": "add", "dimension": "overworld", "x": 1, "z": 2, "name": "  "}) == "name"
    assert check_suggestion({"kind": "delete", "dimension": "nether", "x": 1, "y": 4, "z": 2, "waypoint": "дом"})["y"] == 4
    assert check_suggestion({"kind": "add", "dimension": "overworld", "x": 99_000_000, "z": 1, "name": "дом"}) == "place"


def test_the_map_card_is_fifth_and_uses_the_server_icon():
    card = home_payload(0)["projects"][4]
    assert card["id"] == "mikchan_map"
    assert card["href"] == "/mikchan-map"
    assert card["icon"] == "https://mikchan.net/favicon.ico"
    assert card["title"] == {"en": "mikchan map", "ru": "карта mikchan"}
    assert card["category"] == {"en": "Game", "ru": "игры"}


def test_cloud_name_comes_from_the_host_and_ignores_a_secret(monkeypatch):
    monkeypatch.delenv("CLOUDINARY_CLOUD_NAME", raising=False)
    monkeypatch.setenv("CLOUDINARY_URL", "cloudinary://key:secret@gndf3nby")
    assert cloud_name() == "gndf3nby"
    monkeypatch.setenv("CLOUDINARY_URL", "cloudinary://key:secret@not a host")
    assert cloud_name() == ""


class _Store:
    def __init__(self):
        self.saved = []

    async def read_catalog(self):
        return [
            {
                "id": "nether",
                "bounds": {"minX": 0, "maxX": 512, "minZ": 0, "maxZ": 512},
                "levels": [{"level": 0, "blocks": 512, "tiles": [[0, 0]]}],
                "waypoints": [],
            },
            {
                "id": "overworld",
                "bounds": {"minX": 0, "maxX": 1, "minZ": 0, "maxZ": 1},
                "levels": [],
                "waypoints": [{"name": "дом", "initials": "д", "x": 1, "y": 2, "z": 3, "color": "#AA0000"}],
                "biomes": [{"id": "minecraft:plains", "x": 12, "z": 20}, {"id": "minecraft:forest", "x": 80, "z": 90}],
            },
        ]

    async def biome_at(self, dimension, x, z):
        if dimension == "overworld" and x == 1 and z == 0:
            return {"dimension": dimension, "id": "minecraft:plains", "en": "Plains", "ru": "Равнины", "x": x, "z": z}
        return None

    async def biome_region(self, dimension, x, z):
        if dimension != "overworld":
            return None
        import base64
        import zlib

        grid = bytearray(256 * 256)
        grid[0] = 1
        return {
            "names": ["minecraft:plains"],
            "cells": base64.b64encode(zlib.compress(bytes(grid), 6)).decode("ascii"),
            "rx": x // 512,
            "rz": z // 512,
        }

    async def add_suggestion(self, suggestion):
        self.saved.append(suggestion)

    async def access_keys(self):
        return ["3301", "rei", "muda muda"]

    async def tile_prefix(self):
        return "mikchan-map"


def test_map_api_orders_dimensions_and_stores_a_suggestion(monkeypatch):
    store = _Store()
    monkeypatch.setattr("mikchan_map.mikchan_map.get_store", lambda: store)
    monkeypatch.setenv("CLOUDINARY_CLOUD_NAME", "gndf3nby")
    monkeypatch.setenv("MAP_GATE_SECRET", "test-gate-secret-value")
    app = FastAPI()
    app.include_router(router, prefix="/mikchan-map")
    client = TestClient(app)
    page = client.get("/mikchan-map/")
    assert page.status_code == 200
    assert "Предложить метку" in page.text
    assert "donate-widget.js" in page.text
    assert 'href="https://mikchan.net"' in page.text
    assert 'id="search"' in page.text
    assert 'id="hover"' in page.text
    assert 'id="biome"' in page.text
    assert "Pixelify Sans" in page.text
    assert "api/biomes/region" in page.text
    assert "scrollbar-color: #8b8b8b #1a1a1a" in page.text
    assert 'placeholder="введите ключ доступа"' in page.text
    assert "res.cloudinary.com" not in page.text
    assert "api/tiles/" in page.text
    assert "Координаты скопированы" in page.text
    assert client.get("/mikchan-map/api/map").status_code == 401
    client.cookies.set("mikchan_map", "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.9999999999.bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", path="/mikchan-map")
    assert client.get("/mikchan-map/api/map").status_code == 401
    client.cookies.clear()
    assert client.post("/mikchan-map/api/access", json={"key": "wrong"}).status_code == 401
    assert client.post("/mikchan-map/api/access", json={"key": "muda muda"}).status_code == 200
    catalog = client.get("/mikchan-map/api/map").json()
    assert [item["id"] for item in catalog["dimensions"]] == ["overworld", "nether"]
    assert "cloud" not in catalog
    saved = client.post(
        "/mikchan-map/api/suggestions",
        json={"kind": "add", "dimension": "overworld", "x": 3, "z": 4, "name": "маяк"},
    )
    assert saved.status_code == 201
    assert store.saved[0]["name"] == "маяк"
    rejected = client.post(
        "/mikchan-map/api/suggestions",
        json={"kind": "add", "dimension": "overworld", "x": 3, "z": 4, "name": ""},
    )
    assert rejected.status_code == 400
    assert rejected.json()["error"] == "name"
    markers = client.get("/mikchan-map/api/markers", params={"q": "дом"}).json()
    assert markers["markers"][0]["z"] == 3
    assert client.get("/mikchan-map/api/markers", params={"q": "нет"}).json()["markers"] == []
    biomes = client.get("/mikchan-map/api/biomes", params={"q": "равнины"}).json()
    assert biomes["biomes"][0]["id"] == "minecraft:plains"
    assert biomes["biomes"][0]["ru"] == "Равнины"
    assert client.get("/mikchan-map/api/biomes/at", params={"dimension": "overworld", "x": 1, "z": 0}).json()["biome"]["en"] == "Plains"
    region = client.get("/mikchan-map/api/biomes/region", params={"dimension": "overworld", "x": 1, "z": 2}).json()
    assert region["names"] == ["minecraft:plains"]
    assert region["cells"]
    assert filter_markers([{"id": "overworld", "waypoints": [{"name": "дом", "initials": "д", "x": 1, "y": 2, "z": 3, "color": "#fff"}]}], dimension="", query="Д", limit=5)[0]["name"] == "дом"
    assert filter_biomes([{"id": "overworld", "biomes": [{"id": "minecraft:river", "x": 4, "z": 5}]}], dimension="overworld", query="река", limit=5)[0]["ru"] == "Река"
