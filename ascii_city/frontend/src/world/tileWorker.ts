/**
 * Tile fetch and decode, off the main thread.
 *
 * A 128x128 tile is ~55 KB of layers plus a few hundred records. Decoding it
 * on the render thread costs several frames; here it costs none, and the
 * layers transfer back without a copy.
 */

import { decodeTile } from './tileCodec'

export interface TileRequest {
  type: 'tile'
  requestId: number
  url: string
  tileX: number
  tileY: number
}

export interface TileReady {
  type: 'tile-ready'
  requestId: number
  tileX: number
  tileY: number
  bytes: number
  /** A structured-cloned tile; typed arrays inside are transferred. */
  tile: unknown
}

export interface TileFailed {
  type: 'tile-failed'
  requestId: number
  tileX: number
  tileY: number
  reason: string
}

export type TileWorkerResponse = TileReady | TileFailed

self.onmessage = async (event: MessageEvent<TileRequest>) => {
  const request = event.data
  if (request?.type !== 'tile') return

  try {
    const response = await fetch(request.url, { credentials: 'same-origin' })
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    const payload = await response.arrayBuffer()
    const tile = decodeTile(payload)
    const message: TileReady = {
      type: 'tile-ready',
      requestId: request.requestId,
      tileX: request.tileX,
      tileY: request.tileY,
      bytes: payload.byteLength,
      tile,
    }
    // Hand the layer buffers over instead of cloning 48 KB three times.
    self.postMessage(message, [
      tile.collision.buffer,
      tile.heights.buffer,
      tile.styles.buffer,
    ] as unknown as Transferable[])
  } catch (error) {
    const message: TileFailed = {
      type: 'tile-failed',
      requestId: request.requestId,
      tileX: request.tileX,
      tileY: request.tileY,
      reason: error instanceof Error ? error.message : String(error),
    }
    self.postMessage(message)
  }
}
