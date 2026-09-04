/**
 * The client's view of terrain: generated tiles plus the server's overlay of player edits.
 *
 * Mirror of `ChunkView` and the tile-access half of `age/application/world.py`. Base tiles
 * are generated locally and never transmitted; overlays arrive as index/value pairs, a few
 * bytes per edited tile. Keeping them separate is what makes that split possible — the base
 * stays regenerable, so a chunk can be evicted and rebuilt while the edits persist.
 *
 * Overlays are stored per chunk key even for chunks that are not loaded. An edit can arrive
 * before the chunk it belongs to is generated (the server has no idea what the client has
 * built yet), and dropping it would leave a hole that only a reconnect would fix.
 */

import { CHUNK_TILES, CHUNK_TILE_COUNT } from '../domain/constants'
import { isWalkable, blocksSight } from '../domain/tiles'
import { chunkKey, type ChunkAddress, type WorldGenerator } from './generator'
import {
  edgeToWorld,
  hubToWorld,
  locate,
  tierMinForLane,
  type EdgeDefinition,
  type HubDefinition,
  type Point,
} from './coordinates'

/** A loaded chunk: generated base, plus whatever the server says has changed. */
interface ChunkView {
  address: ChunkAddress
  base: Uint8Array
  overlay: Map<number, number>
  /** Bumped on every overlay change so the renderer knows to rebuild its mesh. */
  revision: number
}

export class ChunkStore {
  private readonly chunks = new Map<string, ChunkView>()
  private readonly pendingOverlays = new Map<string, Map<number, number>>()

  /**
   * Corridor chunk keys the server has declared active.
   *
   * Corridor chunks only. Hubs sit outside the accordion — they are permanent, so the
   * server's topology has no records for them and never names them here. Treating this
   * set as an allowlist for *every* chunk therefore filters out the whole hub, which is
   * where players spawn: a black screen from the first frame. See `isActive`.
   */
  private active = new Set<string>()

  constructor(
    private generator: WorldGenerator,
    private hubs: readonly HubDefinition[],
    private edges: readonly EdgeDefinition[],
  ) {}

  /** Swap in a generator for a new world seed, on reconnect to a different world. */
  setGenerator(generator: WorldGenerator): void {
    this.generator = generator
    this.chunks.clear()
  }

  setLayout(hubs: readonly HubDefinition[], edges: readonly EdgeDefinition[]): void {
    this.hubs = hubs
    this.edges = edges
  }

  /**
   * Record the topology the server has declared.
   *
   * Retiring chunks stay readable: a player being evacuated is still standing on them, and
   * making the ground vanish underneath them mid-walk is worse than briefly rendering a
   * chunk that is about to go away.
   */
  setTopology(activeChunks: readonly string[], retiringChunks: readonly string[]): void {
    this.active = new Set([...activeChunks, ...retiringChunks])
  }

  get activeCount(): number {
    return this.active.size
  }

  get loadedCount(): number {
    return this.chunks.size
  }

  /**
   * Whether a chunk is part of the world right now.
   *
   * Hub chunks always are. Corridor chunks are only while the accordion has their lane
   * open, which is what the server's topology declares. Before the first topology packet
   * everything passes, so the first frames after `WELCOME` draw rather than stall.
   */
  isActive(key: string): boolean {
    if (key.startsWith('hub:')) return true
    return this.active.size === 0 || this.active.has(key)
  }

  /**
   * Load a chunk, generating its base tiles if necessary.
   *
   * Generation is synchronous and costs a couple of milliseconds. That is acceptable
   * because it happens for chunks entering the preload ring, a full second of walking
   * before they are visible, rather than for the chunk underfoot.
   */
  load(address: ChunkAddress): ChunkView {
    const key = chunkKey(address)
    const existing = this.chunks.get(key)
    if (existing !== undefined) return existing

    const view: ChunkView = {
      address,
      base: this.generator.generate(address),
      overlay: this.pendingOverlays.get(key) ?? new Map(),
      revision: 0,
    }
    this.pendingOverlays.delete(key)
    this.chunks.set(key, view)
    return view
  }

  peek(key: string): ChunkView | undefined {
    return this.chunks.get(key)
  }

  /** Drop a chunk that has left the unload ring. Overlays are kept. */
  unload(key: string): void {
    const view = this.chunks.get(key)
    if (view === undefined) return
    if (view.overlay.size > 0) this.pendingOverlays.set(key, view.overlay)
    this.chunks.delete(key)
  }

  /**
   * Apply a server tile delta.
   *
   * Returns whether anything changed, so the renderer only rebuilds a chunk that actually
   * moved. Echoes of the client's own edits arrive here too and are no-ops by the time
   * they land, which is exactly what should happen.
   */
  applyTiles(key: string, changes: ReadonlyArray<readonly [number, number]>): boolean {
    const view = this.chunks.get(key)
    if (view === undefined) {
      // Not loaded yet. Hold the edits so they are there when it is.
      let pending = this.pendingOverlays.get(key)
      if (pending === undefined) {
        pending = new Map()
        this.pendingOverlays.set(key, pending)
      }
      for (const [index, tile] of changes) pending.set(index, tile)
      return false
    }

    let changed = false
    for (const [index, tile] of changes) {
      if (index < 0 || index >= CHUNK_TILE_COUNT) continue
      if (view.base[index] === tile) {
        // Edited back to what the generator produces: drop the entry rather than
        // storing a no-op forever.
        changed = view.overlay.delete(index) || changed
      } else if (view.overlay.get(index) !== tile) {
        view.overlay.set(index, tile)
        changed = true
      }
    }
    if (changed) view.revision += 1
    return changed
  }

  /** The effective tile at a chunk index: overlay if present, base otherwise. */
  tileAt(view: ChunkView, index: number): number {
    const overlaid = view.overlay.get(index)
    return overlaid === undefined ? view.base[index] : overlaid
  }

  /**
   * The tile at a plane point, or `undefined` outside the active topology.
   *
   * `undefined` and "blocked" are deliberately different answers. Outside the world the
   * client must not invent terrain: the local player is stopped there, but a remote entity
   * reported on an unloaded chunk is still drawn where the server says it is.
   */
  tileAtPoint(point: Point): number | undefined {
    const located = locate(point, this.hubs, this.edges)
    if (located === undefined) return undefined
    if (!this.isActive(chunkKey(located.address))) return undefined
    return this.tileAt(this.load(located.address), located.index)
  }

  /**
   * The walkability probe the predictor uses.
   *
   * Bound once and passed around, because it is called four times per axis per replayed
   * input — potentially hundreds of times a frame after a late snapshot — so the closure
   * allocation would otherwise be on the hot path.
   */
  readonly walkable = (x: number, y: number): boolean => {
    const tile = this.tileAtPoint({ x, y })
    // Off the map counts as blocked for movement. The player is inside the topology by
    // construction, so this only fires at the edge of the world, where a wall is right.
    return tile !== undefined && isWalkable(tile)
  }

  readonly opaque = (x: number, y: number): boolean => {
    const tile = this.tileAtPoint({ x, y })
    return tile !== undefined && blocksSight(tile)
  }

  /**
   * Copy a chunk's effective tiles into a flat array for the renderer.
   *
   * Written into a caller-owned buffer rather than returning a new one: the tilemap
   * rebuilds a chunk whenever its revision changes, and at 1024 tiles a chunk that would
   * be a steady stream of garbage.
   */
  readInto(address: ChunkAddress, out: Uint8Array): number {
    const view = this.load(address)
    out.set(view.base)
    for (const [index, tile] of view.overlay) out[index] = tile
    return view.revision
  }

  /**
   * Every chunk address within `radius` chunks of a point, nearest first.
   *
   * Ordering matters: at the moment the player crosses into new territory the nearest
   * chunks are the ones about to be on screen, so generating them first is the difference
   * between a seamless walk and a visible pop.
   */
  addressesAround(point: Point, radius: number): ChunkAddress[] {
    const centre = locate(point, this.hubs, this.edges)
    if (centre === undefined) return []

    const found: Array<{ address: ChunkAddress; distance: number }> = []
    for (let dy = -radius; dy <= radius; dy += 1) {
      for (let dx = -radius; dx <= radius; dx += 1) {
        const address = this.offsetAddress(centre.address, dx, dy)
        if (address === undefined) continue
        if (!this.isActive(chunkKey(address))) continue
        found.push({ address, distance: dx * dx + dy * dy })
      }
    }
    found.sort((a, b) => a.distance - b.distance)
    return found.map((entry) => entry.address)
  }

  /**
   * A neighbouring chunk address, in whichever space the origin is in.
   *
   * Returns `undefined` at a space boundary rather than fabricating an address. Walking
   * from a hub into the corridor crosses frames, and the two are only stitched by the
   * topology the server publishes: guessing here would generate a chunk that does not
   * exist and paint terrain over the join.
   */
  private offsetAddress(address: ChunkAddress, dx: number, dy: number): ChunkAddress | undefined {
    if (address.spaceType === 0) {
      const chunkX = (address.chunkX ?? 0) + dx
      const chunkY = (address.chunkY ?? 0) + dy
      const limit = Math.ceil(this.hubRadius(address.hubId ?? 0) / CHUNK_TILES)
      if (Math.abs(chunkX) > limit || Math.abs(chunkY) > limit) return undefined
      return { spaceType: 0, hubId: address.hubId, chunkX, chunkY }
    }

    const segmentIndex = (address.segmentIndex ?? 0) + dx
    if (segmentIndex < 0) return undefined
    const edge = this.edges.find((candidate) => candidate.edgeId === address.edgeId)
    if (edge !== undefined && segmentIndex >= edge.segments) return undefined

    // Derived from the new lane rather than carried over from the origin: stepping
    // sideways out of the centre lane changes which tier the chunk belongs to, and
    // inheriting the old one names a chunk the server has never heard of.
    const laneOffset = (address.laneOffset ?? 0) + dy
    return {
      spaceType: 1,
      edgeId: address.edgeId,
      segmentIndex,
      laneOffset,
      tierMin: tierMinForLane(laneOffset),
    }
  }

  private hubRadius(hubId: number): number {
    return this.hubs.find((hub) => hub.hubId === hubId)?.radiusTiles ?? 0
  }

  /**
   * A chunk's top-left corner, in world tile coordinates.
   *
   * The renderer needs this to place a chunk's mesh, and it lives here because the store is
   * what holds the hub and edge definitions the transform depends on. Returns the origin even
   * for a chunk in no known space, so a mesh is drawn at a wrong-but-finite place rather than
   * at `NaN`, which in WebGL means an invisible chunk and no error anywhere.
   */
  chunkOriginTiles(address: ChunkAddress): Point {
    if (address.spaceType === 0) {
      const hub = this.hubs.find((candidate) => candidate.hubId === address.hubId)
      if (hub === undefined) return { x: 0, y: 0 }
      return hubToWorld(hub, (address.chunkX ?? 0) * CHUNK_TILES, (address.chunkY ?? 0) * CHUNK_TILES)
    }

    const edge = this.edges.find((candidate) => candidate.edgeId === address.edgeId)
    if (edge === undefined) return { x: 0, y: 0 }
    return edgeToWorld(edge, address.segmentIndex ?? 0, address.laneOffset ?? 0, 0, 0)
  }

  /** Chunk addresses around a point in tile coordinates. Convenience for the renderer. */
  chunksAround(tileX: number, tileY: number, radius: number): ChunkAddress[] {
    return this.addressesAround({ x: tileX, y: tileY }, radius)
  }

  /**
   * The biome at a world point, for colour grading.
   *
   * Answered locally rather than asked of the server. The biome is a pure function of position
   * and world seed, computed identically on both sides and covered by the parity tests, so a
   * request would be a round trip for something already known.
   */
  biomeAt(tileX: number, tileY: number): number {
    return this.generator.biomeAt(tileX, tileY)
  }

  /** Where the camera should look on spawn: the hub's plaza, or the origin. */
  hubOrigin(hubId = 0): Point {
    const hub = this.hubs.find((candidate) => candidate.hubId === hubId)
    return hub === undefined ? { x: 0, y: 0 } : hubToWorld(hub, 0, 0)
  }

  get hubList(): readonly HubDefinition[] {
    return this.hubs
  }

  /** Evict loaded chunks beyond `radius`, so a long walk does not grow memory. */
  pruneAround(point: Point, radius: number): void {
    const keep = new Set(this.addressesAround(point, radius).map(chunkKey))
    for (const key of [...this.chunks.keys()]) {
      if (!keep.has(key)) this.unload(key)
    }
  }

  /** Diagnostics for the debug overlay. */
  stats(): { loaded: number; active: number; overlaid: number; pending: number } {
    let overlaid = 0
    for (const view of this.chunks.values()) overlaid += view.overlay.size
    return {
      loaded: this.chunks.size,
      active: this.active.size,
      overlaid,
      pending: this.pendingOverlays.size,
    }
  }
}

export { CHUNK_TILES }
