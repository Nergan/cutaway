"""Presentation-layer tests: the HTTP surface, the socket handshake, and the tick loop.

These go through the real ASGI app with FastAPI's ``TestClient`` rather than calling
the route functions, because most of what can go wrong here is wiring: a container
that never started, a route mounted at the wrong prefix, a handshake that lets a
client skip a step. Calling the function directly proves none of that.

The world is built with two corridor segments and in-memory storage, so nothing here
touches MongoDB or the network. Terrain generation in pure Python is the slow part,
and two segments keeps the whole file under a few seconds.
"""

from __future__ import annotations

import re
import struct
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from age.config import Settings
from age.domain.constants import PROTOCOL_VERSION
from age.domain.items import EQUIPMENT_SLOTS, INVENTORY_SLOTS, ITEMS
from age.infrastructure import wire
from age.presentation import container as container_module
from age.presentation import ws_routes
from age.presentation.app import create_app
from age.presentation.container import Container, get_container, reset_container


def _settings(**overrides) -> Settings:
    base = {
        "world_id": "test",
        "world_seed": 0x0A6E5EED,
        "corridor_segments": 2,
        "max_clients": 4,
        # Never in a test: a free-tier cluster being asleep is not a test failure,
        # and reaching for it would make this suite depend on the network.
        "use_mongo": False,
        "base_path": "/age",
        "tier_cooldown_seconds": 5.0,
        "allow_dev_controls": True,
        "cdn_base": "https://cdn.jsdelivr.net/gh/Nergan/cdn@main",
    }
    base.update(overrides)
    return Settings(**base)


@asynccontextmanager
async def _lifespan(_: FastAPI):
    """Drive the hooks the orchestrator would normally call.

    ``create_app`` deliberately has no lifespan of its own: the hub owns the process
    and calls ``startup_clients``/``shutdown_clients``. A test has to stand in for it.
    """
    await get_container().startup()
    try:
        yield
    finally:
        await get_container().shutdown()


def _app(settings: Settings | None = None) -> FastAPI:
    reset_container(Container(settings or _settings()))
    app = create_app()
    app.router.lifespan_context = _lifespan
    return app


@pytest.fixture
def client():
    """A running world behind the real app, torn down afterwards.

    The container is process-wide because the orchestrator's lifecycle hooks have
    nowhere else to put it, so it is swapped out and restored around each test.
    """
    previous = container_module._container
    with TestClient(_app()) as running:
        yield running
    reset_container(previous)


# --- client frames ----------------------------------------------------------
#
# The Python codec only encodes what the server sends and only decodes what it
# receives, because that is all the server needs; the TypeScript mirror is the other
# half. A test standing in for a client builds its frames from the same primitives,
# which is also what the parity fixture generator does.


def _hello(name: str = "Rowan", *, protocol: int = PROTOCOL_VERSION) -> bytes:
    return (
        wire.Writer(wire.CLIENT_HELLO)
        .u16(protocol)
        .text(name, 64)
        .u8(0)
        .u8(1)
        .u8(2)
        .u8(3)
        .u8(4)
        .u8(5)
        .build()
    )


def _ready() -> bytes:
    return wire.Writer(wire.CLIENT_READY).build()


def _ping(client_time: float) -> bytes:
    return wire.Writer(wire.CLIENT_PING).f64(client_time).build()


def _server_frame(payload: bytes) -> dict[str, object]:
    """Decode the server frames this suite asserts on, keyed by their type byte."""
    reader = wire.Reader(payload, 1)
    kind = payload[0]

    if kind == wire.SERVER_WELCOME:
        return {
            "kind": "welcome",
            "protocolVersion": reader.u16(),
            "entityId": reader.u32(),
            "worldSeed": reader.u64(),
            "topologyVersion": reader.u32(),
            "currentTier": reader.u8(),
            "edgeId": reader.text(64),
            "spawnX": wire.decode_position(reader.i32()),
            "spawnY": wire.decode_position(reader.i32()),
            "serverTime": reader.f64(),
        }
    if kind == wire.SERVER_TOPOLOGY:
        version = reader.u32()
        tier = reader.u8()
        active = [reader.text(96) for _ in range(reader.u16())]
        retiring = [reader.text(96) for _ in range(reader.u16())]
        return {
            "kind": "topology",
            "topologyVersion": version,
            "currentTier": tier,
            "active": active,
            "retiring": retiring,
        }
    if kind == wire.SERVER_PONG:
        return {"kind": "pong", "clientTime": reader.f64(), "serverTime": reader.f64()}
    if kind == wire.SERVER_ERROR:
        return {"kind": "error", "code": reader.u8(), "detail": reader.text(160)}
    if kind == wire.SERVER_INVENTORY:
        capacity = reader.u8()
        stacks = [(reader.u16(), reader.u16()) for _ in range(reader.u8())]
        equipped = [(reader.u8(), reader.u16()) for _ in range(reader.u8())]
        return {
            "kind": "inventory",
            "capacity": capacity,
            "stacks": stacks,
            "equipped": equipped,
            "maxHealth": reader.u16(),
            "maxResource": reader.u16(),
            "bonusDamage": reader.u16(),
            "moveSpeed": reader.u16() / wire.SPEED_SCALE,
        }
    return {"kind": wire.MESSAGE_NAMES.get(kind, hex(kind))}


def _await_frame(socket, kind: str, *, limit: int = 16) -> dict[str, object]:
    """Read frames until one of ``kind`` arrives.

    The server is free to interleave chat backlog and snapshots with whatever a test
    is waiting for, and asserting on frame order would be asserting on something the
    protocol does not promise.
    """
    for _ in range(limit):
        frame = _server_frame(socket.receive_bytes())
        if frame["kind"] == kind:
            return frame
    raise AssertionError(f"no {kind} frame arrived within {limit} frames")


def _join(socket, name: str = "Rowan") -> dict[str, object]:
    """Complete the handshake and return the Welcome."""
    socket.send_bytes(_hello(name))
    welcome = _await_frame(socket, "welcome")
    socket.send_bytes(_ready())
    return welcome


# --- the app shell ----------------------------------------------------------


def test_the_world_becomes_ready_on_startup(client: TestClient):
    payload = client.get("/api/health").json()

    assert payload["ready"] is True
    assert "error" not in payload
    assert payload["protocol"] == PROTOCOL_VERSION


def test_health_reports_which_storage_is_actually_in_use(client: TestClient):
    """A demo running on a sleeping cluster should say so rather than look broken."""
    assert client.get("/api/health").json()["storage"] == "memory"


def test_the_spa_shell_is_served_or_honestly_refused(client: TestClient):
    response = client.get("/")

    assert response.status_code in (200, 503)
    assert "text/html" in response.headers["content-type"]


def test_the_atelier_has_its_own_shell(client: TestClient):
    """It is a separate bundle entry, not the game with a different route."""
    response = client.get("/atelier")

    assert response.status_code in (200, 503)
    assert "text/html" in response.headers["content-type"]


def test_an_unknown_route_is_a_clean_404(client: TestClient):
    assert client.get("/api/nonexistent").status_code == 404


# --- the client's own URLs --------------------------------------------------
#
# Every path the browser fetches is assembled from a template literal, and nothing
# else checks that the result is a route this server serves. It went wrong exactly
# once, and expensively: the renderer asked for `<mount>/atelier/atlas.json` instead
# of `<mount>/api/atelier/atlas.json`, which typechecks, passes every unit test, and
# leaves a black screen with one 404 in the console.
#
# So the templates are read out of the TypeScript and resolved here. A new endpoint
# fetched from a new path is covered without anyone remembering to add a case.

CLIENT_SRC = Path(__file__).resolve().parents[1] / "age" / "frontend" / "src"

# `${apiBase()}/world`, `${api}/atelier/atlas.png`, `${this.base}/atelier/x.png`.
# The capture is the literal tail; a `?query` is dropped because the route is the path.
_URL_TEMPLATE = re.compile(
    r"\$\{(?:apiBase\(\)|api|this\.base)\}(/[A-Za-z0-9\-_/.]*)",
)

# A tail ending in `/` had a second interpolation after it — a route parameter, or a
# filename the client picks at runtime. The concrete value goes here so the path can
# actually be requested; a missing entry fails loudly rather than as a phantom 404.
_PARAMETERISED = {
    "/dev/tier/": "0",
    "/atelier/import/": "ldtk",
    "/atelier/": "atlas.png",
}


def _client_api_paths() -> set[str]:
    found: set[str] = set()
    for source in CLIENT_SRC.rglob("*.ts*"):
        if source.name.endswith((".test.ts", ".test.tsx")):
            continue
        for tail in _URL_TEMPLATE.findall(source.read_text(encoding="utf-8")):
            if tail.endswith("/"):
                assert tail in _PARAMETERISED, (
                    f"{source.name} fetches {tail}<something>; add the concrete value to "
                    "_PARAMETERISED so this test can request it"
                )
                tail += _PARAMETERISED[tail]
            found.add(tail)
    return found


def test_the_client_builds_urls_this_server_actually_serves(client: TestClient):
    """Every path the browser assembles must resolve. A 404 here is a black screen."""
    tails = _client_api_paths()
    assert len(tails) >= 8, f"The template scan found too little to be working: {tails}"

    missing = []
    for tail in sorted(tails):
        # The tails are relative to the API root, which is where the client's helpers put
        # them. GET first: the write endpoints answer 405 rather than 404, which still
        # proves the route exists, and POSTing a real body per endpoint is what the rest
        # of this file already does.
        if client.get(f"/api{tail}").status_code == 404:
            missing.append(tail)

    assert not missing, f"The client fetches paths that do not exist: {missing}"


def test_the_atlas_the_renderer_asks_for_is_under_the_api_root(client: TestClient):
    """The specific mistake, pinned: the atlas is an API resource, not a static one."""
    assert "/atelier/atlas.json" in _client_api_paths()
    assert client.get("/api/atelier/atlas.json").status_code == 200
    assert client.get("/atelier/atlas.json").status_code == 404


# --- the world descriptor ---------------------------------------------------


def test_the_world_endpoint_carries_everything_the_client_needs_before_a_socket(
    client: TestClient,
):
    payload = client.get("/api/world").json()

    assert payload["protocol"] == PROTOCOL_VERSION
    assert payload["segments"] == 2
    assert payload["currentTier"] == 0
    assert payload["topologyVersion"] >= 1
    assert payload["edgeId"]
    assert len(payload["hubs"]) == 2
    assert len(payload["classes"]) == 14
    assert payload["biomes"]


def test_the_client_can_derive_the_world_geometry_from_the_descriptor(
    client: TestClient,
):
    """The client mirrors the generator, so a mismatch here means wrong terrain."""
    payload = client.get("/api/world").json()

    assert set(payload) >= {"worldSeed", "edgeId", "segments"}
    assert isinstance(payload["worldSeed"], int)
    for hub in payload["hubs"]:
        assert set(hub) == {"hubId", "name", "x", "y", "radiusTiles"}


def test_every_class_arrives_with_a_castable_kit(client: TestClient):
    classes = client.get("/api/world").json()["classes"]

    for entry in classes:
        assert entry["abilities"], entry["key"]
        assert entry["fantasy"], entry["key"]
        for ability in entry["abilities"]:
            assert ability["cooldownMs"] > 0
            assert ability["damage"] or ability["healing"] or ability["kind"] in (4, 5)


def test_the_item_catalogue_arrives_with_the_world_rather_than_on_every_packet(
    client: TestClient,
):
    """Names and stats are static, so the inventory packet only carries ids and counts."""
    payload = client.get("/api/world").json()

    assert payload["inventorySlots"] == INVENTORY_SLOTS
    assert len(payload["items"]) == len(ITEMS)
    assert len(payload["equipmentSlots"]) == len(EQUIPMENT_SLOTS)

    for item in payload["items"]:
        assert set(item) >= {"itemId", "key", "name", "kind", "slot", "rarity"}
        assert item["itemId"] > 0
        assert item["name"]


def test_every_item_the_pack_can_hold_can_be_looked_up_by_the_id_on_the_wire(
    client: TestClient,
):
    """The client draws a stack from its id alone; an id with no entry draws nothing."""
    payload = client.get("/api/world").json()
    by_id = {item["itemId"]: item for item in payload["items"]}

    assert len(by_id) == len(payload["items"])
    for item in ITEMS.values():
        assert by_id[item.item_id]["key"] == item.key


def test_the_debug_endpoint_exposes_the_accordion(client: TestClient):
    payload = client.get("/api/debug").json()

    assert payload["world"]["topology"]["current_tier"] == 0
    assert payload["world"]["topology"]["active"]
    assert "stats" in payload or "population" in payload


# --- the dev controls -------------------------------------------------------


def test_a_tier_can_be_forced_so_the_accordion_is_demonstrable(client: TestClient):
    """Its production cadence is fifteen minutes; a demo has to be able to show it."""
    response = client.post("/api/dev/tier/1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["tierChanged"] is True
    assert payload["currentTier"] == 1
    assert client.get("/api/world").json()["currentTier"] == 1


def test_forcing_the_tier_moves_the_topology_version(client: TestClient):
    before = client.get("/api/world").json()["topologyVersion"]

    client.post("/api/dev/tier/1")

    assert client.get("/api/world").json()["topologyVersion"] > before


def test_forcing_a_tier_that_is_already_current_changes_nothing(client: TestClient):
    payload = client.post("/api/dev/tier/0").json()

    assert payload["tierChanged"] is False
    assert payload["currentTier"] == 0


def test_the_dev_controls_can_be_switched_off():
    previous = container_module._container
    with TestClient(_app(_settings(allow_dev_controls=False))) as running:
        response = running.post("/api/dev/tier/1")
    reset_container(previous)

    assert response.status_code == 403


# --- the Atelier API --------------------------------------------------------


def test_the_catalogue_is_the_editors_starting_state(client: TestClient):
    payload = client.get("/api/atelier/catalogue").json()

    assert payload["recipes"]
    assert payload["ramps"], "The editor needs the palette from the server, not a copy."
    assert payload["rampSteps"] >= 3
    for recipe in payload["recipes"]:
        assert recipe["key"]
        assert recipe["steps"]


def test_the_atlas_is_a_real_png(client: TestClient):
    response = client.get("/api/atelier/atlas.png")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_the_normal_page_is_packed_identically_to_the_colour_page(client: TestClient):
    """Same UVs address both, so a different size would silently mis-light everything."""
    colour = client.get("/api/atelier/atlas.png").content
    normal = client.get("/api/atelier/atlas-normal.png").content

    assert _png_size(colour) == _png_size(normal)


def test_the_atlas_index_tells_the_renderer_which_art_a_tile_uses(client: TestClient):
    index = client.get("/api/atelier/atlas.json").json()

    assert index["tileGround"], "Without this the client would need its own copy."
    assert index["fallbackGround"]
    assert index["character"]["width"] > 0
    assert index["character"]["poseFrames"]
    assert index["decor"]


def test_every_binding_in_the_index_points_at_art_that_exists(client: TestClient):
    index = client.get("/api/atelier/atlas.json").json()
    baked = {placement["name"] for placement in index["frames"]}

    for tile, key in index["tileGround"].items():
        assert key in baked, f"tile {tile} is bound to missing art {key!r}"
    for tile, key in index["tileProp"].items():
        assert key in baked, f"tile {tile} is bound to missing art {key!r}"
    for key in index["decor"]:
        assert key in baked, f"decor {key!r} has no art"
    assert index["fallbackGround"] in baked


def test_an_animated_tile_is_bound_to_art_with_more_than_one_frame(client: TestClient):
    index = client.get("/api/atelier/atlas.json").json()
    frames_per_key: dict[str, int] = {}
    for placement in index["frames"]:
        frames_per_key[placement["name"]] = frames_per_key.get(placement["name"], 0) + 1

    assert index["animated"], "Water animates; something should be in here."
    for tile, fps in index["animated"].items():
        key = index["tileGround"][tile]
        assert frames_per_key[key] > 1, f"{key} animates but has one frame"
        assert fps > 0


def test_every_placement_sits_inside_the_page(client: TestClient):
    """An overflowing placement would sample a neighbour's pixels."""
    index = client.get("/api/atelier/atlas.json").json()

    for placement in index["frames"]:
        assert placement["x"] + placement["w"] <= index["width"], placement["name"]
        assert placement["y"] + placement["h"] <= index["height"], placement["name"]


def test_baking_a_posted_recipe_returns_a_png(client: TestClient):
    catalogue = client.get("/api/atelier/catalogue").json()
    recipe = catalogue["recipes"][0]

    response = client.post("/api/atelier/bake", json=recipe)

    assert response.status_code == 200
    assert response.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_a_bake_preview_is_never_cached(client: TestClient):
    """The editor is iterating; a cached preview is a preview of the last edit."""
    recipe = client.get("/api/atelier/catalogue").json()["recipes"][0]

    response = client.post("/api/atelier/bake", json=recipe)

    assert response.headers["cache-control"] == "no-store"


def test_an_unusable_recipe_is_rejected_with_a_reason(client: TestClient):
    response = client.post("/api/atelier/bake", json={"key": "broken", "steps": "nope"})

    assert response.status_code == 400
    assert response.json()["detail"]


def test_an_absurd_recipe_size_is_clamped_rather_than_baked(client: TestClient):
    """A browser claiming 40000 px square would bake until the worker died."""
    response = client.post(
        "/api/atelier/bake",
        json={"key": "huge", "width": 40000, "height": 40000, "steps": []},
    )

    assert response.status_code == 200
    width, height = _png_size(response.content)
    assert width <= 256 and height <= 256


def test_a_malformed_body_is_rejected_rather_than_crashing(client: TestClient):
    response = client.post(
        "/api/atelier/bake",
        content=b"{not json",
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 400


def test_an_oversized_upload_is_refused_before_it_is_parsed(client: TestClient):
    response = client.post(
        "/api/atelier/import/ldtk",
        content=b"[" + b"0," * 3_000_000 + b"0]",
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 413


def test_a_character_strip_is_baked_from_its_appearance_bytes(client: TestClient):
    response = client.get("/api/atelier/character.png?body=3&hair=5&palette=1&pose=1")

    assert response.status_code == 200
    width, height = _png_size(response.content)
    assert width > height, "A strip is frames side by side."


def test_the_same_appearance_bakes_the_same_character(client: TestClient):
    """Procedural art has to be deterministic or players change shape on reconnect."""
    query = "?body=3&hair=5&palette=1&outfit=2&accent=4&facing=1&pose=1"

    first = client.get(f"/api/atelier/character.png{query}").content
    second = client.get(f"/api/atelier/character.png{query}").content

    assert first == second


def test_two_appearances_bake_differently(client: TestClient):
    first = client.get("/api/atelier/character.png?body=0&hair=0&palette=0").content
    second = client.get("/api/atelier/character.png?body=7&hair=3&palette=2").content

    assert first != second


def test_the_full_sheet_matches_the_layout_the_index_publishes(client: TestClient):
    """The client slices this grid using nothing but the published numbers."""
    layout = client.get("/api/atelier/atlas.json").json()["character"]

    sheet = client.get("/api/atelier/character-sheet.png?body=2&hair=1").content
    width, height = _png_size(sheet)

    assert width == layout["width"] * layout["columns"]
    assert height == layout["height"] * layout["facings"] * len(layout["poseFrames"])


def test_a_normal_map_is_available_for_every_baked_thing(client: TestClient):
    colour = client.get("/api/atelier/character.png?body=1").content
    normals = client.get("/api/atelier/character.png?body=1&normals=true").content

    assert _png_size(colour) == _png_size(normals)
    assert colour != normals


def test_an_ldtk_project_is_converted_rather_than_applied(client: TestClient):
    """An upload that wrote into the live world would be a way to delete player work."""
    project = {
        "defs": {"tilesets": []},
        "levels": [
            {
                "identifier": "Demo",
                "pxWid": 64,
                "pxHei": 64,
                "layerInstances": [
                    {
                        "__identifier": "Terrain",
                        "__type": "IntGrid",
                        "__cWid": 2,
                        "__cHei": 2,
                        "__gridSize": 32,
                        "intGridCsv": [1, 1, 2, 2],
                    }
                ],
            }
        ],
    }

    response = client.post("/api/atelier/import/ldtk", json=project)

    assert response.status_code == 200
    levels = response.json()["levels"]
    assert levels[0]["identifier"] == "Demo"
    assert levels[0]["chunks"]
    # The world is untouched.
    assert client.get("/api/debug").json()["world"]["dirty_chunks"] == 0


def test_a_broken_ldtk_project_is_rejected_with_a_reason(client: TestClient):
    response = client.post("/api/atelier/import/ldtk", json={"levels": "not a list"})

    assert response.status_code == 400
    assert response.json()["detail"]


def test_an_aseprite_export_becomes_frames_and_tags(client: TestClient):
    export = {
        "frames": [
            {
                "filename": "walk 0",
                "frame": {"x": 0, "y": 0, "w": 16, "h": 24},
                "duration": 120,
            },
            {
                "filename": "walk 1",
                "frame": {"x": 16, "y": 0, "w": 16, "h": 24},
                "duration": 120,
            },
        ],
        "meta": {
            "image": "hero.png",
            "size": {"w": 32, "h": 24},
            "frameTags": [{"name": "walk", "from": 0, "to": 1, "direction": "forward"}],
        },
    }

    payload = client.post("/api/atelier/import/aseprite", json=export).json()

    assert payload["image"] == "hero.png"
    assert len(payload["frames"]) == 2
    assert payload["tags"][0]["name"] == "walk"
    assert payload["tags"][0]["frameCount"] == 2


# --- the socket handshake ---------------------------------------------------


def test_a_client_that_says_hello_is_welcomed_into_the_world(client: TestClient):
    with client.websocket_connect("/ws") as socket:
        welcome = _join(socket)

    assert welcome["protocolVersion"] == PROTOCOL_VERSION
    assert welcome["entityId"] > 0
    assert welcome["topologyVersion"] >= 1
    assert welcome["worldSeed"] == 0x0A6E5EED


def test_the_welcome_carries_the_seed_the_client_generates_terrain_from(
    client: TestClient,
):
    descriptor = client.get("/api/world").json()

    with client.websocket_connect("/ws") as socket:
        welcome = _join(socket)

    assert welcome["worldSeed"] == descriptor["worldSeed"]
    assert welcome["edgeId"] == descriptor["edgeId"]


def test_a_player_spawns_somewhere_the_client_can_stand(client: TestClient):
    with client.websocket_connect("/ws") as socket:
        welcome = _join(socket)

    hubs = client.get("/api/world").json()["hubs"]
    nearest = min(
        hubs,
        key=lambda hub: abs(hub["x"] - welcome["spawnX"]) + abs(hub["y"] - welcome["spawnY"]),
    )
    assert abs(welcome["spawnX"] - nearest["x"]) <= nearest["radiusTiles"]
    assert abs(welcome["spawnY"] - nearest["y"]) <= nearest["radiusTiles"]


def test_the_topology_arrives_before_the_client_has_to_draw_anything(
    client: TestClient,
):
    with client.websocket_connect("/ws") as socket:
        socket.send_bytes(_hello())
        _await_frame(socket, "welcome")
        topology = _await_frame(socket, "topology")

    assert topology["active"]
    assert topology["currentTier"] == 0


def test_a_stale_bundle_is_told_to_reload_rather_than_left_to_misparse(
    client: TestClient,
):
    with client.websocket_connect("/ws") as socket:
        socket.send_bytes(_hello(protocol=PROTOCOL_VERSION + 7))
        error = _await_frame(socket, "error")

    assert error["code"] == wire.ERROR_VERSION_MISMATCH
    assert "reload" in str(error["detail"]).lower()


def test_a_client_cannot_skip_the_hello(client: TestClient):
    with client.websocket_connect("/ws") as socket:
        socket.send_bytes(_ready())
        error = _await_frame(socket, "error")

    assert error["code"] == wire.ERROR_INVALID


def test_a_text_frame_on_a_binary_socket_is_refused(client: TestClient):
    with client.websocket_connect("/ws") as socket:
        socket.send_text("hello?")
        error = _await_frame(socket, "error")

    assert error["kind"] == "error"


def test_a_garbled_frame_is_answered_rather_than_dropping_the_session(
    client: TestClient,
):
    """A decode failure is one bad packet, not a reason to end someone's session."""
    with client.websocket_connect("/ws") as socket:
        _join(socket)
        socket.send_bytes(b"\xff\xff\xff\xff")
        error = _await_frame(socket, "error")

        socket.send_bytes(_ping(1.0))
        pong = _await_frame(socket, "pong", limit=40)

    assert error["code"] == wire.ERROR_INVALID
    assert pong["clientTime"] == pytest.approx(1.0), "The session must survive it."


def test_an_oversized_frame_closes_the_socket(client: TestClient):
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws") as socket:
            _join(socket)
            socket.send_bytes(b"\x01" + b"\x00" * (ws_routes.MAX_FRAME_BYTES + 1))
            while True:
                socket.receive_bytes()


def test_a_ping_is_answered_without_waiting_for_the_next_tick(client: TestClient):
    """A round trip that waits for the tick measures the tick, not the network."""
    with client.websocket_connect("/ws") as socket:
        _join(socket)
        socket.send_bytes(_ping(1234.5))
        pong = _await_frame(socket, "pong", limit=40)

    assert pong["clientTime"] == pytest.approx(1234.5, abs=1e-9)
    assert pong["serverTime"] > 0.0


def test_a_joining_player_shows_up_in_the_population(client: TestClient):
    with client.websocket_connect("/ws") as socket:
        _join(socket)
        assert client.get("/api/world").json()["population"] == 1

    assert client.get("/api/world").json()["population"] == 0


def test_the_world_refuses_more_players_than_it_seats():
    previous = container_module._container

    with TestClient(_app(_settings(max_clients=2))) as running:
        with running.websocket_connect("/ws") as first:
            _join(first, "One")
            with running.websocket_connect("/ws") as second:
                _join(second, "Two")
                with running.websocket_connect("/ws") as third:
                    refusal = _await_frame(third, "error")

    reset_container(previous)
    assert refusal["kind"] == "error"
    assert "full" in str(refusal["detail"]).lower()


def test_two_players_get_different_entities(client: TestClient):
    with client.websocket_connect("/ws") as first:
        first_welcome = _join(first, "Rowan")
        with client.websocket_connect("/ws") as second:
            second_welcome = _join(second, "Bruna")

            assert second_welcome["entityId"] != first_welcome["entityId"]
            assert client.get("/api/debug").json()["population"] == 2


def test_a_character_keeps_its_identity_across_a_reconnect(client: TestClient):
    with client.websocket_connect("/ws") as socket:
        first = _join(socket, "Rowan")

    with client.websocket_connect("/ws") as socket:
        again = _join(socket, "Rowan")

    assert again["worldSeed"] == first["worldSeed"]
    assert again["entityId"] > 0


def test_the_handshake_tells_a_character_what_it_is_carrying(client: TestClient):
    """Without this the pack is empty until something changes it, which reads as lost."""
    with client.websocket_connect("/ws") as socket:
        _join(socket)
        inventory = _await_frame(socket, "inventory")

    assert inventory["capacity"] == INVENTORY_SLOTS
    assert inventory["maxHealth"] > 0
    assert inventory["moveSpeed"] > 0


def test_the_pack_is_private_to_its_owner(client: TestClient):
    """Loadouts are not broadcast: a second player's frames must never mention one."""
    with client.websocket_connect("/ws") as first:
        _join(first, "Rowan")
        _await_frame(first, "inventory")

        with client.websocket_connect("/ws") as second:
            _join(second, "Bruna")
            _await_frame(second, "inventory")

            # Anything the first player is sent about the newcomer is public state.
            for _ in range(20):
                frame = _server_frame(first.receive_bytes())
                assert frame["kind"] != "inventory", (
                    "a second inventory frame here would be somebody else's"
                )


def test_wearing_something_raises_the_health_the_server_reports(client: TestClient):
    """The round trip the character sheet is drawn from, through the real socket."""
    with client.websocket_connect("/ws") as socket:
        _join(socket)
        before = _await_frame(socket, "inventory")

        entity = _entity_of(client, "Rowan")
        entity.give("stone_plated_vest", 1)
        index = next(
            slot
            for slot, stack in enumerate(entity.inventory)
            if stack.key == "stone_plated_vest"
        )
        socket.send_bytes(
            wire.Writer(wire.CLIENT_INVENTORY).u8(wire.INVENTORY_EQUIP).u8(index).u16(1).build()
        )
        after = _await_frame(socket, "inventory", limit=60)

    assert after["equipped"], "the vest has to come back as worn"
    assert after["maxHealth"] > before["maxHealth"]


def test_a_silent_cluster_falls_back_to_memory_before_anyone_joins():
    """Constructing the Mongo client is not the same as a server answering.

    ``get_client()`` only parses a URI. Without the ping, every join waits out the
    selection timeout and then refuses to create a character — a demo nobody can
    enter because the free-tier cluster is asleep.

    Driven with ``asyncio.run`` rather than ``pytest.mark.asyncio``: the orchestrator
    suite does not install an async plugin, and a mark the runner does not know is a
    failed workflow, not a skipped test.
    """
    import asyncio

    from age.infrastructure.memory_repositories import MemoryCharacterRepository

    box = Container(_settings())
    box.storage_backend = "mongodb"

    class Down:
        async def load(self, _name: str) -> None:
            raise RuntimeError("connection refused")

    box._topology = Down()
    asyncio.run(box._confirm_storage())

    assert box.storage_backend == "memory"
    assert isinstance(box._characters, MemoryCharacterRepository)


# --- helpers ----------------------------------------------------------------


def _entity_of(client: TestClient, name: str):
    """The live entity behind a joined character, for tests that need to arrange one."""
    world = get_container().world
    for entity in world.entities.values():
        if entity.name == name:
            return entity
    raise AssertionError(f"no entity named {name} is in the world")


def _png_size(data: bytes) -> tuple[int, int]:
    """Read width and height out of a PNG's IHDR."""
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    width, height = struct.unpack(">II", data[16:24])
    return width, height
