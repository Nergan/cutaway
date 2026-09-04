/**
 * Mirror of `ascii_city/domain/constants.py`.
 *
 * These numbers are baked into the wire format, so the two files have to agree
 * exactly. `tests/test_ascii_city_client_parity.py` fails the build if they
 * drift apart.
 */

// --- Spatial layout --------------------------------------------------------
export const CELL_SIZE_M = 2.0
export const TILE_CELLS = 128
export const TILE_SIZE_M = TILE_CELLS * CELL_SIZE_M

// --- Collision grid codes --------------------------------------------------
export const CELL_FREE = 0
export const CELL_BUILDING = 1
export const CELL_WATER = 2
export const CELL_BLOCKED = 3
export const CELL_ROAD = 4
export const CELL_SIDEWALK = 5
export const CELL_INTERACTIVE = 6

export function isSolidCode(code: number): boolean {
  return code === CELL_BUILDING || code === CELL_WATER || code === CELL_BLOCKED
}

// --- Building categories ---------------------------------------------------
export const CATEGORY_HOUSE = 0
export const CATEGORY_SHOP = 1
export const CATEGORY_APARTMENT = 2
export const CATEGORY_OFFICE = 3
export const CATEGORY_SKYSCRAPER = 4
export const CATEGORY_WAREHOUSE = 5
export const CATEGORY_STATION = 6
export const CATEGORY_OTHER = 7

export const CATEGORY_NAMES = [
  'small_house',
  'shop',
  'apartment_block',
  'office',
  'skyscraper',
  'warehouse',
  'station',
  'other',
] as const

export const ROOF_FLAT = 0
export const ROOF_GABLED = 1
export const ROOF_ANTENNA = 2

export const ROAD_STREET = 0
export const ROAD_AVENUE = 1
export const ROAD_PATH = 2
export const ROAD_PLAZA = 3

// --- Player physics --------------------------------------------------------
export const PLAYER_RADIUS_M = 0.35
export const EYE_HEIGHT_M = 1.7
export const WALK_SPEED_MS = 3.4
export const RUN_SPEED_MS = 6.2
export const JUMP_SPEED_MS = 5.6
export const GRAVITY_MS2 = 22.0
export const MAX_PITCH_RAD = 1.2

// --- Simulation timing -----------------------------------------------------
export const SIMULATION_HZ = 20
export const SNAPSHOT_HZ = 20
export const TICK_SECONDS = 1 / SIMULATION_HZ
export const MAX_CLIENTS = 50
export const MAX_QUEUED_INPUTS = 8

// --- Interest management ---------------------------------------------------
export const FULL_DETAIL_RADIUS_M = 80.0
export const SIMPLIFIED_RADIUS_M = 150.0

// --- Chat ------------------------------------------------------------------
export const CHAT_MAX_LENGTH = 240
export const CHAT_RATE_LIMIT = 5
export const CHAT_RATE_WINDOW_S = 10.0
export const CHAT_PROXIMITY_RADIUS_M = 30.0
export const CHAT_HISTORY_SIZE = 50

// --- Wire encoding ---------------------------------------------------------
export const POSITION_SCALE = 100
export const MAX_ENCODABLE_POSITION_M = 65535 / POSITION_SCALE

/** A district may not extend past the last position the wire can name. */
export const MAX_TILES_PER_AXIS = Math.floor(MAX_ENCODABLE_POSITION_M / TILE_SIZE_M)
export const ANGLE_SCALE = 65536
export const PITCH_SCALE = 100
export const PLAYER_COLOR_COUNT = 12
export const PLAYER_AVATAR_COUNT = 24

export const ANIMATION_IDLE = 0
export const ANIMATION_WALK = 1
export const ANIMATION_RUN = 2

export const TAU = Math.PI * 2

/** Pull the three packed fields out of a style byte. */
export function unpackStyle(byte: number): {
  category: number
  facade: number
  window: number
} {
  return {
    category: byte & 0b111,
    facade: (byte >> 3) & 0b111,
    window: (byte >> 6) & 0b11,
  }
}
