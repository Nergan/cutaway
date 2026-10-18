/**
 * The column walk compiled from `ascii_city/wasm`.
 *
 * Painting stays in the TypeScript raycaster. If the module is missing, every
 * column uses the TypeScript walk instead.
 */

import { FLOOR_STEP_M } from '../domain/constants'
import type { CollisionGrid } from '../world/collisionGrid'

export interface CityWalker {
  cellSize: number
  cast(
    originX: number,
    originY: number,
    rayX: number,
    rayY: number,
    maxCells: number,
    layers: number,
    out: Float64Array,
  ): number
  free(): void
}

interface WalkExports {
  memory: WebAssembly.Memory
  prepare(count: number): number
  heights_ptr(): number
  styles_ptr(): number
  bind_grid(width: number, height: number, cellSize: number, floorStep: number): void
  out_ptr(): number
  cast(
    originX: number,
    originY: number,
    rayX: number,
    rayY: number,
    maxCells: number,
    layers: number,
  ): number
}

let exports: WalkExports | null = null
let loading: Promise<void> | null = null
let enabled = true

export function walkLoaded(): boolean {
  return exports !== null
}

export function useWalk(next: boolean): void {
  enabled = next
}

async function loadBytes(): Promise<ArrayBuffer> {
  const response = await fetch(new URL('../walk/ascii_city_walk.wasm', import.meta.url))
  if (!response.ok) throw new Error('walk wasm missing')
  return response.arrayBuffer()
}

export function loadWalk(bytes?: ArrayBuffer): Promise<void> {
  if (exports && !bytes) return Promise.resolve()
  if (!bytes && loading) return loading
  const next = (bytes ? Promise.resolve(bytes) : loadBytes())
    .then((payload) => WebAssembly.instantiate(payload))
    .then((result) => {
      exports = result.instance.exports as unknown as WalkExports
    })
    .catch(() => {
      exports = null
    })
  if (!bytes) loading = next
  return next
}

export function openWalker(grid: CollisionGrid): CityWalker | null {
  if (!enabled || !exports) return null
  const wasm = exports
  const count = grid.width * grid.height
  const cellsPtr = wasm.prepare(count)
  const heightsPtr = wasm.heights_ptr()
  const stylesPtr = wasm.styles_ptr()
  const memory = new Uint8Array(wasm.memory.buffer)
  memory.set(grid.cells.subarray(0, count), cellsPtr)
  memory.set(grid.heights.subarray(0, count), heightsPtr)
  memory.set(grid.styles.subarray(0, count), stylesPtr)
  wasm.bind_grid(grid.width, grid.height, grid.cellSize, FLOOR_STEP_M)
  return {
    cellSize: grid.cellSize,
    cast: (originX, originY, rayX, rayY, maxCells, layers, out) => {
      const found = wasm.cast(originX, originY, rayX, rayY, maxCells, layers)
      const raw = new Float64Array(wasm.memory.buffer, wasm.out_ptr(), found * 8)
      out.set(raw)
      return found
    },
    free: () => undefined,
  }
}
