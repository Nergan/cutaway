/**
 * Client-side mirror of `ascii_city/domain/world.py::CollisionGrid`.
 *
 * Prediction needs the same walkability answers the server gives, and the
 * raycaster needs the same height field, so both layers live here behind one
 * query surface.
 */

import { CELL_SIZE_M, FLOOR_STEP_M, STEP_UP_M, isSolidCode } from '../domain/constants'
import type { WorldTile } from '../domain/types'

export class CollisionGrid {
  readonly cells: Uint8Array
  readonly heights: Uint8Array
  readonly styles: Uint8Array

  constructor(
    readonly width: number,
    readonly height: number,
    readonly cellSize: number = CELL_SIZE_M,
    buffers?: { cells: Uint8Array; heights: Uint8Array; styles: Uint8Array },
  ) {
    const area = width * height
    this.cells = buffers?.cells ?? new Uint8Array(area)
    this.heights = buffers?.heights ?? new Uint8Array(area)
    this.styles = buffers?.styles ?? new Uint8Array(area)
  }

  get widthM(): number {
    return this.width * this.cellSize
  }

  get heightM(): number {
    return this.height * this.cellSize
  }

  /** Out of bounds reads as a wall, exactly as the server does. */
  codeAt(cx: number, cy: number): number {
    if (cx < 0 || cy < 0 || cx >= this.width || cy >= this.height) return 3
    return this.cells[cy * this.width + cx]
  }

  heightAt(cx: number, cy: number): number {
    if (cx < 0 || cy < 0 || cx >= this.width || cy >= this.height) return 0
    return this.heights[cy * this.width + cx]
  }

  styleAt(cx: number, cy: number): number {
    if (cx < 0 || cy < 0 || cx >= this.width || cy >= this.height) return 0
    return this.styles[cy * this.width + cx]
  }

  isSolidCell(cx: number, cy: number): boolean {
    return isSolidCode(this.codeAt(cx, cy))
  }

  /** Elevation of the walkable surface, in metres above street level. */
  floorAt(cx: number, cy: number): number {
    if (this.isSolidCell(cx, cy)) return 0
    return this.heightAt(cx, cy) * FLOOR_STEP_M
  }

  /**
   * Whether the player fits here, standing with their feet at `feetZ`.
   *
   * A cell is in the way when it is solid, and also when its floor is further
   * above the feet than one stride: that is what makes a terrace an obstacle
   * from the street and a surface from the stairs.
   */
  isFreeCircle(x: number, y: number, radius: number, feetZ = Infinity): boolean {
    const minCx = Math.floor((x - radius) / this.cellSize)
    const maxCx = Math.floor((x + radius) / this.cellSize)
    const minCy = Math.floor((y - radius) / this.cellSize)
    const maxCy = Math.floor((y + radius) / this.cellSize)
    for (let cy = minCy; cy <= maxCy; cy += 1) {
      for (let cx = minCx; cx <= maxCx; cx += 1) {
        if (this.isSolidCell(cx, cy)) return false
        if (this.floorAt(cx, cy) > feetZ + STEP_UP_M) return false
      }
    }
    return true
  }

  /** Highest floor under the player's footprint: what they stand on. */
  groundAt(x: number, y: number, radius: number): number {
    const minCx = Math.floor((x - radius) / this.cellSize)
    const maxCx = Math.floor((x + radius) / this.cellSize)
    const minCy = Math.floor((y - radius) / this.cellSize)
    const maxCy = Math.floor((y + radius) / this.cellSize)
    let ground = 0
    for (let cy = minCy; cy <= maxCy; cy += 1) {
      for (let cx = minCx; cx <= maxCx; cx += 1) {
        const floor = this.floorAt(cx, cy)
        if (floor > ground) ground = floor
      }
    }
    return ground
  }

  clampToWorld(point: { x: number; y: number }): void {
    const margin = this.cellSize * 0.5
    point.x = Math.min(Math.max(point.x, margin), this.widthM - margin)
    point.y = Math.min(Math.max(point.y, margin), this.heightM - margin)
  }
}

/** Blit one decoded tile into the district-wide grid. */
export function blitTile(grid: CollisionGrid, tile: WorldTile): void {
  const cells = tile.cells
  const baseX = tile.tileX * cells
  const baseY = tile.tileY * cells
  for (let localY = 0; localY < cells; localY += 1) {
    const source = localY * cells
    const destination = (baseY + localY) * grid.width + baseX
    grid.cells.set(tile.collision.subarray(source, source + cells), destination)
    grid.heights.set(tile.heights.subarray(source, source + cells), destination)
    grid.styles.set(tile.styles.subarray(source, source + cells), destination)
  }
}
