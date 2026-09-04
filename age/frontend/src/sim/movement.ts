/**
 * Movement and collision, browser side.
 *
 * Mirror of `age/application/movement.py`, and the pairing matters more here than
 * anywhere else in the client. Prediction only feels authoritative while the client
 * reaches the same position the server will: if the two disagree about a wall, the
 * player is corrected every tick and the game feels like it is fighting them.
 *
 * The axis-separated resolution is the part that must not be "improved". Sliding along a
 * wall is a consequence of trying each axis independently, and a cleverer sweep would
 * produce a different answer than the server's.
 */

import { PLAYER_RADIUS_TILES, RUN_SPEED_TILES_S, WALK_SPEED_TILES_S } from '../domain/constants'

export interface Point {
  x: number
  y: number
}

/** What the collision routine needs from the world, and nothing more. */
export interface WalkableProbe {
  (x: number, y: number): boolean
}

export interface MoveResult {
  x: number
  y: number
  collided: boolean
}

/**
 * Whether a circle at `(x, y)` clears every tile it overlaps.
 *
 * Tests the four extremes of the bounding box rather than the centre: a centre test lets
 * a body's edges sink into walls at speed, and testing every covered tile is unnecessary
 * at these radii, because a body under one tile wide cannot straddle more than the four
 * corners.
 */
export function fits(walkable: WalkableProbe, x: number, y: number, radius: number): boolean {
  return (
    walkable(x - radius, y - radius) &&
    walkable(x + radius, y - radius) &&
    walkable(x - radius, y + radius) &&
    walkable(x + radius, y + radius)
  )
}

/**
 * Apply a movement delta, sliding along whatever blocks it.
 *
 * Each axis is attempted independently: if the combined move is blocked but the
 * horizontal component alone is not, the entity moves horizontally. Without this a player
 * walking diagonally into a wall stops dead, which feels broken even though it is
 * technically correct.
 */
export function resolveCollision(
  walkable: WalkableProbe,
  from: Point,
  dx: number,
  dy: number,
  radius = PLAYER_RADIUS_TILES,
): MoveResult {
  let { x, y } = from
  let collided = false

  if (dx !== 0) {
    const candidate = x + dx
    if (fits(walkable, candidate, y, radius)) x = candidate
    else collided = true
  }

  if (dy !== 0) {
    const candidate = y + dy
    if (fits(walkable, x, candidate, radius)) y = candidate
    else collided = true
  }

  return { x, y, collided }
}

/**
 * Normalised movement direction from the button bits.
 *
 * Diagonals are normalised so holding two keys is not faster than one — which the server
 * treats as a speed hack, so getting this wrong locally means being corrected constantly.
 */
export function moveAxis(buttons: number, up: number, down: number, left: number, right: number): Point {
  const dx = (buttons & right ? 1 : 0) - (buttons & left ? 1 : 0)
  const dy = (buttons & down ? 1 : 0) - (buttons & up ? 1 : 0)
  if (dx !== 0 && dy !== 0) {
    const inv = 0.7071067811865476
    return { x: dx * inv, y: dy * inv }
  }
  return { x: dx, y: dy }
}

export function speedFor(running: boolean, classMultiplier = 1.0): number {
  return (running ? RUN_SPEED_TILES_S : WALK_SPEED_TILES_S) * classMultiplier
}

/**
 * Integrate one input locally, exactly as the server will.
 *
 * `deltaTime` is clamped the same way the server clamps it. Sending an unclamped frame is
 * the simplest speed hack there is, so the server refuses to honour one; predicting with
 * a value it would reject just guarantees a correction.
 */
export function applyInput(
  walkable: WalkableProbe,
  from: Point,
  axis: Point,
  running: boolean,
  deltaTime: number,
  classMultiplier = 1.0,
  radius = PLAYER_RADIUS_TILES,
): MoveResult {
  const step = Math.min(Math.max(deltaTime, 0), 0.25)
  const speed = speedFor(running, classMultiplier)
  return resolveCollision(walkable, from, axis.x * speed * step, axis.y * speed * step, radius)
}
