/**
 * Glyph atlas baked once at startup with Canvas2D.
 *
 * Two channels come out of it: red is the crisp glyph, green is the same glyph
 * blurred. The shader adds a little of the green back on top, which is what
 * gives characters their neon bleed without a separate bloom pass.
 */

import { CHARSET } from './charset'

export interface GlyphAtlas {
  canvas: HTMLCanvasElement
  /** Cell size in the atlas, in pixels. */
  cellWidth: number
  cellHeight: number
  columns: number
  rows: number
  /** Font stack the atlas was rasterised with, reused by the 2D fallback. */
  fontFamily: string
}

const FONT_STACK =
  '"Cascadia Mono", "JetBrains Mono", "Fira Code", "DejaVu Sans Mono", ' +
  'Menlo, Consolas, "Courier New", monospace'

const ATLAS_COLUMNS = 16

export function buildGlyphAtlas(cellWidth = 16, cellHeight = 32): GlyphAtlas {
  const columns = ATLAS_COLUMNS
  const rows = Math.ceil(CHARSET.length / columns)
  const canvas = document.createElement('canvas')
  canvas.width = columns * cellWidth
  canvas.height = rows * cellHeight

  const context = canvas.getContext('2d', { willReadFrequently: false })
  if (!context) throw new Error('This browser cannot rasterise the glyph atlas.')

  context.clearRect(0, 0, canvas.width, canvas.height)
  context.textAlign = 'center'
  context.textBaseline = 'middle'
  // Box-drawing characters are designed to touch the cell edges, so the font
  // size follows the cell height rather than leaving a comfortable margin.
  context.font = `${Math.round(cellHeight * 0.82)}px ${FONT_STACK}`

  // Pass one: the blurred copy into green.
  context.globalCompositeOperation = 'source-over'
  context.fillStyle = '#00ff00'
  context.shadowColor = '#00ff00'
  context.shadowBlur = Math.max(2, Math.round(cellWidth * 0.35))
  drawAll(context, cellWidth, cellHeight, columns)

  // Pass two: the crisp copy into red, added on top of the glow.
  context.shadowBlur = 0
  context.globalCompositeOperation = 'lighter'
  context.fillStyle = '#ff0000'
  drawAll(context, cellWidth, cellHeight, columns)
  context.globalCompositeOperation = 'source-over'

  return { canvas, cellWidth, cellHeight, columns, rows, fontFamily: FONT_STACK }
}

function drawAll(
  context: CanvasRenderingContext2D,
  cellWidth: number,
  cellHeight: number,
  columns: number,
): void {
  for (let index = 0; index < CHARSET.length; index += 1) {
    const character = CHARSET[index]
    if (character === ' ') continue
    const column = index % columns
    const row = Math.floor(index / columns)
    context.fillText(
      character,
      column * cellWidth + cellWidth / 2,
      row * cellHeight + cellHeight / 2,
      cellWidth,
    )
  }
}
