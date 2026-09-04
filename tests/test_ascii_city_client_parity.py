"""Guards against the Python server and the TypeScript client drifting apart.

Two things have to stay in lockstep: the shared constants, which are literally
duplicated in two files, and the binary fixtures the Vitest suites decode. Both
are checked here so a protocol change that only lands on one side fails in CI
rather than in a player's browser.
"""

from __future__ import annotations

import base64
import json
import math
import re
from pathlib import Path

import pytest

from ascii_city.domain import constants as py_constants
from ascii_city.infrastructure import wire_codec as wire
from ascii_city.infrastructure.quantise import round_half_up
from ascii_city.tools.make_fixtures import FIXTURE_PATH, build as build_fixtures

CLIENT_ROOT = Path(__file__).resolve().parents[1] / "ascii_city" / "frontend" / "src"
CONSTANTS_TS = CLIENT_ROOT / "domain" / "constants.ts"

# Every constant the wire format or the simulation depends on. A name here must
# exist on both sides with the same value.
SHARED_CONSTANTS = (
    "CELL_SIZE_M",
    "TILE_CELLS",
    "TILE_SIZE_M",
    "CELL_FREE",
    "CELL_BUILDING",
    "CELL_WATER",
    "CELL_BLOCKED",
    "CELL_ROAD",
    "CELL_SIDEWALK",
    "CELL_INTERACTIVE",
    "CATEGORY_HOUSE",
    "CATEGORY_SHOP",
    "CATEGORY_APARTMENT",
    "CATEGORY_OFFICE",
    "CATEGORY_SKYSCRAPER",
    "CATEGORY_WAREHOUSE",
    "CATEGORY_STATION",
    "CATEGORY_OTHER",
    "ROOF_FLAT",
    "ROOF_GABLED",
    "ROOF_ANTENNA",
    "ROAD_STREET",
    "ROAD_AVENUE",
    "ROAD_PATH",
    "ROAD_PLAZA",
    "PLAYER_RADIUS_M",
    "EYE_HEIGHT_M",
    "WALK_SPEED_MS",
    "RUN_SPEED_MS",
    "JUMP_SPEED_MS",
    "GRAVITY_MS2",
    "FLOOR_STEP_M",
    "STEP_UP_M",
    "MAX_PITCH_RAD",
    "SIMULATION_HZ",
    "SNAPSHOT_HZ",
    "MAX_CLIENTS",
    "MAX_QUEUED_INPUTS",
    "FULL_DETAIL_RADIUS_M",
    "SIMPLIFIED_RADIUS_M",
    "CHAT_MAX_LENGTH",
    "CHAT_RATE_LIMIT",
    "CHAT_RATE_WINDOW_S",
    "CHAT_PROXIMITY_RADIUS_M",
    "CHAT_HISTORY_SIZE",
    "POSITION_SCALE",
    "MAX_ENCODABLE_POSITION_M",
    "MAX_TILES_PER_AXIS",
    "ANGLE_SCALE",
    "PITCH_SCALE",
    "PLAYER_COLOR_COUNT",
    "PLAYER_AVATAR_COUNT",
    "ANIMATION_IDLE",
    "ANIMATION_WALK",
    "ANIMATION_RUN",
)

_EXPORT = re.compile(r"^export const (?P<name>[A-Z][A-Z0-9_]*) = (?P<value>[^\n]+)$", re.MULTILINE)


class _Math:
    """Just enough of JavaScript's ``Math`` to fold the constant expressions."""

    floor = staticmethod(math.floor)
    ceil = staticmethod(math.ceil)
    PI = math.pi


def parse_client_constants() -> dict[str, float]:
    """Read the numeric exports out of the TypeScript mirror.

    Values are arithmetic over literals and earlier constants, which Python
    evaluates identically. Anything else (arrays, calls) simply does not parse
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


def test_the_client_mirror_exists():
    assert CONSTANTS_TS.is_file(), "The TypeScript constants mirror is missing."


@pytest.mark.parametrize("name", SHARED_CONSTANTS)
def test_shared_constants_agree(name: str, client_constants: dict[str, float]):
    assert hasattr(py_constants, name), f"{name} vanished from the Python constants."
    assert name in client_constants, f"{name} is missing from constants.ts."
    assert client_constants[name] == pytest.approx(
        float(getattr(py_constants, name))
    ), f"{name} differs between the server and the client."


def test_the_client_derives_its_tick_from_the_simulation_rate():
    values = parse_client_constants()
    assert values["TICK_SECONDS"] == pytest.approx(1 / py_constants.SIMULATION_HZ)


# --- fixture freshness ------------------------------------------------------


def test_the_committed_fixtures_are_current():
    """Regenerating must be a no-op, or the client is testing a stale protocol."""
    assert FIXTURE_PATH.is_file(), "Run `python -m ascii_city.tools.make_fixtures`."
    committed = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert committed == build_fixtures(), (
        "The protocol fixtures are stale. Re-run "
        "`python -m ascii_city.tools.make_fixtures` and commit the result."
    )


def test_every_fixture_frame_decodes_back_into_python():
    """The fixtures are only useful if the reference itself accepts them."""
    fixtures = build_fixtures()
    frames = fixtures["clientFrames"]

    command = wire.decode_client_frame(base64.b64decode(frames["input"]["encoded"]))
    assert isinstance(command, __import__(
        "ascii_city.domain.player", fromlist=["InputCommand"]
    ).InputCommand)
    assert command.sequence == frames["input"]["command"]["sequence"]
    assert command.forward == pytest.approx(1.0)
    assert command.strafe == pytest.approx(-0.5)
    assert command.sprint is True

    chat = wire.decode_client_frame(base64.b64decode(frames["chat"]["encoded"]))
    assert isinstance(chat, wire.ChatRequest)
    assert chat.text == frames["chat"]["text"]

    ping = wire.decode_client_frame(base64.b64decode(frames["ping"]["encoded"]))
    assert isinstance(ping, wire.PingRequest)
    assert ping.client_time == frames["ping"]["clientTime"]


# --- rounding ---------------------------------------------------------------


@pytest.mark.parametrize(
    "value, expected",
    [
        (0.5, 1),
        (1.5, 2),
        (2.5, 3),
        (-0.5, 0),
        (-1.5, -1),
        (0.4999, 0),
        (0.0, 0),
        (7.0, 7),
    ],
)
def test_rounding_matches_javascript_math_round(value: float, expected: int):
    """These are the exact values `Math.round` produces, halves included."""
    assert round_half_up(value) == expected


def test_python_builtin_rounding_would_have_disagreed():
    """Documents why the codecs do not simply call round()."""
    assert round(0.5) == 0 and round_half_up(0.5) == 1
    assert round(2.5) == 2 and round_half_up(2.5) == 3


def test_half_centimetre_positions_encode_the_way_the_client_encodes_them():
    assert wire.encode_position(0.005) == 1
    assert wire.encode_position(0.015) == 2


def test_pitch_and_yaw_halves_round_the_same_way_too():
    assert wire.encode_pitch(0.005) == 1
    assert wire.encode_yaw(math.tau / 131072) == 1
