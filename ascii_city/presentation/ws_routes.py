"""WebSocket transport adapter for the city room."""

from __future__ import annotations

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..application.room import Member, PlayerConnection
from ..domain.errors import RoomFullError
from ..infrastructure.wire_codec import MAX_FRAME_BYTES, NOTICE_ERROR, encode_notice
from .container import get_container

logger = logging.getLogger(__name__)

router = APIRouter()

CLOSE_ROOM_FULL = 4001
CLOSE_WORLD_UNAVAILABLE = 4002
CLOSE_BAD_FRAME = 4003


class WebSocketPlayerConnection(PlayerConnection):
    def __init__(self, socket: WebSocket) -> None:
        self._socket = socket

    async def send(self, payload: bytes) -> None:
        await self._socket.send_bytes(payload)

    async def close(self, code: int, reason: str) -> None:
        await self._socket.close(code=code, reason=reason[:120])


@router.websocket("/ws")
async def game_socket(websocket: WebSocket) -> None:
    # Accept first so the browser receives a close code it can show the user.
    await websocket.accept()
    container = get_container()

    try:
        await container.ready()
    except Exception as exc:
        logger.warning("Refusing a connection while the world is unavailable: %s", exc)
        await _fail(websocket, CLOSE_WORLD_UNAVAILABLE, "The district failed to load.")
        return

    room = container.room
    connection = WebSocketPlayerConnection(websocket)
    member: Member | None = None
    try:
        member = await room.join(connection)
    except RoomFullError:
        await _fail(websocket, CLOSE_ROOM_FULL, "The district is full. Try again shortly.")
        return

    try:
        while True:
            event = await websocket.receive()
            kind = event.get("type")
            if kind == "websocket.disconnect":
                break
            payload = event.get("bytes")
            if payload is None:
                # The protocol is binary end to end; text frames are a client bug.
                await connection.send(
                    encode_notice(NOTICE_ERROR, "This endpoint only accepts binary frames.")
                )
                continue
            if len(payload) > MAX_FRAME_BYTES:
                await _fail(websocket, CLOSE_BAD_FRAME, "Frame too large.")
                break
            await room.handle_frame(member, payload)
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("Unexpected failure on the socket for %s", member.state.nickname)
    finally:
        await room.leave(member)


async def _fail(websocket: WebSocket, code: int, reason: str) -> None:
    try:
        await websocket.send_bytes(encode_notice(NOTICE_ERROR, reason))
        await websocket.close(code=code, reason=reason)
    except Exception:
        logger.debug("Could not deliver the refusal reason to the client.", exc_info=True)
