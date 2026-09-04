/**
 * Client-side prediction and reconciliation.
 *
 * The player moves the instant a key goes down, but the server still owns the
 * result. When a snapshot acknowledges input N, we rewind to the acknowledged
 * position, replay everything after N, and blend the leftover error away over
 * a few frames so a correction reads as a nudge rather than a teleport.
 */

import { EYE_HEIGHT_M, POSITION_SCALE } from '../domain/constants'
import type { CollisionGrid } from '../world/collisionGrid'
import type { InputCommand } from '../net/wire'
import { movePlayer, type MovableState } from './movement'

/**
 * Positions arrive quantised to centimetres, so a mismatch below the
 * quantisation step is noise, not a divergence.
 *
 * Rounding two axes can be off by `sqrt(2) / 2` centimetres, and the replay
 * amplifies that: a rewind that lands half a centimetre on the wrong side of a
 * cell boundary flips `isFreeCircle`, which rejects a whole step instead of
 * part of one. The threshold therefore sits well above the rounding rather
 * than at it, and inside it the client keeps its own unrounded position.
 */
const IGNORED_ERROR_M = 3 / POSITION_SCALE

/** Past this the client is provably wrong (packet loss, a nudge, a respawn). */
const SNAP_ERROR_M = 2.5

/** Fraction of the remaining error removed per second while blending. */
const CORRECTION_PER_SECOND = 12

export interface PredictionOffset {
  x: number
  y: number
}

export class Predictor {
  private readonly pending: InputCommand[] = []
  /** Visual minus authoritative, decayed towards zero every frame. */
  readonly offset: PredictionOffset = { x: 0, y: 0 }
  lastCorrectionM = 0

  constructor(readonly state: MovableState) {}

  /** Apply an input locally and remember it until the server confirms it. */
  push(command: InputCommand, grid: CollisionGrid, dt: number): void {
    movePlayer(this.state, command, grid, dt)
    this.pending.push(command)
    // A second of unacknowledged input is already a broken connection.
    if (this.pending.length > 64) this.pending.shift()
  }

  get pendingCount(): number {
    return this.pending.length
  }

  /**
   * Rewind to the authoritative position and replay unacknowledged input.
   *
   * `dt` is the fixed simulation step, because that is what the server used.
   */
  reconcile(
    authoritative: { x: number; y: number; z?: number; velocityZ?: number },
    ackSequence: number,
    grid: CollisionGrid,
    dt: number,
  ): void {
    while (this.pending.length > 0 && seqLessOrEqual(this.pending[0].sequence, ackSequence)) {
      this.pending.shift()
    }

    const predictedX = this.state.x
    const predictedY = this.state.y
    const predictedZ = this.state.z
    const predictedVelocityZ = this.state.velocityZ

    this.state.x = authoritative.x
    this.state.y = authoritative.y
    if (authoritative.z !== undefined) this.state.z = authoritative.z
    if (authoritative.velocityZ !== undefined) this.state.velocityZ = authoritative.velocityZ
    for (const command of this.pending) movePlayer(this.state, command, grid, dt)

    const errorX = predictedX - this.state.x
    const errorY = predictedY - this.state.y
    const error = Math.hypot(errorX, errorY)
    this.lastCorrectionM = error

    if (error <= IGNORED_ERROR_M) {
      // The server confirmed what we already had. Adopting its rounded value
      // would push our float off the server's by half a centimetre for good,
      // and near a facade that is the difference between sliding along the
      // wall and being refused the step entirely.
      this.state.x = predictedX
      this.state.y = predictedY
      if (Math.abs(predictedZ - this.state.z) <= IGNORED_ERROR_M) {
        this.state.z = predictedZ
        this.state.velocityZ = predictedVelocityZ
      }
      this.offset.x = 0
      this.offset.y = 0
      return
    }
    if (error > SNAP_ERROR_M) {
      // Too large to hide; show the truth.
      this.offset.x = 0
      this.offset.y = 0
      return
    }
    // Carry the old visual position forward and let it decay into the new one.
    this.offset.x += errorX
    this.offset.y += errorY
  }

  /** Position to render this frame: authoritative plus the decaying error. */
  view(dt: number): { x: number; y: number; z: number } {
    const decay = Math.exp(-CORRECTION_PER_SECOND * Math.max(dt, 0))
    this.offset.x *= decay
    this.offset.y *= decay
    if (Math.abs(this.offset.x) < 1e-4) this.offset.x = 0
    if (Math.abs(this.offset.y) < 1e-4) this.offset.y = 0
    return {
      x: this.state.x + this.offset.x,
      y: this.state.y + this.offset.y,
      z: this.state.z,
    }
  }

  reset(x: number, y: number, z = EYE_HEIGHT_M): void {
    this.pending.length = 0
    this.state.x = x
    this.state.y = y
    this.state.z = z
    this.state.velocityZ = 0
    this.offset.x = 0
    this.offset.y = 0
    this.lastCorrectionM = 0
  }
}

/** Sequence numbers are u32 and wrap; compare on the short arc. */
export function seqLessOrEqual(a: number, b: number): boolean {
  return ((b - a) >>> 0) < 0x80000000
}
