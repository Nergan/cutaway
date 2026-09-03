/**
 * Remote players are drawn in the past.
 *
 * Snapshots land every 50 ms, and the frame rate is not a multiple of that, so
 * rendering the newest sample directly makes other people stutter. Holding a
 * short buffer and sampling it one snapshot behind trades a fixed 50 ms of
 * latency for motion that never jumps.
 */

import { SNAPSHOT_HZ, TAU } from '../domain/constants'
import type { SnapshotEntry } from '../net/wire'

export const INTERPOLATION_DELAY_MS = 1000 / SNAPSHOT_HZ

/** Beyond this the player was gone long enough that a slide would be a lie. */
const EXTRAPOLATION_LIMIT_MS = 250

interface Sample {
  t: number
  x: number
  y: number
  yaw: number
  pitch: number
  animation: number
  simplified: boolean
}

export interface InterpolatedPlayer {
  id: number
  x: number
  y: number
  yaw: number
  pitch: number
  animation: number
  simplified: boolean
}

/** Shortest-arc angle blend, so a player crossing north does not spin around. */
export function lerpAngle(from: number, to: number, alpha: number): number {
  const delta = ((((to - from) % TAU) + TAU + Math.PI) % TAU) - Math.PI
  return from + delta * alpha
}

class Track {
  readonly samples: Sample[] = []

  push(sample: Sample): void {
    const last = this.samples[this.samples.length - 1]
    if (last && sample.t <= last.t) return
    this.samples.push(sample)
    if (this.samples.length > 24) this.samples.shift()
  }

  /** Drop everything older than the sample still needed at `renderTime`. */
  prune(renderTime: number): void {
    while (this.samples.length > 2 && this.samples[1].t <= renderTime) {
      this.samples.shift()
    }
  }

  sample(renderTime: number): Sample | null {
    const count = this.samples.length
    if (count === 0) return null
    if (count === 1) return this.samples[0]

    for (let index = 0; index < count - 1; index += 1) {
      const a = this.samples[index]
      const b = this.samples[index + 1]
      if (renderTime >= a.t && renderTime <= b.t) {
        const span = b.t - a.t
        const alpha = span > 0 ? (renderTime - a.t) / span : 1
        return {
          t: renderTime,
          x: a.x + (b.x - a.x) * alpha,
          y: a.y + (b.y - a.y) * alpha,
          yaw: lerpAngle(a.yaw, b.yaw, alpha),
          pitch: a.pitch + (b.pitch - a.pitch) * alpha,
          animation: b.animation,
          simplified: b.simplified,
        }
      }
    }

    if (renderTime < this.samples[0].t) return this.samples[0]
    // Ahead of the buffer: hold the last pose rather than invent motion.
    return this.samples[count - 1]
  }
}

/** One buffer per remote player, fed by snapshots and read by the renderer. */
export class InterpolationBuffer {
  private readonly tracks = new Map<number, Track>()

  ingest(entries: SnapshotEntry[], receivedAt: number): void {
    for (const entry of entries) {
      let track = this.tracks.get(entry.id)
      if (!track) {
        track = new Track()
        this.tracks.set(entry.id, track)
      }
      track.push({
        t: receivedAt,
        x: entry.x,
        y: entry.y,
        yaw: entry.yaw,
        pitch: entry.pitch,
        animation: entry.animation,
        simplified: entry.simplified,
      })
    }
  }

  forget(id: number): void {
    this.tracks.delete(id)
  }

  clear(): void {
    this.tracks.clear()
  }

  /** Everyone visible at `now`, sampled one snapshot interval in the past. */
  sample(now: number): InterpolatedPlayer[] {
    const renderTime = now - INTERPOLATION_DELAY_MS
    const out: InterpolatedPlayer[] = []
    for (const [id, track] of this.tracks) {
      track.prune(renderTime)
      const sample = track.sample(renderTime)
      if (!sample) continue
      // A player the snapshot stopped mentioning has walked out of interest
      // range; drop them once the buffer can no longer cover the render time.
      if (renderTime - sample.t > EXTRAPOLATION_LIMIT_MS) {
        this.tracks.delete(id)
        continue
      }
      out.push({
        id,
        x: sample.x,
        y: sample.y,
        yaw: sample.yaw,
        pitch: sample.pitch,
        animation: sample.animation,
        simplified: sample.simplified,
      })
    }
    return out
  }
}
