/**
 * Interpolation behaviour for remote entities.
 *
 * The failure modes here are all visual: extrapolating past the newest sample makes a
 * lagging player slide away and snap back; interpolating a facing angle as a plain number
 * makes them spin a full turn when they cross north; a mis-signed clock offset renders
 * everything either frozen or teleporting.
 */

import { describe, expect, it } from 'vitest'

import { SNAPSHOT_INTERVAL_SECONDS } from '../domain/constants'
import { ClockSync, RENDER_DELAY_SECONDS, Track } from './interpolation'

function walkEast(count: number, step = 1): Track {
  const track = new Track()
  for (let i = 0; i < count; i += 1) {
    track.push({ time: i * SNAPSHOT_INTERVAL_SECONDS, x: i * step, y: 0, facing: 0 })
  }
  return track
}

describe('the render delay', () => {
  it('is deeper than a single snapshot interval', () => {
    // One interval leaves nothing to interpolate into the moment a packet is late.
    expect(RENDER_DELAY_SECONDS).toBeGreaterThan(SNAPSHOT_INTERVAL_SECONDS)
  })
})

describe('a track', () => {
  it('has no pose before it has any samples', () => {
    expect(new Track().poseAt(0)).toBeUndefined()
  })

  it('holds still with a single sample', () => {
    const track = new Track()
    track.push({ time: 0, x: 3, y: 4, facing: 1 })
    expect(track.poseAt(10)).toEqual({ x: 3, y: 4, facing: 1, speed: 0 })
  })

  it('interpolates halfway between two samples', () => {
    const track = walkEast(2)
    const pose = track.poseAt(SNAPSHOT_INTERVAL_SECONDS / 2)
    expect(pose?.x).toBeCloseTo(0.5, 10)
  })

  it('holds position rather than extrapolating past the newest sample', () => {
    // Extrapolating is wrong the instant someone changes direction, and being wrong
    // about a position looks far worse than being late about it.
    const track = walkEast(3)
    const newest = track.latest!
    const pose = track.poseAt(newest.time + 5)
    expect(pose?.x).toBeCloseTo(newest.x, 10)
  })

  it('clamps to the oldest sample rather than reporting nothing', () => {
    // Happens for one frame after a spawn, when the render time is still behind the
    // first snapshot.
    const track = walkEast(3)
    const pose = track.poseAt(-10)
    expect(pose?.x).toBeCloseTo(0, 10)
  })

  it('reports a speed the animation can use', () => {
    const track = walkEast(3, 2)
    const pose = track.poseAt(SNAPSHOT_INTERVAL_SECONDS * 1.5)
    expect(pose?.speed).toBeCloseTo(2 / SNAPSHOT_INTERVAL_SECONDS, 6)
  })

  it('turns the short way round the compass', () => {
    // Interpolated as a rotation, not a number: from 350 to 10 degrees is a 20 degree
    // turn, not a 340 degree one.
    const track = new Track()
    const nearlyFull = (350 / 180) * Math.PI
    const justPast = (10 / 180) * Math.PI
    track.push({ time: 0, x: 0, y: 0, facing: nearlyFull })
    track.push({ time: 1, x: 0, y: 0, facing: justPast })

    const pose = track.poseAt(0.5)!
    // Halfway is 0 degrees, reached either just below 2pi or just above 0.
    const normalised = ((pose.facing % (2 * Math.PI)) + 2 * Math.PI) % (2 * Math.PI)
    const distanceFromNorth = Math.min(normalised, 2 * Math.PI - normalised)
    expect(distanceFromNorth).toBeLessThan(0.02)
  })

  it('drops an out-of-order sample instead of inserting it', () => {
    // A duplicated snapshot after a reconnect would otherwise make an entity walk
    // backwards for a frame.
    const track = walkEast(3)
    const before = track.length
    track.push({ time: 0, x: 99, y: 99, facing: 0 })
    expect(track.length).toBe(before)
    expect(track.poseAt(SNAPSHOT_INTERVAL_SECONDS)?.x).toBeCloseTo(1, 10)
  })

  it('bounds its memory', () => {
    const track = new Track(8)
    for (let i = 0; i < 100; i += 1) track.push({ time: i, x: i, y: 0, facing: 0 })
    expect(track.length).toBeLessThanOrEqual(8)
  })

  it('keeps enough history to interpolate after pruning', () => {
    const track = walkEast(10)
    track.prune(SNAPSHOT_INTERVAL_SECONDS * 8)
    expect(track.length).toBeGreaterThanOrEqual(2)
    expect(track.poseAt(SNAPSHOT_INTERVAL_SECONDS * 8.5)).toBeDefined()
  })
})

describe('clock sync', () => {
  it('is not ready until it has seen a pong', () => {
    expect(new ClockSync().ready).toBe(false)
  })

  it('recovers a constant offset from a symmetric round trip', () => {
    const sync = new ClockSync()
    // Server clock runs 1000 s ahead. Sent at t=10, replied at server 1010.04, received
    // at t=10.08: a symmetric 80 ms round trip.
    sync.observePong(10, 1010.04, 10.08)
    expect(sync.toLocal(1010.04)).toBeCloseTo(10.04, 6)
    expect(sync.latencyMs).toBeCloseTo(40, 6)
  })

  it('prefers the least delayed sample over an average', () => {
    // Averaging folds every network hiccup into the estimate permanently; the minimum
    // round trip is the closest thing to the true offset.
    const sync = new ClockSync()
    sync.observePong(10, 1010.04, 10.08) // clean, 80 ms
    const clean = sync.toLocal(1010.04)

    sync.observePong(11, 1011.4, 11.8) // 800 ms spike
    expect(sync.toLocal(1010.04)).toBeCloseTo(clean, 6)
  })

  it('puts the render time in the past by the delay', () => {
    const sync = new ClockSync()
    expect(sync.renderTime(100)).toBeCloseTo(100 - RENDER_DELAY_SECONDS, 10)
  })

  it('never reports a negative latency', () => {
    // A clock that jumped backwards mid-session would otherwise produce one.
    const sync = new ClockSync()
    sync.observePong(10, 1010, 9.9)
    expect(sync.latencyMs).toBeGreaterThanOrEqual(0)
  })
})
