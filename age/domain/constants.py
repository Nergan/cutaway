"""Tunables shared by the server and the browser client.

Every value here is mirrored in ``frontend/src/domain/constants.ts``. The two
files are compared constant-by-constant by ``tests/test_age_client_parity.py``,
so a change that only lands on one side fails in CI instead of desynchronising a
player mid-session.

Units are stated in the names: ``_TILES`` for world distance, ``_PX`` for
rendered pixels, ``_MS``/``_S`` for time, ``_HZ`` for rates. World positions are
always tile coordinates, never pixels; the renderer is the only thing that knows
about pixels.
"""

from __future__ import annotations

import math

# --- spatial units ----------------------------------------------------------

# A tile is the atomic unit of terrain: one entry in a chunk's tile array, one
# claimable/diggable cell, and one lighting sample. 32 px matches the pixel-art
# grid the Atelier bakes at.
TILE_SIZE_PX = 32

# GDD 16.2 settled on 32x32 tiles per chunk as the balance point between memory,
# save granularity, and streaming spikes for a 2D action game.
CHUNK_TILES = 32
CHUNK_TILE_COUNT = CHUNK_TILES * CHUNK_TILES
CHUNK_SIZE_PX = CHUNK_TILES * TILE_SIZE_PX

# Hub zones are 8x8 chunks per GDD 5.4, so 256 tiles on a side, centred on the
# hub origin. Generation is lazy, so the nominal size costs nothing until walked.
HUB_CHUNKS_PER_SIDE = 8
HUB_RADIUS_TILES = HUB_CHUNKS_PER_SIDE * CHUNK_TILES // 2

# --- accordion topology -----------------------------------------------------

# The MVP world is two hubs joined by one edge (Accordion Spec section 6).
CORRIDOR_SEGMENTS = 8

# Tier 0 activates the centre lane only; tier 1 adds the two flanking lanes.
MAX_TIER = 1
TIER_0_LANES = (0,)
TIER_1_LANES = (-1, 0, 1)

# Hysteresis from Accordion Spec 4.2: ten players to expand, five to contract,
# so the topology cannot oscillate around a single threshold.
EXPANSION_PLAYER_THRESHOLD = 10
CONTRACTION_PLAYER_THRESHOLD = 5

# Fifteen minutes between tier changes in production. The demo overrides this
# through AGE_TIER_COOLDOWN_SECONDS so the accordion is observable in a sitting.
TIER_COOLDOWN_SECONDS = 900
TIER_EVALUATION_INTERVAL_SECONDS = 60

# A chunk spends this long in PREPARING before it may go ACTIVE. It gives the
# client time to fade the tiles in rather than popping them into existence, and it
# is the window the server has to actually build the terrain.
CHUNK_PREPARE_SECONDS = 2.0
CHUNK_RETIRE_SECONDS = 2.0

# --- simulation cadence -----------------------------------------------------

# TDD 2.2 INV-7 mandates an explicit, documented degradation rather than a silent
# one. This slice runs the Python core at 30 Hz and says so; the network layer,
# the prediction model, and the wire format are all rate-agnostic, so a faster
# core can raise this without a protocol change.
SIMULATION_HZ = 30
TICK_SECONDS = 1.0 / SIMULATION_HZ

# Snapshots are deliberately slower than the simulation (GDD 16.10). The client
# interpolates across a two-snapshot buffer to hide the gap.
SNAPSHOT_HZ = 15
SNAPSHOT_INTERVAL_SECONDS = 1.0 / SNAPSHOT_HZ

# NPC decisions run at a third of the simulation rate; their movement still
# integrates every tick so they never look choppy (TDD 12.2).
AI_DECISION_DIVISOR = 3

INPUT_HZ = 30
INTERPOLATION_BUFFER_SNAPSHOTS = 2

HEARTBEAT_INTERVAL_SECONDS = 5.0
CONNECTION_TIMEOUT_SECONDS = 15.0

# --- movement ---------------------------------------------------------------

WALK_SPEED_TILES_S = 4.5
RUN_SPEED_TILES_S = 7.0

# Collision radius. Slightly under half a tile so a player fits through a
# one-tile gap without wedging on the corners.
PLAYER_RADIUS_TILES = 0.35

# The server rejects a client-reported position that drifts further than this
# from its own authoritative value and rubber-bands instead (TDD 15.3).
POSITION_TOLERANCE_TILES = 1.5
SPEED_HACK_FACTOR = 1.5

# --- combat -----------------------------------------------------------------

# Positions are kept for this long so a hit can be validated against where the
# target actually was when the attacker pressed the button (TDD 10.2).
LAG_COMPENSATION_WINDOW_MS = 200
POSITION_HISTORY_SECONDS = 1.0

RESPAWN_DELAY_SECONDS = 5.0
BASE_MAX_HEALTH = 100
BASE_MAX_RESOURCE = 100

# Levelling (GDD 6.4). The curve is deliberately shallow and the cap low: this slice
# needs progression to be visible within a few minutes of play, not tuned.
MAX_LEVEL = 20
#: The level at which a base class may take its second half (GDD 6.3). The first
#: level-up is the composition, so it is reachable from a handful of kills.
COMPOSE_LEVEL = 2
#: Experience for placing or harvesting one tile. Small enough that levelling by
#: landscaping is slower than levelling by fighting, large enough to be a path.
BUILD_EXPERIENCE = 3
#: What a level is worth, on top of the class multiplier applied to the base pools.
#: Flat rather than proportional so a level is worth the same to every class and the
#: gap between a tank and a mage does not widen with nothing but time played.
HEALTH_PER_LEVEL = 6
RESOURCE_PER_LEVEL = 4
RESOURCE_REGEN_PER_SECOND = 6.0
HEALTH_REGEN_PER_SECOND = 1.5

# Global minimum between two ability activations, on top of per-ability
# cooldowns. Stops a client spraying inputs faster than the game can mean it.
ABILITY_MIN_INTERVAL_MS = 150

# --- area of interest and streaming ----------------------------------------

# Radii in chunks around the player (TDD 7.6). Active chunks are simulated and
# rendered, preload is fetched in the background, beyond unload is released.
AOI_ACTIVE_RADIUS_CHUNKS = 2
AOI_PRELOAD_RADIUS_CHUNKS = 3
AOI_UNLOAD_RADIUS_CHUNKS = 4

# Entities further than this are not replicated even inside an active chunk.
AOI_VIEW_DISTANCE_TILES = 48.0

MAX_ENTITIES_PER_SNAPSHOT = 64

# --- terrain ----------------------------------------------------------------

# Regrowth ladder from GDD 9.2. An untouched, unclaimed tile climbs one stage
# per interval until it is mature forest again.
REGROWTH_STAGE_SECONDS = 60.0
TERRAIN_FLUSH_INTERVAL_SECONDS = 30.0
BUILD_RANGE_TILES = 4.0

# --- chat -------------------------------------------------------------------

CHAT_MAX_LENGTH = 240
CHAT_RATE_LIMIT = 5
CHAT_RATE_WINDOW_S = 10.0
CHAT_PROXIMITY_RADIUS_TILES = 24.0
CHAT_HISTORY_SIZE = 64

CHANNEL_LOCAL = 0
CHANNEL_GLOBAL = 1
CHANNEL_SYSTEM = 2

# --- wire encoding ----------------------------------------------------------

# Raised to 2 for the inventory packets and for the state byte added to SERVER_SPAWN.
# Earlier additions left it alone because the new packet was optional in both directions,
# so an old client simply never saw one. Neither of these is. The inventory snapshot is
# sent unprompted on join, and the spawn byte changes the length of a packet that already
# existed, which a mismatched reader does not fail on — it reads the appearance bytes one
# position out and draws a character with someone else's face.
PROTOCOL_VERSION = 2

# Positions travel as int32 in 1/64-tile steps: about 0.5 px at the native tile
# size, which is finer than a player can perceive, and covers +-33 million tiles.
POSITION_SCALE = 64
MAX_ENCODABLE_POSITION_TILES = 2147483647 / POSITION_SCALE

# Facing travels as uint16 across a full turn: ~0.005 degrees per step.
ANGLE_SCALE = 65536 / (2 * math.pi)

# Health and resource are replicated as percentages in a single byte.
PERCENT_SCALE = 255

MAX_CLIENTS = 50
MAX_QUEUED_INPUTS = 32
MAX_NAME_LENGTH = 24

# --- entity kinds -----------------------------------------------------------

ENTITY_PLAYER = 0
ENTITY_NPC = 1
ENTITY_STRUCTURE = 2
ENTITY_PROJECTILE = 3
ENTITY_PROP = 4

# --- day/night and weather -------------------------------------------------

# A full day in six minutes: long enough to feel like a cycle, short enough that
# a visitor sees dawn, noon, dusk, and night without waiting.
DAY_LENGTH_SECONDS = 360.0

WEATHER_CLEAR = 0
WEATHER_CLOUDY = 1
WEATHER_RAIN = 2
WEATHER_STORM = 3
WEATHER_FOG = 4
WEATHER_SNOW = 5

WEATHER_MIN_DURATION_SECONDS = 45.0
WEATHER_MAX_DURATION_SECONDS = 150.0

# --- rendering budget -------------------------------------------------------

# The atlas the client bakes procedurally at boot. One page holds every tile
# variant and prop frame for the slice, plus a matching normal-map page.
ATLAS_SIZE_PX = 1024
ATLAS_PADDING_PX = 2

# Cap on simultaneously animated characters before off-screen rigs freeze.
MAX_ANIMATED_CHARACTERS = 48
