/**
 * Tiles, biomes, and the regrowth ladder.
 *
 * Mirror of `age/domain/tiles.py`. Tile ids are small integers because a chunk is a flat
 * `Uint8Array` here and a `bytearray` on the server. The renderer never switches on the
 * id: it looks the tile up in the atlas built from the Atelier recipes, so adding a tile
 * is a data change rather than a code change.
 */

/**
 * Terrain tile kinds.
 *
 * Ordering is deliberate: values below `WATER` are walkable, so a single comparison
 * answers the collision question on the hot path.
 */
export const Tile = {
  BARE_GROUND: 0,
  GRASS: 1,
  TALL_GRASS: 2,
  BUSH: 3,
  SAPLING: 4,
  SAND: 5,
  GRAVEL: 6,
  DIRT_ROAD: 7,
  COBBLE_ROAD: 8,
  FLOOR_WOOD: 9,
  FLOOR_STONE: 10,
  SNOW: 11,
  ASH: 12,

  // Everything from here on blocks movement.
  WATER: 13,
  DEEP_WATER: 14,
  TREE: 15,
  DEAD_TREE: 16,
  ROCK: 17,
  CLIFF: 18,
  WALL_WOOD: 19,
  WALL_STONE: 20,
  FENCE: 21,
  CACTUS: 22,
} as const

export type TileId = (typeof Tile)[keyof typeof Tile]

export const FIRST_BLOCKING_TILE = Tile.WATER

/** True when an entity may occupy this tile. */
export function isWalkable(tile: number): boolean {
  return tile < FIRST_BLOCKING_TILE
}

/**
 * True when the tile stops a line-of-sight raycast.
 *
 * Water is transparent even though it blocks movement, so archers can shoot across a
 * river that nobody can walk over.
 */
export function blocksSight(tile: number): boolean {
  return tile >= Tile.TREE
}

export const Biome = {
  MEADOW: 0,
  FOREST: 1,
  DEEP_FOREST: 2,
  WETLAND: 3,
  HEATH: 4,
  DESERT: 5,
  HIGHLAND: 6,
  ASHLAND: 7,
} as const

export type BiomeId = (typeof Biome)[keyof typeof Biome]

export interface BiomeProfile {
  biome: BiomeId
  name: string
  ground: number
  /** `[tile, cumulativeProbability]` pairs, consumed in order against one hash. */
  scatter: ReadonlyArray<readonly [number, number]>
  weather: ReadonlyArray<readonly [number, number]>
  ambientTint: readonly [number, number, number]
  danger: number
}

const CLEAR = 0
const CLOUDY = 1
const RAIN = 2
const STORM = 3
const FOG = 4
const SNOW = 5

export const BIOME_PROFILES: Record<number, BiomeProfile> = {
  [Biome.MEADOW]: {
    biome: Biome.MEADOW,
    name: 'meadow',
    ground: Tile.GRASS,
    scatter: [[Tile.TALL_GRASS, 0.18], [Tile.BUSH, 0.24], [Tile.TREE, 0.28], [Tile.ROCK, 0.30]],
    weather: [[CLEAR, 0.55], [CLOUDY, 0.80], [RAIN, 0.95], [FOG, 1.0]],
    ambientTint: [255, 246, 224],
    danger: 0,
  },
  [Biome.FOREST]: {
    biome: Biome.FOREST,
    name: 'forest',
    ground: Tile.GRASS,
    scatter: [[Tile.TREE, 0.20], [Tile.BUSH, 0.30], [Tile.TALL_GRASS, 0.38], [Tile.ROCK, 0.42]],
    weather: [[CLEAR, 0.35], [CLOUDY, 0.65], [RAIN, 0.90], [FOG, 1.0]],
    ambientTint: [226, 240, 214],
    danger: 1,
  },
  [Biome.DEEP_FOREST]: {
    biome: Biome.DEEP_FOREST,
    name: 'deep forest',
    ground: Tile.GRASS,
    scatter: [[Tile.TREE, 0.38], [Tile.BUSH, 0.48], [Tile.DEAD_TREE, 0.52], [Tile.ROCK, 0.56]],
    weather: [[CLOUDY, 0.30], [RAIN, 0.60], [FOG, 0.85], [STORM, 1.0]],
    ambientTint: [196, 216, 198],
    danger: 3,
  },
  [Biome.WETLAND]: {
    biome: Biome.WETLAND,
    name: 'wetland',
    ground: Tile.GRASS,
    scatter: [[Tile.WATER, 0.22], [Tile.TALL_GRASS, 0.40], [Tile.BUSH, 0.46], [Tile.DEAD_TREE, 0.50]],
    weather: [[FOG, 0.35], [RAIN, 0.70], [CLOUDY, 0.90], [STORM, 1.0]],
    ambientTint: [206, 226, 226],
    danger: 2,
  },
  [Biome.HEATH]: {
    biome: Biome.HEATH,
    name: 'heath',
    ground: Tile.GRAVEL,
    scatter: [[Tile.BUSH, 0.14], [Tile.ROCK, 0.22], [Tile.TALL_GRASS, 0.30], [Tile.DEAD_TREE, 0.32]],
    weather: [[CLEAR, 0.40], [CLOUDY, 0.70], [RAIN, 0.88], [STORM, 1.0]],
    ambientTint: [238, 232, 214],
    danger: 2,
  },
  [Biome.DESERT]: {
    biome: Biome.DESERT,
    name: 'desert',
    ground: Tile.SAND,
    scatter: [[Tile.ROCK, 0.15], [Tile.CACTUS, 0.25], [Tile.WATER, 0.28], [Tile.GRAVEL, 0.34]],
    weather: [[CLEAR, 0.82], [CLOUDY, 0.96], [STORM, 1.0]],
    ambientTint: [255, 238, 198],
    danger: 2,
  },
  [Biome.HIGHLAND]: {
    biome: Biome.HIGHLAND,
    name: 'highland',
    ground: Tile.GRAVEL,
    scatter: [[Tile.ROCK, 0.20], [Tile.CLIFF, 0.30], [Tile.SNOW, 0.40], [Tile.DEAD_TREE, 0.43]],
    weather: [[SNOW, 0.35], [CLOUDY, 0.65], [FOG, 0.85], [STORM, 1.0]],
    ambientTint: [224, 234, 246],
    danger: 3,
  },
  [Biome.ASHLAND]: {
    biome: Biome.ASHLAND,
    name: 'ashland',
    ground: Tile.ASH,
    scatter: [[Tile.ROCK, 0.18], [Tile.DEAD_TREE, 0.28], [Tile.CLIFF, 0.33]],
    weather: [[CLOUDY, 0.40], [FOG, 0.70], [STORM, 1.0]],
    ambientTint: [226, 210, 206],
    danger: 4,
  },
}

/**
 * Assign a biome from three normalised noise fields.
 *
 * Ordering matters: elevation gates first because altitude dominates climate, then the
 * temperature and moisture pair distinguishes the mid-altitude biomes. All three inputs
 * are in `[0, 1]`.
 */
export function classifyBiome(elevation: number, temperature: number, moisture: number): BiomeId {
  if (elevation > 0.82) return Biome.HIGHLAND
  if (elevation < 0.28) return moisture > 0.45 ? Biome.WETLAND : Biome.HEATH
  if (temperature > 0.70 && moisture < 0.32) return Biome.DESERT
  if (temperature > 0.78 && moisture < 0.18) return Biome.ASHLAND
  if (moisture > 0.62) return elevation > 0.5 ? Biome.DEEP_FOREST : Biome.WETLAND
  if (moisture > 0.40) return Biome.FOREST
  return Biome.MEADOW
}

// --- regrowth ---------------------------------------------------------------

export const REGROWTH_LADDER: Record<number, number> = {
  [Tile.BARE_GROUND]: Tile.GRASS,
  [Tile.GRASS]: Tile.TALL_GRASS,
  [Tile.TALL_GRASS]: Tile.BUSH,
  [Tile.BUSH]: Tile.SAPLING,
  [Tile.SAPLING]: Tile.TREE,
}

/** Tiles a player may dig or clear, and what they leave behind. */
export const HARVEST_RESULTS: Record<number, readonly [number, string, number]> = {
  [Tile.TREE]: [Tile.BARE_GROUND, 'wood', 4],
  [Tile.DEAD_TREE]: [Tile.BARE_GROUND, 'wood', 2],
  [Tile.SAPLING]: [Tile.BARE_GROUND, 'wood', 1],
  [Tile.BUSH]: [Tile.BARE_GROUND, 'fibre', 2],
  [Tile.TALL_GRASS]: [Tile.GRASS, 'fibre', 1],
  [Tile.GRASS]: [Tile.BARE_GROUND, 'soil', 1],
  [Tile.ROCK]: [Tile.GRAVEL, 'stone', 3],
  [Tile.CLIFF]: [Tile.GRAVEL, 'stone', 5],
  [Tile.CACTUS]: [Tile.SAND, 'fibre', 2],
}

/** What a material places, and how much of it one tile costs. */
export const BUILD_RECIPES: Record<string, readonly [number, number]> = {
  wood: [Tile.WALL_WOOD, 2],
  stone: [Tile.WALL_STONE, 3],
  soil: [Tile.BARE_GROUND, 1],
  fibre: [Tile.FENCE, 2],
  plank: [Tile.FLOOR_WOOD, 1],
  flagstone: [Tile.FLOOR_STONE, 1],
}

/**
 * Structures are removable; natural terrain is not, so a player cannot delete a cliff to
 * shortcut through it.
 */
export const PLAYER_PLACED_TILES: ReadonlySet<number> = new Set([
  Tile.WALL_WOOD,
  Tile.WALL_STONE,
  Tile.FENCE,
  Tile.FLOOR_WOOD,
  Tile.FLOOR_STONE,
  Tile.DIRT_ROAD,
  Tile.COBBLE_ROAD,
])
