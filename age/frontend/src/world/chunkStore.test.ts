/**
 * The overlay composition rules.
 *
 * These are the cases where a plausible-looking implementation silently loses a player's
 * work: an edit arriving before its chunk, a chunk evicted with unsaved overlays, an edit
 * that reverts to the generated value.
 */

import { beforeEach, describe, expect, it } from 'vitest'

import { CHUNK_TILE_COUNT } from '../domain/constants'
import { Tile } from '../domain/tiles'
import { ChunkStore } from './chunkStore'
import { buildWorld } from './coordinates'
import { SpaceType, WorldGenerator, chunkKey, type ChunkAddress } from './generator'

const EDGE_ID = 'emberhold-rookmarch'
const layout = buildWorld(EDGE_ID, 8)

const address: ChunkAddress = {
  spaceType: SpaceType.EDGE,
  edgeId: EDGE_ID,
  segmentIndex: 0,
  laneOffset: 0,
  tierMin: 0,
}
const key = chunkKey(address)

let store: ChunkStore

beforeEach(() => {
  store = new ChunkStore(new WorldGenerator(0xa6e5eedn), layout.hubs, layout.edges)
  store.setTopology([key], [])
})

describe('loading', () => {
  it('generates a full chunk of tiles', () => {
    const view = store.load(address)
    expect(view.base.length).toBe(CHUNK_TILE_COUNT)
  })

  it('returns the same view rather than regenerating', () => {
    expect(store.load(address)).toBe(store.load(address))
  })
})

describe('overlays', () => {
  it('reports a changed tile instead of the generated one', () => {
    const view = store.load(address)
    const index = 0
    const generated = view.base[index]
    const replacement = generated === Tile.WALL_STONE ? Tile.WALL_WOOD : Tile.WALL_STONE

    expect(store.applyTiles(key, [[index, replacement]])).toBe(true)
    expect(store.tileAt(view, index)).toBe(replacement)
    // The base is untouched, which is what lets the chunk be evicted and rebuilt.
    expect(view.base[index]).toBe(generated)
  })

  it('holds an edit that arrives before its chunk is loaded', () => {
    // The server has no idea which chunks the client has generated, so this ordering is
    // routine rather than exceptional. Dropping the edit would leave a hole until reconnect.
    expect(store.applyTiles(key, [[7, Tile.WALL_STONE]])).toBe(false)

    const view = store.load(address)
    expect(store.tileAt(view, 7)).toBe(Tile.WALL_STONE)
  })

  it('keeps overlays when a chunk is evicted, and restores them on reload', () => {
    const view = store.load(address)
    const index = 11
    const replacement = view.base[index] === Tile.FENCE ? Tile.WALL_WOOD : Tile.FENCE
    store.applyTiles(key, [[index, replacement]])

    store.unload(key)
    expect(store.loadedCount).toBe(0)

    const reloaded = store.load(address)
    expect(store.tileAt(reloaded, index)).toBe(replacement)
  })

  it('drops an overlay that matches the generated tile', () => {
    // Otherwise a tile harvested and regrown accumulates a permanent no-op entry, and the
    // overlay grows without bound over a long session.
    const view = store.load(address)
    store.applyTiles(key, [[3, Tile.WALL_STONE]])
    expect(store.stats().overlaid).toBe(1)

    store.applyTiles(key, [[3, view.base[3]]])
    expect(store.stats().overlaid).toBe(0)
  })

  it('reports no change when an edit is already applied', () => {
    // Echoes of the client's own edits arrive here and should not trigger a mesh rebuild.
    store.load(address)
    store.applyTiles(key, [[5, Tile.WALL_STONE]])
    expect(store.applyTiles(key, [[5, Tile.WALL_STONE]])).toBe(false)
  })

  it('ignores an out-of-range index rather than growing the array', () => {
    store.load(address)
    expect(store.applyTiles(key, [[CHUNK_TILE_COUNT + 10, Tile.WALL_STONE]])).toBe(false)
    expect(store.applyTiles(key, [[-1, Tile.WALL_STONE]])).toBe(false)
  })

  it('bumps the revision so the renderer knows to rebuild', () => {
    store.load(address)
    const before = store.peek(key)!.revision
    store.applyTiles(key, [[9, Tile.WALL_STONE]])
    expect(store.peek(key)!.revision).toBeGreaterThan(before)
  })
})

describe('reading for the renderer', () => {
  it('writes composed tiles into a caller-owned buffer', () => {
    const view = store.load(address)
    store.applyTiles(key, [[4, Tile.WALL_STONE]])

    const out = new Uint8Array(CHUNK_TILE_COUNT)
    store.readInto(address, out)

    expect(out[4]).toBe(Tile.WALL_STONE)
    expect(out[5]).toBe(view.base[5])
  })
})

describe('walkability', () => {
  it('treats a point outside the topology as blocked', () => {
    // The player is inside the topology by construction, so this only fires at the world
    // edge, where a wall is the right answer.
    store.setTopology([key], [])
    expect(store.walkable(1e6, 1e6)).toBe(false)
  })

  it('distinguishes "no terrain" from "blocked terrain"', () => {
    // A remote entity standing on an unloaded chunk still has to be drawn where the server
    // says it is, so the tile query has to be able to say "I do not know".
    expect(store.tileAtPoint({ x: 1e6, y: 1e6 })).toBeUndefined()
  })

  it('answers from the overlay, not the generated base', () => {
    // A wall a player built has to stop them, and a tile they cleared has to let them
    // through, before the server confirms either.
    const view = store.load(address)
    let walkableIndex = -1
    for (let i = 0; i < CHUNK_TILE_COUNT; i += 1) {
      if (view.base[i] < Tile.WATER) {
        walkableIndex = i
        break
      }
    }
    expect(walkableIndex).toBeGreaterThanOrEqual(0)

    store.applyTiles(key, [[walkableIndex, Tile.WALL_STONE]])
    expect(store.tileAt(view, walkableIndex)).toBe(Tile.WALL_STONE)
  })
})

describe('streaming', () => {
  it('returns nearby chunks nearest first', () => {
    // At the moment a player crosses into new territory, the nearest chunks are the ones
    // about to be on screen.
    store.setTopology([], [])
    const around = store.addressesAround({ x: 0, y: 0 }, 2)
    expect(around.length).toBeGreaterThan(1)

    const first = around[0]
    const last = around[around.length - 1]
    expect(Math.abs(first.segmentIndex ?? 0) + Math.abs(first.laneOffset ?? 0)).toBeLessThanOrEqual(
      Math.abs(last.segmentIndex ?? 0) + Math.abs(last.laneOffset ?? 0),
    )
  })

  it('does not stream chunks the server has not activated', () => {
    // Generating an inactive lane would paint terrain the player cannot reach.
    store.setTopology([key], [])
    const around = store.addressesAround({ x: 0, y: 0 }, 2)
    expect(around.every((candidate) => store.isActive(chunkKey(candidate)))).toBe(true)
  })

  it('keeps retiring chunks readable', () => {
    // A player being evacuated is still standing on one; making the ground vanish
    // underneath them is worse than briefly drawing a chunk that is going away.
    const retiring = chunkKey({ ...address, segmentIndex: 3 })
    store.setTopology([key], [retiring])
    expect(store.isActive(retiring)).toBe(true)
  })

  it('evicts chunks outside the radius', () => {
    store.setTopology([], [])
    for (const candidate of store.addressesAround({ x: 0, y: 0 }, 3)) store.load(candidate)
    const before = store.loadedCount
    expect(before).toBeGreaterThan(4)

    store.pruneAround({ x: 0, y: 0 }, 1)
    expect(store.loadedCount).toBeLessThan(before)
  })

  it('does not walk off the end of the corridor', () => {
    // Segment -1 does not exist, and generating it would put terrain behind the start.
    store.setTopology([], [])
    const around = store.addressesAround({ x: 0, y: 0 }, 4)
    expect(around.every((candidate) => (candidate.segmentIndex ?? 0) >= 0)).toBe(true)
  })
})

describe('hubs against the accordion', () => {
  // The server's topology covers the corridor only: hubs are permanent, so it has no
  // records for them and never names them. Treating that list as an allowlist for every
  // chunk filtered out the entire hub — which is where players spawn — and produced a
  // black screen with nothing in the console to explain it.

  it('keeps hub chunks active even though the topology never lists them', () => {
    store.setTopology([key], [])
    expect(store.isActive(chunkKey({ spaceType: SpaceType.HUB, hubId: 0, chunkX: 0, chunkY: 0 }))).toBe(
      true,
    )
  })

  it('streams terrain around a spawn point inside a hub', () => {
    store.setTopology([key], [])
    const spawn = store.hubOrigin(0)

    const around = store.addressesAround({ x: spawn.x, y: spawn.y + 3 }, 2)

    expect(around.length).toBeGreaterThan(1)
    expect(around.every((candidate) => candidate.spaceType === SpaceType.HUB)).toBe(true)
  })

  it('still refuses a corridor lane the accordion has closed', () => {
    // The permanence of hubs must not turn the allowlist off for the corridor as well.
    store.setTopology([key], [])
    const closed = chunkKey({ ...address, laneOffset: 1, tierMin: 1 })
    expect(store.isActive(closed)).toBe(false)
  })
})
