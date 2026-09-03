/**
 * Renderer facade: owns the character grid, the backend and adaptive quality.
 *
 * Quality is expressed as the size of a character cell in CSS pixels. Bigger
 * cells mean fewer rays, which is the only knob that meaningfully changes cost
 * here, so the auto-tuner moves that first and only then drops the extras.
 */

import type { CollisionGrid } from '../world/collisionGrid'
import { CellBuffer } from './cellBuffer'
import { CanvasCellRenderer } from './canvasRenderer'
import { buildGlyphAtlas, type GlyphAtlas } from './glyphAtlas'
import { DEFAULT_QUALITY, Raycaster, type Camera, type RaycastQuality } from './raycaster'
import { renderSprites, type Sprite } from './sprites'
import { WebGLCellRenderer } from './webglRenderer'

export type QualityPreset = 'auto' | 'high' | 'balanced' | 'low'

export interface RendererStats {
  backend: 'webgl2' | 'canvas2d'
  columns: number
  rows: number
  cellPixels: number
  frameMs: number
  fps: number
}

/** Cell width in CSS pixels for each rung of the quality ladder. */
const LADDER = [3, 4, 5, 6, 8, 10]
const CELL_ASPECT = 2

const TARGET_FRAME_MS = 1000 / 60
const RELAX_FRAME_MS = 1000 / 50

export class Renderer {
  private readonly atlas: GlyphAtlas
  private readonly buffer = new CellBuffer(1, 1)
  private readonly raycaster = new Raycaster({ ...DEFAULT_QUALITY })
  private backend: WebGLCellRenderer | CanvasCellRenderer
  private readonly backendName: 'webgl2' | 'canvas2d'

  private rung = 0
  private preset: QualityPreset = 'auto'
  private frameMs = TARGET_FRAME_MS
  private sinceAdjust = 0
  private cssWidth = 1
  private cssHeight = 1

  constructor(private readonly canvas: HTMLCanvasElement) {
    this.atlas = buildGlyphAtlas()
    try {
      this.backend = new WebGLCellRenderer(canvas, this.atlas)
      this.backendName = 'webgl2'
    } catch {
      this.backend = new CanvasCellRenderer(canvas, this.atlas)
      this.backendName = 'canvas2d'
      // Software text rendering cannot afford a dense grid.
      this.rung = 3
    }
  }

  get stats(): RendererStats {
    return {
      backend: this.backendName,
      columns: this.buffer.columns,
      rows: this.buffer.rows,
      cellPixels: LADDER[this.rung],
      frameMs: this.frameMs,
      fps: this.frameMs > 0 ? 1000 / this.frameMs : 0,
    }
  }

  get quality(): RaycastQuality {
    return this.raycaster.quality
  }

  setPreset(preset: QualityPreset): void {
    this.preset = preset
    if (preset === 'high') this.rung = this.backendName === 'webgl2' ? 0 : 2
    if (preset === 'balanced') this.rung = 2
    if (preset === 'low') this.rung = 4
    this.applyRung()
    this.resize(this.cssWidth, this.cssHeight)
  }

  setFieldOfView(degrees: number): void {
    this.raycaster.quality.fov = (Math.min(110, Math.max(55, degrees)) * Math.PI) / 180
  }

  resize(cssWidth: number, cssHeight: number): void {
    this.cssWidth = Math.max(1, cssWidth)
    this.cssHeight = Math.max(1, cssHeight)
    const cell = LADDER[this.rung]
    const columns = Math.max(24, Math.floor(this.cssWidth / cell))
    const rows = Math.max(14, Math.floor(this.cssHeight / (cell * CELL_ASPECT)))
    this.buffer.resize(columns, rows)

    // Render at exactly one atlas cell per character: sharper than the CSS
    // size and still far below the cost of a full-resolution framebuffer.
    const deviceCell = this.backendName === 'webgl2' ? 8 : Math.max(6, Math.round(cell * 0.75))
    this.canvas.width = columns * deviceCell
    this.canvas.height = rows * deviceCell * CELL_ASPECT
    this.canvas.style.width = `${this.cssWidth}px`
    this.canvas.style.height = `${this.cssHeight}px`
  }

  render(grid: CollisionGrid, camera: Camera, sprites: Sprite[], dt: number): void {
    const started = performance.now()
    this.raycaster.time += dt
    this.raycaster.render(this.buffer, grid, camera)
    renderSprites(this.buffer, camera, sprites, this.raycaster.quality.fov, this.raycaster.time)
    this.backend.draw(this.buffer)

    const elapsed = performance.now() - started
    // An exponential average keeps one slow frame from flipping the quality.
    this.frameMs += (elapsed - this.frameMs) * 0.1
    this.autoTune(dt)
  }

  dispose(): void {
    this.backend.dispose()
  }

  private autoTune(dt: number): void {
    if (this.preset !== 'auto') return
    this.sinceAdjust += dt
    if (this.sinceAdjust < 1.5) return

    if (this.frameMs > RELAX_FRAME_MS && this.rung < LADDER.length - 1) {
      this.rung += 1
    } else if (this.frameMs < TARGET_FRAME_MS * 0.55 && this.rung > 0) {
      this.rung -= 1
    } else {
      this.sinceAdjust = 0
      return
    }
    this.sinceAdjust = 0
    this.applyRung()
    this.resize(this.cssWidth, this.cssHeight)
  }

  /** Coarser grids also get shorter draw distance and fewer silhouettes. */
  private applyRung(): void {
    const quality = this.raycaster.quality
    quality.layers = this.rung <= 1 ? 8 : this.rung <= 3 ? 5 : 3
    quality.viewDistance = this.rung <= 1 ? 240 : this.rung <= 3 ? 190 : 140
    quality.groundDetail = this.rung <= 4
    if (this.backend instanceof WebGLCellRenderer) {
      this.backend.glow = this.rung <= 2 ? 0.55 : 0.35
    }
  }
}
