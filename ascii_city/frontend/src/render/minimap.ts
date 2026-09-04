/**
 * The district seen from above.
 *
 * The map itself never changes, so it is rasterised once into an offscreen
 * canvas at one pixel per cell. Drawing a frame is then a single `drawImage`
 * crop plus a handful of dots, which is cheap enough to run on its own rAF
 * next to the raycaster.
 */

import {
  CELL_BLOCKED,
  CELL_BUILDING,
  CELL_INTERACTIVE,
  CELL_ROAD,
  CELL_SIDEWALK,
  CELL_WATER,
} from '../domain/constants'
import type { CollisionGrid } from '../world/collisionGrid'

export interface MinimapSource {
  canvas: HTMLCanvasElement
  /** Cells across and down, which is also the canvas size in pixels. */
  width: number
  height: number
  cellSize: number
}

/**
 * 0xRRGGBB per collision code, indexed directly by the code.
 *
 * Streets are the bright part and buildings the dark mass, which is the wrong
 * way round for a photograph and the right way round for a map: what you read
 * a minimap for is where you can go.
 */
const CELL_INK: readonly number[] = [
  0x0a0f14, // free
  0x1d242e, // building
  0x123044, // water
  0x16211a, // blocked (parks, planters)
  0x3b4858, // road
  0x2b3543, // sidewalk
  0xc08a4a, // interactive (doors, kiosks)
]

/** Buildings get a height tint so towers read differently from low blocks. */
const TALL_INK = 0x46566d

export function buildMinimap(grid: CollisionGrid): MinimapSource {
  const canvas = document.createElement('canvas')
  canvas.width = grid.width
  canvas.height = grid.height

  const context = canvas.getContext('2d')
  if (!context) throw new Error('This browser cannot rasterise the minimap.')

  const image = context.createImageData(grid.width, grid.height)
  const pixels = image.data

  for (let index = 0; index < grid.cells.length; index += 1) {
    const code = grid.cells[index]
    let ink = CELL_INK[code] ?? CELL_INK[0]

    if (code === CELL_BUILDING) {
      // heights are metres in one byte; 60 m and up is a tower.
      const lift = Math.min(1, grid.heights[index] / 60)
      ink = blend(ink, TALL_INK, lift)
    }

    const at = index * 4
    pixels[at] = (ink >> 16) & 0xff
    pixels[at + 1] = (ink >> 8) & 0xff
    pixels[at + 2] = ink & 0xff
    pixels[at + 3] = 255
  }

  context.putImageData(image, 0, 0)
  return { canvas, width: grid.width, height: grid.height, cellSize: grid.cellSize }
}

function blend(from: number, to: number, amount: number): number {
  const r = ((from >> 16) & 0xff) + (((to >> 16) & 0xff) - ((from >> 16) & 0xff)) * amount
  const g = ((from >> 8) & 0xff) + (((to >> 8) & 0xff) - ((from >> 8) & 0xff)) * amount
  const b = (from & 0xff) + ((to & 0xff) - (from & 0xff)) * amount
  return (Math.round(r) << 16) | (Math.round(g) << 8) | Math.round(b)
}

/** Codes a player can stand on, kept here so the legend and the map agree. */
export const WALKABLE_INK_CODES = [CELL_ROAD, CELL_SIDEWALK, CELL_INTERACTIVE] as const
export const SOLID_INK_CODES = [CELL_BUILDING, CELL_WATER, CELL_BLOCKED] as const
