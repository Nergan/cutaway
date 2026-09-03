"""Authoritative movement.

This module is the single definition of how a player moves. The client mirrors
it in ``frontend/src/sim/movement.ts`` for prediction, and any divergence shows
up as a small reconciliation nudge rather than a desync, because the server
result always wins.

A player position never comes from the network, so teleporting is impossible by
construction: the only thing a client can influence is the direction of a step
whose length the server computes.
"""

from __future__ import annotations

import math

from ..domain.constants import (
    ANIMATION_IDLE,
    ANIMATION_RUN,
    ANIMATION_WALK,
    PLAYER_RADIUS_M,
    RUN_SPEED_MS,
    WALK_SPEED_MS,
)
from ..domain.player import InputCommand, PlayerState
from ..domain.world import CollisionGrid

MAX_STEP_SECONDS = 0.1
"""Clamp for the integration step. At 6.2 m/s this keeps a step under a cell,
so a fast player can never tunnel through a two metre wall."""


def move_player(
    state: PlayerState,
    command: InputCommand,
    grid: CollisionGrid,
    dt: float,
) -> None:
    """Advance ``state`` in place by one simulation step."""
    step = min(max(dt, 0.0), MAX_STEP_SECONDS)
    state.yaw = command.yaw
    state.pitch = command.pitch

    forward = command.forward
    strafe = command.strafe
    magnitude = math.hypot(forward, strafe)
    if magnitude < 1e-4 or step == 0.0:
        state.velocity_x = 0.0
        state.velocity_y = 0.0
        state.animation = ANIMATION_IDLE
        state.last_input_sequence = command.sequence
        return

    if magnitude > 1.0:
        forward /= magnitude
        strafe /= magnitude
        magnitude = 1.0

    speed = RUN_SPEED_MS if command.sprint else WALK_SPEED_MS
    cos_yaw = math.cos(command.yaw)
    sin_yaw = math.sin(command.yaw)
    # Strafing is the yaw vector rotated a quarter turn clockwise.
    dx = (forward * cos_yaw + strafe * sin_yaw) * speed * step
    dy = (forward * sin_yaw - strafe * cos_yaw) * speed * step

    start_x, start_y = state.x, state.y
    # Resolving axes separately is what lets a player slide along a facade
    # instead of sticking to it.
    if dx and grid.is_free_circle(state.x + dx, state.y, PLAYER_RADIUS_M):
        state.x += dx
    if dy and grid.is_free_circle(state.x, state.y + dy, PLAYER_RADIUS_M):
        state.y += dy
    state.x, state.y = grid.clamp_to_world(state.x, state.y)

    state.velocity_x = (state.x - start_x) / step
    state.velocity_y = (state.y - start_y) / step
    travelled = math.hypot(state.x - start_x, state.y - start_y)
    if travelled < 1e-4:
        state.animation = ANIMATION_IDLE
    else:
        state.animation = ANIMATION_RUN if command.sprint else ANIMATION_WALK
    state.last_input_sequence = command.sequence


def find_safe_position(
    grid: CollisionGrid, x: float, y: float, radius: float = PLAYER_RADIUS_M
) -> tuple[float, float]:
    """Nudge a position out of geometry, searching outward in a small spiral.

    Spawn points are validated at generation time, so this only matters when a
    world version changes underneath a live room.
    """
    if grid.is_free_circle(x, y, radius):
        return x, y
    step = grid.cell_size
    for ring in range(1, 12):
        for index in range(8 * ring):
            angle = index / (8 * ring) * math.tau
            candidate_x = x + math.cos(angle) * step * ring
            candidate_y = y + math.sin(angle) * step * ring
            candidate_x, candidate_y = grid.clamp_to_world(candidate_x, candidate_y)
            if grid.is_free_circle(candidate_x, candidate_y, radius):
                return candidate_x, candidate_y
    return grid.clamp_to_world(x, y)
