/**
 * Hand-placeable dressing: the fountain, market stalls, benches, lanterns, crates.
 *
 * These have no tile of their own and no gameplay effect — you cannot be blocked by a
 * lantern — so unlike terrain they are pure presentation and are derived on the client
 * alone. That is a deliberate line: anything the simulation can be wrong about has to be
 * mirrored and parity-tested, and anything it cannot does not.
 *
 * The long-term source of these is the Atelier's location editor, which authors placements
 * per chunk and stores them alongside the terrain overlay. Until there is authored content,
 * the hub's dressing is laid out here.
 *
 * The layout is a designed table rather than a rule evaluated per tile, and that is the
 * lesson of the first version. That one placed a campfire at the centre, four lanterns at
 * the plaza corners, and a lantern at every street crossing, all from modulo arithmetic — a
 * hundred-odd tiles of paving with seven objects on it. The result was technically a lit
 * town and read as an empty field with lamp posts in it. A square looks inhabited because of
 * what people put on it, and the arrangement of those things is a composition, which is not
 * something modulo arithmetic produces.
 */

import { CHUNK_TILES, HUB_RADIUS_TILES } from '../domain/constants'
import { chunkKey, SpaceType, type ChunkAddress } from '../world/generator'

export interface Placement {
  /** A key in the atlas: one of the Atelier's decor recipes. */
  key: string
  /** World tile coordinates of the sprite's base. */
  x: number
  y: number
  /** Whether this placement emits light after dark. */
  light: 'lantern' | 'campfire' | undefined
}

/** Matches the hub street spacing in `hubTile`. */
const STREET_SPACING = 12

/** Matches the paved plaza in `hubTile`: hub-local `max(|x|, |y|) <= 6`. */
const PLAZA_HALF = 6

/** How often a lantern stands along a street. Twelve left long dark stretches between them. */
const LANTERN_SPACING = 6

/**
 * One piece of dressing at a fixed hub-local position.
 *
 * Hub-local coordinates have the plaza centre at the origin, so these read as a plan of the
 * square: negative `y` is north of the fountain, negative `x` is west of it.
 */
interface Fixture {
  key: string
  localX: number
  localY: number
  light?: 'lantern' | 'campfire'
}

/**
 * The plaza itself.
 *
 * The fountain is the focal point, so everything else is arranged with respect to it: benches
 * on the diagonals facing in, planters softening the four straight approaches, banners at the
 * mouths of the streets, and lanterns at the corners where the paving ends. Nothing sits on
 * the axes through the centre except the banners, because the four street mouths are where
 * players walk in and blocking a sightline to the fountain wastes it.
 */
const PLAZA: readonly Fixture[] = [
  { key: 'fountain', localX: 0, localY: 0 },

  { key: 'bench', localX: -4, localY: -3 },
  { key: 'bench', localX: 4, localY: -3 },
  { key: 'bench', localX: -4, localY: 3 },
  { key: 'bench', localX: 4, localY: 3 },

  { key: 'planter', localX: -2, localY: -5 },
  { key: 'planter', localX: 2, localY: -5 },
  { key: 'planter', localX: -2, localY: 5 },
  { key: 'planter', localX: 2, localY: 5 },
  { key: 'planter', localX: -5, localY: -1 },
  { key: 'planter', localX: -5, localY: 1 },
  { key: 'planter', localX: 5, localY: -1 },
  { key: 'planter', localX: 5, localY: 1 },

  { key: 'lantern', localX: -5, localY: -5, light: 'lantern' },
  { key: 'lantern', localX: 5, localY: -5, light: 'lantern' },
  { key: 'lantern', localX: -5, localY: 5, light: 'lantern' },
  { key: 'lantern', localX: 5, localY: 5, light: 'lantern' },

  { key: 'banner', localX: -1, localY: -6 },
  { key: 'banner', localX: 1, localY: -6 },
  { key: 'banner', localX: -1, localY: 6 },
  { key: 'banner', localX: 1, localY: 6 },
]

/**
 * The market, on the block between the plaza and the first street north of it.
 *
 * Stalls stand back from the street with their stock spilling out in front, which is the
 * arrangement that reads as trade: a row of stalls flush against the kerb reads as a fence.
 * The gaps between them are uneven on purpose — evenly spaced stalls read as a colonnade.
 */
const MARKET: readonly Fixture[] = [
  { key: 'market_stall', localX: -8, localY: -9 },
  { key: 'market_stall', localX: -3, localY: -9 },
  { key: 'market_stall', localX: 3, localY: -9 },
  { key: 'market_stall', localX: 9, localY: -9 },

  { key: 'crate', localX: -9, localY: -7 },
  { key: 'sacks', localX: -7, localY: -7 },
  { key: 'barrel', localX: -2, localY: -7 },
  { key: 'crate', localX: 4, localY: -7 },
  { key: 'barrel', localX: 8, localY: -7 },
  { key: 'sacks', localX: 10, localY: -7 },

  { key: 'sign', localX: -5, localY: -8 },
  { key: 'sign', localX: 6, localY: -8 },
]

/**
 * The yard south of the plaza: a well, a fire to stand around, and stores.
 *
 * The campfire lives here rather than on the plaza, where the first version put it. A fire in
 * the middle of a formal paved square is a camp, not a town; moved to the working yard behind
 * it, the same sprite reads as a place where people boil things.
 */
const YARD: readonly Fixture[] = [
  { key: 'well', localX: -9, localY: 9 },
  { key: 'campfire', localX: 8, localY: 8, light: 'campfire' },
  { key: 'bench', localX: 6, localY: 9 },
  { key: 'bench', localX: 10, localY: 9 },
  { key: 'barrel', localX: -7, localY: 8 },
  { key: 'crate', localX: -6, localY: 10 },
  { key: 'planter', localX: 0, localY: 9 },
  { key: 'planter', localX: -2, localY: 10 },
  { key: 'planter', localX: 2, localY: 10 },
]

const FIXTURES: readonly Fixture[] = [...PLAZA, ...MARKET, ...YARD]

/**
 * Decor for one chunk.
 *
 * Takes the chunk's origin in world tiles so the caller, which already computed it to place
 * the terrain mesh, does not pay for it twice.
 */
export function decorFor(
  address: ChunkAddress,
  originTileX: number,
  originTileY: number,
): Placement[] {
  if (address.spaceType !== SpaceType.HUB) return []

  const placements: Placement[] = []
  const chunkX = address.chunkX ?? 0
  const chunkY = address.chunkY ?? 0

  // Hub-local tile range this chunk covers. The hub's own origin is its centre, so these run
  // negative on two sides, which is why the modulo below has to be floor-based.
  const localX0 = chunkX * CHUNK_TILES
  const localY0 = chunkY * CHUNK_TILES
  const localX1 = localX0 + CHUNK_TILES
  const localY1 = localY0 + CHUNK_TILES

  // The fixed set first. Filtered by the chunk's own range rather than walked per tile: there
  // are a few dozen fixtures and a thousand tiles in a chunk.
  for (const fixture of FIXTURES) {
    if (fixture.localX < localX0 || fixture.localX >= localX1) continue
    if (fixture.localY < localY0 || fixture.localY >= localY1) continue
    placements.push({
      key: fixture.key,
      // Half a tile across so the sprite is centred in its cell, and a whole tile down so its
      // base sits on the cell's bottom edge, which is where the depth sort expects it.
      x: originTileX + (fixture.localX - localX0) + 0.5,
      y: originTileY + (fixture.localY - localY0) + 1,
      light: fixture.light,
    })
  }

  // Then street lighting, which does want a rule: the grid is generated, so the lamps on it
  // have to be too, and a hand-placed lamp every six tiles over a 256-tile town is not a
  // composition anyone would author.
  for (let ty = 0; ty < CHUNK_TILES; ty += 1) {
    const localY = localY0 + ty
    for (let tx = 0; tx < CHUNK_TILES; tx += 1) {
      const localX = localX0 + tx

      const distance = Math.max(Math.abs(localX), Math.abs(localY))
      // The plaza is dressed by hand above, and outside the zone is wilderness.
      if (distance <= PLAZA_HALF || distance > HUB_RADIUS_TILES) continue

      const onStreetX = mod(localX, STREET_SPACING) === 0
      const onStreetY = mod(localY, STREET_SPACING) === 0
      // A crossing satisfies both axes, so it would otherwise get two lanterns in one cell.
      const lit = onStreetX
        ? mod(localY, LANTERN_SPACING) === 0
        : onStreetY && mod(localX, LANTERN_SPACING) === 0
      if (!lit) continue

      placements.push({
        key: 'lantern',
        x: originTileX + tx + 0.5,
        y: originTileY + ty + 1,
        light: 'lantern',
      })
    }
  }

  return placements
}

/** Floor-based modulo, so a negative hub coordinate lands on the same grid as a positive one. */
function mod(value: number, by: number): number {
  return ((value % by) + by) % by
}

/**
 * Memoises {@link decorFor} per chunk.
 *
 * Deriving placements walks a thousand tiles, and the renderer asks for every visible chunk
 * every frame. The results never change for a given chunk, so this is the whole optimisation:
 * a map from chunk key to a list that is usually empty.
 */
export class DecorCache {
  private readonly byChunk = new Map<string, Placement[]>()

  forChunk(address: ChunkAddress, originTileX: number, originTileY: number): readonly Placement[] {
    const key = chunkKey(address)
    let found = this.byChunk.get(key)
    if (found === undefined) {
      found = decorFor(address, originTileX, originTileY)
      // Bounded the same way the chunk store is: a very long walk should not accumulate a
      // placement list for every chunk ever seen. Cleared wholesale rather than evicted by
      // recency, because rebuilding one entry is a millisecond and tracking recency is not
      // free.
      if (this.byChunk.size > 512) this.byChunk.clear()
      this.byChunk.set(key, found)
    }
    return found
  }

  clear(): void {
    this.byChunk.clear()
  }
}
