/**
 * The raycaster has no browser dependencies, so its output can be inspected
 * directly as a character grid. These tests check the structural claims the
 * renderer makes — sky above, ground below, nearer geometry occluding farther
 * geometry — rather than exact pixels, which would break on every tweak.
 */

import { describe, expect, it } from 'vitest'

import { CELL_BUILDING, CELL_ROAD, EYE_HEIGHT_M } from '../domain/constants'
import { CollisionGrid } from '../world/collisionGrid'
import { CellBuffer, CELL_STRIDE } from './cellBuffer'
import { CHARSET, G_SPACE } from './charset'
import { DEFAULT_QUALITY, Raycaster, type Camera } from './raycaster'
import { renderSprites, type Sprite } from './sprites'

const COLUMNS = 60
const ROWS = 30

function district(): CollisionGrid {
  const grid = new CollisionGrid(64, 64, 2)
  grid.cells.fill(CELL_ROAD)
  return grid
}

function box(grid: CollisionGrid, cx: number, cy: number, height: number): void {
  const at = cy * grid.width + cx
  grid.cells[at] = CELL_BUILDING
  grid.heights[at] = height
}

/** Camera in the middle of the district, facing east along +x. */
function camera(overrides: Partial<Camera> = {}): Camera {
  return { x: 64, y: 64, z: EYE_HEIGHT_M, yaw: 0, pitch: 0, ...overrides }
}

function frame(grid: CollisionGrid, view: Camera, quality = DEFAULT_QUALITY): CellBuffer {
  const buffer = new CellBuffer(COLUMNS, ROWS)
  new Raycaster({ ...quality }).render(buffer, grid, view)
  return buffer
}

/** The character grid as strings, which is how a failure is worth reading. */
function asText(buffer: CellBuffer): string[] {
  const lines: string[] = []
  for (let row = 0; row < buffer.rows; row += 1) {
    let line = ''
    for (let column = 0; column < buffer.columns; column += 1) {
      line += CHARSET[buffer.glyphAt(column, row)] ?? '?'
    }
    lines.push(line)
  }
  return lines
}

function background(buffer: CellBuffer, column: number, row: number): number[] {
  const at = (row * buffer.columns + column) * CELL_STRIDE
  return [buffer.data[at + 5], buffer.data[at + 6], buffer.data[at + 7]]
}

describe('an empty district', () => {
  it('paints every cell, leaving nothing stale', () => {
    const buffer = frame(district(), camera())
    const lines = asText(buffer)
    expect(lines).toHaveLength(ROWS)
    expect(lines.every((line) => line.length === COLUMNS)).toBe(true)
  })

  it('reports no nearby geometry at all', () => {
    const buffer = frame(district(), camera())
    expect([...buffer.depth].every((depth) => depth > 40)).toBe(true)
  })

  it('puts a darker sky above a lit ground', () => {
    const buffer = frame(district(), camera())
    const sky = background(buffer, COLUMNS / 2, 2)
    const ground = background(buffer, COLUMNS / 2, ROWS - 2)
    const brightness = (color: number[]) => color[0] + color[1] + color[2]
    expect(brightness(ground)).toBeGreaterThan(brightness(sky))
  })

  it('scrolls the horizon down when the camera looks up', () => {
    const level = frame(district(), camera())
    const up = frame(district(), camera({ pitch: 0.8 }))
    const skyRows = (buffer: CellBuffer) => {
      let count = 0
      for (let row = 0; row < ROWS; row += 1) {
        // Ground cells carry road grain; sky cells are blank or a star.
        if (buffer.glyphAt(COLUMNS / 2, row) === G_SPACE) count += 1
      }
      return count
    }
    expect(skyRows(up)).toBeGreaterThan(skyRows(level))
  })
})

describe('a single building', () => {
  it('appears ahead and records its distance in the depth buffer', () => {
    const grid = district()
    box(grid, 37, 32, 20)
    const buffer = frame(grid, camera())
    const centre = COLUMNS / 2
    // The wall sits ten cells east of the camera, so twenty-ish metres away.
    expect(buffer.depth[centre]).toBeGreaterThan(8)
    expect(buffer.depth[centre]).toBeLessThan(14)
  })

  it('is not what the depth buffer reports once the camera turns away', () => {
    const grid = district()
    box(grid, 37, 32, 20)
    const ahead = frame(grid, camera())
    const behind = frame(grid, camera({ yaw: Math.PI }))
    // Facing west there is nothing but the district boundary, far off.
    expect(behind.depth[COLUMNS / 2]).toBeGreaterThan(ahead.depth[COLUMNS / 2] * 4)
  })

  it('treats the district boundary as a flat wall so the void never shows', () => {
    const buffer = frame(district(), camera())
    // Perpendicular distance, so a flat wall reads the same across the view.
    expect(buffer.depth[COLUMNS / 2]).toBeCloseTo(64, 0)
    expect(buffer.depth[2]).toBeCloseTo(64, 0)
  })

  it('covers more rows the taller it is', () => {
    const short = district()
    box(short, 37, 32, 8)
    const tall = district()
    box(tall, 37, 32, 60)

    const wallRows = (grid: CollisionGrid) => {
      const buffer = frame(grid, camera())
      let count = 0
      for (let row = 0; row < ROWS; row += 1) {
        if (buffer.glyphAt(COLUMNS / 2, row) !== G_SPACE) count += 1
      }
      return count
    }
    expect(wallRows(tall)).toBeGreaterThan(wallRows(short))
  })

  it('covers more rows the closer it is', () => {
    const near = district()
    box(near, 35, 32, 30)
    const far = district()
    box(far, 50, 32, 30)

    const topRow = (grid: CollisionGrid) => {
      const buffer = frame(grid, camera())
      for (let row = 0; row < ROWS; row += 1) {
        if (buffer.glyphAt(COLUMNS / 2, row) !== G_SPACE) return row
      }
      return ROWS
    }
    expect(topRow(near)).toBeLessThan(topRow(far))
  })
})

describe('silhouettes', () => {
  it('lets a tower behind a low wall cut into the sky', () => {
    const grid = district()
    box(grid, 35, 32, 6) // a low wall right in front
    box(grid, 45, 32, 90) // a tower well behind it

    const withLayers = frame(grid, camera(), { ...DEFAULT_QUALITY, layers: 6 })
    const withoutLayers = frame(grid, camera(), { ...DEFAULT_QUALITY, layers: 1 })

    const topRow = (buffer: CellBuffer) => {
      for (let row = 0; row < ROWS; row += 1) {
        if (buffer.glyphAt(COLUMNS / 2, row) !== G_SPACE) return row
      }
      return ROWS
    }
    // With silhouettes the tower shows above the wall; without, it does not.
    expect(topRow(withLayers)).toBeLessThan(topRow(withoutLayers))
  })

  it('still reports the nearest wall as the depth, not the tower behind it', () => {
    const grid = district()
    box(grid, 35, 32, 6)
    box(grid, 45, 32, 90)
    const buffer = frame(grid, camera())
    expect(buffer.depth[COLUMNS / 2]).toBeLessThan(10)
  })
})

describe('other players', () => {
  const spriteAt = (x: number, y: number): Sprite => ({
    id: 2,
    x,
    y,
    animation: 1,
    nickname: 'violet-conduit',
    color: 2,
    avatar: 3,
  })

  function occupiedCells(buffer: CellBuffer, before: CellBuffer): number {
    let changed = 0
    for (let index = 0; index < buffer.data.length; index += CELL_STRIDE) {
      if (buffer.data[index] !== before.data[index]) changed += 1
    }
    return changed
  }

  it('draws someone standing in the open street', () => {
    const grid = district()
    const view = camera()
    const buffer = frame(grid, view)
    const before = new CellBuffer(COLUMNS, ROWS)
    before.data.set(buffer.data)

    renderSprites(buffer, view, [spriteAt(70, 64)], DEFAULT_QUALITY.fov, 0)
    expect(occupiedCells(buffer, before)).toBeGreaterThan(4)
  })

  it('hides someone standing behind a building, nameplate included', () => {
    const grid = district()
    // A facade wide enough to cover the whole view, not a single pillar.
    for (let cy = 20; cy < 44; cy += 1) box(grid, 34, cy, 30)
    const view = camera()
    const buffer = frame(grid, view)
    const before = new CellBuffer(COLUMNS, ROWS)
    before.data.set(buffer.data)

    renderSprites(buffer, view, [spriteAt(90, 64)], DEFAULT_QUALITY.fov, 0)
    expect(occupiedCells(buffer, before)).toBe(0)
  })

  it('still shows someone standing beside a narrow pillar', () => {
    const grid = district()
    box(grid, 34, 32, 30)
    const view = camera()
    const buffer = frame(grid, view)
    const before = new CellBuffer(COLUMNS, ROWS)
    before.data.set(buffer.data)

    // A two metre pillar does not hide a person standing to one side of it.
    renderSprites(buffer, view, [spriteAt(78, 58)], DEFAULT_QUALITY.fov, 0)
    expect(occupiedCells(buffer, before)).toBeGreaterThan(4)
  })

  it('ignores someone standing behind the camera', () => {
    const grid = district()
    const view = camera()
    const buffer = frame(grid, view)
    const before = new CellBuffer(COLUMNS, ROWS)
    before.data.set(buffer.data)

    renderSprites(buffer, view, [spriteAt(40, 64)], DEFAULT_QUALITY.fov, 0)
    expect(occupiedCells(buffer, before)).toBe(0)
  })

  it('spells a nickname without dropping a letter', () => {
    const grid = district()
    const view = camera()
    const buffer = frame(grid, view)
    renderSprites(buffer, view, [spriteAt(70, 64)], DEFAULT_QUALITY.fov, 0)

    const rendered = asText(buffer).join('\n')
    expect(rendered).toContain('violet-conduit')
  })
})

describe('the glyph vocabulary', () => {
  it('covers every character a nickname or a chat line can contain', () => {
    const printable = ' abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.,:;!?'
    for (const character of printable) {
      expect(CHARSET, `missing ${character}`).toContain(character)
    }
  })

  it('stays within the byte the cell buffer gives a glyph index', () => {
    expect(CHARSET.length).toBeLessThanOrEqual(256)
  })

  it('has no duplicate entries, which would waste atlas space', () => {
    expect(new Set(CHARSET).size).toBe(CHARSET.length)
  })
})
