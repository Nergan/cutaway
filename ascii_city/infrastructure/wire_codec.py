"""Binary WebSocket protocol. ``docs/protocol.md`` is the normative reference.

Everything is little-endian. Positions travel as unsigned centimetres and
angles as unsigned fractions of a turn, which keeps a snapshot entry at ten
bytes: a full room stays an order of magnitude below the traffic budget the
orchestrator grants this project.
"""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass

from ..domain.chat import ChatMessage, ChatScope
from ..domain.constants import (
    ANGLE_SCALE,
    PITCH_SCALE,
    POSITION_SCALE,
)
from ..domain.errors import ProtocolError
from ..domain.player import InputCommand, PlayerState
from .quantise import round_half_up

TAU = math.tau

# Client to server.
MSG_INPUT = 0x01
MSG_CHAT = 0x02
MSG_PING = 0x03
MSG_RENAME = 0x04
MSG_SET_AVATAR = 0x05

INPUT_FLAG_SPRINT = 0x01
INPUT_FLAG_JUMP = 0x02

# Server to client.
MSG_WELCOME = 0x81
MSG_SNAPSHOT = 0x82
MSG_CHAT_OUT = 0x83
MSG_NOTICE = 0x84
MSG_ROSTER_SYNC = 0x85
MSG_ROSTER_ADD = 0x86
MSG_ROSTER_REMOVE = 0x87
MSG_PONG = 0x88
MSG_ROSTER_UPDATE = 0x89

NOTICE_INFO = 0
NOTICE_WARNING = 1
NOTICE_ERROR = 2
NOTICE_RATE_LIMIT = 3

MAX_FRAME_BYTES = 4096
"""Anything larger than this from a client is dropped before parsing."""

_INPUT = struct.Struct("<IbbHbBI")
_SNAPSHOT_HEAD = struct.Struct("<IIHHHh")
_SNAPSHOT_ENTRY = struct.Struct("<HHHHHbB")
_PONG = struct.Struct("<II")

SNAPSHOT_FLAG_SIMPLIFIED = 0x04


def encode_position(value: float) -> int:
    scaled = round_half_up(value * POSITION_SCALE)
    return 0 if scaled < 0 else 65535 if scaled > 65535 else scaled


def decode_position(value: int) -> float:
    return value / POSITION_SCALE


def encode_yaw(value: float) -> int:
    return round_half_up((value % TAU) / TAU * ANGLE_SCALE) & 0xFFFF


def decode_yaw(value: int) -> float:
    return value / ANGLE_SCALE * TAU


def encode_velocity(value: float) -> int:
    """Vertical speed as signed centimetres per second.

    The client replays its unacknowledged input from the authoritative state,
    and without the vertical velocity that replay has to guess, which turns
    every jump into a stutter as each snapshot flattens the arc.
    """
    scaled = round_half_up(value * POSITION_SCALE)
    return -32768 if scaled < -32768 else 32767 if scaled > 32767 else scaled


def decode_velocity(value: int) -> float:
    return value / POSITION_SCALE


def encode_pitch(value: float) -> int:
    scaled = round_half_up(value * PITCH_SCALE)
    return -127 if scaled < -127 else 127 if scaled > 127 else scaled


def decode_pitch(value: int) -> float:
    return value / PITCH_SCALE


@dataclass(frozen=True, slots=True)
class ChatRequest:
    scope: ChatScope
    text: str


@dataclass(frozen=True, slots=True)
class PingRequest:
    client_time: int


@dataclass(frozen=True, slots=True)
class RenameRequest:
    nickname: str


@dataclass(frozen=True, slots=True)
class SetAvatarRequest:
    avatar: int


ClientFrame = InputCommand | ChatRequest | PingRequest | RenameRequest | SetAvatarRequest


def decode_client_frame(payload: bytes) -> ClientFrame:
    """Parse one client frame or raise :class:`ProtocolError`.

    Callers must treat every field as hostile; this function only guarantees
    structural validity, while range clamping happens in the domain layer.
    """
    if not payload:
        raise ProtocolError("Empty frame.")
    if len(payload) > MAX_FRAME_BYTES:
        raise ProtocolError("Frame exceeds the maximum size.")

    kind = payload[0]
    body = payload[1:]

    if kind == MSG_INPUT:
        if len(body) != _INPUT.size:
            raise ProtocolError("Malformed input frame.")
        sequence, forward, strafe, yaw, pitch, flags, client_time = _INPUT.unpack(body)
        return InputCommand.sanitised(
            sequence=sequence,
            forward=forward / 100.0,
            strafe=strafe / 100.0,
            yaw=decode_yaw(yaw),
            pitch=decode_pitch(pitch),
            sprint=bool(flags & INPUT_FLAG_SPRINT),
            jump=bool(flags & INPUT_FLAG_JUMP),
            client_time=client_time,
        )

    if kind == MSG_CHAT:
        if len(body) < 3:
            raise ProtocolError("Malformed chat frame.")
        scope_value = body[0]
        length = int.from_bytes(body[1:3], "little")
        raw = body[3 : 3 + length]
        if len(raw) != length:
            raise ProtocolError("Chat frame is truncated.")
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ProtocolError("Chat text is not valid UTF-8.") from exc
        if scope_value not in (0, 1):
            raise ProtocolError("Clients may only send global or proximity chat.")
        return ChatRequest(scope=ChatScope.from_wire(scope_value), text=text)

    if kind == MSG_PING:
        if len(body) != 4:
            raise ProtocolError("Malformed ping frame.")
        return PingRequest(client_time=int.from_bytes(body, "little"))

    if kind == MSG_RENAME:
        if len(body) < 2:
            raise ProtocolError("Malformed rename frame.")
        length = int.from_bytes(body[0:2], "little")
        raw = body[2 : 2 + length]
        if len(raw) != length:
            raise ProtocolError("Rename frame is truncated.")
        try:
            nickname = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ProtocolError("Nickname is not valid UTF-8.") from exc
        return RenameRequest(nickname=nickname)

    if kind == MSG_SET_AVATAR:
        if len(body) != 1:
            raise ProtocolError("Malformed avatar frame.")
        return SetAvatarRequest(avatar=body[0])

    raise ProtocolError(f"Unknown frame type 0x{kind:02x}.")


def encode_welcome(
    *,
    player: PlayerState,
    simulation_hz: int,
    snapshot_hz: int,
    server_time_ms: int,
    world_id: str,
    world_version: int,
    tiles_x: int,
    tiles_y: int,
    tile_cells: int,
    cell_size: float,
) -> bytes:
    nickname = player.nickname.encode("utf-8")
    world = world_id.encode("utf-8")
    out = bytearray()
    out.append(MSG_WELCOME)
    out += struct.pack(
        "<HBBB",
        player.id,
        player.color,
        player.avatar,
        len(nickname),
    )
    out += nickname
    out += struct.pack(
        "<HHHHBBIBBHfI",
        encode_position(player.x),
        encode_position(player.y),
        encode_position(player.z),
        encode_yaw(player.yaw),
        simulation_hz,
        snapshot_hz,
        server_time_ms & 0xFFFFFFFF,
        tiles_x,
        tiles_y,
        tile_cells,
        cell_size,
        world_version,
    )
    out.append(len(world))
    out += world
    return bytes(out)


def encode_snapshot(
    *,
    tick: int,
    ack_sequence: int,
    viewer: PlayerState,
    entries: list[tuple[PlayerState, bool]],
) -> bytes:
    out = bytearray()
    out.append(MSG_SNAPSHOT)
    out += _SNAPSHOT_HEAD.pack(
        tick & 0xFFFFFFFF,
        ack_sequence & 0xFFFFFFFF,
        encode_position(viewer.x),
        encode_position(viewer.y),
        encode_position(viewer.z),
        encode_velocity(viewer.velocity_z),
    )
    out.append(min(255, len(entries)))
    for state, simplified in entries[:255]:
        flags = state.animation & 0x03
        if simplified:
            flags |= SNAPSHOT_FLAG_SIMPLIFIED
        out += _SNAPSHOT_ENTRY.pack(
            state.id,
            encode_position(state.x),
            encode_position(state.y),
            # Without a height the whole street looks bolted to the pavement:
            # you see a player's jump in their own view and nowhere else.
            encode_position(state.z),
            encode_yaw(state.yaw),
            encode_pitch(state.pitch),
            flags,
        )
    return bytes(out)


def encode_chat(message: ChatMessage) -> bytes:
    text = message.text.encode("utf-8")
    nickname = message.nickname.encode("utf-8")
    out = bytearray()
    out.append(MSG_CHAT_OUT)
    out += struct.pack("<IHBd", message.id & 0xFFFFFFFF, message.sender_id, message.scope.wire, message.created_at)
    out.append(len(nickname))
    out += nickname
    out += len(text).to_bytes(2, "little")
    out += text
    return bytes(out)


def encode_notice(code: int, text: str) -> bytes:
    payload = text.encode("utf-8")[:512]
    out = bytearray()
    out.append(MSG_NOTICE)
    out.append(code & 0xFF)
    out += len(payload).to_bytes(2, "little")
    out += payload
    return bytes(out)


def _roster_entry(out: bytearray, player: PlayerState) -> None:
    nickname = player.nickname.encode("utf-8")
    out += player.id.to_bytes(2, "little")
    out.append(player.color)
    out.append(player.avatar)
    out.append(len(nickname))
    out += nickname


def encode_roster_sync(players: list[PlayerState]) -> bytes:
    out = bytearray()
    out.append(MSG_ROSTER_SYNC)
    out += len(players).to_bytes(2, "little")
    for player in players:
        _roster_entry(out, player)
    return bytes(out)


def encode_roster_add(player: PlayerState) -> bytes:
    out = bytearray()
    out.append(MSG_ROSTER_ADD)
    _roster_entry(out, player)
    return bytes(out)


def encode_roster_update(player: PlayerState) -> bytes:
    out = bytearray()
    out.append(MSG_ROSTER_UPDATE)
    _roster_entry(out, player)
    return bytes(out)


def encode_rename(nickname: str) -> bytes:
    payload = nickname.encode("utf-8")
    out = bytearray()
    out.append(MSG_RENAME)
    out += len(payload).to_bytes(2, "little")
    out += payload
    return bytes(out)


def encode_set_avatar(avatar: int) -> bytes:
    return bytes([MSG_SET_AVATAR, avatar & 0xFF])


def encode_roster_remove(player_id: int) -> bytes:
    return bytes([MSG_ROSTER_REMOVE]) + player_id.to_bytes(2, "little")


def encode_pong(client_time: int, server_time_ms: int) -> bytes:
    return bytes([MSG_PONG]) + _PONG.pack(client_time & 0xFFFFFFFF, server_time_ms & 0xFFFFFFFF)
