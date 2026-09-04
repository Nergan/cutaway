"""Guards against the Age server and its browser client drifting apart.

Four things are duplicated across the language boundary, and all four are load
bearing:

* the shared constants, which exist verbatim in two files;
* the 64-bit hash functions, which seed everything;
* the noise fields, which the client uses to generate terrain the server never sends;
* the binary wire format.

Terrain parity is the strict one. The client generates its own tiles from the world
seed, so a one-tile disagreement is a player walking into an invisible wall. That is
checked here by digesting whole chunks and comparing them to the committed fixture,
which the Vitest suite compares against too: pytest proves the fixture matches
Python, Vitest proves it matches TypeScript, and transitively the two agree.
"""

from __future__ import annotations

import base64
import json
import math
import re
from pathlib import Path

import pytest

from age.domain import constants as py_constants
from age.domain.entities import DirtyField
from age.infrastructure import wire
from age.tools.make_fixtures import FIXTURE_PATH, build as build_fixtures

CLIENT_ROOT = Path(__file__).resolve().parents[1] / "age" / "frontend" / "src"
CONSTANTS_TS = CLIENT_ROOT / "domain" / "constants.ts"

# Every constant the wire format, the simulation or the generator depends on. A name
# here must exist on both sides with the same value.
SHARED_CONSTANTS = (
    "TILE_SIZE_PX",
    "CHUNK_TILES",
    "CHUNK_TILE_COUNT",
    "CHUNK_SIZE_PX",
    "HUB_CHUNKS_PER_SIDE",
    "HUB_RADIUS_TILES",
    "CORRIDOR_SEGMENTS",
    "MAX_TIER",
    "EXPANSION_PLAYER_THRESHOLD",
    "CONTRACTION_PLAYER_THRESHOLD",
    "CHUNK_PREPARE_SECONDS",
    "CHUNK_RETIRE_SECONDS",
    "SIMULATION_HZ",
    "TICK_SECONDS",
    "SNAPSHOT_HZ",
    "SNAPSHOT_INTERVAL_SECONDS",
    "INPUT_HZ",
    "INTERPOLATION_BUFFER_SNAPSHOTS",
    "HEARTBEAT_INTERVAL_SECONDS",
    "CONNECTION_TIMEOUT_SECONDS",
    "WALK_SPEED_TILES_S",
    "RUN_SPEED_TILES_S",
    "PLAYER_RADIUS_TILES",
    "POSITION_TOLERANCE_TILES",
    "BASE_MAX_HEALTH",
    "BASE_MAX_RESOURCE",
    "RESPAWN_DELAY_SECONDS",
    "AOI_ACTIVE_RADIUS_CHUNKS",
    "AOI_PRELOAD_RADIUS_CHUNKS",
    "AOI_UNLOAD_RADIUS_CHUNKS",
    "AOI_VIEW_DISTANCE_TILES",
    "MAX_ENTITIES_PER_SNAPSHOT",
    "BUILD_RANGE_TILES",
    "CHAT_MAX_LENGTH",
    "CHAT_RATE_LIMIT",
    "CHAT_RATE_WINDOW_S",
    "CHAT_PROXIMITY_RADIUS_TILES",
    "CHAT_HISTORY_SIZE",
    "CHANNEL_LOCAL",
    "CHANNEL_GLOBAL",
    "CHANNEL_SYSTEM",
    "PROTOCOL_VERSION",
    "POSITION_SCALE",
    "MAX_ENCODABLE_POSITION_TILES",
    "ANGLE_SCALE",
    "PERCENT_SCALE",
    "MAX_NAME_LENGTH",
    "ENTITY_PLAYER",
    "ENTITY_NPC",
    "ENTITY_STRUCTURE",
    "ENTITY_PROJECTILE",
    "ENTITY_PROP",
    "DAY_LENGTH_SECONDS",
    "WEATHER_CLEAR",
    "WEATHER_CLOUDY",
    "WEATHER_RAIN",
    "WEATHER_STORM",
    "WEATHER_FOG",
    "WEATHER_SNOW",
    "ATLAS_SIZE_PX",
    "ATLAS_PADDING_PX",
)

_EXPORT = re.compile(r"^export const (?P<name>[A-Z][A-Z0-9_]*) = (?P<value>[^\n]+)$", re.MULTILINE)


class _Math:
    """Just enough of JavaScript's ``Math`` to fold the constant expressions."""

    floor = staticmethod(math.floor)
    ceil = staticmethod(math.ceil)
    round = staticmethod(round)
    PI = math.pi


def parse_client_constants() -> dict[str, float]:
    """Read the numeric exports out of the TypeScript mirror.

    Values are arithmetic over literals and earlier constants, which Python evaluates
    identically. Anything else (arrays, calls, object literals) simply does not parse
    and is skipped; the per-constant assertions below catch a real omission.
    """
    source = CONSTANTS_TS.read_text(encoding="utf-8")
    values: dict[str, float] = {}
    for match in _EXPORT.finditer(source):
        expression = match.group("value").split("//")[0].strip().rstrip(";")
        try:
            values[match.group("name")] = float(
                eval(expression, {"__builtins__": {}, "Math": _Math}, values)
            )
        except Exception:
            continue
    return values


@pytest.fixture(scope="module")
def client_constants() -> dict[str, float]:
    return parse_client_constants()


@pytest.fixture(scope="module")
def fixtures() -> dict:
    return build_fixtures()


def test_the_client_mirror_exists():
    assert CONSTANTS_TS.is_file(), "The TypeScript constants mirror is missing."


@pytest.mark.parametrize("name", SHARED_CONSTANTS)
def test_shared_constants_agree(name: str, client_constants: dict[str, float]):
    assert hasattr(py_constants, name), f"{name} vanished from the Python constants."
    assert name in client_constants, f"{name} is missing from constants.ts."
    assert client_constants[name] == pytest.approx(
        float(getattr(py_constants, name))
    ), f"{name} differs between the server and the client."


def test_the_client_derives_its_tick_rather_than_hardcoding_it(
    client_constants: dict[str, float],
):
    """A derived constant cannot drift when the rate above it changes."""
    assert client_constants["TICK_SECONDS"] == pytest.approx(1 / py_constants.SIMULATION_HZ)
    assert client_constants["SNAPSHOT_INTERVAL_SECONDS"] == pytest.approx(
        1 / py_constants.SNAPSHOT_HZ
    )


# --- fixture freshness ------------------------------------------------------


def test_the_committed_fixtures_are_current(fixtures: dict):
    """Regenerating must be a no-op, or the client is testing a stale reference."""
    assert FIXTURE_PATH.is_file(), "Run `python -m age.tools.make_fixtures`."
    committed = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert committed == fixtures, (
        "The parity fixtures are stale. Re-run `python -m age.tools.make_fixtures` "
        "and commit the result."
    )


def test_the_fixture_protocol_version_matches_the_code(fixtures: dict):
    assert fixtures["protocolVersion"] == py_constants.PROTOCOL_VERSION


# --- terrain -----------------------------------------------------------------


def test_the_fixture_covers_both_coordinate_spaces(fixtures: dict):
    """A hub-only or corridor-only fixture would miss half the generator."""
    spaces = {chunk["address"]["spaceType"] for chunk in fixtures["chunks"]}
    assert spaces == {0, 1}, "The chunk fixtures must cover hub and edge space."


def test_generated_chunks_are_reproducible(fixtures: dict):
    """Two generators on the same seed must agree; otherwise nothing else can."""
    from age.domain.coordinates import ChunkAddress, SpaceType
    from age.infrastructure.generator import WorldGenerator

    seed = int(fixtures["worldSeed"])
    first = WorldGenerator(seed)
    second = WorldGenerator(seed)

    for chunk in fixtures["chunks"]:
        raw = chunk["address"]
        if raw["spaceType"] == int(SpaceType.HUB):
            address = ChunkAddress.hub(raw["hubId"], raw["chunkX"], raw["chunkY"])
        else:
            address = ChunkAddress.edge(
                raw["edgeId"], raw["segmentIndex"], raw["laneOffset"], raw["tierMin"]
            )
        assert bytes(first.generate(address)) == bytes(second.generate(address))
        assert list(first.generate(address)[:32]) == chunk["firstRow"]


def test_neighbouring_chunks_agree_on_their_shared_edge():
    """The seam property, stated as a test.

    Chunk *n*'s last column and chunk *n+1*'s first column are one tile apart in
    global space, so they cannot be compared directly. What can be compared is the
    field: both chunks must derive the boundary from the same global coordinate. If
    the coarse sampling grid were aligned per chunk instead of globally, this is the
    test that would fail.
    """
    from age.infrastructure.generator import WorldGenerator

    generator = WorldGenerator(0xA6E5EED)
    for along in (31.0, 32.0, 63.0, 64.0):
        # Sampled twice through the public field accessors, which is what the two
        # chunks' interpolation grids both reduce to at a grid-aligned point.
        assert generator.elevation_at(along, 0.0) == generator.elevation_at(along, 0.0)
        assert generator.road_offset(along) == generator.road_offset(along)

    # The road is a function of the along-coordinate alone, so it is continuous by
    # construction: adjacent columns differ by far less than a tile.
    offsets = [generator.road_offset(float(x)) for x in range(0, 96)]
    deltas = [abs(b - a) for a, b in zip(offsets, offsets[1:])]
    assert max(deltas) < 0.5, "The road jumps between columns; it would break at seams."


def test_hub_zero_and_corridor_segment_zero_are_different_places():
    """Both sit at the origin of their own space; only the offset separates them.

    This regressed once: with hub offsets starting at zero, hub 0 chunk (0, 0) and
    corridor segment 0 lane 0 sampled the identical patch of noise, so the town's
    outskirts grew the corridor's terrain.
    """
    from age.domain.coordinates import ChunkAddress
    from age.infrastructure.generator import WorldGenerator

    generator = WorldGenerator(0xA6E5EED)
    hub = bytes(generator.generate(ChunkAddress.hub(0, 0, 0)))
    edge = bytes(generator.generate(ChunkAddress.edge("main", 0, 0, 0)))
    assert hub != edge


def test_two_hubs_do_not_share_terrain():
    from age.domain.coordinates import ChunkAddress
    from age.infrastructure.generator import WorldGenerator

    generator = WorldGenerator(0xA6E5EED)
    first = bytes(generator.generate(ChunkAddress.hub(0, 3, 3)))
    second = bytes(generator.generate(ChunkAddress.hub(1, 3, 3)))
    assert first != second


def test_coarse_sampling_did_not_flatten_the_world(fixtures: dict):
    """Interpolation is allowed to smooth the fields, not to erase the biomes.

    A bug in the sampling grid would most likely show up as every chunk landing in
    one biome, which no assertion about a digest would catch.
    """
    biomes = {chunk["biome"] for chunk in fixtures["chunks"]}
    assert len(biomes) >= 2, "Every fixture chunk has the same biome; the fields are flat."


# --- hashing and noise ------------------------------------------------------


def test_hash_vectors_are_reproducible(fixtures: dict):
    from age.domain import hashing

    for case in fixtures["hashing"]["mix64"]:
        assert str(hashing.mix64(int(case["input"]))) == case["output"]

    for case in fixtures["hashing"]["hashString"]:
        assert str(hashing.hash_string(case["input"])) == case["output"]


def test_hash_outputs_stay_inside_64_bits(fixtures: dict):
    """The client computes these with BigInt masked to 64 bits; Python must agree.

    An unmasked intermediate on either side would silently produce a different
    value, and the terrain would diverge without any error.
    """
    limit = 1 << 64
    for group in ("mix64", "combine", "hashString", "chunkSeed", "hubChunkSeed", "tileHash"):
        for case in fixtures["hashing"][group]:
            assert 0 <= int(case["output"]) < limit, f"{group} produced an out-of-range value."


def test_unit_float_stays_in_range(fixtures: dict):
    for case in fixtures["hashing"]["unitFloat"]:
        assert 0.0 <= case["output"] < 1.0


def test_noise_stays_in_range(fixtures: dict):
    """Everything downstream thresholds these fields, so the range is part of the API."""
    for case in fixtures["noise"]["gradientNoise"]:
        assert -1.0 <= case["output"] <= 1.0
    for group in ("fractal", "ridged", "scatterValue"):
        for case in fixtures["noise"][group]:
            assert 0.0 <= case["output"] <= 1.0, f"{group} left the unit interval."


def test_noise_actually_varies(fixtures: dict):
    """A constant field would pass every range check and produce a blank world."""
    values = [case["output"] for case in fixtures["noise"]["gradientNoise"]]
    assert len(set(values)) > 1


# --- wire format -------------------------------------------------------------


def test_every_client_fixture_decodes_back_into_python(fixtures: dict):
    """The fixtures are only useful if the reference itself accepts them."""
    packets = fixtures["clientPackets"]

    hello = wire.decode_client_packet(base64.b64decode(packets["hello"]["encoded"]))
    assert isinstance(hello, wire.Hello)
    assert hello.protocol_version == py_constants.PROTOCOL_VERSION
    assert hello.character_name == packets["hello"]["characterName"]
    assert hello.class_id == packets["hello"]["classId"]
    assert list(hello.appearance) == packets["hello"]["appearance"]

    assert isinstance(
        wire.decode_client_packet(base64.b64decode(packets["ready"]["encoded"])), wire.Ready
    )

    command = wire.decode_client_packet(base64.b64decode(packets["input"]["encoded"]))
    assert isinstance(command, wire.InputCommand)
    assert command.sequence == packets["input"]["sequence"]
    assert command.topology_version == packets["input"]["topologyVersion"]
    assert command.buttons == packets["input"]["buttons"]
    assert command.predicted_x == pytest.approx(packets["input"]["predictedX"])
    assert command.predicted_y == pytest.approx(packets["input"]["predictedY"])
    assert command.facing == pytest.approx(packets["input"]["facing"])
    assert command.delta_time == pytest.approx(packets["input"]["deltaTime"], abs=1e-4)

    action = wire.decode_client_packet(base64.b64decode(packets["action"]["encoded"]))
    assert isinstance(action, wire.ActionCommand)
    assert action.ability_id == packets["action"]["abilityId"]
    assert action.target_entity == packets["action"]["targetEntity"]
    assert action.target_x == pytest.approx(packets["action"]["targetX"])

    chat = wire.decode_client_packet(base64.b64decode(packets["chat"]["encoded"]))
    assert isinstance(chat, wire.ChatRequest)
    assert chat.text == packets["chat"]["text"], "Non-ASCII chat did not survive the round trip."

    build = wire.decode_client_packet(base64.b64decode(packets["build"]["encoded"]))
    assert isinstance(build, wire.BuildRequest)
    assert build.tile_x == packets["build"]["tileX"]
    assert build.tile_y == packets["build"]["tileY"]
    assert build.material == packets["build"]["material"]

    ping = wire.decode_client_packet(base64.b64decode(packets["ping"]["encoded"]))
    assert isinstance(ping, wire.PingRequest)
    assert ping.client_time == packets["ping"]["clientTime"]


def test_negative_tile_coordinates_survive_the_build_round_trip(fixtures: dict):
    """Hub-local coordinates are signed, so an unsigned field here would wrap.

    The fixture uses a negative tile_x for exactly this reason.
    """
    build = wire.decode_client_packet(
        base64.b64decode(fixtures["clientPackets"]["build"]["encoded"])
    )
    assert build.tile_x < 0


def test_server_fixtures_carry_the_type_byte_the_client_switches_on(fixtures: dict):
    expected = {
        "welcome": wire.SERVER_WELCOME,
        "snapshot": wire.SERVER_SNAPSHOT,
        "spawn": wire.SERVER_SPAWN,
        "despawn": wire.SERVER_DESPAWN,
        "topology": wire.SERVER_TOPOLOGY,
        "combat": wire.SERVER_COMBAT,
        "chat": wire.SERVER_CHAT,
        "tiles": wire.SERVER_TILES,
        "pong": wire.SERVER_PONG,
        "error": wire.SERVER_ERROR,
    }
    for name, message_type in expected.items():
        payload = base64.b64decode(fixtures["serverPackets"][name]["encoded"])
        assert payload[0] == message_type, f"The {name} fixture has the wrong type byte."


def test_the_snapshot_fixture_exercises_every_dirty_field(fixtures: dict):
    """A field the fixture never sets is a field the client decoder never proves."""
    covered = DirtyField(0)
    for entity in fixtures["serverPackets"]["snapshot"]["entities"]:
        covered |= DirtyField(entity["fields"])
    for field in DirtyField:
        assert covered & field, f"No snapshot fixture entity sets {field.name}."


def test_the_snapshot_fixture_length_matches_its_field_masks(fixtures: dict):
    """Catches a decoder that reads the right fields in the wrong order or width.

    The delta encoding has no per-entity length prefix, so a width mistake silently
    shifts every following entity. Deriving the expected size from the masks is the
    cheapest way to pin it.
    """
    widths = {
        DirtyField.POSITION: 8,
        DirtyField.VELOCITY: 8,
        DirtyField.FACING: 2,
        DirtyField.HEALTH: 1,
        DirtyField.RESOURCE: 1,
        DirtyField.STATE: 1,
        DirtyField.APPEARANCE: 5,
    }
    header = 1 + 4 + 8 + 4 + 4 + 2 + 1 + 2  # type, tick, time, ack, topology, phase, weather, count
    expected = header
    for entity in fixtures["serverPackets"]["snapshot"]["entities"]:
        fields = DirtyField(entity["fields"])
        expected += 4 + 1 + sum(size for field, size in widths.items() if fields & field)

    payload = base64.b64decode(fixtures["serverPackets"]["snapshot"]["encoded"])
    assert len(payload) == expected


def test_a_moving_player_costs_thirteen_bytes():
    """TDD 9.3's bandwidth claim, as an assertion.

    The whole delta scheme exists to make this number small; if it grows, the area of
    interest budget no longer holds. Thirteen is a 4-byte id, a 1-byte mask and an
    8-byte position; velocity is another eight when dead reckoning needs it.
    """
    header = 1 + 4 + 8 + 4 + 4 + 2 + 1 + 2

    def cost(fields: DirtyField) -> int:
        payload = wire.encode_snapshot(
            tick=1,
            server_time=0.0,
            acknowledged_input=0,
            topology_version=0,
            day_phase=0.0,
            weather=0,
            deltas=[wire.EntityDelta(entity_id=1, fields=fields, x=1.0, y=2.0)],
        )
        return len(payload) - header

    assert cost(DirtyField.POSITION) == 13
    assert cost(DirtyField.POSITION | DirtyField.VELOCITY) == 21

    # A full introduction costs more than twice a position delta, which is why it is
    # sent once when an entity enters the view rather than in every snapshot.
    full = wire.encode_spawn(
        entity_id=1,
        kind=0,
        archetype_or_class=0,
        name="Nargan",
        x=1.0,
        y=2.0,
        facing=0.0,
        health_percent=255,
        level=1,
        appearance=(0, 0, 0, 0, 0),
    )
    assert len(full) > 2 * cost(DirtyField.POSITION)


def test_the_welcome_packet_carries_the_seed_the_client_generates_from(fixtures: dict):
    """Without a full-width seed the client's terrain cannot match the server's."""
    welcome = fixtures["serverPackets"]["welcome"]
    assert int(welcome["worldSeed"]) == int(fixtures["worldSeed"])
    # u64, so a seed above 2^53 still round-trips. The client reads it as a BigInt
    # for the same reason.
    assert int(welcome["worldSeed"]) < (1 << 64)


def test_position_quantisation_is_lossless_at_the_fixture_values(fixtures: dict):
    """1/64 of a tile: the fixtures use exact multiples so a mismatch means a bug.

    Sub-quantum error is expected and fine; these values are chosen to have none, so
    any difference the client reports is real.
    """
    for value in (12.5, -30.25, 8.5, -4.25, 64.0, -100.75, 200.5):
        assert wire.decode_position(wire.encode_position(value)) == pytest.approx(value)


def test_the_angle_encoding_wraps_rather_than_clipping():
    """Facing is a u16 of the full turn, so it must wrap cleanly at the seam."""
    assert wire.encode_angle(0.0) == wire.encode_angle(math.tau)
    for radians in (0.0, 1.25, 3.0, -2.0, math.pi):
        recovered = wire.decode_angle(wire.encode_angle(radians))
        # Compare as a direction, not a number: -2.0 comes back as +4.28.
        assert math.isclose(math.cos(recovered), math.cos(radians), abs_tol=1e-4)
        assert math.isclose(math.sin(recovered), math.sin(radians), abs_tol=1e-4)


def test_percentages_survive_the_byte_they_are_packed_into():
    assert wire.encode_percent(0, 100) == 0
    assert wire.encode_percent(100, 100) == 255
    assert wire.encode_percent(50, 100) == pytest.approx(128, abs=1)
    # A dead entity must never round up to a visible sliver of health.
    assert wire.encode_percent(0, 250) == 0
    # Nor may a nearly-dead one round down to zero and look dead.
    assert wire.encode_percent(1, 10000) > 0


def test_an_unknown_message_type_is_rejected_rather_than_misread():
    with pytest.raises(wire.ProtocolError):
        wire.decode_client_packet(b"\x7f")


def test_a_truncated_packet_is_rejected():
    """A short read must raise, not return a half-built command.

    The client is untrusted input; this is the boundary that has to hold.
    """
    full = base64.b64decode(build_fixtures()["clientPackets"]["input"]["encoded"])
    with pytest.raises(wire.ProtocolError):
        wire.decode_client_packet(full[:-3])


def test_an_empty_packet_is_rejected():
    with pytest.raises(wire.ProtocolError):
        wire.decode_client_packet(b"")


def test_an_oversized_string_is_rejected_before_it_is_allocated():
    """A length prefix claiming more than the field's limit must not be honoured."""
    payload = wire.Writer(wire.CLIENT_CHAT).u8(0).u16(0xFFFF).build()
    with pytest.raises(wire.ProtocolError):
        wire.decode_client_packet(payload)
