/**
 * Line-for-line mirror of `ascii_city/application/movement.py`.
 *
 * Keeping the two implementations identical is what makes prediction silent:
 * the client arrives at the same position the server does, so reconciliation
 * has nothing to correct except genuine packet loss.
 */

import {
  ANIMATION_IDLE,
  ANIMATION_RUN,
  ANIMATION_WALK,
  PLAYER_RADIUS_M,
  RUN_SPEED_MS,
  WALK_SPEED_MS,
} from '../domain/constants'
import type { CollisionGrid } from '../world/collisionGrid'
import type { InputCommand } from '../net/wire'

/** At 6.2 m/s this keeps one step under a cell, so tunnelling is impossible. */
export const MAX_STEP_SECONDS = 0.1

export interface MovableState {
  x: number
  y: number
  yaw: number
  pitch: number
  animation: number
}

export function movePlayer(
  state: MovableState,
  command: InputCommand,
  grid: CollisionGrid,
  dt: number,
): void {
  const step = Math.min(Math.max(dt, 0), MAX_STEP_SECONDS)
  state.yaw = command.yaw
  state.pitch = command.pitch

  let forward = command.forward
  let strafe = command.strafe
  let magnitude = Math.hypot(forward, strafe)
  if (magnitude < 1e-4 || step === 0) {
    state.animation = ANIMATION_IDLE
    return
  }

  if (magnitude > 1) {
    forward /= magnitude
    strafe /= magnitude
    magnitude = 1
  }

  const speed = command.sprint ? RUN_SPEED_MS : WALK_SPEED_MS
  const cosYaw = Math.cos(command.yaw)
  const sinYaw = Math.sin(command.yaw)
  // Strafing is the yaw vector rotated a quarter turn clockwise.
  const dx = (forward * cosYaw + strafe * sinYaw) * speed * step
  const dy = (forward * sinYaw - strafe * cosYaw) * speed * step

  const startX = state.x
  const startY = state.y
  // Separate axes let a player slide along a facade instead of sticking to it.
  if (dx !== 0 && grid.isFreeCircle(state.x + dx, state.y, PLAYER_RADIUS_M)) state.x += dx
  if (dy !== 0 && grid.isFreeCircle(state.x, state.y + dy, PLAYER_RADIUS_M)) state.y += dy
  grid.clampToWorld(state)

  const travelled = Math.hypot(state.x - startX, state.y - startY)
  state.animation =
    travelled < 1e-4 ? ANIMATION_IDLE : command.sprint ? ANIMATION_RUN : ANIMATION_WALK
}
