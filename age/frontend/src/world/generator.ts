/**
 * The layered chunk generator, browser side.
 *
 * Mirror of `age/infrastructure/generator.py`, and the reason terrain costs nothing on
 * the wire: given the world seed from the welcome packet, the client reproduces every
 * tile the server would have sent. Only player edits are transmitted.
 *
 * That only works while this file agrees with the server exactly, so it is a deliberate
 * line-by-line translation rather than an independent implementation — including the
 * coarse field sampling, which is not just an optimisation here. Interpolating between
 * grid samples produces different tiles than evaluating per tile, so if one side sampled
 * and the other did not the terrain would differ.
 *
 * `tests/test_age_client_parity.py` compares whole generated chunks between the two.
 */

import { CHUNK_TILES, CHUNK_TILE_COUNT, HUB_RADIUS_TILES } from '../domain/constants'
import { BIOME_PROFILES, Biome, Tile, classifyBiome, type BiomeId } from '../domain/tiles'
import { chunkSeed, combine, hubChunkSeed, unitFloat } from './hashing'
import { fractal, gradientNoise, ridged, scatterValue } from './noise'

// Field frequencies, in cycles per tile. Elevation varies slowest so mountains are
// regional; moisture varies fastest so a forest can end without the altitude changing.
const ELEVATION_FREQ = 0.006
const TEMPERATURE_FREQ = 0.0035
const MOISTURE_FREQ = 0.009

// Independent seed offsets so the fields are uncorrelated.
const ELEVATION_SALT = 0x00e1e1n
const TEMPERATURE_SALT = 0x007e77n
const MOISTURE_SALT = 0x00d01fn
const ROAD_SALT = 0x00add1n
const RIVER_SALT = 0x00f10dn
const SCATTER_SALT = 0x005ca7
const POI_SALT = 0x000901

const ROAD_HALF_WIDTH = 1.6
const ROAD_VERGE = ROAD_HALF_WIDTH + 1.4
const NO_ROAD = 1e9
const ROAD_WANDER_TILES = 5.0
const ROAD_WANDER_FREQ = 0.011

const RIVER_THRESHOLD = 0.955

// Sampling strides for the continuous fields, in tiles. Must match the server: these
// change the output, not just the cost. The grid is aligned in global coordinates, so two
// neighbouring chunks interpolate between the same sample points and the seam holds.
const FIELD_STEP = 4
const RIVER_STEP = 2

export const SpaceType = { HUB: 0, EDGE: 1 } as const

export interface ChunkAddress {
  spaceType: number
  hubId?: number
  chunkX?: number
  chunkY?: number
  edgeId?: string
  segmentIndex?: number
  laneOffset?: number
  tierMin?: number
}

/** Stable string form, matching `ChunkAddress.key` on the server. */
export function chunkKey(address: ChunkAddress): string {
  if (address.spaceType === SpaceType.HUB) {
    return `hub:${address.hubId}:${address.chunkX ?? 0}:${address.chunkY ?? 0}`
  }
  return `edge:${address.edgeId}:${address.segmentIndex ?? 0}:${address.laneOffset ?? 0}:${address.tierMin ?? 0}`
}

export interface ChunkFields {
  biome: BiomeId
  elevation: number
  temperature: number
  moisture: number
}

function clamp01(value: number): number {
  if (value < 0.0) return 0.0
  if (value > 1.0) return 1.0
  return value
}

/** Bilinear read from a row-major `span * span` grid at fractional indices. */
function bilinear(grid: Float64Array, span: number, fx: number, fy: number): number {
  const x0 = Math.trunc(fx)
  const y0 = Math.trunc(fy)
  const tx = fx - x0
  const ty = fy - y0
  const base = y0 * span + x0
  const below = base + span
  const top = grid[base] + (grid[base + 1] - grid[base]) * tx
  const bottom = grid[below] + (grid[below + 1] - grid[below]) * tx
  return top + (bottom - top) * ty
}

export class WorldGenerator {
  private readonly tiles = new Map<string, Uint8Array>()
  private readonly fields = new Map<string, ChunkFields>()

  constructor(
    readonly worldSeed: bigint,
    private readonly cacheLimit = 512,
  ) {}

  // --- global coordinate mapping -----------------------------------------

  /**
   * The global tile coordinate of a chunk's top-left tile.
   *
   * For corridor chunks the global frame is `(along, across)`: edge-local, but continuous
   * across the whole corridor, which is exactly what the noise fields need to stay
   * seamless. Hub chunks are pushed into a distant region of the same frame, keyed by hub
   * id, and the offsets start at one rather than zero so hub 0 does not land on the
   * corridor's own origin and generate identical terrain.
   */
  private origin(address: ChunkAddress): readonly [number, number] {
    if (address.spaceType === SpaceType.EDGE) {
      return [(address.segmentIndex ?? 0) * CHUNK_TILES, (address.laneOffset ?? 0) * CHUNK_TILES]
    }
    const hubIndex = (address.hubId ?? 0) + 1
    return [
      hubIndex * 4096.0 + (address.chunkX ?? 0) * CHUNK_TILES,
      hubIndex * 2048.0 + (address.chunkY ?? 0) * CHUNK_TILES,
    ]
  }

  private seedFor(address: ChunkAddress): bigint {
    if (address.spaceType === SpaceType.HUB) {
      return hubChunkSeed(this.worldSeed, address.hubId ?? 0, address.chunkX ?? 0, address.chunkY ?? 0)
    }
    return chunkSeed(
      this.worldSeed,
      address.edgeId ?? '',
      address.segmentIndex ?? 0,
      address.laneOffset ?? 0,
      address.tierMin ?? 0,
    )
  }

  // --- layer 2: the continuous fields ------------------------------------

  elevationAt(gx: number, gy: number): number {
    return fractal(this.worldSeed + ELEVATION_SALT, gx, gy, 4, ELEVATION_FREQ)
  }

  private temperature(gx: number, gy: number, elevation: number): number {
    const base = fractal(this.worldSeed + TEMPERATURE_SALT, gx, gy, 3, TEMPERATURE_FREQ)
    // Altitude cools: the lapse-rate coupling that stops a desert appearing on a
    // mountain top.
    return clamp01(base - (elevation - 0.5) * 0.45)
  }

  private moisture(gx: number, gy: number, elevation: number): number {
    const base = fractal(this.worldSeed + MOISTURE_SALT, gx, gy, 4, MOISTURE_FREQ)
    // Rain shadow: high ground wrings moisture out of the air.
    return clamp01(base - Math.max(0.0, elevation - 0.62) * 0.6)
  }

  /** `[elevation, temperature, moisture]` at one point, sampled directly. */
  climateAt(gx: number, gy: number): readonly [number, number, number] {
    const elevation = this.elevationAt(gx, gy)
    return [elevation, this.temperature(gx, gy, elevation), this.moisture(gx, gy, elevation)]
  }

  biomeAt(gx: number, gy: number): BiomeId {
    const [elevation, temperature, moisture] = this.climateAt(gx, gy)
    return classifyBiome(elevation, temperature, moisture)
  }

  /**
   * How far the road has wandered from the corridor centre line.
   *
   * A function of the along-coordinate only, so every chunk the road crosses computes the
   * same centre for the same `along` and the road cannot break at a seam.
   */
  roadOffset(along: number): number {
    return gradientNoise(this.worldSeed + ROAD_SALT, along * ROAD_WANDER_FREQ, 0.0) * ROAD_WANDER_TILES
  }

  riverField(gx: number, gy: number): number {
    return ridged(this.worldSeed + RIVER_SALT, gx, gy, 3, 0.008)
  }

  // --- layer 3 and 4: assembly -------------------------------------------

  /** Tiles for a chunk. Row-major, `CHUNK_TILE_COUNT` bytes. */
  generate(address: ChunkAddress): Uint8Array {
    const key = chunkKey(address)
    const cached = this.tiles.get(key)
    if (cached !== undefined) return cached

    const tiles = this.build(address)
    if (this.tiles.size >= this.cacheLimit) {
      // Drop the oldest insertion. Map preserves insertion order, so the first key is
      // the least recently *added*, which for chunk streaming is close enough to least
      // recently used and costs nothing to track.
      const oldest = this.tiles.keys().next().value
      if (oldest !== undefined) {
        this.tiles.delete(oldest)
        this.fields.delete(oldest)
      }
    }
    this.tiles.set(key, tiles)
    return tiles
  }

  fieldsFor(address: ChunkAddress): ChunkFields {
    const key = chunkKey(address)
    const cached = this.fields.get(key)
    if (cached !== undefined) return cached

    const [ox, oy] = this.origin(address)
    const [elevation, temperature, moisture] = this.climateAt(
      ox + CHUNK_TILES * 0.5,
      oy + CHUNK_TILES * 0.5,
    )
    const computed: ChunkFields = {
      biome: classifyBiome(elevation, temperature, moisture),
      elevation,
      temperature,
      moisture,
    }
    this.fields.set(key, computed)
    return computed
  }

  invalidate(address: ChunkAddress): void {
    const key = chunkKey(address)
    this.tiles.delete(key)
    this.fields.delete(key)
  }

  private build(address: ChunkAddress): Uint8Array {
    const seed = this.seedFor(address)
    const [ox, oy] = this.origin(address)
    const isHub = address.spaceType === SpaceType.HUB
    const tiles = new Uint8Array(CHUNK_TILE_COUNT)

    const climateSpan = CHUNK_TILES / FIELD_STEP + 1
    const riverSpan = CHUNK_TILES / RIVER_STEP + 1

    // One extra row and column so bilinear interpolation has a far corner for the last
    // tile. Sample positions are global, so the chunk to the right recomputes this
    // chunk's right edge and gets the same numbers.
    const elevation = new Float64Array(climateSpan * climateSpan)
    const temperature = new Float64Array(climateSpan * climateSpan)
    const moisture = new Float64Array(climateSpan * climateSpan)
    for (let gy = 0; gy < climateSpan; gy += 1) {
      for (let gx = 0; gx < climateSpan; gx += 1) {
        const [e, t, m] = this.climateAt(ox + gx * FIELD_STEP, oy + gy * FIELD_STEP)
        const at = gy * climateSpan + gx
        elevation[at] = e
        temperature[at] = t
        moisture[at] = m
      }
    }

    const rivers = new Float64Array(riverSpan * riverSpan)
    for (let gy = 0; gy < riverSpan; gy += 1) {
      for (let gx = 0; gx < riverSpan; gx += 1) {
        rivers[gy * riverSpan + gx] = this.riverField(ox + gx * RIVER_STEP, oy + gy * RIVER_STEP)
      }
    }

    // The road wanders as a function of the along-coordinate only, so one value per
    // column serves every row.
    const roadOffsets = new Float64Array(CHUNK_TILES)
    for (let tx = 0; tx < CHUNK_TILES; tx += 1) roadOffsets[tx] = this.roadOffset(ox + tx)

    for (let ty = 0; ty < CHUNK_TILES; ty += 1) {
      const row = ty * CHUNK_TILES
      const gy = oy + ty
      const climateFy = ty / FIELD_STEP
      const riverFy = ty / RIVER_STEP

      for (let tx = 0; tx < CHUNK_TILES; tx += 1) {
        const climateFx = tx / FIELD_STEP
        const biome = classifyBiome(
          bilinear(elevation, climateSpan, climateFx, climateFy),
          bilinear(temperature, climateSpan, climateFx, climateFy),
          bilinear(moisture, climateSpan, climateFx, climateFy),
        )
        const river = bilinear(rivers, riverSpan, tx / RIVER_STEP, riverFy)

        tiles[row + tx] = isHub
          ? this.hubTile(seed, address, tx, ty, biome, river)
          : this.wildTile(seed, tx, ty, biome, river, Math.abs(gy - roadOffsets[tx]))
      }
    }

    this.coherencePass(tiles, seed)
    this.placePois(tiles, seed, address)
    return tiles
  }

  /** One corridor tile, from the already-sampled fields. */
  private wildTile(
    seed: bigint,
    tx: number,
    ty: number,
    biome: BiomeId,
    river: number,
    roadDistance: number,
  ): number {
    // The road wins over everything: it is the navigational spine.
    if (roadDistance <= ROAD_HALF_WIDTH) return Tile.DIRT_ROAD

    // Rivers cut second, but never across the road: a bridge is implied rather than
    // modelled, which keeps the corridor traversable at every seed.
    if (river > RIVER_THRESHOLD && roadDistance > ROAD_HALF_WIDTH + 1.0) return Tile.WATER

    const profile = BIOME_PROFILES[biome]

    // Verges: keep the ground clear next to the road so it stays readable.
    if (roadDistance <= ROAD_VERGE) return profile.ground

    const roll = scatterValue(seed, tx, ty, SCATTER_SALT)
    for (const [tile, cumulative] of profile.scatter) {
      if (roll < cumulative) return tile
    }
    return profile.ground
  }

  /**
   * One hub-zone tile.
   *
   * Hubs are laid out rather than grown: a paved plaza at the centre, radial streets, and
   * buildings on the blocks between them. A placeholder for hand-authored hubs, which is
   * what the Atelier exists to produce; the point is that the shape reads as a town.
   */
  private hubTile(
    seed: bigint,
    address: ChunkAddress,
    tx: number,
    ty: number,
    biome: BiomeId,
    river: number,
  ): number {
    const lx = (address.chunkX ?? 0) * CHUNK_TILES + tx
    const ly = (address.chunkY ?? 0) * CHUNK_TILES + ty
    const distance = Math.max(Math.abs(lx), Math.abs(ly))

    if (distance <= 6) return Tile.FLOOR_STONE // central plaza

    if (distance > HUB_RADIUS_TILES) {
      // Outside the zone proper, fall through to wilderness so the rim blends rather
      // than ending in a wall. No road: the corridor's spine belongs to the corridor.
      return this.wildTile(seed, tx, ty, biome, river, NO_ROAD)
    }

    // Radial street grid every twelve tiles.
    if (mod(lx, 12) === 0 || mod(ly, 12) === 0) return Tile.COBBLE_ROAD

    // Blocks: mostly buildings near the centre, thinning towards the rim.
    const blockRoll = unitFloat(combine(seed, floorDiv(lx, 12), floorDiv(ly, 12), 0x8109))
    const density = 1.0 - distance / (HUB_RADIUS_TILES + 1.0)
    if (blockRoll < density * 0.75) {
      const edgeOfBlock =
        mod(lx, 12) === 1 || mod(lx, 12) === 11 || mod(ly, 12) === 1 || mod(ly, 12) === 11
      return edgeOfBlock ? Tile.WALL_STONE : Tile.FLOOR_WOOD
    }

    const gardenRoll = scatterValue(seed, tx, ty, SCATTER_SALT)
    if (gardenRoll < 0.10) return Tile.TREE
    if (gardenRoll < 0.20) return Tile.BUSH
    return Tile.GRASS
  }

  /**
   * Give the threshold layout the adjacency sense Wave Function Collapse would have
   * provided, in one pass with no backtracking.
   *
   * Two rules: an isolated water tile is a puddle in the middle of a meadow and reads as
   * noise, so it is filled in; and hard terrain touching plain grass gets gravel between
   * them. Neither can cascade, because both read the original array and write a copy.
   * That bounded, single-pass property is what makes this affordable where real WFC is
   * not.
   */
  private coherencePass(tiles: Uint8Array, seed: bigint): void {
    const original = tiles.slice()

    // Outside the chunk, report -1 rather than guessing. That keeps the rule consistent
    // across a seam without needing the neighbour to be loaded.
    const at = (x: number, y: number): number =>
      x < 0 || y < 0 || x >= CHUNK_TILES || y >= CHUNK_TILES ? -1 : original[y * CHUNK_TILES + x]

    for (let y = 0; y < CHUNK_TILES; y += 1) {
      for (let x = 0; x < CHUNK_TILES; x += 1) {
        const index = y * CHUNK_TILES + x
        const tile = original[index]
        const neighbours = [at(x - 1, y), at(x + 1, y), at(x, y - 1), at(x, y + 1)]

        if (tile === Tile.WATER) {
          if (!neighbours.some((n) => n === Tile.WATER)) tiles[index] = Tile.GRASS
          continue
        }

        if (
          (tile === Tile.GRASS || tile === Tile.TALL_GRASS) &&
          neighbours.some((n) => n === Tile.CLIFF || n === Tile.ROCK) &&
          unitFloat(combine(seed, x, y, 0x5c17)) < 0.55
        ) {
          tiles[index] = Tile.GRAVEL
        }
      }
    }
  }

  /**
   * Layer 4: one optional point of interest per chunk, never in a hub.
   *
   * Position and kind come from the chunk seed, so a point of interest is a property of
   * the world rather than of when the chunk happened to load.
   */
  private placePois(tiles: Uint8Array, seed: bigint, address: ChunkAddress): void {
    if (address.spaceType === SpaceType.HUB) return
    if (unitFloat(combine(seed, POI_SALT, 0, 0)) > 0.34) return

    const cx = 6 + Math.trunc(unitFloat(combine(seed, POI_SALT, 1, 0)) * (CHUNK_TILES - 12))
    const cy = 6 + Math.trunc(unitFloat(combine(seed, POI_SALT, 2, 0)) * (CHUNK_TILES - 12))
    const kind = Math.trunc(unitFloat(combine(seed, POI_SALT, 3, 0)) * 3.0)

    if (kind === 0) this.stampRuin(tiles, cx, cy, seed)
    else if (kind === 1) this.stampCamp(tiles, cx, cy)
    else this.stampQuarry(tiles, cx, cy, seed)
  }

  private set(tiles: Uint8Array, x: number, y: number, tile: number): void {
    if (x >= 0 && x < CHUNK_TILES && y >= 0 && y < CHUNK_TILES) {
      tiles[y * CHUNK_TILES + x] = tile
    }
  }

  /** A broken stone rectangle: walls with gaps, flagstones inside. */
  private stampRuin(tiles: Uint8Array, cx: number, cy: number, seed: bigint): void {
    const half = 3
    for (let dy = -half; dy <= half; dy += 1) {
      for (let dx = -half; dx <= half; dx += 1) {
        if (Math.abs(dx) === half || Math.abs(dy) === half) {
          if (unitFloat(combine(seed, dx, dy, 0x8171)) < 0.65) {
            this.set(tiles, cx + dx, cy + dy, Tile.WALL_STONE)
          }
        } else {
          this.set(tiles, cx + dx, cy + dy, Tile.FLOOR_STONE)
        }
      }
    }
  }

  /** An abandoned camp: a cleared ring with a fire scar in the middle. */
  private stampCamp(tiles: Uint8Array, cx: number, cy: number): void {
    for (let dy = -2; dy <= 2; dy += 1) {
      for (let dx = -2; dx <= 2; dx += 1) {
        this.set(tiles, cx + dx, cy + dy, Tile.BARE_GROUND)
      }
    }
    this.set(tiles, cx, cy, Tile.ASH)
    this.set(tiles, cx - 2, cy - 2, Tile.FENCE)
    this.set(tiles, cx + 2, cy + 2, Tile.FENCE)
  }

  /** A rock cluster worth mining. */
  private stampQuarry(tiles: Uint8Array, cx: number, cy: number, seed: bigint): void {
    for (let dy = -2; dy <= 2; dy += 1) {
      for (let dx = -2; dx <= 2; dx += 1) {
        if (dx * dx + dy * dy > 5) continue
        const roll = unitFloat(combine(seed, dx, dy, 0x9427))
        this.set(tiles, cx + dx, cy + dy, roll < 0.7 ? Tile.ROCK : Tile.GRAVEL)
      }
    }
  }
}

/**
 * Python's `%` and `//` on negative operands, which JavaScript does not provide.
 *
 * `-5 % 12` is `-5` in JavaScript and `7` in Python, and `Math.trunc(-5 / 12)` is `0`
 * where Python's `-5 // 12` is `-1`. The hub street grid and the block hash both index on
 * negative coordinates, so using the native operators would mirror the town about its
 * own centre.
 */
function mod(value: number, divisor: number): number {
  return ((value % divisor) + divisor) % divisor
}

function floorDiv(value: number, divisor: number): number {
  return Math.floor(value / divisor)
}

export { Biome }
