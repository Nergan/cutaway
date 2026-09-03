"""End-to-end coverage of the ASGI app: HTTP endpoints and a live WebSocket.

These run the real application through Starlette's TestClient, so they exercise
routing, the container lifecycle, gzip negotiation and the binary socket the
same way a browser would.
"""

from __future__ import annotations

import struct
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from ascii_city.config import Settings
from ascii_city.domain.constants import CELL_SIZE_M, TILE_CELLS
from ascii_city.infrastructure import wire_codec as wire
from ascii_city.infrastructure.tile_codec import decode_tile
from ascii_city.main import asgi_app, shutdown_clients, startup_clients
from ascii_city.presentation.container import Container, reset_container
from ascii_city.presentation.ws_routes import CLOSE_ROOM_FULL

BASE = "/ascii-city"


def small_settings(**overrides) -> Settings:
    defaults = dict(
        world_id="test",
        world_seed=0x1234ABCD,
        world_version=1,
        tiles_x=1,
        tiles_y=1,
        tile_cells=TILE_CELLS,
        cell_size=CELL_SIZE_M,
        room_id="city:test:main",
        max_clients=4,
        use_mongo=False,  # never touch the shared cluster from a test
        base_path=BASE,
    )
    defaults.update(overrides)
    return Settings(**defaults)


@pytest.fixture
def client(request):
    """A TestClient over the real sub-app, mounted where the hub would mount it."""
    settings = getattr(request, "param", None) or small_settings()
    reset_container(Container(settings))

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await startup_clients()
        try:
            yield
        finally:
            await shutdown_clients()

    root = FastAPI(lifespan=lifespan)
    root.mount(BASE, asgi_app)
    with TestClient(root) as test_client:
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            payload = test_client.get(f"{BASE}/healthz").json()
            if payload["status"] == "ok":
                break
            time.sleep(0.05)
        else:
            pytest.fail(f"District did not become ready: {payload}")
        yield test_client
    reset_container(Container(small_settings()))


# --- metadata --------------------------------------------------------------


def test_world_metadata_describes_the_district(client):
    payload = client.get(f"{BASE}/api/world").json()
    world = payload["world"]
    assert world["id"] == "test"
    assert world["tilesX"] == 1 and world["tilesY"] == 1
    assert world["tileCells"] == TILE_CELLS
    assert world["cellSize"] == CELL_SIZE_M
    assert world["widthM"] == TILE_CELLS * CELL_SIZE_M
    assert world["source"] == "procedural"
    assert payload["network"]["simulationHz"] == 20
    assert payload["chat"]["maxLength"] == 240
    assert payload["physics"]["playerRadius"] > 0


def test_healthz_reports_readiness_and_backend(client):
    payload = client.get(f"{BASE}/healthz").json()
    assert payload["status"] == "ok"
    assert payload["storage"] == "memory"
    assert payload["error"] is None


def test_room_status_is_online_and_empty(client):
    payload = client.get(f"{BASE}/api/room").json()
    assert payload["status"] == "online"
    assert payload["population"] == 0
    assert payload["maxClients"] == 4
    assert "nicknames" not in payload, "the roster must not leak through HTTP"


def test_index_is_served(client):
    response = client.get(f"{BASE}/")
    assert response.status_code == 200
    assert "ASCII CITY" in response.text


# --- tiles -----------------------------------------------------------------


def test_tile_is_binary_and_decodes(client):
    response = client.get(
        f"{BASE}/api/world/tiles/0/0", headers={"accept-encoding": "identity"}
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/octet-stream"

    tile = decode_tile(response.content)
    assert tile.cells == TILE_CELLS
    assert tile.tile_x == 0 and tile.tile_y == 0
    assert len(tile.buildings) > 20
    assert len(tile.collision) == TILE_CELLS * TILE_CELLS


def test_tile_is_gzipped_when_the_client_accepts_it(client):
    response = client.get(
        f"{BASE}/api/world/tiles/0/0", headers={"accept-encoding": "gzip"}
    )
    assert response.headers.get("content-encoding") == "gzip"
    # httpx transparently decompresses, so the decoded body is the raw tile.
    assert decode_tile(response.content).cells == TILE_CELLS
    assert int(response.headers["x-tile-bytes"]) > len(response.content) // 2


def test_tiles_are_cacheable_and_revalidate(client):
    first = client.get(f"{BASE}/api/world/tiles/0/0")
    etag = first.headers["etag"]
    assert "immutable" in first.headers["cache-control"]

    second = client.get(f"{BASE}/api/world/tiles/0/0", headers={"if-none-match": etag})
    assert second.status_code == 304
    assert not second.content


def test_unknown_tile_is_a_clean_404(client):
    assert client.get(f"{BASE}/api/world/tiles/9/9").status_code == 404


# --- websocket -------------------------------------------------------------


def read_until(socket, kind: int, *, contains: bytes = b"", timeout: float = 10.0) -> bytes:
    """Drain frames until the wanted one shows up.

    Snapshots stream at 20 Hz and queue up while a test does anything else, so
    the search is bounded by wall clock rather than by a frame count.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        frame = socket.receive_bytes()
        if frame and frame[0] == kind and contains in frame:
            return frame
    raise AssertionError(f"frame 0x{kind:02x} never arrived")


def parse_welcome(payload: bytes) -> dict:
    player_id, color, nick_len = struct.unpack_from("<HBB", payload, 1)
    nickname = payload[4 : 4 + nick_len].decode()
    return {"id": player_id, "color": color, "nickname": nickname}


def input_frame(sequence: int, yaw: float = 0.0) -> bytes:
    return bytes([wire.MSG_INPUT]) + struct.pack(
        "<IbbHbBI", sequence, 100, 0, wire.encode_yaw(yaw), 0, 0, 0
    )


def chat_frame(text: str) -> bytes:
    encoded = text.encode("utf-8")
    return bytes([wire.MSG_CHAT, 0]) + len(encoded).to_bytes(2, "little") + encoded


def test_a_connection_receives_a_server_issued_nickname(client):
    with client.websocket_connect(f"{BASE}/ws") as socket:
        welcome = parse_welcome(read_until(socket, wire.MSG_WELCOME))
        assert welcome["id"] > 0
        assert 6 <= len(welcome["nickname"]) <= 24
        assert "-" in welcome["nickname"]


def test_snapshots_flow_without_any_client_input(client):
    with client.websocket_connect(f"{BASE}/ws") as socket:
        read_until(socket, wire.MSG_WELCOME)
        assert read_until(socket, wire.MSG_SNAPSHOT)


def test_two_tabs_share_one_room_and_see_each_other(client):
    with client.websocket_connect(f"{BASE}/ws") as first:
        first_welcome = parse_welcome(read_until(first, wire.MSG_WELCOME))
        with client.websocket_connect(f"{BASE}/ws") as second:
            second_welcome = parse_welcome(read_until(second, wire.MSG_WELCOME))
            assert second_welcome["id"] != first_welcome["id"]
            assert second_welcome["nickname"] != first_welcome["nickname"]

            # The first tab is told about the newcomer.
            roster = read_until(first, wire.MSG_ROSTER_ADD)
            assert int.from_bytes(roster[1:3], "little") == second_welcome["id"]

            assert client.get(f"{BASE}/api/room").json()["population"] == 2

        # And about the departure.
        removal = read_until(first, wire.MSG_ROSTER_REMOVE)
        assert int.from_bytes(removal[1:3], "little") == second_welcome["id"]


def test_chat_crosses_between_connections(client):
    with client.websocket_connect(f"{BASE}/ws") as first:
        read_until(first, wire.MSG_WELCOME)
        with client.websocket_connect(f"{BASE}/ws") as second:
            speaker = parse_welcome(read_until(second, wire.MSG_WELCOME))
            second.send_bytes(chat_frame("hello from the other tab"))

            # Join announcements share the frame type, so match on the text.
            frame = read_until(first, wire.MSG_CHAT_OUT, contains=b"hello from the other tab")
            assert speaker["nickname"].encode() in frame


def test_movement_is_applied_by_the_server(client):
    with client.websocket_connect(f"{BASE}/ws") as socket:
        read_until(socket, wire.MSG_WELCOME)
        before = wire._SNAPSHOT_HEAD.unpack_from(read_until(socket, wire.MSG_SNAPSHOT), 1)

        for sequence in range(1, 25):
            socket.send_bytes(input_frame(sequence))

        after = before
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            after = wire._SNAPSHOT_HEAD.unpack_from(read_until(socket, wire.MSG_SNAPSHOT), 1)
            if after[1] > 0:
                break
        assert after[1] > 0, "the server never acknowledged an input"
        assert (after[2], after[3]) != (before[2], before[3]), "the player never moved"


def test_a_text_frame_earns_a_notice(client):
    with client.websocket_connect(f"{BASE}/ws") as socket:
        read_until(socket, wire.MSG_WELCOME)
        socket.send_text("this protocol is binary")
        notice = read_until(socket, wire.MSG_NOTICE)
        assert notice[1] == wire.NOTICE_ERROR


@pytest.mark.parametrize("client", [small_settings(max_clients=2)], indirect=True)
def test_a_full_room_refuses_the_extra_socket_with_a_reason(client):
    with client.websocket_connect(f"{BASE}/ws") as first, client.websocket_connect(
        f"{BASE}/ws"
    ) as second:
        read_until(first, wire.MSG_WELCOME)
        read_until(second, wire.MSG_WELCOME)

        with client.websocket_connect(f"{BASE}/ws") as third:
            notice = third.receive_bytes()
            assert notice[0] == wire.MSG_NOTICE and notice[1] == wire.NOTICE_ERROR
            assert b"full" in notice
            with pytest.raises(WebSocketDisconnect) as refusal:
                third.receive_bytes()
            assert refusal.value.code == CLOSE_ROOM_FULL
