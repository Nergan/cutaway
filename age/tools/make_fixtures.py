"""Freeze the cross-language fixtures the client tests itself against.

The Python side is the reference implementation for three things the client has to
reproduce exactly: the hash functions, the noise fields, and the wire format. This
script records what the reference produces so the Vitest suites can compare, and so
pytest can re-derive the same file and fail if it has gone stale.

Whole chunks are recorded as digests rather than tile arrays. A 32x32 chunk is a
kilobyte and there are eight of them here; the digest catches any single-tile
disagreement just as well and keeps the fixture file readable in a diff.

Run from the repository root after touching hashing, noise, the generator or the
protocol::

    python -m age.tools.make_fixtures
"""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

from ..domain import hashing
from ..domain.coordinates import ChunkAddress
from ..domain.entities import DirtyField
from ..infrastructure import noise, wire
from ..infrastructure.generator import WorldGenerator

FIXTURE_PATH = (
    Path(__file__).resolve().parents[1] / "frontend" / "src" / "__fixtures__" / "parity.json"
)

# An arbitrary but fixed seed. Any value works; it only has to be the same on both
# sides, and a recognisable one makes a failing diff easier to read.
WORLD_SEED = 0x00A6E_5EED


def _b64(payload: bytes) -> str:
    return base64.b64encode(payload).decode("ascii")


def _digest(tiles: bytes | bytearray) -> str:
    return hashlib.sha256(bytes(tiles)).hexdigest()[:32]


def _hashing_vectors() -> dict[str, object]:
    """Hash outputs as decimal strings, because they exceed JavaScript's safe range.

    The client parses them with ``BigInt``, which is also what it computes with, so
    the comparison is exact rather than approximate.
    """
    return {
        "mix64": [
            {"input": str(value), "output": str(hashing.mix64(value))}
            for value in (0, 1, 2, 0xDEADBEEF, WORLD_SEED, (1 << 64) - 1)
        ],
        "combine": [
            {"args": [str(seed), a, b, c], "output": str(hashing.combine(seed, a, b, c))}
            for seed, a, b, c in (
                (WORLD_SEED, 0, 0, 0),
                (WORLD_SEED, 1, 0, 0),
                (WORLD_SEED, -1, -1, 0),
                (WORLD_SEED, 31, 31, 0x5CA7),
                (0, -2048, 4096, 7),
            )
        ],
        "hashString": [
            {"input": text, "output": str(hashing.hash_string(text))}
            for text in ("", "a", "main", "hub-a:hub-b", "\u041c\u0438\u0440")
        ],
        "chunkSeed": [
            {
                "args": [str(WORLD_SEED), edge, segment, lane, tier],
                "output": str(hashing.chunk_seed(WORLD_SEED, edge, segment, lane, tier)),
            }
            for edge, segment, lane, tier in (
                ("main", 0, 0, 0),
                ("main", 3, -1, 2),
                ("main", 12, 2, 4),
            )
        ],
        "hubChunkSeed": [
            {
                "args": [str(WORLD_SEED), hub, cx, cy],
                "output": str(hashing.hub_chunk_seed(WORLD_SEED, hub, cx, cy)),
            }
            for hub, cx, cy in ((0, 0, 0), (0, -1, 2), (1, 3, -3))
        ],
        "unitFloat": [
            {"input": str(value), "output": hashing.unit_float(value)}
            for value in (0, 1, 1 << 32, (1 << 64) - 1, hashing.mix64(WORLD_SEED))
        ],
        "tileHash": [
            {
                "args": [str(WORLD_SEED), x, y, salt],
                "output": str(hashing.tile_hash(WORLD_SEED, x, y, salt)),
            }
            for x, y, salt in ((0, 0, 0), (17, -5, 0x5CA7), (-31, 31, 0x901))
        ],
    }


def _noise_vectors() -> dict[str, object]:
    """Float outputs, compared with a tight tolerance rather than for equality.

    Both sides use IEEE-754 doubles and the same operation order, so agreement is
    exact in practice, but the tests allow 1e-12 so a harmless difference in how a
    literal is folded cannot fail the build.
    """
    points = ((0.0, 0.0), (1.5, -2.25), (137.0, 42.0), (-1024.5, 2048.75), (0.375, 0.625))
    return {
        "gradientNoise": [
            {"seed": str(WORLD_SEED), "x": x, "y": y, "output": noise.gradient_noise(WORLD_SEED, x, y)}
            for x, y in points
        ],
        "fractal": [
            {
                "seed": str(WORLD_SEED),
                "x": x,
                "y": y,
                "octaves": octaves,
                "frequency": frequency,
                "output": noise.fractal(WORLD_SEED, x, y, octaves=octaves, frequency=frequency),
            }
            for (x, y), octaves, frequency in (
                ((0.0, 0.0), 4, 0.006),
                ((137.0, 42.0), 3, 0.0035),
                ((-1024.5, 2048.75), 4, 0.009),
            )
        ],
        "ridged": [
            {
                "seed": str(WORLD_SEED),
                "x": x,
                "y": y,
                "octaves": 3,
                "frequency": 0.008,
                "output": noise.ridged(WORLD_SEED, x, y, octaves=3, frequency=0.008),
            }
            for x, y in points
        ],
        "scatterValue": [
            {
                "seed": str(WORLD_SEED),
                "x": int(x),
                "y": int(y),
                "salt": 0x5CA7,
                "output": noise.scatter_value(WORLD_SEED, int(x), int(y), 0x5CA7),
            }
            for x, y in points
        ],
    }


def _chunk_addresses() -> list[ChunkAddress]:
    """A spread wide enough to exercise every branch of the generator.

    Corridor chunks on and off the road, negative lanes, the hub centre, a hub chunk
    that straddles the rim into the wilderness fallback, and a second hub to prove
    the two do not share terrain.
    """
    return [
        ChunkAddress.edge("main", 0, 0, 0),
        ChunkAddress.edge("main", 1, 0, 0),
        ChunkAddress.edge("main", 4, -1, 2),
        ChunkAddress.edge("main", 7, 2, 4),
        ChunkAddress.hub(0, 0, 0),
        ChunkAddress.hub(0, 1, 0),
        ChunkAddress.hub(0, 3, 3),
        ChunkAddress.hub(1, 0, 0),
    ]


def _chunk_vectors() -> list[dict[str, object]]:
    generator = WorldGenerator(WORLD_SEED)
    out: list[dict[str, object]] = []
    for address in _chunk_addresses():
        tiles = generator.generate(address)
        fields = generator.fields_of(address)
        out.append(
            {
                "key": address.key,
                "address": {
                    "spaceType": int(address.space_type),
                    "hubId": address.hub_id,
                    "chunkX": address.chunk_x,
                    "chunkY": address.chunk_y,
                    "edgeId": address.edge_id,
                    "segmentIndex": address.segment_index,
                    "laneOffset": address.lane_offset,
                    "tierMin": address.tier_min,
                },
                "digest": _digest(tiles),
                # A readable slice, so a failure says which tiles differ instead of
                # only that a hash did not match.
                "firstRow": list(tiles[:32]),
                "centreRow": list(tiles[16 * 32 : 17 * 32]),
                "biome": int(fields.biome),
                "elevation": fields.elevation,
                "temperature": fields.temperature,
                "moisture": fields.moisture,
            }
        )
    return out


def _client_packets() -> dict[str, object]:
    """Client frames encoded by the client and decoded here, in the tests."""
    hello = (
        wire.Writer(wire.CLIENT_HELLO)
        .u16(wire.PROTOCOL_VERSION)
        .text("Nargan", 64)
        .u8(3)
        .u8(1)
        .u8(2)
        .u8(3)
        .u8(4)
        .u8(5)
        .build()
    )
    input_frame = (
        wire.Writer(wire.CLIENT_INPUT)
        .u32(1234)
        .u32(7)
        .u8(wire.INPUT_UP | wire.INPUT_RIGHT | wire.INPUT_RUN)
        .u16(wire.encode_angle(1.25))
        .i32(wire.encode_position(12.5))
        .i32(wire.encode_position(-30.25))
        .u16(333)
        .build()
    )
    action = (
        wire.Writer(wire.CLIENT_ACTION)
        .u32(88)
        .u32(7)
        .u16(42)
        .i32(wire.encode_position(64.0))
        .i32(wire.encode_position(-8.5))
        .u32(4096)
        .build()
    )
    chat = wire.Writer(wire.CLIENT_CHAT).u8(1).text("\u041f\u0440\u0438\u0432\u0435\u0442", 512).build()
    build = (
        wire.Writer(wire.CLIENT_BUILD)
        .u32(7)
        .u8(wire.BUILD_PLACE)
        .i32(-12)
        .i32(48)
        .text("stone", 32)
        .build()
    )
    ping = wire.Writer(wire.CLIENT_PING).f64(1234.5).build()

    return {
        "hello": {
            "encoded": _b64(hello),
            "protocolVersion": wire.PROTOCOL_VERSION,
            "characterName": "Nargan",
            "classId": 3,
            "appearance": [1, 2, 3, 4, 5],
        },
        "ready": {"encoded": _b64(wire.Writer(wire.CLIENT_READY).build())},
        "input": {
            "encoded": _b64(input_frame),
            "sequence": 1234,
            "topologyVersion": 7,
            "buttons": wire.INPUT_UP | wire.INPUT_RIGHT | wire.INPUT_RUN,
            "facing": wire.decode_angle(wire.encode_angle(1.25)),
            "predictedX": 12.5,
            "predictedY": -30.25,
            "deltaTime": 0.0333,
        },
        "action": {
            "encoded": _b64(action),
            "sequence": 88,
            "abilityId": 42,
            "targetX": 64.0,
            "targetY": -8.5,
            "targetEntity": 4096,
        },
        "chat": {"encoded": _b64(chat), "channel": 1, "text": "\u041f\u0440\u0438\u0432\u0435\u0442"},
        "build": {
            "encoded": _b64(build),
            "action": wire.BUILD_PLACE,
            "tileX": -12,
            "tileY": 48,
            "material": "stone",
        },
        "ping": {"encoded": _b64(ping), "clientTime": 1234.5},
    }


def _server_packets() -> dict[str, object]:
    """Server frames encoded here and decoded by the client, in Vitest."""
    welcome = wire.encode_welcome(
        entity_id=17,
        world_seed=WORLD_SEED,
        topology_version=3,
        current_tier=2,
        edge_id="main",
        spawn_x=8.5,
        spawn_y=-4.25,
        server_time=1000.5,
    )

    moving = wire.EntityDelta(
        entity_id=17,
        fields=DirtyField.POSITION | DirtyField.VELOCITY | DirtyField.FACING,
        x=12.5,
        y=-30.25,
        vx=3.0,
        vy=-1.5,
        facing=1.25,
    )
    hurt = wire.EntityDelta(
        entity_id=64,
        fields=DirtyField.POSITION | DirtyField.HEALTH | DirtyField.STATE,
        x=-100.75,
        y=200.5,
        health_percent=61,
        state=2,
    )
    dressed = wire.EntityDelta(
        entity_id=99,
        fields=DirtyField.APPEARANCE | DirtyField.RESOURCE,
        resource_percent=40,
        appearance=(1, 2, 3, 4, 5),
    )
    snapshot = wire.encode_snapshot(
        tick=4242,
        server_time=1010.25,
        acknowledged_input=1234,
        topology_version=3,
        day_phase=0.25,
        weather=2,
        deltas=[moving, hurt, dressed],
    )

    spawn = wire.encode_spawn(
        entity_id=64,
        kind=1,
        archetype_or_class=5,
        name="Wolf",
        x=-100.75,
        y=200.5,
        facing=-2.0,
        health_percent=100,
        level=7,
        appearance=(9, 8, 7, 6, 5),
    )

    topology = wire.encode_topology(
        topology_version=4,
        current_tier=3,
        active_chunks=["edge:main:0:1:3", "edge:main:1:1:3"],
        retiring_chunks=["edge:main:8:0:0"],
    )

    combat = wire.encode_combat(
        attacker_id=17,
        target_id=64,
        ability_id=42,
        damage=37,
        healing=0,
        killed=False,
        x=-100.75,
        y=200.5,
    )

    return {
        "welcome": {
            "encoded": _b64(welcome),
            "protocolVersion": wire.PROTOCOL_VERSION,
            "entityId": 17,
            "worldSeed": str(WORLD_SEED),
            "topologyVersion": 3,
            "currentTier": 2,
            "edgeId": "main",
            "spawnX": 8.5,
            "spawnY": -4.25,
            "serverTime": 1000.5,
        },
        "snapshot": {
            "encoded": _b64(snapshot),
            "tick": 4242,
            "serverTime": 1010.25,
            "acknowledgedInput": 1234,
            "topologyVersion": 3,
            "dayPhase": 0.25,
            "weather": 2,
            "entities": [
                {
                    "entityId": 17,
                    "fields": int(moving.fields),
                    "x": 12.5,
                    "y": -30.25,
                    "vx": 3.0,
                    "vy": -1.5,
                    "facing": wire.decode_angle(wire.encode_angle(1.25)),
                },
                {
                    "entityId": 64,
                    "fields": int(hurt.fields),
                    "x": -100.75,
                    "y": 200.5,
                    "healthPercent": 61,
                    "state": 2,
                },
                {
                    "entityId": 99,
                    "fields": int(dressed.fields),
                    "resourcePercent": 40,
                    "appearance": [1, 2, 3, 4, 5],
                },
            ],
        },
        "spawn": {
            "encoded": _b64(spawn),
            "entityId": 64,
            "kind": 1,
            "archetype": 5,
            "name": "Wolf",
            "x": -100.75,
            "y": 200.5,
            "facing": wire.decode_angle(wire.encode_angle(-2.0)),
            "healthPercent": 100,
            "level": 7,
            "appearance": [9, 8, 7, 6, 5],
        },
        "despawn": {"encoded": _b64(wire.encode_despawn(64, wire.DESPAWN_DIED)), "entityId": 64},
        "topology": {
            "encoded": _b64(topology),
            "topologyVersion": 4,
            "currentTier": 3,
            "activeChunks": ["edge:main:0:1:3", "edge:main:1:1:3"],
            "retiringChunks": ["edge:main:8:0:0"],
        },
        "combat": {
            "encoded": _b64(combat),
            "attackerId": 17,
            "targetId": 64,
            "abilityId": 42,
            "damage": 37,
            "healing": 0,
            "killed": False,
        },
        "chat": {
            "encoded": _b64(
                wire.encode_chat(sender_id=17, channel=1, sender_name="Nargan", text="hello")
            ),
            "senderId": 17,
            "channel": 1,
            "senderName": "Nargan",
            "text": "hello",
        },
        "tiles": {
            "encoded": _b64(wire.encode_tiles("edge:main:0:0:0", {5: 19, 300: 7, 1023: 0})),
            "chunkKey": "edge:main:0:0:0",
            "changes": [[5, 19], [300, 7], [1023, 0]],
        },
        "pong": {"encoded": _b64(wire.encode_pong(1234.5, 1240.75)), "clientTime": 1234.5, "serverTime": 1240.75},
        "error": {
            "encoded": _b64(wire.encode_error(wire.ERROR_VERSION_MISMATCH, "old client")),
            "code": wire.ERROR_VERSION_MISMATCH,
            "detail": "old client",
        },
    }


def build() -> dict[str, object]:
    """The whole fixture document. Pure, so pytest can compare it to the file."""
    return {
        "note": "Generated by `python -m age.tools.make_fixtures`. Do not edit by hand.",
        "protocolVersion": wire.PROTOCOL_VERSION,
        "worldSeed": str(WORLD_SEED),
        "hashing": _hashing_vectors(),
        "noise": _noise_vectors(),
        "chunks": _chunk_vectors(),
        "clientPackets": _client_packets(),
        "serverPackets": _server_packets(),
    }


def main() -> None:
    FIXTURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE_PATH.write_text(json.dumps(build(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {FIXTURE_PATH.relative_to(Path.cwd())}")


if __name__ == "__main__":
    main()
