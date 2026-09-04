"""The binary wire protocol.

TDD 5.5 lists FlatBuffers as a candidate pending a Go+TypeScript prototype, with
MessagePack as the documented fallback. This slice uses neither: a hand-rolled
little-endian binary format built on ``struct`` here and ``DataView`` on the
client. The reasoning is in ``docs/protocol.md``, but briefly, the delta encoder is
the thing that actually determines packet size, a schema compiler does not help
write one, and a hand-rolled format costs two mirrored files and no build step.
The framing is versioned, so adopting FlatBuffers later is a codec swap.

Every integer is little-endian. Every packet starts with a one-byte message type.
Floats never travel as floats: positions are fixed-point ints, angles are
normalised uint16s, and health is a percentage byte. Quantising on purpose means
the wire size is predictable and the client and server round identically.
"""

from __future__ import annotations

import math
import struct
from collections.abc import Sequence
from dataclasses import dataclass, field

from ..domain.constants import (
    ANGLE_SCALE,
    CHAT_MAX_LENGTH,
    MAX_NAME_LENGTH,
    PERCENT_SCALE,
    POSITION_SCALE,
    PROTOCOL_VERSION,
)
from ..domain.entities import DirtyField, EntityId

# --- message types ----------------------------------------------------------
#
# Client-to-server types have the high bit clear, server-to-client set. A packet
# arriving on the wrong side is therefore rejected by inspection rather than by
# accident.

CLIENT_HELLO = 0x01
CLIENT_READY = 0x02
CLIENT_INPUT = 0x03
CLIENT_ACTION = 0x04
CLIENT_CHAT = 0x05
CLIENT_BUILD = 0x06
CLIENT_PING = 0x07
CLIENT_DEV_TIER = 0x08
CLIENT_COMPOSE = 0x09
CLIENT_INVENTORY = 0x0A

SERVER_WELCOME = 0x81
SERVER_SNAPSHOT = 0x82
SERVER_SPAWN = 0x83
SERVER_DESPAWN = 0x84
SERVER_TOPOLOGY = 0x85
SERVER_COMBAT = 0x86
SERVER_CHAT = 0x87
SERVER_TILES = 0x88
SERVER_PONG = 0x89
SERVER_ERROR = 0x8A
SERVER_PROGRESS = 0x8B
SERVER_INVENTORY = 0x8C

# What a client wants done with a slot. ``EQUIP``, ``USE`` and ``DROP`` address an
# inventory index; ``UNEQUIP`` addresses an equipment slot.
INVENTORY_EQUIP = 0
INVENTORY_UNEQUIP = 1
INVENTORY_USE = 2
INVENTORY_DROP = 3

# Input bit flags, packed into one byte.
INPUT_UP = 1 << 0
INPUT_DOWN = 1 << 1
INPUT_LEFT = 1 << 2
INPUT_RIGHT = 1 << 3
INPUT_RUN = 1 << 4

# Despawn reasons, so the client can decide whether to play an effect.
DESPAWN_OUT_OF_RANGE = 0
DESPAWN_DIED = 1
DESPAWN_DISCONNECTED = 2
DESPAWN_CHUNK_RETIRED = 3

# Error codes.
ERROR_STALE_TOPOLOGY = 1
ERROR_SAFE_ZONE = 2
ERROR_OUT_OF_RANGE = 3
ERROR_ON_COOLDOWN = 4
ERROR_NO_RESOURCE = 5
ERROR_NO_MATERIAL = 6
ERROR_INVALID = 7
ERROR_RATE_LIMITED = 8
ERROR_DEAD = 9
# Distinct from ERROR_INVALID because the client can act on it: a mismatch means a
# stale cached bundle, and the only fix is a hard reload.
ERROR_VERSION_MISMATCH = 10

# Build actions.
BUILD_PLACE = 0
BUILD_HARVEST = 1


class ProtocolError(ValueError):
    """Raised on a malformed packet. Always the client's fault; never fatal."""


# --- quantisation -----------------------------------------------------------
#
# JavaScript's Math.round breaks ties upward; Python's round() breaks them to
# even. Encoding a position ending in exactly half a step would therefore
# disagree by one unit between the two, which shows up as a permanent
# reconciliation error. round_half_up is the shared definition.


def round_half_up(value: float) -> int:
    """Round half away from zero on the positive side, matching ``Math.round``."""
    return math.floor(value + 0.5)


def encode_position(tiles: float) -> int:
    return round_half_up(tiles * POSITION_SCALE)


def decode_position(raw: int) -> float:
    return raw / POSITION_SCALE


def encode_angle(radians: float) -> int:
    """Normalise to ``[0, 2pi)`` then scale into a uint16."""
    turns = radians % (2.0 * math.pi)
    if turns < 0.0:
        turns += 2.0 * math.pi
    return round_half_up(turns * ANGLE_SCALE) & 0xFFFF


def decode_angle(raw: int) -> float:
    return raw / ANGLE_SCALE


def encode_percent(current: int, maximum: int) -> int:
    """Quantise a fraction into a byte, reserving zero to mean *actually* empty.

    The renderer treats a health of 0 as death, so a living entity must never encode
    as 0 however little health it has left. With the current 100-point pools every
    point is worth two steps and rounding could not reach zero anyway, but a boss
    with a four-figure pool would otherwise appear dead for its last few points.
    """
    if maximum <= 0:
        return 0
    ratio = current / maximum
    if ratio <= 0.0:
        return 0
    if ratio >= 1.0:
        return PERCENT_SCALE
    return max(1, round_half_up(ratio * PERCENT_SCALE))


# --- writer and reader ------------------------------------------------------


class Writer:
    """Little-endian byte builder."""

    __slots__ = ("_parts",)

    def __init__(self, message_type: int) -> None:
        self._parts: list[bytes] = [struct.pack("<B", message_type)]

    def u8(self, value: int) -> "Writer":
        self._parts.append(struct.pack("<B", value & 0xFF))
        return self

    def u16(self, value: int) -> "Writer":
        self._parts.append(struct.pack("<H", value & 0xFFFF))
        return self

    def u32(self, value: int) -> "Writer":
        self._parts.append(struct.pack("<I", value & 0xFFFFFFFF))
        return self

    def i32(self, value: int) -> "Writer":
        self._parts.append(struct.pack("<i", value))
        return self

    def u64(self, value: int) -> "Writer":
        self._parts.append(struct.pack("<Q", value & 0xFFFFFFFFFFFFFFFF))
        return self

    def f32(self, value: float) -> "Writer":
        self._parts.append(struct.pack("<f", value))
        return self

    def f64(self, value: float) -> "Writer":
        self._parts.append(struct.pack("<d", value))
        return self

    def text(self, value: str, limit: int) -> "Writer":
        """Length-prefixed UTF-8.

        Truncation happens on the encoded bytes but respects character
        boundaries, so a clipped multi-byte character never produces a payload the
        client cannot decode.
        """
        encoded = value.encode("utf-8")[:limit]
        while encoded:
            try:
                encoded.decode("utf-8")
                break
            except UnicodeDecodeError:
                encoded = encoded[:-1]
        self._parts.append(struct.pack("<H", len(encoded)))
        self._parts.append(encoded)
        return self

    def raw(self, payload: bytes) -> "Writer":
        self._parts.append(payload)
        return self

    def build(self) -> bytes:
        return b"".join(self._parts)


class Reader:
    """Little-endian byte cursor that refuses to read past the end."""

    __slots__ = ("_data", "_offset")

    def __init__(self, data: bytes, offset: int = 0) -> None:
        self._data = data
        self._offset = offset

    @property
    def remaining(self) -> int:
        return len(self._data) - self._offset

    def _take(self, count: int) -> bytes:
        if self.remaining < count:
            raise ProtocolError(f"packet ended early: wanted {count}, had {self.remaining}")
        chunk = self._data[self._offset : self._offset + count]
        self._offset += count
        return chunk

    def u8(self) -> int:
        return self._take(1)[0]

    def u16(self) -> int:
        return struct.unpack("<H", self._take(2))[0]

    def u32(self) -> int:
        return struct.unpack("<I", self._take(4))[0]

    def i32(self) -> int:
        return struct.unpack("<i", self._take(4))[0]

    def u64(self) -> int:
        return struct.unpack("<Q", self._take(8))[0]

    def f32(self) -> float:
        return struct.unpack("<f", self._take(4))[0]

    def f64(self) -> float:
        return struct.unpack("<d", self._take(8))[0]

    def text(self, limit: int) -> str:
        length = self.u16()
        if length > limit:
            raise ProtocolError(f"string of {length} bytes exceeds the {limit} byte limit")
        return self._take(length).decode("utf-8", errors="replace")


# --- client to server -------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Hello:
    """First packet: who is connecting, and as what."""

    protocol_version: int
    character_name: str
    class_id: int
    appearance: tuple[int, int, int, int, int]


@dataclass(frozen=True, slots=True)
class Ready:
    """The client has rendered the initial state and wants snapshots."""


@dataclass(frozen=True, slots=True)
class InputCommand:
    """One movement intent.

    ``sequence`` is the client's own counter. The server echoes the highest it has
    processed so the client knows which predictions are confirmed. ``predicted_x``
    and ``predicted_y`` are where the client thinks it ended up; the server uses
    them only to decide whether to rubber-band, never as authority.
    """

    sequence: int
    topology_version: int
    buttons: int
    facing: float
    predicted_x: float
    predicted_y: float
    delta_time: float

    @property
    def move_axis(self) -> tuple[float, float]:
        """Normalised movement direction from the button bits.

        Diagonals are normalised so holding two keys is not faster than one, which
        the server would otherwise treat as a speed hack.
        """
        dx = (1.0 if self.buttons & INPUT_RIGHT else 0.0) - (
            1.0 if self.buttons & INPUT_LEFT else 0.0
        )
        dy = (1.0 if self.buttons & INPUT_DOWN else 0.0) - (
            1.0 if self.buttons & INPUT_UP else 0.0
        )
        if dx and dy:
            inv = 0.7071067811865476
            return dx * inv, dy * inv
        return dx, dy

    @property
    def running(self) -> bool:
        return bool(self.buttons & INPUT_RUN)


@dataclass(frozen=True, slots=True)
class ActionCommand:
    """An ability activation aimed at a point."""

    sequence: int
    topology_version: int
    ability_id: int
    target_x: float
    target_y: float
    target_entity: EntityId


@dataclass(frozen=True, slots=True)
class ChatRequest:
    channel: int
    text: str


@dataclass(frozen=True, slots=True)
class BuildRequest:
    """Place or harvest a single tile."""

    topology_version: int
    action: int
    tile_x: int
    tile_y: int
    material: str


@dataclass(frozen=True, slots=True)
class PingRequest:
    client_time: float


@dataclass(frozen=True, slots=True)
class DevTierRequest:
    """Force a tier change, for demonstration and tests.

    Gated behind a server setting. Without it the accordion only moves on real
    population changes, which nobody is going to sit through in a demo.
    """

    target_tier: int


@dataclass(frozen=True, slots=True)
class ComposeRequest:
    """Add a second half to the character's class (GDD 6.3).

    Sent once, when a base-class character has levelled and the client has asked
    them which half to take. The server is the one that decides whether the choice
    is available, so this carries nothing but the half.
    """

    half: int


@dataclass(frozen=True, slots=True)
class InventoryCommand:
    """Equip, unequip, use, or drop one slot.

    One packet for four verbs rather than four packets, because they share a shape
    and differ only in what the slot means. ``count`` is only read by ``DROP``; the
    others move exactly one item, and letting a client equip two of something would
    be a question the equipment map has no way to answer.
    """

    action: int
    slot: int
    count: int


ClientPacket = (
    Hello
    | Ready
    | InputCommand
    | ActionCommand
    | ChatRequest
    | BuildRequest
    | PingRequest
    | DevTierRequest
    | ComposeRequest
    | InventoryCommand
)


def decode_client_packet(data: bytes) -> ClientPacket:
    """Parse one client frame. Raises :class:`ProtocolError` on anything odd."""
    if not data:
        raise ProtocolError("empty packet")

    reader = Reader(data, 1)
    message_type = data[0]

    if message_type == CLIENT_HELLO:
        return Hello(
            protocol_version=reader.u16(),
            character_name=reader.text(MAX_NAME_LENGTH * 4),
            class_id=reader.u8(),
            appearance=(reader.u8(), reader.u8(), reader.u8(), reader.u8(), reader.u8()),
        )

    if message_type == CLIENT_READY:
        return Ready()

    if message_type == CLIENT_INPUT:
        return InputCommand(
            sequence=reader.u32(),
            topology_version=reader.u32(),
            buttons=reader.u8(),
            facing=decode_angle(reader.u16()),
            predicted_x=decode_position(reader.i32()),
            predicted_y=decode_position(reader.i32()),
            delta_time=reader.u16() / 10000.0,
        )

    if message_type == CLIENT_ACTION:
        return ActionCommand(
            sequence=reader.u32(),
            topology_version=reader.u32(),
            ability_id=reader.u16(),
            target_x=decode_position(reader.i32()),
            target_y=decode_position(reader.i32()),
            target_entity=reader.u32(),
        )

    if message_type == CLIENT_CHAT:
        return ChatRequest(channel=reader.u8(), text=reader.text(CHAT_MAX_LENGTH * 4))

    if message_type == CLIENT_BUILD:
        return BuildRequest(
            topology_version=reader.u32(),
            action=reader.u8(),
            tile_x=reader.i32(),
            tile_y=reader.i32(),
            material=reader.text(32),
        )

    if message_type == CLIENT_PING:
        return PingRequest(client_time=reader.f64())

    if message_type == CLIENT_DEV_TIER:
        return DevTierRequest(target_tier=reader.u8())

    if message_type == CLIENT_COMPOSE:
        return ComposeRequest(half=reader.u8())

    if message_type == CLIENT_INVENTORY:
        return InventoryCommand(action=reader.u8(), slot=reader.u8(), count=reader.u8())

    raise ProtocolError(f"unknown client message type 0x{message_type:02X}")


# --- server to client -------------------------------------------------------


def encode_welcome(
    *,
    entity_id: EntityId,
    world_seed: int,
    topology_version: int,
    current_tier: int,
    edge_id: str,
    spawn_x: float,
    spawn_y: float,
    server_time: float,
) -> bytes:
    """Everything the client needs to start generating its own world.

    The world seed is the important field: with it the client reproduces terrain
    locally, so no chunk of tiles is ever transmitted. Only player edits are.
    """
    return (
        Writer(SERVER_WELCOME)
        .u16(PROTOCOL_VERSION)
        .u32(entity_id)
        .u64(world_seed)
        .u32(topology_version)
        .u8(current_tier)
        .text(edge_id, 64)
        .i32(encode_position(spawn_x))
        .i32(encode_position(spawn_y))
        .f64(server_time)
        .build()
    )


@dataclass(slots=True)
class EntityDelta:
    """One entity's changed fields, ready to encode."""

    entity_id: EntityId
    fields: DirtyField
    x: float = 0.0
    y: float = 0.0
    vx: float = 0.0
    vy: float = 0.0
    facing: float = 0.0
    health_percent: int = 0
    resource_percent: int = 0
    state: int = 0
    appearance: tuple[int, int, int, int, int] = (0, 0, 0, 0, 0)


def encode_snapshot(
    *,
    tick: int,
    server_time: float,
    acknowledged_input: int,
    topology_version: int,
    day_phase: float,
    weather: int,
    deltas: list[EntityDelta],
) -> bytes:
    """A delta snapshot.

    Per entity the payload is a 4-byte id, a 1-byte field mask, and only the
    flagged fields. A player who is only moving costs 4 + 1 + 8 = 13 bytes, which
    is what keeps a full area of interest inside the bandwidth budget without
    compression.
    """
    writer = (
        Writer(SERVER_SNAPSHOT)
        .u32(tick)
        .f64(server_time)
        .u32(acknowledged_input)
        .u32(topology_version)
        .u16(round_half_up(day_phase * 65535.0) & 0xFFFF)
        .u8(weather)
        .u16(len(deltas))
    )

    for delta in deltas:
        writer.u32(delta.entity_id).u8(int(delta.fields) & 0xFF)
        if delta.fields & DirtyField.POSITION:
            writer.i32(encode_position(delta.x)).i32(encode_position(delta.y))
        if delta.fields & DirtyField.VELOCITY:
            writer.i32(encode_position(delta.vx)).i32(encode_position(delta.vy))
        if delta.fields & DirtyField.FACING:
            writer.u16(encode_angle(delta.facing))
        if delta.fields & DirtyField.HEALTH:
            writer.u8(delta.health_percent)
        if delta.fields & DirtyField.RESOURCE:
            writer.u8(delta.resource_percent)
        if delta.fields & DirtyField.STATE:
            writer.u8(delta.state)
        if delta.fields & DirtyField.APPEARANCE:
            for component in delta.appearance:
                writer.u8(component)

    return writer.build()


def encode_spawn(
    *,
    entity_id: EntityId,
    kind: int,
    archetype_or_class: int,
    name: str,
    x: float,
    y: float,
    facing: float,
    health_percent: int,
    level: int,
    state: int,
    appearance: tuple[int, int, int, int, int],
) -> bytes:
    """A full entity introduction, sent once when it enters the view.

    Carries ``state`` because it has to be complete: an entity is introduced once and
    then only ever described by deltas, so a field the introduction leaves out is a
    field the client invents. This one was left out, and the field it stood for was
    liveness — so every entity arrived at the client reading as dead, which meant every
    entity was drawn in the one-frame hurt pose, greyed and half-faded, and no character
    in the game ever animated. Nothing detected it because the client's default was a
    plausible-looking zero rather than an absence.
    """
    writer = (
        Writer(SERVER_SPAWN)
        .u32(entity_id)
        .u8(kind)
        .u8(archetype_or_class)
        .text(name, MAX_NAME_LENGTH * 4)
        .i32(encode_position(x))
        .i32(encode_position(y))
        .u16(encode_angle(facing))
        .u8(health_percent)
        .u16(level)
        .u8(state)
    )
    for component in appearance:
        writer.u8(component)
    return writer.build()


def encode_despawn(entity_id: EntityId, reason: int) -> bytes:
    return Writer(SERVER_DESPAWN).u32(entity_id).u8(reason).build()


def encode_topology(
    *,
    topology_version: int,
    current_tier: int,
    active_chunks: list[str],
    retiring_chunks: list[str],
) -> bytes:
    """A topology change.

    Chunk keys rather than tiles: the client already knows how to generate any
    chunk it can name, so activating a lane costs a few dozen bytes.
    """
    writer = (
        Writer(SERVER_TOPOLOGY)
        .u32(topology_version)
        .u8(current_tier)
        .u16(len(active_chunks))
    )
    for key in active_chunks:
        writer.text(key, 96)
    writer.u16(len(retiring_chunks))
    for key in retiring_chunks:
        writer.text(key, 96)
    return writer.build()


def encode_combat(
    *,
    attacker_id: EntityId,
    target_id: EntityId,
    ability_id: int,
    damage: int,
    healing: int,
    killed: bool,
    x: float,
    y: float,
) -> bytes:
    return (
        Writer(SERVER_COMBAT)
        .u32(attacker_id)
        .u32(target_id)
        .u16(ability_id)
        .u16(min(damage, 0xFFFF))
        .u16(min(healing, 0xFFFF))
        .u8(1 if killed else 0)
        .i32(encode_position(x))
        .i32(encode_position(y))
        .build()
    )


def encode_chat(*, sender_id: EntityId, channel: int, sender_name: str, text: str) -> bytes:
    return (
        Writer(SERVER_CHAT)
        .u32(sender_id)
        .u8(channel)
        .text(sender_name, MAX_NAME_LENGTH * 4)
        .text(text, CHAT_MAX_LENGTH * 4)
        .build()
    )


def encode_tiles(chunk_key: str, changes: dict[int, int]) -> bytes:
    """A tile overlay delta for one chunk.

    Index-plus-value pairs, not a whole chunk: a player digging one tile costs
    three bytes rather than a kilobyte.
    """
    writer = Writer(SERVER_TILES).text(chunk_key, 96).u16(len(changes))
    for index, tile in sorted(changes.items()):
        writer.u16(index).u8(tile)
    return writer.build()


def encode_pong(client_time: float, server_time: float) -> bytes:
    return Writer(SERVER_PONG).f64(client_time).f64(server_time).build()


def encode_error(code: int, detail: str = "") -> bytes:
    return Writer(SERVER_ERROR).u8(code).text(detail, 160).build()


def encode_progress(
    *,
    level: int,
    experience: int,
    next_level_at: int,
    class_id: int,
    compose_available: bool,
    ability_ids: Sequence[int],
) -> bytes:
    """Level, experience, and the class kit that follows from them.

    Sent on connect and whenever any of it changes, rather than folded into the
    snapshot: it changes a handful of times per session, and the snapshot is the one
    packet that goes out thirty times a second.

    ``ability_ids`` travels with the class rather than being derived client-side, so
    the bar cannot disagree with what the server will actually accept.
    """
    writer = (
        Writer(SERVER_PROGRESS)
        .u16(level)
        .u32(experience)
        .u32(next_level_at)
        .u8(class_id)
        .u8(1 if compose_available else 0)
        .u8(len(ability_ids))
    )
    for ability_id in ability_ids:
        writer.u16(ability_id)
    return writer.build()


#: Move speed travels in hundredths of a tile per second. Two bytes at that
#: resolution covers everything the movement integrator can produce, and it keeps the
#: only float in the packet off the wire.
SPEED_SCALE = 100


def encode_inventory(
    *,
    capacity: int,
    stacks: Sequence[tuple[int, int]],
    equipped: Sequence[tuple[int, int]],
    max_health: int,
    max_resource: int,
    bonus_damage: int,
    move_speed: float,
) -> bytes:
    """What one player is carrying, wearing, and what it adds up to.

    Private to its owner and never broadcast: another player's bag is not something
    the client has anywhere to put, and replicating it would be the single largest
    per-entity payload in the protocol for no visible effect.

    The derived stats ride along rather than being recomputed client-side. The client
    knows vitals only as a fraction of a maximum it cannot see, so without these the
    character sheet could show the bars but not the numbers behind them, and a helm
    that adds twelve health would be invisible.
    """
    writer = Writer(SERVER_INVENTORY).u8(capacity).u8(len(stacks))
    for item_id, count in stacks:
        writer.u16(item_id).u16(min(count, 0xFFFF))

    writer.u8(len(equipped))
    for slot, item_id in equipped:
        writer.u8(slot).u16(item_id)

    return (
        writer.u16(min(max(max_health, 0), 0xFFFF))
        .u16(min(max(max_resource, 0), 0xFFFF))
        .u16(min(max(bonus_damage, 0), 0xFFFF))
        .u16(min(max(round_half_up(move_speed * SPEED_SCALE), 0), 0xFFFF))
        .build()
    )


# --- introspection ----------------------------------------------------------

MESSAGE_NAMES: dict[int, str] = {
    CLIENT_HELLO: "hello",
    CLIENT_READY: "ready",
    CLIENT_INPUT: "input",
    CLIENT_ACTION: "action",
    CLIENT_CHAT: "chat",
    CLIENT_BUILD: "build",
    CLIENT_PING: "ping",
    CLIENT_DEV_TIER: "dev_tier",
    CLIENT_COMPOSE: "compose",
    CLIENT_INVENTORY: "inventory",
    SERVER_WELCOME: "welcome",
    SERVER_SNAPSHOT: "snapshot",
    SERVER_SPAWN: "spawn",
    SERVER_DESPAWN: "despawn",
    SERVER_TOPOLOGY: "topology",
    SERVER_COMBAT: "combat",
    SERVER_CHAT: "chat",
    SERVER_TILES: "tiles",
    SERVER_PONG: "pong",
    SERVER_ERROR: "error",
    SERVER_PROGRESS: "progress",
    SERVER_INVENTORY: "inventory",
}
