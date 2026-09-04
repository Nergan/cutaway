"""Dimensional constants shared by the simulation, the codecs and the client.

Everything the wire protocol depends on lives here so that a change is visible
in one place. ``docs/protocol.md`` documents the same numbers for the client.
"""

from __future__ import annotations

from typing import Final

# --- Spatial layout --------------------------------------------------------
# Local metric coordinates only: x east, y north, z up. Latitude/longitude never
# reaches the runtime; an OSM import projects into this frame first.
CELL_SIZE_M: Final[float] = 2.0
"""Edge length of one collision/raycast cell in metres."""

TILE_CELLS: Final[int] = 128
"""Cells per tile edge. 128 * 2 m = the 256 m tile the specification asks for."""

TILE_SIZE_M: Final[float] = TILE_CELLS * CELL_SIZE_M

# --- Collision grid codes --------------------------------------------------
CELL_FREE: Final[int] = 0
CELL_BUILDING: Final[int] = 1
CELL_WATER: Final[int] = 2
CELL_BLOCKED: Final[int] = 3
CELL_ROAD: Final[int] = 4
CELL_SIDEWALK: Final[int] = 5
CELL_INTERACTIVE: Final[int] = 6

SOLID_CELLS: Final[frozenset[int]] = frozenset({CELL_BUILDING, CELL_WATER, CELL_BLOCKED})

# --- Street furniture ------------------------------------------------------
# The index travels on the wire inside every tile, so this list may only ever
# grow at the end. The client mirrors it in `frontend/src/domain/constants.ts`.
PROP_LAMP: Final[int] = 0
PROP_TREE: Final[int] = 1
PROP_KIOSK: Final[int] = 2
PROP_SIGN: Final[int] = 3
PROP_BENCH: Final[int] = 4
PROP_VENDING: Final[int] = 5
PROP_TRAFFIC_LIGHT: Final[int] = 6
PROP_BOLLARD: Final[int] = 7
PROP_PLANTER: Final[int] = 8
PROP_STALL: Final[int] = 9
PROP_BANNER: Final[int] = 10
PROP_NPC: Final[int] = 11
PROP_KIND_COUNT: Final[int] = 12
WALKABLE_CELLS: Final[frozenset[int]] = frozenset(
    {CELL_FREE, CELL_ROAD, CELL_SIDEWALK, CELL_INTERACTIVE}
)

# --- Building categories ---------------------------------------------------
CATEGORY_HOUSE: Final[int] = 0
CATEGORY_SHOP: Final[int] = 1
CATEGORY_APARTMENT: Final[int] = 2
CATEGORY_OFFICE: Final[int] = 3
CATEGORY_SKYSCRAPER: Final[int] = 4
CATEGORY_WAREHOUSE: Final[int] = 5
CATEGORY_STATION: Final[int] = 6
CATEGORY_OTHER: Final[int] = 7

CATEGORY_NAMES: Final[tuple[str, ...]] = (
    "small_house",
    "shop",
    "apartment_block",
    "office",
    "skyscraper",
    "warehouse",
    "station",
    "other",
)

# Fallback heights in metres when a source provides neither height nor levels.
# Mirrors the priority ladder in docs/osm-import.md.
CATEGORY_DEFAULT_HEIGHT_M: Final[tuple[int, ...]] = (8, 6, 18, 24, 80, 10, 12, 12)

LEVEL_HEIGHT_M: Final[float] = 3.0
MAX_BUILDING_HEIGHT_M: Final[int] = 255
"""Heights travel as one unsigned byte of metres, so this is a hard ceiling."""

ROOF_FLAT: Final[int] = 0
ROOF_GABLED: Final[int] = 1
ROOF_ANTENNA: Final[int] = 2

ROAD_STREET: Final[int] = 0
ROAD_AVENUE: Final[int] = 1
ROAD_PATH: Final[int] = 2
ROAD_PLAZA: Final[int] = 3
ROAD_TYPE_NAMES: Final[tuple[str, ...]] = ("street", "avenue", "path", "plaza")

# --- Player physics --------------------------------------------------------
PLAYER_RADIUS_M: Final[float] = 0.35
EYE_HEIGHT_M: Final[float] = 1.7
WALK_SPEED_MS: Final[float] = 3.4
RUN_SPEED_MS: Final[float] = 6.2
JUMP_SPEED_MS: Final[float] = 7.4
GRAVITY_MS2: Final[float] = 20.0
"""Together these clear about 1.35 m, which is a hop you can feel and enough
to get onto the raised decks and terraces the district is built with."""

FLOOR_STEP_M: Final[float] = 0.25
"""Quantum of ground elevation.

The height byte means two different things depending on the cell under it. On
a solid cell it is the height of the wall in metres; on a walkable one it is
how far the floor is lifted, counted in these steps. Reusing the byte is what
lets terraces, sunken parks and stairs ship without another tile layer, and a
quarter of a metre is a stair riser you can actually see."""

STEP_UP_M: Final[float] = 0.6
"""How much rise a walking player takes in their stride. Two risers. Anything
taller has to be jumped, which is what makes the raised decks worth jumping
onto."""

MAX_PITCH_RAD: Final[float] = 1.2
"""Roughly 69 degrees. Beyond that the raycaster horizon leaves the viewport."""

# --- Simulation timing -----------------------------------------------------
SIMULATION_HZ: Final[int] = 20
SNAPSHOT_HZ: Final[int] = 20
"""Snapshots ride every tick. At twelve bytes per visible entry a full fifty
player room costs roughly 12 MB per minute, well inside the orchestrator's
256 MB traffic budget for this project."""
MAX_CLIENTS: Final[int] = 50
MAX_QUEUED_INPUTS: Final[int] = 8
"""Inputs buffered per player per tick. Anything beyond this is a flood."""

# --- Interest management ---------------------------------------------------
FULL_DETAIL_RADIUS_M: Final[float] = 80.0
SIMPLIFIED_RADIUS_M: Final[float] = 150.0

# --- Chat ------------------------------------------------------------------
CHAT_MAX_LENGTH: Final[int] = 240
CHAT_RATE_LIMIT: Final[int] = 5
CHAT_RATE_WINDOW_S: Final[float] = 10.0
CHAT_PROXIMITY_RADIUS_M: Final[float] = 30.0
CHAT_HISTORY_SIZE: Final[int] = 50

# --- Wire encoding ---------------------------------------------------------
POSITION_SCALE: Final[int] = 100
"""Positions travel as unsigned centimetres, so one world axis spans 655.35 m."""

MAX_ENCODABLE_POSITION_M: Final[float] = 65535 / POSITION_SCALE

MAX_TILES_PER_AXIS: Final[int] = int(MAX_ENCODABLE_POSITION_M // TILE_SIZE_M)
"""A district may not extend past the last position the wire can name.

Configuration is clamped to this rather than trusted, because the failure mode
is silent: a player past the limit would encode to the maximum and appear
frozen against the district edge instead of where they are. Widening the world
means widening the position field, which is a protocol version.
"""

ANGLE_SCALE: Final[int] = 65536
"""Yaw travels as an unsigned fraction of a full turn."""

PITCH_SCALE: Final[int] = 100
"""Pitch travels as signed hundredths of a radian, which fits a signed byte."""

PLAYER_COLOR_COUNT: Final[int] = 12

PLAYER_AVATAR_COUNT: Final[int] = 24
"""Glyphs a player may wear as their avatar. The table itself is client-side;
the wire only carries the index, so adding a glyph is not a protocol change."""

ANIMATION_IDLE: Final[int] = 0
ANIMATION_WALK: Final[int] = 1
ANIMATION_RUN: Final[int] = 2
