/**
 * Client-side prediction and server reconciliation for the local player.
 *
 * The problem this solves: at 80 ms of latency, waiting for the server to confirm a
 * keypress before moving makes the game feel broken. So the client moves immediately and
 * keeps every unconfirmed input; when a snapshot arrives it says which input it had
 * processed, and the client replays everything after that from the server's position.
 *
 * The subtle part is what happens when the server *agrees*. Snapping to an authoritative
 * position that matches the prediction still produces a visible twitch, because the
 * replay lands a fraction of a tile away from where the player was drawn. So a small
 * disagreement is absorbed smoothly over a few frames and only a large one snaps. That
 * threshold is the difference between "responsive" and "rubber-banding", and it is the
 * one number here worth tuning by feel.
 *
 * Reference: Valve's "Latency Compensating Methods" and Gabriel Gambetta's
 * client-server-game-architecture series, both cited by TDD 15.
 */

import { POSITION_TOLERANCE_TILES } from '../domain/constants'
import { applyInput, type Point, type WalkableProbe } from './movement'

/** One input the client has sent and the server has not yet confirmed. */
export interface PendingInput {
  sequence: number
  axis: Point
  running: boolean
  deltaTime: number
}

/**
 * How far the server may disagree before the client snaps instead of easing.
 *
 * Below this the error is absorbed over several frames and the player sees nothing. Above
 * it, easing would be a lie: the player has genuinely been somewhere else (a collision the
 * client mispredicted, a knockback, a teleport) and pretending otherwise means walking
 * through a wall for half a second.
 */
const SNAP_THRESHOLD_TILES = 1.0

/**
 * Fraction of the remaining error removed per tick while easing.
 *
 * 0.25 clears 90% of it in about eight ticks, a quarter of a second at 30 Hz: fast enough
 * that the position is honest by the time it matters, slow enough to be invisible.
 */
const EASE_RATE = 0.25

export class Predictor {
  /** Where the simulation says the player is, before smoothing. */
  private simulated: Point = { x: 0, y: 0 }

  /**
   * The offset still being eased away, in tiles.
   *
   * Kept separate from the position rather than folded into it so that reconciliation
   * always works from the authoritative value. Folding it in would compound the error.
   */
  private error: Point = { x: 0, y: 0 }

  private pending: PendingInput[] = []
  private nextSequence = 1
  private classMultiplier = 1.0

  /** Diagnostics for the debug overlay, not used by the simulation. */
  readonly stats = { replays: 0, snaps: 0, lastReplayDepth: 0, lastErrorTiles: 0 }

  constructor(private walkable: WalkableProbe) {}

  /** Point the predictor at a new world. Called when the topology changes. */
  setWalkable(walkable: WalkableProbe): void {
    this.walkable = walkable
  }

  setClassMultiplier(multiplier: number): void {
    this.classMultiplier = multiplier
  }

  /** Hard reset to an authoritative position, on spawn or respawn. */
  reset(x: number, y: number): void {
    this.simulated = { x, y }
    this.error = { x: 0, y: 0 }
    this.pending = []
  }

  /** The position to draw: the simulation plus whatever error is still being eased. */
  get position(): Point {
    return { x: this.simulated.x + this.error.x, y: this.simulated.y + this.error.y }
  }

  /** The position to send to the server: the simulation, unsmoothed. */
  get predicted(): Point {
    return { ...this.simulated }
  }

  get pendingCount(): number {
    return this.pending.length
  }

  /**
   * Predict one input locally and record it for replay.
   *
   * Returns the sequence number, which the caller puts on the wire so the server can
   * acknowledge it.
   */
  push(axis: Point, running: boolean, deltaTime: number): number {
    const sequence = this.nextSequence
    this.nextSequence += 1

    this.pending.push({ sequence, axis, running, deltaTime })
    this.simulated = this.integrate(this.simulated, { sequence, axis, running, deltaTime })

    // Bound the queue. At 30 Hz this is two seconds of input; anything older than that
    // is not going to be acknowledged, and replaying it would be worse than dropping it.
    if (this.pending.length > 64) this.pending.splice(0, this.pending.length - 64)

    return sequence
  }

  /**
   * Fold in an authoritative position and replay the inputs the server had not seen.
   *
   * `acknowledged` is the highest sequence the server has processed. Everything at or
   * below it is history; everything above it has to be re-simulated from the
   * authoritative position, because the server's answer already includes their effect
   * only up to that point.
   */
  reconcile(authoritative: Point, acknowledged: number): void {
    // Drop confirmed inputs first, so the replay only covers what is genuinely pending.
    const stillPending = this.pending.filter((input) => input.sequence > acknowledged)
    this.pending = stillPending

    let replayed: Point = { ...authoritative }
    for (const input of stillPending) {
      replayed = this.integrate(replayed, input)
    }

    // Where the player is currently being drawn, so the correction can be measured
    // against what they can actually see rather than against the raw simulation.
    const drawn = this.position
    const dx = replayed.x - drawn.x
    const dy = replayed.y - drawn.y
    const distance = Math.hypot(dx, dy)

    this.stats.replays += 1
    this.stats.lastReplayDepth = stillPending.length
    this.stats.lastErrorTiles = distance

    this.simulated = replayed

    if (distance > SNAP_THRESHOLD_TILES) {
      // Genuinely somewhere else. Snapping is honest and the least confusing.
      this.error = { x: 0, y: 0 }
      this.stats.snaps += 1
    } else {
      // Keep drawing where the player was and walk the difference off over the next few
      // frames. Signs are inverted because `error` is added to the simulated position.
      this.error = { x: -dx, y: -dy }
    }
  }

  /**
   * Ease the outstanding error towards zero. Called once per rendered frame.
   *
   * Frame-rate independent: the per-tick rate is converted using the actual frame time so
   * the correction takes the same wall-clock duration at 30 fps as at 144.
   */
  advanceSmoothing(deltaTime: number): void {
    if (this.error.x === 0 && this.error.y === 0) return

    const ticks = deltaTime * 30
    const retained = Math.pow(1 - EASE_RATE, ticks)
    this.error = { x: this.error.x * retained, y: this.error.y * retained }

    // Below a sixteenth of a tile the remainder is sub-pixel; zeroing it stops the
    // multiply from running forever on a value nobody can see.
    if (Math.abs(this.error.x) < 1 / 16 && Math.abs(this.error.y) < 1 / 16) {
      this.error = { x: 0, y: 0 }
    }
  }

  /**
   * Whether the server has drifted far enough to be worth reporting.
   *
   * Used by the debug overlay, and a useful signal in its own right: a client that
   * repeatedly exceeds the server's own tolerance is mispredicting something real, not
   * just suffering from jitter.
   */
  get drifting(): boolean {
    return this.stats.lastErrorTiles > POSITION_TOLERANCE_TILES
  }

  private integrate(from: Point, input: PendingInput): Point {
    const result = applyInput(
      this.walkable,
      from,
      input.axis,
      input.running,
      input.deltaTime,
      this.classMultiplier,
    )
    return { x: result.x, y: result.y }
  }
}
