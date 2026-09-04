/**
 * Hand-placeable dressing: lanterns, campfires, banners, crates.
 *
 * These have no tile of their own and no gameplay effect — you cannot be blocked by a lantern
 * — so unlike terrain they are pure presentation and are derived on the client alone. That is
 * a deliberate line: anything the simulation can be wrong about has to be mirrored and
 * parity-tested, and anything it cannot does not.
 *
 * The long-term source of these is the Atelier's location editor, which authors placements per
 * chunk and stores them alongside the terrain overlay. Until there is authored content, hubs
 * get lanterns at their street corners from the same grid the hub layout uses, which is enough
 * to make a town at night look like a town at night.
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

/** Matches the hub street spacing in `hubTile`. Lanterns go where the streets cross. */
const STREET_SPACING = 12

/** The plaza half-width. Inside it, lanterns ring the square rather than sitting on the grid. */
const PLAZA_HALF = 6

/**
 * Decor for one chunk.
 *
 * Takes the chunk's origin in world tiles so the caller, which already computed it to place the
 * terrain mesh, does not pay for it twice.
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

  for (let ty = 0; ty < CHUNK_TILES; ty += 1) {
    const localY = localY0 + ty
    for (let tx = 0; tx < CHUNK_TILES; tx += 1) {
      const localX = localX0 + tx

      const distance = Math.max(Math.abs(localX), Math.abs(localY))
      if (distance > HUB_RADIUS_TILES) continue

      const onStreetX = mod(localX, STREET_SPACING) === 0
      const onStreetY = mod(localY, STREET_SPACING) === 0

      if (distance <= PLAZA_HALF) {
        // The plaza: a campfire at the exact centre, lanterns at the four corners of the
        // square. A gathering place needs a focal point, and this is the cheapest one.
        if (localX === 0 && localY === 0) {
          placements.push({ key: 'campfire', x: originTileX + tx + 0.5, y: originTileY + ty + 1, light: 'campfire' })
        } else if (Math.abs(localX) === PLAZA_HALF - 1 && Math.abs(localY) === PLAZA_HALF - 1) {
          placements.push({ key: 'lantern', x: originTileX + tx + 0.5, y: originTileY + ty + 1, light: 'lantern' })
        }
        continue
      }

      // Street corners get a lantern; the long stretches between them do not, or a town would
      // read as a runway.
      if (onStreetX && onStreetY) {
        placements.push({
          key: 'lantern',
          x: originTileX + tx + 0.5,
          y: originTileY + ty + 1,
          light: 'lantern',
        })
      }
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
