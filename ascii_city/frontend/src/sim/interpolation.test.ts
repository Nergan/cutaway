import { describe, expect, it } from 'vitest'

import { ANIMATION_WALK, EYE_HEIGHT_M } from '../domain/constants'
import type { SnapshotEntry } from '../net/wire'
import { INTERPOLATION_DELAY_MS, InterpolationBuffer, lerpAngle } from './interpolation'

function entry(id: number, x: number, y: number, yaw = 0, z = EYE_HEIGHT_M): SnapshotEntry {
  return { id, x, y, z, yaw, pitch: 0, animation: ANIMATION_WALK, simplified: false }
}

describe('angle blending', () => {
  it('takes the short way around when crossing the wrap point', () => {
    const blended = lerpAngle(6.1, 0.2, 0.5)
    // Halfway between 6.1 and 0.2 the short way is just past the wrap.
    expect(Math.cos(blended)).toBeCloseTo(Math.cos(6.383 % (Math.PI * 2)), 2)
    expect(blended).toBeGreaterThan(6.1)
  })

  it('interpolates linearly away from the wrap point', () => {
    expect(lerpAngle(1, 2, 0.25)).toBeCloseTo(1.25, 6)
  })
})

describe('the interpolation buffer', () => {
  it('renders a player one snapshot interval in the past', () => {
    const buffer = new InterpolationBuffer()
    buffer.ingest([entry(2, 0, 0)], 1000)
    buffer.ingest([entry(2, 10, 0)], 1000 + INTERPOLATION_DELAY_MS)

    const sampled = buffer.sample(1000 + INTERPOLATION_DELAY_MS)
    expect(sampled).toHaveLength(1)
    // At render time 1000 the buffer holds exactly the first sample.
    expect(sampled[0].x).toBeCloseTo(0, 5)
  })

  it('blends between two samples rather than snapping', () => {
    const buffer = new InterpolationBuffer()
    buffer.ingest([entry(2, 0, 0)], 1000)
    buffer.ingest([entry(2, 10, 0)], 1100)

    const halfway = buffer.sample(1050 + INTERPOLATION_DELAY_MS)
    expect(halfway[0].x).toBeCloseTo(5, 5)
  })

  it('holds the last pose instead of extrapolating into a wall', () => {
    const buffer = new InterpolationBuffer()
    buffer.ingest([entry(2, 0, 0)], 1000)
    buffer.ingest([entry(2, 10, 0)], 1100)

    const ahead = buffer.sample(1150 + INTERPOLATION_DELAY_MS)
    expect(ahead[0].x).toBeCloseTo(10, 5)
  })

  it('forgets a player who has been silent far too long', () => {
    const buffer = new InterpolationBuffer()
    buffer.ingest([entry(2, 0, 0)], 1000)
    expect(buffer.sample(1000 + INTERPOLATION_DELAY_MS)).toHaveLength(1)
    expect(buffer.sample(5000)).toHaveLength(0)
    expect(buffer.sample(5100)).toHaveLength(0)
  })

  it('drops a player the roster removed', () => {
    const buffer = new InterpolationBuffer()
    buffer.ingest([entry(2, 0, 0), entry(3, 1, 1)], 1000)
    buffer.forget(3)
    const sampled = buffer.sample(1000 + INTERPOLATION_DELAY_MS)
    expect(sampled.map((player) => player.id)).toEqual([2])
  })

  it('ignores a stale sample that arrives out of order', () => {
    const buffer = new InterpolationBuffer()
    buffer.ingest([entry(2, 10, 0)], 1100)
    buffer.ingest([entry(2, 0, 0)], 1000)
    const sampled = buffer.sample(1100 + INTERPOLATION_DELAY_MS)
    expect(sampled[0].x).toBeCloseTo(10, 5)
  })

  it('keeps the buffer bounded under a long session', () => {
    const buffer = new InterpolationBuffer()
    for (let index = 0; index < 500; index += 1) {
      buffer.ingest([entry(2, index, 0)], 1000 + index * 50)
    }
    const sampled = buffer.sample(1000 + 499 * 50 + INTERPOLATION_DELAY_MS)
    expect(sampled).toHaveLength(1)
    expect(sampled[0].x).toBeGreaterThan(490)
  })

  it('clears every track on reconnect', () => {
    const buffer = new InterpolationBuffer()
    buffer.ingest([entry(2, 0, 0), entry(3, 1, 1)], 1000)
    buffer.clear()
    expect(buffer.sample(1000 + INTERPOLATION_DELAY_MS)).toHaveLength(0)
  })
})
