/**
 * Main-thread facade over the tile worker.
 *
 * Loads the world descriptor, pulls every tile of the district in parallel and
 * stitches them into the grid the renderer and the predictor share. Tiles are
 * immutable per world version, so the browser cache does the rest on reload.
 */

import type { WorldMetadata, WorldTile } from '../domain/types'
import { CollisionGrid, blitTile } from './collisionGrid'
import type { TileRequest, TileWorkerResponse } from './tileWorker'
import { decodeTile } from './tileCodec'

export interface LoadProgress {
  loaded: number
  total: number
  bytes: number
}

export interface LoadedWorld {
  metadata: WorldMetadata
  grid: CollisionGrid
  tiles: WorldTile[]
}

/** Concurrency cap: enough to saturate a link, few enough to stay polite. */
const PARALLEL_TILE_REQUESTS = 4

export class WorldClient {
  private worker: Worker | null = null
  private nextRequestId = 1
  private readonly inflight = new Map<
    number,
    { resolve: (tile: WorldTile) => void; reject: (error: Error) => void }
  >()

  constructor(private readonly basePath: string) {}

  async fetchMetadata(signal?: AbortSignal): Promise<WorldMetadata> {
    const response = await fetch(`${this.basePath}/api/world`, {
      credentials: 'same-origin',
      signal,
    })
    if (!response.ok) throw new Error(`The world metadata endpoint answered ${response.status}.`)
    return (await response.json()) as WorldMetadata
  }

  async load(
    onProgress?: (progress: LoadProgress) => void,
    signal?: AbortSignal,
  ): Promise<LoadedWorld> {
    const metadata = await this.fetchMetadata(signal)
    const { tilesX, tilesY, tileCells, cellSize } = metadata.world

    const grid = new CollisionGrid(tilesX * tileCells, tilesY * tileCells, cellSize)
    const coordinates: Array<[number, number]> = []
    for (let y = 0; y < tilesY; y += 1) {
      for (let x = 0; x < tilesX; x += 1) coordinates.push([x, y])
    }

    const tiles: WorldTile[] = []
    const progress: LoadProgress = { loaded: 0, total: coordinates.length, bytes: 0 }
    let cursor = 0

    const pump = async (): Promise<void> => {
      while (cursor < coordinates.length) {
        if (signal?.aborted) throw new Error('World loading was cancelled.')
        const [x, y] = coordinates[cursor]
        cursor += 1
        const tile = await this.requestTile(x, y)
        blitTile(grid, tile)
        tiles.push(tile)
        progress.loaded += 1
        onProgress?.({ ...progress })
      }
    }

    await Promise.all(
      Array.from({ length: Math.min(PARALLEL_TILE_REQUESTS, coordinates.length) }, pump),
    )
    return { metadata, grid, tiles }
  }

  dispose(): void {
    this.worker?.terminate()
    this.worker = null
    for (const pending of this.inflight.values()) {
      pending.reject(new Error('The tile loader was shut down.'))
    }
    this.inflight.clear()
  }

  private ensureWorker(): Worker | null {
    if (this.worker) return this.worker
    if (typeof Worker === 'undefined') return null
    try {
      this.worker = new Worker(new URL('./tileWorker.ts', import.meta.url), { type: 'module' })
      this.worker.onmessage = (event: MessageEvent<TileWorkerResponse>) => {
        const message = event.data
        const pending = this.inflight.get(message.requestId)
        if (!pending) return
        this.inflight.delete(message.requestId)
        if (message.type === 'tile-ready') pending.resolve(message.tile as WorldTile)
        else pending.reject(new Error(message.reason))
      }
      this.worker.onerror = () => {
        // A broken worker must not strand the loader; fall back to the main thread.
        this.worker?.terminate()
        this.worker = null
      }
      return this.worker
    } catch {
      return null
    }
  }

  private requestTile(tileX: number, tileY: number): Promise<WorldTile> {
    const url = `${this.basePath}/api/world/tiles/${tileX}/${tileY}`
    const worker = this.ensureWorker()
    if (!worker) return this.fetchTileOnMainThread(url)

    const requestId = this.nextRequestId
    this.nextRequestId += 1
    return new Promise<WorldTile>((resolve, reject) => {
      this.inflight.set(requestId, { resolve, reject })
      const request: TileRequest = { type: 'tile', requestId, url, tileX, tileY }
      worker.postMessage(request)
    })
  }

  private async fetchTileOnMainThread(url: string): Promise<WorldTile> {
    const response = await fetch(url, { credentials: 'same-origin' })
    if (!response.ok) throw new Error(`Tile request failed with HTTP ${response.status}.`)
    return decodeTile(await response.arrayBuffer())
  }
}
