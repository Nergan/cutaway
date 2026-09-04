/**
 * Rain, snow, and storm, as a screen-space particle layer.
 *
 * Screen space rather than world space on purpose: precipitation is between the camera and the
 * world, and tying it to world coordinates would make it slide when the camera pans, which
 * reads as the rain being painted on the ground.
 *
 * Drawn as one `Graphics` rebuilt each frame rather than as a sprite per drop. A few hundred
 * line segments in one geometry is a single draw call; a few hundred sprites is a few hundred
 * transforms, and the drops are two-pixel streaks that no one will inspect closely.
 */

import { Container, Graphics } from 'pixi.js'

import type { WeatherParticles } from './atmosphere'

interface Drop {
  x: number
  y: number
  /** Per-drop speed multiplier, so the field has depth instead of falling as a sheet. */
  scale: number
}

export class WeatherLayer {
  readonly root = new Container()

  private readonly graphics = new Graphics()
  private readonly drops: Drop[] = []

  private width = 1
  private height = 1
  /** Horizontal phase, so snow drifts rather than falling dead straight. */
  private phase = 0

  constructor() {
    this.root.addChild(this.graphics)
  }

  resize(width: number, height: number): void {
    this.width = Math.max(1, width)
    this.height = Math.max(1, height)
  }

  /**
   * Advance and redraw.
   *
   * `params.count` is sized for a 1080p viewport in `atmosphere.ts`, and scaled here by the
   * actual area, so a small window is not filled with a blizzard.
   */
  update(params: WeatherParticles, deltaSeconds: number): void {
    const wanted =
      params.count === 0
        ? 0
        : Math.round(params.count * Math.min(2, (this.width * this.height) / (1920 * 1080)))

    if (wanted === 0) {
      if (this.drops.length > 0) this.drops.length = 0
      this.graphics.clear()
      this.root.visible = false
      return
    }
    this.root.visible = true

    while (this.drops.length < wanted) this.drops.push(this.spawn(Math.random() * this.height))
    if (this.drops.length > wanted) this.drops.length = wanted

    this.phase += deltaSeconds
    // Snow sways; rain does not. The check is on speed because a slow particle is snow.
    const swaying = params.speed < 200
    const sway = swaying ? Math.sin(this.phase * 1.3) * params.drift * 0.5 : 0

    this.graphics.clear()

    for (const drop of this.drops) {
      drop.y += params.speed * drop.scale * deltaSeconds
      drop.x += (params.drift * drop.scale + sway) * deltaSeconds

      // Wrap rather than respawn: a drop that leaves the bottom re-enters at the top with its
      // own speed intact, which keeps the field's depth stable instead of resampling it.
      if (drop.y > this.height) {
        drop.y -= this.height + params.length
        drop.x = Math.random() * (this.width + Math.abs(params.drift))
      }
      if (drop.x > this.width + params.length) drop.x -= this.width + params.length * 2
      else if (drop.x < -params.length) drop.x += this.width + params.length * 2

      if (params.length <= 3) {
        // Snow: a dot, sized by its depth so the near flakes read as nearer.
        const size = 1 + Math.round(drop.scale)
        this.graphics.rect(drop.x, drop.y, size, size)
      } else {
        // Rain: a streak along its own velocity, so the wind is visible in the drop.
        const fall = params.length * drop.scale
        const lean = (params.drift / params.speed) * fall
        this.graphics.moveTo(drop.x, drop.y).lineTo(drop.x + lean, drop.y + fall)
      }
    }

    const colour =
      (Math.round(params.colour[0] * 255) << 16) |
      (Math.round(params.colour[1] * 255) << 8) |
      Math.round(params.colour[2] * 255)

    if (params.length <= 3) this.graphics.fill({ color: colour, alpha: params.alpha })
    else this.graphics.stroke({ color: colour, alpha: params.alpha, width: 1 })
  }

  private spawn(y: number): Drop {
    return {
      x: Math.random() * this.width,
      y,
      // A narrow spread: too wide and the slowest drops appear to hang in the air.
      scale: 0.7 + Math.random() * 0.6,
    }
  }

  destroy(): void {
    this.graphics.destroy()
    this.root.destroy()
  }
}
