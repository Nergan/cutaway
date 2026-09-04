/**
 * Prediction and reconciliation behaviour.
 *
 * These are the cases that produce visible bugs rather than test failures: a replay that
 * double-counts an input makes the player creep forward; one that drops an input makes
 * them stutter; easing an error that should have snapped walks them through a wall.
 */

import { describe, expect, it } from 'vitest'

import { WALK_SPEED_TILES_S } from '../domain/constants'
import { fits, moveAxis, resolveCollision } from './movement'
import { Predictor } from './prediction'
import { INPUT_DOWN, INPUT_LEFT, INPUT_RIGHT, INPUT_RUN, INPUT_UP } from '../net/wire'

/** Open world. */
const open = () => true

/** A wall along x = 5, so anything at or past it is blocked. */
const wallAtFive = (x: number) => x < 5

describe('collision', () => {
  it('slides along a wall instead of stopping dead', () => {
    // Walking diagonally into a wall: the blocked axis is refused, the free one is not.
    const result = resolveCollision(wallAtFive, { x: 4.5, y: 0 }, 1, 1, 0.35)
    expect(result.collided).toBe(true)
    expect(result.x).toBeCloseTo(4.5, 6)
    expect(result.y).toBeCloseTo(1, 6)
  })

  it('tests the body, not the centre point', () => {
    // A centre test would let the body's edge sink a third of a tile into the wall.
    expect(fits(wallAtFive, 4.9, 0, 0.35)).toBe(false)
    expect(fits(wallAtFive, 4.5, 0, 0.35)).toBe(true)
  })

  it('normalises diagonals so two keys are not faster than one', () => {
    // The server treats an over-long diagonal as a speed hack, so this has to match.
    const diagonal = moveAxis(INPUT_UP | INPUT_RIGHT, INPUT_UP, INPUT_DOWN, INPUT_LEFT, INPUT_RIGHT)
    expect(Math.hypot(diagonal.x, diagonal.y)).toBeCloseTo(1, 12)
  })

  it('cancels opposing keys', () => {
    const axis = moveAxis(INPUT_LEFT | INPUT_RIGHT, INPUT_UP, INPUT_DOWN, INPUT_LEFT, INPUT_RIGHT)
    expect(axis).toEqual({ x: 0, y: 0 })
  })
})

describe('prediction', () => {
  it('moves immediately, without waiting for the server', () => {
    // The entire point: at 80 ms of latency, waiting to move feels broken.
    const predictor = new Predictor(open)
    predictor.reset(0, 0)
    predictor.push({ x: 1, y: 0 }, false, 1 / 30)
    expect(predictor.predicted.x).toBeCloseTo(WALK_SPEED_TILES_S / 30, 10)
  })

  it('hands out increasing sequence numbers', () => {
    const predictor = new Predictor(open)
    const first = predictor.push({ x: 1, y: 0 }, false, 1 / 30)
    const second = predictor.push({ x: 1, y: 0 }, false, 1 / 30)
    expect(second).toBeGreaterThan(first)
  })

  it('lands exactly where the server does when both integrate the same inputs', () => {
    // If this drifts, every snapshot produces a correction even on a perfect connection.
    const predictor = new Predictor(open)
    predictor.reset(0, 0)
    for (let i = 0; i < 10; i += 1) predictor.push({ x: 1, y: 0 }, false, 1 / 30)

    // What the server would compute from the same ten inputs.
    let authoritative = { x: 0, y: 0 }
    for (let i = 0; i < 10; i += 1) {
      authoritative = resolveCollision(open, authoritative, WALK_SPEED_TILES_S / 30, 0)
    }

    expect(predictor.predicted.x).toBeCloseTo(authoritative.x, 10)
  })

  it('replays only the inputs the server has not acknowledged', () => {
    const predictor = new Predictor(open)
    predictor.reset(0, 0)
    const sequences = [0, 0, 0, 0, 0]
    for (let i = 0; i < 5; i += 1) sequences[i] = predictor.push({ x: 1, y: 0 }, false, 1 / 30)

    const step = WALK_SPEED_TILES_S / 30
    // Server has processed the first three; its position reflects exactly those.
    predictor.reconcile({ x: step * 3, y: 0 }, sequences[2])

    expect(predictor.pendingCount).toBe(2)
    // Three confirmed plus two replayed, so five in total: the same place as before.
    expect(predictor.predicted.x).toBeCloseTo(step * 5, 8)
    expect(predictor.stats.lastReplayDepth).toBe(2)
  })

  it('does not double-count an acknowledged input', () => {
    // The classic reconciliation bug: replaying the confirmed input on top of the
    // server's position, so the player creeps forward a step per snapshot.
    const predictor = new Predictor(open)
    predictor.reset(0, 0)
    const sequence = predictor.push({ x: 1, y: 0 }, false, 1 / 30)

    const step = WALK_SPEED_TILES_S / 30
    predictor.reconcile({ x: step, y: 0 }, sequence)
    expect(predictor.predicted.x).toBeCloseTo(step, 10)

    // A second snapshot with no new input must not move anything.
    predictor.reconcile({ x: step, y: 0 }, sequence)
    expect(predictor.predicted.x).toBeCloseTo(step, 10)
    expect(predictor.pendingCount).toBe(0)
  })

  it('eases a small disagreement rather than snapping', () => {
    // A visible twitch on every snapshot is what naive reconciliation feels like, even
    // when the server broadly agrees.
    const predictor = new Predictor(open)
    predictor.reset(0, 0)
    const drawnBefore = predictor.position

    predictor.reconcile({ x: 0.2, y: 0 }, 0)

    // The drawn position barely moves, even though the simulation jumped.
    expect(predictor.position.x).toBeCloseTo(drawnBefore.x, 6)
    expect(predictor.predicted.x).toBeCloseTo(0.2, 10)
    expect(predictor.stats.snaps).toBe(0)
  })

  it('converges on the authoritative position as the error is eased away', () => {
    const predictor = new Predictor(open)
    predictor.reset(0, 0)
    predictor.reconcile({ x: 0.2, y: 0 }, 0)

    for (let frame = 0; frame < 60; frame += 1) predictor.advanceSmoothing(1 / 60)

    expect(predictor.position.x).toBeCloseTo(0.2, 4)
  })

  it('snaps when the server says the player is somewhere else entirely', () => {
    // A mispredicted collision, a knockback or a teleport. Easing here would draw the
    // player walking through whatever actually stopped them.
    const predictor = new Predictor(open)
    predictor.reset(0, 0)
    predictor.reconcile({ x: 40, y: 0 }, 0)

    expect(predictor.stats.snaps).toBe(1)
    expect(predictor.position.x).toBeCloseTo(40, 10)
  })

  it('smooths at the same wall-clock rate regardless of frame rate', () => {
    const at30 = new Predictor(open)
    const at144 = new Predictor(open)
    at30.reset(0, 0)
    at144.reset(0, 0)
    at30.reconcile({ x: 0.5, y: 0 }, 0)
    at144.reconcile({ x: 0.5, y: 0 }, 0)

    for (let i = 0; i < 15; i += 1) at30.advanceSmoothing(1 / 30)
    for (let i = 0; i < 72; i += 1) at144.advanceSmoothing(1 / 144)

    // Half a second of easing either way.
    expect(at30.position.x).toBeCloseTo(at144.position.x, 3)
  })

  it('respects walls during a replay', () => {
    // Replaying without collision would tunnel the player through geometry the server
    // has already stopped them at.
    const predictor = new Predictor(wallAtFive)
    predictor.reset(4, 0)
    for (let i = 0; i < 20; i += 1) predictor.push({ x: 1, y: 0 }, true, 1 / 30)

    predictor.reconcile({ x: 4, y: 0 }, 0)
    expect(predictor.predicted.x).toBeLessThan(5)
  })

  it('bounds the pending queue so a disconnect cannot grow it forever', () => {
    const predictor = new Predictor(open)
    predictor.reset(0, 0)
    for (let i = 0; i < 500; i += 1) predictor.push({ x: 1, y: 0 }, false, 1 / 30)
    expect(predictor.pendingCount).toBeLessThanOrEqual(64)
  })

  it('clamps a dishonest frame time the way the server will', () => {
    // "One input, ten-second frame" is the simplest speed hack; the server clamps to
    // 0.25 s, so predicting anything longer only earns a correction.
    const honest = new Predictor(open)
    const liar = new Predictor(open)
    honest.reset(0, 0)
    liar.reset(0, 0)
    honest.push({ x: 1, y: 0 }, false, 0.25)
    liar.push({ x: 1, y: 0 }, false, 10)
    expect(liar.predicted.x).toBeCloseTo(honest.predicted.x, 10)
  })

  it('runs at the class speed multiplier', () => {
    const quick = new Predictor(open)
    quick.setClassMultiplier(1.2)
    quick.reset(0, 0)
    quick.push({ x: 1, y: 0 }, false, 1 / 30)
    expect(quick.predicted.x).toBeCloseTo((WALK_SPEED_TILES_S * 1.2) / 30, 10)
  })

  it('runs faster while running', () => {
    const predictor = new Predictor(open)
    predictor.reset(0, 0)
    predictor.push({ x: 1, y: 0 }, true, 1 / 30)
    const running = predictor.predicted.x

    predictor.reset(0, 0)
    predictor.push({ x: 1, y: 0 }, false, 1 / 30)
    expect(running).toBeGreaterThan(predictor.predicted.x)
    expect(INPUT_RUN).toBeGreaterThan(0)
  })
})
