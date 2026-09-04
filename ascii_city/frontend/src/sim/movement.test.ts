/**
 * The client's copy of the movement rules.
 *
 * `tests/test_ascii_city_movement.py` asserts the same behaviours against the
 * Python original; these run the mirror through the same situations so a
 * divergence surfaces as a failing test rather than as rubber-banding.
 */

import { describe, expect, it } from 'vitest'

import {
  ANIMATION_IDLE,
  ANIMATION_RUN,
  ANIMATION_WALK,
  CELL_BUILDING,
  CELL_SIDEWALK,
  EYE_HEIGHT_M,
  FLOOR_STEP_M,
  RUN_SPEED_MS,
  TICK_SECONDS,
  WALK_SPEED_MS,
} from '../domain/constants'
import { CollisionGrid } from '../world/collisionGrid'
import type { InputCommand } from '../net/wire'
import { MAX_STEP_SECONDS, movePlayer } from './movement'

function openGrid(width = 16, height = 16): CollisionGrid {
  return new CollisionGrid(width, height, 2)
}

function wallAt(grid: CollisionGrid, cx: number, cy: number): void {
  grid.cells[cy * grid.width + cx] = CELL_BUILDING
}

function command(overrides: Partial<InputCommand> = {}): InputCommand {
  return {
    sequence: 1,
    forward: 0,
    strafe: 0,
    yaw: 0,
    pitch: 0,
    sprint: false,
    jump: false,
    clientTime: 0,
    ...overrides,
  }
}

function player(x = 10, y = 10) {
  return { x, y, z: 1.7, velocityZ: 0, yaw: 0, pitch: 0, animation: ANIMATION_IDLE }
}

describe('walking', () => {
  it('moves east at the walk speed when yaw is zero', () => {
    const state = player()
    movePlayer(state, command({ forward: 1 }), openGrid(), TICK_SECONDS)
    expect(state.x).toBeCloseTo(10 + WALK_SPEED_MS * TICK_SECONDS, 6)
    expect(state.y).toBeCloseTo(10, 6)
    expect(state.animation).toBe(ANIMATION_WALK)
  })

  it('moves faster while sprinting and says so in the animation', () => {
    const state = player()
    movePlayer(state, command({ forward: 1, sprint: true }), openGrid(), TICK_SECONDS)
    expect(state.x).toBeCloseTo(10 + RUN_SPEED_MS * TICK_SECONDS, 6)
    expect(state.animation).toBe(ANIMATION_RUN)
  })

  it('gives diagonal input no speed advantage', () => {
    const straight = player()
    const diagonal = player()
    movePlayer(straight, command({ forward: 1 }), openGrid(), TICK_SECONDS)
    movePlayer(diagonal, command({ forward: 1, strafe: 1 }), openGrid(), TICK_SECONDS)

    const straightDistance = Math.hypot(straight.x - 10, straight.y - 10)
    const diagonalDistance = Math.hypot(diagonal.x - 10, diagonal.y - 10)
    expect(diagonalDistance).toBeCloseTo(straightDistance, 6)
  })

  it('strafes to the right of the facing direction', () => {
    const state = player()
    movePlayer(state, command({ strafe: 1 }), openGrid(), TICK_SECONDS)
    // Facing east, right is south, which is negative y in this frame.
    expect(state.y).toBeLessThan(10)
    expect(state.x).toBeCloseTo(10, 6)
  })

  it('stops the moment the input goes quiet', () => {
    const state = player()
    movePlayer(state, command({ forward: 1 }), openGrid(), TICK_SECONDS)
    const moved = state.x
    movePlayer(state, command({ sequence: 2 }), openGrid(), TICK_SECONDS)
    expect(state.x).toBeCloseTo(moved, 6)
    expect(state.animation).toBe(ANIMATION_IDLE)
  })

  it('adopts the yaw and pitch the command carries even while standing still', () => {
    const state = player()
    movePlayer(state, command({ yaw: 2.5, pitch: -0.8 }), openGrid(), TICK_SECONDS)
    expect(state.yaw).toBeCloseTo(2.5, 6)
    expect(state.pitch).toBeCloseTo(-0.8, 6)
  })
})

describe('collisions', () => {
  it('refuses to walk into a wall', () => {
    const grid = openGrid()
    wallAt(grid, 6, 5)
    const state = player(11.0, 11.0)
    for (let step = 0; step < 40; step += 1) {
      movePlayer(state, command({ sequence: step, forward: 1 }), grid, TICK_SECONDS)
    }
    expect(state.x).toBeLessThan(12)
  })

  it('slides along a facade instead of sticking to it', () => {
    const grid = openGrid()
    wallAt(grid, 6, 5)
    const state = player(11.0, 10.4)
    // Pushing north-east into the wall should still make northward progress.
    for (let step = 0; step < 30; step += 1) {
      movePlayer(
        state,
        command({ sequence: step, forward: 1, strafe: -1 }),
        grid,
        TICK_SECONDS,
      )
    }
    expect(state.y).toBeGreaterThan(10.4)
  })

  it('cannot tunnel through a wall with an absurd timestep', () => {
    const grid = openGrid()
    wallAt(grid, 6, 5)
    const state = player(11.0, 11.0)
    movePlayer(state, command({ forward: 1, sprint: true }), grid, 30)
    expect(state.x).toBeLessThan(12)
    expect(MAX_STEP_SECONDS).toBeLessThanOrEqual(0.1)
  })

  it('stays inside the district however hard it is pushed', () => {
    const grid = openGrid(8, 8)
    const state = player(1, 1)
    for (let step = 0; step < 200; step += 1) {
      movePlayer(state, command({ sequence: step, forward: -1, sprint: true }), grid, TICK_SECONDS)
    }
    expect(state.x).toBeGreaterThanOrEqual(1)
    expect(state.y).toBeGreaterThanOrEqual(0)
    expect(state.x).toBeLessThanOrEqual(grid.widthM)
  })
})

describe('relief', () => {
  /** The open grid with everything east of cell 6 raised by `risers`. */
  function stepped(risers: number): CollisionGrid {
    const grid = openGrid()
    for (let cy = 0; cy < grid.height; cy += 1) {
      for (let cx = 6; cx < grid.width; cx += 1) {
        grid.cells[cy * grid.width + cx] = CELL_SIDEWALK
        grid.heights[cy * grid.width + cx] = risers
      }
    }
    return grid
  }

  function walkEast(grid: CollisionGrid, state: ReturnType<typeof player>, ticks: number): void {
    for (let step = 0; step < ticks; step += 1) {
      movePlayer(state, command({ sequence: step, forward: 1 }), grid, TICK_SECONDS)
    }
  }

  it('walks up a low step and stands on it', () => {
    const grid = stepped(2)
    const state = player(10, 10)
    walkEast(grid, state, 30)
    expect(state.x).toBeGreaterThan(13)
    expect(state.z).toBeCloseTo(EYE_HEIGHT_M + 2 * FLOOR_STEP_M, 6)
  })

  it('refuses a terrace taller than a stride', () => {
    const grid = stepped(5)
    const state = player(10, 10)
    walkEast(grid, state, 30)
    expect(state.x).toBeLessThan(12)
    expect(state.z).toBeCloseTo(EYE_HEIGHT_M, 6)
  })

  it('lets a jump carry the player onto that terrace', () => {
    const grid = stepped(5)
    const state = player(10, 10)
    for (let step = 0; step < 40; step += 1) {
      movePlayer(state, command({ sequence: step, forward: 1, jump: step === 0 }), grid, TICK_SECONDS)
    }
    expect(state.x).toBeGreaterThan(13)
    expect(state.z).toBeCloseTo(EYE_HEIGHT_M + 5 * FLOOR_STEP_M, 6)
  })

  it('falls back to the street on the way off', () => {
    const grid = stepped(5)
    const state = player(20, 10)
    state.z = EYE_HEIGHT_M + 5 * FLOOR_STEP_M
    for (let step = 0; step < 80; step += 1) {
      movePlayer(state, command({ sequence: step, forward: 1, yaw: Math.PI }), grid, TICK_SECONDS)
    }
    expect(state.x).toBeLessThan(11)
    expect(state.z).toBeCloseTo(EYE_HEIGHT_M, 6)
  })
})

describe('the collision grid', () => {
  it('treats everything outside the district as solid', () => {
    const grid = openGrid(4, 4)
    expect(grid.isSolidCell(-1, 0)).toBe(true)
    expect(grid.isSolidCell(4, 0)).toBe(true)
    expect(grid.isSolidCell(0, 0)).toBe(false)
  })

  it('reports a circle overlapping a wall as blocked', () => {
    const grid = openGrid()
    wallAt(grid, 3, 3)
    expect(grid.isFreeCircle(7.0, 7.0, 0.35)).toBe(false)
    expect(grid.isFreeCircle(11.0, 11.0, 0.35)).toBe(true)
  })
})
