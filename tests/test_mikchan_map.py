from fastapi import FastAPI
from fastapi.testclient import TestClient

from mikchan_map.markers import check_suggestion, color_hex, parse_waypoints
from mikchan_map.mikchan_map import cloud_name, router
from mikchan_map.xaero_cache import parse_cache
from orchestrator.home import home_payload


def _i32(value: int) -> bytes:
    return value.to_bytes(4, "big", signed=True)


def _leaf() -> bytes:
    raw = bytearray(16384)
    raw[0:4] = bytes((20, 140, 40, 200))
    raw[4:8] = bytes((255, 0, 0, 0))
    return b"".join(
        (
            _i32(0x00020018),
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


def test_cache_keeps_lit_pixels_and_drops_the_empty_red_marker():
    image = parse_cache(_leaf(), leaf=True, level=0)
    assert image.major == 2 and image.minor == 24
    assert image.rgba[0:4] == bytes((20, 140, 40, 255))
    assert image.rgba[4:8] == bytes(4)
    assert image.opaque_pixels() == 1


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
            },
        ]

    async def add_suggestion(self, suggestion):
        self.saved.append(suggestion)


def test_map_api_orders_dimensions_and_stores_a_suggestion(monkeypatch):
    store = _Store()
    monkeypatch.setattr("mikchan_map.mikchan_map.get_store", lambda: store)
    monkeypatch.setenv("CLOUDINARY_CLOUD_NAME", "gndf3nby")
    app = FastAPI()
    app.include_router(router, prefix="/mikchan-map")
    client = TestClient(app)
    page = client.get("/mikchan-map/")
    assert page.status_code == 200
    assert "Предложить метку" in page.text
    catalog = client.get("/mikchan-map/api/map").json()
    assert [item["id"] for item in catalog["dimensions"]] == ["overworld", "nether"]
    assert catalog["cloud"] == "gndf3nby"
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
