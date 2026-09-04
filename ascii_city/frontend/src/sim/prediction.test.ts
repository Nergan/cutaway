import { describe, expect, it } from 'vitest'

import { ANIMATION_IDLE, TICK_SECONDS, WALK_SPEED_MS } from '../domain/constants'
import { CollisionGrid } from '../world/collisionGrid'
import type { InputCommand } from '../net/wire'
import { Predictor, seqLessOrEqual } from './prediction'

function grid(): CollisionGrid {
  return new CollisionGrid(32, 32, 2)
}

function command(sequence: number, forward = 1): InputCommand {
  return {
    sequence,
    forward,
    strafe: 0,
    yaw: 0,
    pitch: 0,
    sprint: false,
    jump: false,
    clientTime: 0,
  }
}

function predictor(x = 20, y = 20): Predictor {
  return new Predictor({
    x,
    y,
    z: 1.7,
    velocityZ: 0,
    yaw: 0,
    pitch: 0,
    animation: ANIMATION_IDLE,
  })
}

describe('prediction', () => {
  it('moves immediately, without waiting for the server', () => {
    const subject = predictor()
    subject.push(command(1), grid(), TICK_SECONDS)
    expect(subject.state.x).toBeCloseTo(20 + WALK_SPEED_MS * TICK_SECONDS, 6)
    expect(subject.pendingCount).toBe(1)
  })

  it('drops acknowledged input and keeps the rest', () => {
    const subject = predictor()
    const world = grid()
    for (let sequence = 1; sequence <= 5; sequence += 1) {
      subject.push(command(sequence), world, TICK_SECONDS)
    }
    const afterThree = 20 + WALK_SPEED_MS * TICK_SECONDS * 3
    subject.reconcile({ x: afterThree, y: 20 }, 3, world, TICK_SECONDS)
    expect(subject.pendingCount).toBe(2)
  })

  it('replays unacknowledged input so the prediction survives reconciliation', () => {
    const subject = predictor()
    const world = grid()
    for (let sequence = 1; sequence <= 5; sequence += 1) {
      subject.push(command(sequence), world, TICK_SECONDS)
    }
    const predicted = subject.state.x
    subject.reconcile(
      { x: 20 + WALK_SPEED_MS * TICK_SECONDS * 3, y: 20 },
      3,
      world,
      TICK_SECONDS,
    )
    // The server agreed, so replaying the last two inputs lands in the same place.
    expect(subject.state.x).toBeCloseTo(predicted, 6)
    expect(subject.lastCorrectionM).toBeLessThan(0.001)
  })

  it('accepts the server position when the two disagree', () => {
    const subject = predictor()
    const world = grid()
    subject.push(command(1), world, TICK_SECONDS)
    subject.reconcile({ x: 25, y: 20 }, 1, world, TICK_SECONDS)
    expect(subject.state.x).toBeCloseTo(25, 6)
  })

  it('hides a small correction behind a decaying offset', () => {
    const subject = predictor()
    const world = grid()
    subject.push(command(1), world, TICK_SECONDS)
    const predicted = subject.state.x
    subject.reconcile({ x: predicted - 0.4, y: 20 }, 1, world, TICK_SECONDS)

    // The authoritative position moved, but the first rendered frame has not.
    const first = subject.view(0)
    expect(first.x).toBeCloseTo(predicted, 4)

    let last = first.x
    for (let frame = 0; frame < 60; frame += 1) last = subject.view(1 / 60).x
    expect(last).toBeCloseTo(subject.state.x, 3)
  })

  it('shows a large correction immediately rather than sliding for a second', () => {
    const subject = predictor()
    const world = grid()
    subject.push(command(1), world, TICK_SECONDS)
    subject.reconcile({ x: 40, y: 20 }, 1, world, TICK_SECONDS)
    expect(subject.view(0).x).toBeCloseTo(40, 6)
  })

  it('ignores a mismatch smaller than the wire quantisation', () => {
    const subject = predictor()
    const world = grid()
    subject.push(command(1), world, TICK_SECONDS)
    const predicted = subject.state.x
    subject.reconcile({ x: predicted - 0.004, y: 20 }, 1, world, TICK_SECONDS)
    expect(subject.view(0).x).toBeCloseTo(subject.state.x, 6)
  })

  it('keeps its own position when the server only rounded it', () => {
    // Adopting the rounded value leaves the client half a centimetre off the
    // server for good, and next to a facade that offset is the difference
    // between sliding along the wall and having the whole step refused, which
    // is what an invisible wall actually is.
    const subject = predictor()
    const world = grid()
    subject.push(command(1), world, TICK_SECONDS)
    const predicted = subject.state.x
    const quantised = Math.round(predicted * 100) / 100
    subject.reconcile({ x: quantised, y: 20 }, 1, world, TICK_SECONDS)
    expect(subject.state.x).toBe(predicted)
  })

  it('walks a wall without the server rounding stealing whole steps', () => {
    const world = grid()
    for (let cy = 0; cy < 32; cy += 1) world.cells[cy * 32 + 12] = 1 // a facade at x = 24 m

    const free = new Predictor({
      x: 23,
      y: 20,
      z: 1.7,
      velocityZ: 0,
      yaw: 0,
      pitch: 0,
      animation: ANIMATION_IDLE,
    })
    const reconciled = predictor(23, 20)
    // Walk into the wall at an angle, reconciling against a server that agrees
    // but can only report centimetres.
    for (let sequence = 1; sequence <= 80; sequence += 1) {
      const step = { ...command(sequence), yaw: 0.35 }
      free.push(step, world, TICK_SECONDS)
      reconciled.push(step, world, TICK_SECONDS)
      const truth = free.state
      reconciled.reconcile(
        { x: Math.round(truth.x * 100) / 100, y: Math.round(truth.y * 100) / 100 },
        sequence,
        world,
        TICK_SECONDS,
      )
    }
    // One lost step is 17 cm, so anything at that scale is the bug returning.
    expect(Math.hypot(reconciled.state.x - free.state.x, reconciled.state.y - free.state.y))
      .toBeLessThan(0.02)
  })

  it('replays a jump from the reported vertical velocity', () => {
    const subject = predictor()
    const world = grid()
    subject.push({ ...command(1), jump: true }, world, TICK_SECONDS)
    const rising = subject.state.velocityZ
    expect(rising).toBeGreaterThan(0)

    subject.push(command(2), world, TICK_SECONDS)
    // The server confirms the take-off, velocity and all.
    subject.reconcile(
      { x: subject.state.x, y: 20, z: 1.7 + rising * TICK_SECONDS, velocityZ: rising },
      1,
      world,
      TICK_SECONDS,
    )
    // Still going up: without the velocity on the wire this collapsed to zero
    // every snapshot and the jump turned into a stutter.
    expect(subject.state.velocityZ).toBeGreaterThan(0)
    expect(subject.state.z).toBeGreaterThan(1.7)
  })

  it('bounds the pending queue so a dead connection cannot grow it forever', () => {
    const subject = predictor()
    const world = grid()
    for (let sequence = 1; sequence <= 500; sequence += 1) {
      subject.push(command(sequence), world, TICK_SECONDS)
    }
    expect(subject.pendingCount).toBeLessThanOrEqual(64)
  })

  it('clears everything on a respawn', () => {
    const subject = predictor()
    const world = grid()
    subject.push(command(1), world, TICK_SECONDS)
    subject.reset(5, 6)
    expect(subject.pendingCount).toBe(0)
    expect(subject.view(0)).toEqual({ x: 5, y: 6, z: 1.7 })
  })
})

describe('sequence comparison', () => {
  it('handles ordinary ordering', () => {
    expect(seqLessOrEqual(3, 5)).toBe(true)
    expect(seqLessOrEqual(5, 3)).toBe(false)
    expect(seqLessOrEqual(4, 4)).toBe(true)
  })

  it('handles the u32 wrap without stranding the queue', () => {
    expect(seqLessOrEqual(0xfffffffe, 2)).toBe(true)
    expect(seqLessOrEqual(2, 0xfffffffe)).toBe(false)
  })
})
