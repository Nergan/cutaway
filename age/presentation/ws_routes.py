"""The WebSocket adapter.

Translates socket frames into queued commands and nothing else. Every decision about
what a command *means* belongs to the simulation; this decides only whether a frame
is well-formed enough to be worth queueing.

The handshake is the one exception, because a character has to exist before the
simulation has anything to queue commands against. Hello and Ready are handled here,
in order, and a client that sends anything else first is refused.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..application.chat import ChatMessage
from ..domain.constants import PROTOCOL_VERSION
from ..infrastructure import wire
from .connection import Connection
from .container import get_container

logger = logging.getLogger(__name__)

router = APIRouter()

CLOSE_WORLD_UNAVAILABLE = 4001
CLOSE_ROOM_FULL = 4002
CLOSE_BAD_PROTOCOL = 4003
CLOSE_BAD_FRAME = 4004

# One input packet is 24 bytes and the largest client frame is a chat message. A
# kilobyte is generous; anything bigger is not this protocol.
MAX_FRAME_BYTES = 1024

# How many scrollback lines a joining player receives, so a conversation already in
# progress is visible rather than starting blank.
CHAT_BACKLOG = 20


class WebSocketTransport:
    """Adapts a FastAPI socket to :class:`~age.presentation.connection.Transport`."""

    __slots__ = ("_socket",)

    def __init__(self, socket: WebSocket) -> None:
        self._socket = socket

    async def send_bytes(self, payload: bytes) -> None:
        await self._socket.send_bytes(payload)

    async def close(self, code: int, reason: str) -> None:
        await self._socket.close(code=code, reason=reason)


@router.websocket("/ws")
async def game_socket(websocket: WebSocket) -> None:
    # Accept before any check, so a refusal arrives as a close code the browser can
    # read rather than as a failed handshake it cannot explain.
    await websocket.accept()
    container = get_container()

    try:
        await container.ready()
    except Exception as exc:
        logger.warning("Refusing a connection while the world is unavailable: %s", exc)
        await _refuse(websocket, CLOSE_WORLD_UNAVAILABLE, "The world failed to load.")
        return

    room = container.room
    if room.is_full:
        await _refuse(websocket, CLOSE_ROOM_FULL, "The world is full. Try again shortly.")
        return

    session_id = uuid.uuid4().hex
    connection = Connection(session_id, WebSocketTransport(websocket))
    connection.start()
    room.attach(connection)

    try:
        if not await _handshake(websocket, connection, room, container):
            return

        while True:
            event = await websocket.receive()
            if event.get("type") == "websocket.disconnect":
                break

            payload = event.get("bytes")
            if payload is None:
                connection.enqueue(
                    wire.encode_error(wire.ERROR_INVALID, "This endpoint is binary only.")
                )
                continue
            if len(payload) > MAX_FRAME_BYTES:
                await _refuse(websocket, CLOSE_BAD_FRAME, "Frame too large.")
                break

            try:
                command = wire.decode_client_packet(payload)
            except wire.ProtocolError as exc:
                logger.debug("Malformed frame from %s: %s", session_id, exc)
                connection.enqueue(wire.encode_error(wire.ERROR_INVALID, str(exc)[:120]))
                continue

            if isinstance(command, wire.PingRequest):
                # Answered here rather than queued: a round-trip measurement that
                # waits for the next tick measures the tick, not the network.
                connection.enqueue(
                    wire.encode_pong(command.client_time, room.simulation.world.now)
                )
                continue

            if isinstance(command, wire.Ready):
                # Snapshots only start once the client says it has rendered the
                # initial state, so the first thing it draws is a whole world rather
                # than a half-streamed one.
                session = room.simulation.world.sessions.get(session_id)
                if session is not None:
                    session.ready = True
                continue

            room.simulation.enqueue(session_id, command)

    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("Unexpected failure on the socket for %s", session_id)
    finally:
        await room.detach(connection)


async def _handshake(
    websocket: WebSocket, connection: Connection, room, container
) -> bool:
    """Read Hello, create the character, send Welcome, then wait for Ready."""
    try:
        first = await websocket.receive()
    except WebSocketDisconnect:
        return False

    payload = first.get("bytes")
    if payload is None:
        await _refuse(websocket, CLOSE_BAD_PROTOCOL, "Expected a binary hello.")
        return False

    try:
        hello = wire.decode_client_packet(payload)
    except wire.ProtocolError as exc:
        await _refuse(websocket, CLOSE_BAD_PROTOCOL, f"Bad hello: {exc}")
        return False

    if not isinstance(hello, wire.Hello):
        await _refuse(websocket, CLOSE_BAD_PROTOCOL, "The first frame must be a hello.")
        return False

    if hello.protocol_version != PROTOCOL_VERSION:
        # A version mismatch is a stale cached bundle. Saying so is much more useful
        # than letting the client mis-parse every subsequent packet.
        await _refuse(
            websocket,
            CLOSE_BAD_PROTOCOL,
            f"Protocol {hello.protocol_version} is not {PROTOCOL_VERSION}. Reload the page.",
            wire.ERROR_VERSION_MISMATCH,
        )
        return False

    simulation = room.simulation
    try:
        joined = await simulation.sessions.join(
            session_id=connection.session_id,
            character_name=hello.character_name,
            class_id=hello.class_id,
            appearance=hello.appearance,
        )
    except Exception as exc:
        logger.warning("Could not create a character for %s: %s", connection.session_id, exc)
        await _refuse(
            websocket, CLOSE_WORLD_UNAVAILABLE, "Your character could not be loaded."
        )
        return False

    room.bind_entity(connection, joined.entity.entity_id)

    world = simulation.world
    connection.enqueue(
        wire.encode_welcome(
            entity_id=joined.entity.entity_id,
            world_seed=world.world_seed,
            topology_version=world.topology.topology_version,
            current_tier=world.topology.current_tier,
            edge_id=world.edge.edge_id,
            spawn_x=joined.entity.position.x,
            spawn_y=joined.entity.position.y,
            server_time=world.now,
        )
    )
    connection.enqueue(
        wire.encode_topology(
            topology_version=world.topology.topology_version,
            current_tier=world.topology.current_tier,
            active_chunks=simulation.manager.active_chunk_keys(),
            retiring_chunks=simulation.manager.retiring_chunk_keys(),
        )
    )

    for message in simulation.chat.history[-CHAT_BACKLOG:]:
        connection.enqueue(_chat_frame(message))

    greeting = (
        f"{joined.entity.name} returns to the wilds."
        if joined.returning
        else f"{joined.entity.name} arrives for the first time."
    )
    room.system_message(greeting)
    return True


def _chat_frame(message: ChatMessage) -> bytes:
    return wire.encode_chat(
        sender_id=message.sender_id,
        channel=message.channel,
        sender_name=message.sender_name,
        text=message.text,
    )


async def _refuse(
    websocket: WebSocket, code: int, reason: str, error: int = wire.ERROR_INVALID
) -> None:
    try:
        await websocket.send_bytes(wire.encode_error(error, reason[:150]))
        await websocket.close(code=code, reason=reason[:120])
    except Exception:
        logger.debug("Could not deliver the refusal to the client.", exc_info=True)
