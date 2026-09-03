/**
 * Canvas2D fallback for machines without WebGL2.
 *
 * Drawing 14 000 characters one at a time is far too slow, so cells are
 * grouped into runs that share a colour and drawn as strings. The result is a
 * dimmer city — there is no cheap glow here — but it is the same city.
 */

import { CELL_STRIDE } from './cellBuffer'
import type { CellBuffer } from './cellBuffer'
import { CHARSET } from './charset'
import type { GlyphAtlas } from './glyphAtlas'

export class CanvasCellRenderer {
  private readonly context: CanvasRenderingContext2D
  private cellWidth = 8
  private cellHeight = 16

  constructor(
    private readonly canvas: HTMLCanvasElement,
    private readonly atlas: GlyphAtlas,
  ) {
    const context = canvas.getContext('2d', { alpha: false })
    if (!context) throw new Error('This browser provides no 2D canvas either.')
    this.context = context
    this.context.textBaseline = 'top'
  }

  draw(buffer: CellBuffer): void {
    const context = this.context
    const width = this.canvas.width
    const height = this.canvas.height
    this.cellWidth = width / buffer.columns
    this.cellHeight = height / buffer.rows
    context.font = `${Math.round(this.cellHeight * 0.86)}px ${this.atlas.fontFamily}`

    const data = buffer.data
    for (let row = 0; row < buffer.rows; row += 1) {
      const y = row * this.cellHeight
      let column = 0
      // Backgrounds first: long horizontal runs of one colour are common.
      while (column < buffer.columns) {
        const at = (row * buffer.columns + column) * CELL_STRIDE
        const key = (data[at + 5] << 16) | (data[at + 6] << 8) | data[at + 7]
        let span = 1
        while (column + span < buffer.columns) {
          const next = (row * buffer.columns + column + span) * CELL_STRIDE
          const nextKey = (data[next + 5] << 16) | (data[next + 6] << 8) | data[next + 7]
          if (nextKey !== key) break
          span += 1
        }
        context.fillStyle = `rgb(${data[at + 5]},${data[at + 6]},${data[at + 7]})`
        context.fillRect(
          Math.floor(column * this.cellWidth),
          Math.floor(y),
          Math.ceil(span * this.cellWidth) + 1,
          Math.ceil(this.cellHeight) + 1,
        )
        column += span
      }

      column = 0
      while (column < buffer.columns) {
        const at = (row * buffer.columns + column) * CELL_STRIDE
        if (data[at] === 0) {
          column += 1
          continue
        }
        const key = (data[at + 2] << 16) | (data[at + 3] << 8) | data[at + 4]
        let text = CHARSET[data[at]]
        let span = 1
        while (column + span < buffer.columns) {
          const next = (row * buffer.columns + column + span) * CELL_STRIDE
          const nextKey = (data[next + 2] << 16) | (data[next + 3] << 8) | data[next + 4]
          if (nextKey !== key || data[next] === 0) break
          text += CHARSET[data[next]]
          span += 1
        }
        context.fillStyle = `rgb(${data[at + 2]},${data[at + 3]},${data[at + 4]})`
        // A run drawn as one string relies on the font being monospace, which
        // the atlas font stack guarantees.
        context.fillText(text, column * this.cellWidth, y)
        column += span
      }
    }
  }

  dispose(): void {
    /* Nothing to release: the 2D context dies with the canvas. */
  }
}
