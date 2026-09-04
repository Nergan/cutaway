/**
 * Tunables shared by the browser client and the server.
 *
 * This is the mirror of `age/domain/constants.py`, and `tests/test_age_client_parity.py`
 * compares the two constant by constant. A value changed on one side only fails in CI
 * rather than desynchronising a player mid-session.
 *
 * The names carry the units: `_TILES` for world distance, `_PX` for rendered pixels,
 * `_MS`/`_S` for time, `_HZ` for rates. World positions are always tile coordinates;
 * the renderer is the only thing that knows about pixels.
 */

// --- spatial units ----------------------------------------------------------

export const TILE_SIZE_PX = 32
export const CHUNK_TILES = 32
export const CHUNK_TILE_COUNT = CHUNK_TILES * CHUNK_TILES
export const CHUNK_SIZE_PX = CHUNK_TILES * TILE_SIZE_PX

export const HUB_CHUNKS_PER_SIDE = 8
export const HUB_RADIUS_TILES = Math.floor((HUB_CHUNKS_PER_SIDE * CHUNK_TILES) / 2)

// --- accordion topology -----------------------------------------------------

export const CORRIDOR_SEGMENTS = 8

export const MAX_TIER = 1
export const TIER_0_LANES = [0] as const
export const TIER_1_LANES = [-1, 0, 1] as const

export const EXPANSION_PLAYER_THRESHOLD = 10
export const CONTRACTION_PLAYER_THRESHOLD = 5

export const TIER_COOLDOWN_SECONDS = 900
export const TIER_EVALUATION_INTERVAL_SECONDS = 60

export const CHUNK_PREPARE_SECONDS = 2.0
export const CHUNK_RETIRE_SECONDS = 2.0

// --- simulation cadence -----------------------------------------------------

export const SIMULATION_HZ = 30
export const TICK_SECONDS = 1.0 / SIMULATION_HZ

export const SNAPSHOT_HZ = 15
export const SNAPSHOT_INTERVAL_SECONDS = 1.0 / SNAPSHOT_HZ

export const AI_DECISION_DIVISOR = 3

export const INPUT_HZ = 30
export const INTERPOLATION_BUFFER_SNAPSHOTS = 2

export const HEARTBEAT_INTERVAL_SECONDS = 5.0
export const CONNECTION_TIMEOUT_SECONDS = 15.0

// --- movement ---------------------------------------------------------------

export const WALK_SPEED_TILES_S = 4.5
export const RUN_SPEED_TILES_S = 7.0

export const PLAYER_RADIUS_TILES = 0.35

export const POSITION_TOLERANCE_TILES = 1.5
export const SPEED_HACK_FACTOR = 1.5

// --- combat -----------------------------------------------------------------

export const LAG_COMPENSATION_WINDOW_MS = 200
export const POSITION_HISTORY_SECONDS = 1.0

export const RESPAWN_DELAY_SECONDS = 5.0
export const BASE_MAX_HEALTH = 100
export const BASE_MAX_RESOURCE = 100
export const RESOURCE_REGEN_PER_SECOND = 6.0
export const HEALTH_REGEN_PER_SECOND = 1.5

export const ABILITY_MIN_INTERVAL_MS = 150

// --- area of interest and streaming ----------------------------------------

export const AOI_ACTIVE_RADIUS_CHUNKS = 2
export const AOI_PRELOAD_RADIUS_CHUNKS = 3
export const AOI_UNLOAD_RADIUS_CHUNKS = 4

export const AOI_VIEW_DISTANCE_TILES = 48.0

export const MAX_ENTITIES_PER_SNAPSHOT = 64

// --- terrain ----------------------------------------------------------------

export const REGROWTH_STAGE_SECONDS = 60.0
export const TERRAIN_FLUSH_INTERVAL_SECONDS = 30.0
export const BUILD_RANGE_TILES = 4.0

// --- chat -------------------------------------------------------------------

export const CHAT_MAX_LENGTH = 240
export const CHAT_RATE_LIMIT = 5
export const CHAT_RATE_WINDOW_S = 10.0
export const CHAT_PROXIMITY_RADIUS_TILES = 24.0
export const CHAT_HISTORY_SIZE = 64

export const CHANNEL_LOCAL = 0
export const CHANNEL_GLOBAL = 1
export const CHANNEL_SYSTEM = 2

// --- wire encoding ----------------------------------------------------------

export const PROTOCOL_VERSION = 1

export const POSITION_SCALE = 64
export const MAX_ENCODABLE_POSITION_TILES = 2147483647 / POSITION_SCALE

export const ANGLE_SCALE = 65536 / (2 * Math.PI)

export const PERCENT_SCALE = 255

export const MAX_CLIENTS = 50
export const MAX_QUEUED_INPUTS = 32
export const MAX_NAME_LENGTH = 24

// --- entity kinds -----------------------------------------------------------

export const ENTITY_PLAYER = 0
export const ENTITY_NPC = 1
export const ENTITY_STRUCTURE = 2
export const ENTITY_PROJECTILE = 3
export const ENTITY_PROP = 4

// --- day/night and weather -------------------------------------------------

export const DAY_LENGTH_SECONDS = 360.0

export const WEATHER_CLEAR = 0
export const WEATHER_CLOUDY = 1
export const WEATHER_RAIN = 2
export const WEATHER_STORM = 3
export const WEATHER_FOG = 4
export const WEATHER_SNOW = 5

export const WEATHER_MIN_DURATION_SECONDS = 45.0
export const WEATHER_MAX_DURATION_SECONDS = 150.0

// --- rendering budget -------------------------------------------------------

export const ATLAS_SIZE_PX = 1024
export const ATLAS_PADDING_PX = 2

export const MAX_ANIMATED_CHARACTERS = 48
