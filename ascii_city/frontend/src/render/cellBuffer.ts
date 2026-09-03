/**
 * The character grid the renderer draws.
 *
 * One interleaved byte array holds everything the GPU needs, so a frame is a
 * single buffer upload. Layout per cell, stride 8:
 *
 *   0 glyph index   1 effect flags   2..4 foreground rgb   5..7 background rgb
 */

export const CELL_STRIDE = 8

export const EFFECT_NONE = 0
/** Adds extra bloom in the shader: neon signage, lit windows, avatars. */
export const EFFECT_GLOW = 1

export class CellBuffer {
  data: Uint8Array
  /** Per-column depth of the nearest wall, used by the sprite pass. */
  depth: Float32Array

  constructor(
    public columns: number,
    public rows: number,
  ) {
    this.data = new Uint8Array(columns * rows * CELL_STRIDE)
    this.depth = new Float32Array(columns)
  }

  get cellCount(): number {
    return this.columns * this.rows
  }

  resize(columns: number, rows: number): void {
    if (columns === this.columns && rows === this.rows) return
    this.columns = columns
    this.rows = rows
    this.data = new Uint8Array(columns * rows * CELL_STRIDE)
    this.depth = new Float32Array(columns)
  }

  clear(): void {
    this.data.fill(0)
    this.depth.fill(Infinity)
  }

  set(
    column: number,
    row: number,
    glyph: number,
    fr: number,
    fg: number,
    fb: number,
    br: number,
    bg: number,
    bb: number,
    effect: number = EFFECT_NONE,
  ): void {
    if (column < 0 || row < 0 || column >= this.columns || row >= this.rows) return
    const at = (row * this.columns + column) * CELL_STRIDE
    const data = this.data
    data[at] = glyph
    data[at + 1] = effect
    data[at + 2] = fr
    data[at + 3] = fg
    data[at + 4] = fb
    data[at + 5] = br
    data[at + 6] = bg
    data[at + 7] = bb
  }

  glyphAt(column: number, row: number): number {
    return this.data[(row * this.columns + column) * CELL_STRIDE]
  }
}
