/**
 * Entity interpolation for everything that is not the local player.
 *
 * Snapshots arrive 15 times a second but the screen redraws 60 or more, so remote entities
 * have to be drawn between the positions the server reported. The trick is to render them
 * deliberately in the past — one snapshot interval behind — so there are always two
 * samples to interpolate between and no need to guess.
 *
 * That delay is a real cost: you see other players where they were ~66 ms ago. It is paid
 * because the alternative, extrapolating forward, is wrong whenever someone changes
 * direction, and being wrong about a position looks far worse than being late about it.
 * The server compensates for the delay when resolving abilities, which is what makes
 * aiming at the drawn position fair (`lag_compensation_window_ms` in the combat code).
 *
 * Reference: Valve's source multiplayer networking notes, cited by TDD 15.2.
 */

import { INTERPOLATION_BUFFER_SNAPSHOTS, SNAPSHOT_INTERVAL_SECONDS } from '../domain/constants'

export interface Sample {
  time: number
  x: number
  y: number
  facing: number
}

export interface Pose {
  x: number
  y: number
  facing: number
  /** Tiles per second, derived from the samples. Drives the walk animation. */
  speed: number
}

/**
 * How far behind the newest snapshot to render.
 *
 * One interval would leave nothing to interpolate into the moment a packet is late, so the
 * buffer is deliberately deeper than the minimum.
 */
export const RENDER_DELAY_SECONDS = SNAPSHOT_INTERVAL_SECONDS * INTERPOLATION_BUFFER_SNAPSHOTS

/** Shortest signed angular difference, so a turn never takes the long way round. */
function angleDelta(from: number, to: number): number {
  const turn = Math.PI * 2
  let delta = (to - from) % turn
  if (delta > Math.PI) delta -= turn
  if (delta < -Math.PI) delta += turn
  return delta
}

/**
 * A ring of recent positions for one entity, queried at a render timestamp.
 *
 * Sized to hold about a second of history. That is far more than interpolation needs, but
 * it is also what the client uses to draw a trail behind a moving entity and to answer
 * "where was this a moment ago" for hit sparks.
 */
export class Track {
  private samples: Sample[] = []

  constructor(private readonly capacity = 24) {}

  get latest(): Sample | undefined {
    return this.samples[this.samples.length - 1]
  }

  get length(): number {
    return this.samples.length
  }

  /**
   * Record a server position.
   *
   * Out-of-order samples are dropped rather than sorted in. Over a WebSocket they cannot
   * happen — TCP delivers in order — but a duplicated snapshot after a reconnect can, and
   * inserting one in the middle would make an entity briefly walk backwards.
   */
  push(sample: Sample): void {
    const newest = this.latest
    if (newest && sample.time <= newest.time) return

    this.samples.push(sample)
    if (this.samples.length > this.capacity) this.samples.shift()
  }

  /** Forget everything, on despawn or a topology change. */
  clear(): void {
    this.samples = []
  }

  /**
   * The pose to draw at `renderTime`, which the caller has already put in the past.
   *
   * Three cases: between two samples, interpolate; before the oldest, clamp to it, which
   * happens for one frame after an entity spawns; after the newest, hold position rather
   * than extrapolate. Holding briefly is why a lagging entity appears to pause instead of
   * sliding off in the direction it was last going and snapping back.
   */
  poseAt(renderTime: number): Pose | undefined {
    if (this.samples.length === 0) return undefined
    if (this.samples.length === 1) {
      const only = this.samples[0]
      return { x: only.x, y: only.y, facing: only.facing, speed: 0 }
    }

    const oldest = this.samples[0]
    if (renderTime <= oldest.time) {
      return { x: oldest.x, y: oldest.y, facing: oldest.facing, speed: 0 }
    }

    const newest = this.samples[this.samples.length - 1]
    if (renderTime >= newest.time) {
      const previous = this.samples[this.samples.length - 2]
      const span = newest.time - previous.time
      const speed = span > 0 ? Math.hypot(newest.x - previous.x, newest.y - previous.y) / span : 0
      return { x: newest.x, y: newest.y, facing: newest.facing, speed }
    }

    // Walk backwards: the answer is almost always in the last pair, so a linear scan from
    // the end beats a binary search on a buffer this small.
    for (let i = this.samples.length - 1; i > 0; i -= 1) {
      const after = this.samples[i]
      const before = this.samples[i - 1]
      if (renderTime >= before.time && renderTime <= after.time) {
        const span = after.time - before.time
        const t = span > 0 ? (renderTime - before.time) / span : 0
        const speed = span > 0 ? Math.hypot(after.x - before.x, after.y - before.y) / span : 0
        return {
          x: before.x + (after.x - before.x) * t,
          y: before.y + (after.y - before.y) * t,
          // Interpolated as a rotation, not a number, or an entity crossing the seam
          // between 359 and 1 degrees would spin all the way round.
          facing: before.facing + angleDelta(before.facing, after.facing) * t,
          speed,
        }
      }
    }

    return { x: newest.x, y: newest.y, facing: newest.facing, speed: 0 }
  }

  /** Drop samples older than `before`, to stop a long session from growing memory. */
  prune(before: number): void {
    while (this.samples.length > 2 && this.samples[0].time < before) this.samples.shift()
  }
}

/**
 * Estimates the offset between the server's clock and the local one.
 *
 * Interpolation needs snapshot timestamps on the same timeline as the render loop, and the
 * two clocks have no fixed relationship. The offset is taken as the *minimum* seen rather
 * than an average, because the minimum corresponds to the least-delayed packet, which is
 * the closest thing to the true offset. Averaging would fold every network hiccup into the
 * estimate permanently.
 */
export class ClockSync {
  private offset = 0
  private best = Number.POSITIVE_INFINITY
  private samples = 0
  latencyMs = 0

  /** Feed a pong. All three times are in seconds on their own clock. */
  observePong(clientTime: number, serverTime: number, now: number): void {
    const roundTrip = now - clientTime

    // Smoothed rather than instantaneous. The round trip is measured to the moment the reply
    // is handled on the main thread, so one long frame — a chunk build, a garbage collection —
    // lands in the sample as if it were network delay, and a raw reading latches that spike
    // on screen until the next pong seconds later. The average moves for a real change in
    // conditions and shrugs off a single stall.
    const sample = Math.max(0, roundTrip * 1000) / 2
    this.latencyMs = this.samples === 0 ? sample : this.latencyMs * 0.8 + sample * 0.2

    if (roundTrip < this.best) {
      this.best = roundTrip
      // The server's timestamp was taken about half a round trip ago.
      this.offset = serverTime + roundTrip / 2 - now
    }
    this.samples += 1

    // Re-baseline every few minutes. Clocks drift, and a single lucky early sample would
    // otherwise stay authoritative for the whole session.
    if (this.samples % 600 === 0) this.best = roundTrip
  }

  /** A server timestamp converted to local time. */
  toLocal(serverTime: number): number {
    return serverTime - this.offset
  }

  /** The local time to render remote entities at, delay included. */
  renderTime(now: number): number {
    return now - RENDER_DELAY_SECONDS
  }

  get ready(): boolean {
    return this.samples > 0
  }

  /** The estimated server-minus-local offset, in seconds. For the diagnostics overlay. */
  get offsetSeconds(): number {
    return this.offset
  }
}
