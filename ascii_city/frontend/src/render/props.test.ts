/**
 * Street furniture is generated server-side and was, for a long time, decoded
 * and then thrown away. These tests hold the pass that finally draws it, and
 * they read the character grid directly rather than any pixels.
 */

import { describe, expect, it } from 'vitest'

import { CELL_BUILDING, CELL_ROAD, EYE_HEIGHT_M, PROP_LAMP, PROP_TREE } from '../domain/constants'
import type { WorldTile } from '../domain/types'
import { CollisionGrid } from '../world/collisionGrid'
import { CellBuffer } from './cellBuffer'
import { CHARSET } from './charset'
import { bakeLightMap, collectProps, renderProps, type WorldProp } from './props'
import { DEFAULT_QUALITY, Raycaster, type Camera } from './raycaster'

const COLUMNS = 80
const ROWS = 40

function district(): CollisionGrid {
  const grid = new CollisionGrid(64, 64, 2)
  grid.cells.fill(CELL_ROAD)
  return grid
}

function camera(overrides: Partial<Camera> = {}): Camera {
  return { x: 64, y: 64, z: EYE_HEIGHT_M, yaw: 0, pitch: 0, ...overrides }
}

/** Draw the world, then the furniture, exactly as the renderer orders them. */
function frame(grid: CollisionGrid, view: Camera, props: WorldProp[]): CellBuffer {
  const buffer = new CellBuffer(COLUMNS, ROWS)
  const raycaster = new Raycaster({ ...DEFAULT_QUALITY })
  raycaster.render(buffer, grid, view)
  renderProps(buffer, view, props, DEFAULT_QUALITY.fov, 0)
  return buffer
}

function glyphs(buffer: CellBuffer): string {
  let out = ''
  for (let row = 0; row < buffer.rows; row += 1) {
    for (let column = 0; column < buffer.columns; column += 1) {
      out += CHARSET[buffer.glyphAt(column, row)] ?? '?'
    }
    out += '\n'
  }
  return out
}

function lamp(x: number, y: number): WorldProp {
  return { x, y, kind: PROP_LAMP, seed: 0.5 }
}

describe('street furniture', () => {
  it('draws a lamp standing in front of the camera', () => {
    const empty = glyphs(frame(district(), camera(), []))
    const dressed = glyphs(frame(district(), camera(), [lamp(74, 64)]))
    expect(dressed).not.toEqual(empty)
    // The pole is box-drawing pipe and the head is a half block.
    expect(dressed).toContain('\u2502')
  })

  it('leaves the scene alone when the furniture is behind the camera', () => {
    const empty = glyphs(frame(district(), camera(), []))
    const behind = glyphs(frame(district(), camera(), [lamp(54, 64)]))
    expect(behind).toEqual(empty)
  })

  it('hides furniture standing behind a wall', () => {
    const grid = district()
    // A tall building at x = 70 m, between the camera and the lamp at 80 m.
    for (let cy = 30; cy < 34; cy += 1) {
      const at = cy * grid.width + 35
      grid.cells[at] = CELL_BUILDING
      grid.heights[at] = 40
    }
    const walled = glyphs(frame(grid, camera(), [lamp(80, 64)]))
    const bare = glyphs(frame(grid, camera(), []))
    expect(walled).toEqual(bare)
  })

  it('drops furniture past the draw distance instead of drawing a speck', () => {
    const far = glyphs(frame(district(), camera(), [lamp(64 + 120, 64)]))
    expect(far).toEqual(glyphs(frame(district(), camera(), [])))
  })

  it('lights the pavement around a lamp and nowhere else', () => {
    const light = bakeLightMap([lamp(20, 20)], 64, 64, 2)
    const atLamp = light[10 * 64 + 10]
    const nearby = light[10 * 64 + 12]
    const distant = light[10 * 64 + 30]
    expect(atLamp).toBeGreaterThan(0.5)
    expect(nearby).toBeGreaterThan(0)
    expect(nearby).toBeLessThan(atLamp)
    expect(distant).toBe(0)
  })

  it('bakes nothing for furniture that does not emit', () => {
    const light = bakeLightMap([{ x: 20, y: 20, kind: PROP_TREE, seed: 0 }], 64, 64, 2)
    expect(light.every((value) => value === 0)).toBe(true)
  })

  it('places tile-local furniture in world metres', () => {
    const tile = {
      tileX: 1,
      tileY: 2,
      cells: 128,
      props: [{ id: 7, x: 3, y: 4, kind: PROP_LAMP }],
    } as unknown as WorldTile
    const [prop] = collectProps([tile], 2)
    // Tile origin plus the cell, sampled at the middle of that cell.
    expect(prop.x).toBeCloseTo((128 + 3 + 0.5) * 2, 6)
    expect(prop.y).toBeCloseTo((256 + 4 + 0.5) * 2, 6)
    expect(prop.seed).toBeGreaterThanOrEqual(0)
    expect(prop.seed).toBeLessThan(1)
  })
})
