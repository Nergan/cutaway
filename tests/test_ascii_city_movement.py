"""Authoritative movement: collisions, sliding, speed ceilings, no tunnelling."""

from __future__ import annotations

import math

import pytest

from ascii_city.application.movement import MAX_STEP_SECONDS, find_safe_position, move_player
from ascii_city.domain.constants import (
    ANIMATION_IDLE,
    ANIMATION_RUN,
    ANIMATION_WALK,
    CELL_BUILDING,
    CELL_ROAD,
    CELL_SIDEWALK,
    EYE_HEIGHT_M,
    FLOOR_STEP_M,
    PLAYER_RADIUS_M,
    RUN_SPEED_MS,
    WALK_SPEED_MS,
)
from ascii_city.domain.player import InputCommand, PlayerState
from ascii_city.domain.world import CollisionGrid

STEP = 1 / 20


def corridor_grid() -> CollisionGrid:
    """A 20 x 20 cell room walled on the outside with a pillar at (10, 10)."""
    grid = CollisionGrid(20, 20, 2.0)
    for y in range(20):
        for x in range(20):
            solid = x in (0, 19) or y in (0, 19)
            grid.set(x, y, CELL_BUILDING if solid else CELL_ROAD, 20 if solid else 0)
    grid.set(10, 10, CELL_BUILDING, 30)
    return grid


def player_at(x: float, y: float) -> PlayerState:
    return PlayerState(id=1, nickname="Tester-1000", color=0, x=x, y=y)


def command(forward=0.0, strafe=0.0, yaw=0.0, sprint=False, jump=False, sequence=1) -> InputCommand:
    return InputCommand.sanitised(
        sequence=sequence,
        forward=forward,
        strafe=strafe,
        yaw=yaw,
        pitch=0.0,
        sprint=sprint,
        jump=jump,
        client_time=0,
    )


def test_walking_covers_the_expected_distance():
    grid = corridor_grid()
    state = player_at(10.0, 10.0)
    move_player(state, command(forward=1.0, yaw=0.0), grid, STEP)
    assert state.x == pytest.approx(10.0 + WALK_SPEED_MS * STEP)
    assert state.y == pytest.approx(10.0)
    assert state.animation == ANIMATION_WALK


def test_sprinting_is_capped_at_the_run_speed():
    grid = corridor_grid()
    state = player_at(10.0, 10.0)
    move_player(state, command(forward=1.0, yaw=0.0, sprint=True), grid, STEP)
    assert state.x == pytest.approx(10.0 + RUN_SPEED_MS * STEP)
    assert state.animation == ANIMATION_RUN


def test_diagonal_input_is_normalised():
    """Holding forward and strafe must not be faster than holding one."""
    grid = corridor_grid()
    straight = player_at(10.0, 10.0)
    diagonal = player_at(10.0, 10.0)
    move_player(straight, command(forward=1.0, yaw=0.0), grid, STEP)
    move_player(diagonal, command(forward=1.0, strafe=1.0, yaw=0.0), grid, STEP)

    straight_distance = math.hypot(straight.x - 10.0, straight.y - 10.0)
    diagonal_distance = math.hypot(diagonal.x - 10.0, diagonal.y - 10.0)
    assert diagonal_distance == pytest.approx(straight_distance, rel=1e-6)


def test_out_of_range_input_is_clamped_not_trusted():
    grid = corridor_grid()
    state = player_at(10.0, 10.0)
    move_player(state, command(forward=1000.0, yaw=0.0), grid, STEP)
    assert state.x - 10.0 == pytest.approx(WALK_SPEED_MS * STEP)


def test_a_wall_blocks_movement():
    grid = corridor_grid()
    # Just inside the west wall, which spans x in [0, 2) metres.
    state = player_at(2.0 + PLAYER_RADIUS_M + 0.01, 10.0)
    for sequence in range(40):
        move_player(state, command(forward=1.0, yaw=math.pi, sequence=sequence), grid, STEP)
    assert state.x >= 2.0 + PLAYER_RADIUS_M - 1e-6
    assert grid.is_free_circle(state.x, state.y, PLAYER_RADIUS_M)


def test_a_player_slides_along_a_wall_instead_of_sticking():
    grid = corridor_grid()
    state = player_at(2.0 + PLAYER_RADIUS_M + 0.01, 10.0)
    start_y = state.y
    # Push north-west into the wall: the x component is refused, y survives.
    for sequence in range(20):
        move_player(
            state,
            command(forward=1.0, strafe=1.0, yaw=math.pi, sequence=sequence),
            grid,
            STEP,
        )
    assert state.y > start_y + 1.0
    assert grid.is_free_circle(state.x, state.y, PLAYER_RADIUS_M)


def test_no_tunnelling_even_at_the_maximum_step():
    """A long step must still stop at geometry rather than jump through it."""
    grid = corridor_grid()
    state = player_at(16.0, 21.0)
    for sequence in range(200):
        move_player(
            state,
            command(forward=1.0, yaw=math.pi, sprint=True, sequence=sequence),
            grid,
            MAX_STEP_SECONDS * 4,  # deliberately larger than the clamp
        )
        assert grid.is_free_circle(state.x, state.y, PLAYER_RADIUS_M), (state.x, state.y)


def test_idle_input_stops_the_player():
    grid = corridor_grid()
    state = player_at(10.0, 10.0)
    move_player(state, command(forward=1.0), grid, STEP)
    move_player(state, command(forward=0.0, sequence=2), grid, STEP)
    assert state.animation == ANIMATION_IDLE
    assert state.velocity_x == 0.0 and state.velocity_y == 0.0
    assert state.last_input_sequence == 2


def test_the_player_cannot_leave_the_world():
    grid = corridor_grid()
    state = player_at(3.0, 3.0)
    for sequence in range(400):
        move_player(
            state,
            command(forward=1.0, strafe=1.0, yaw=math.pi * 1.25, sprint=True, sequence=sequence),
            grid,
            STEP,
        )
    assert 0 <= state.x <= grid.width_m
    assert 0 <= state.y <= grid.height_m


def stepped_grid(risers: int) -> CollisionGrid:
    """The corridor room, with everything east of x=12 raised by `risers`."""
    grid = corridor_grid()
    for y in range(1, 19):
        for x in range(12, 19):
            grid.set(x, y, CELL_SIDEWALK, risers)
    return grid


def walk_east(grid: CollisionGrid, state: PlayerState, ticks: int) -> None:
    for sequence in range(1, ticks + 1):
        move_player(state, command(forward=1.0, yaw=0.0, sequence=sequence), grid, STEP)


def test_a_low_step_is_walked_up_and_stood_on():
    grid = stepped_grid(2)  # half a metre
    state = player_at(22.0, 10.0)
    state.z = EYE_HEIGHT_M
    walk_east(grid, state, 30)
    assert state.x > 25.0, "the step should not have stopped the walk"
    assert state.z == pytest.approx(EYE_HEIGHT_M + 2 * FLOOR_STEP_M)


def test_a_terrace_taller_than_a_stride_blocks_the_walk():
    grid = stepped_grid(5)  # 1.25 m: a jump, not a stride
    state = player_at(22.0, 10.0)
    state.z = EYE_HEIGHT_M
    walk_east(grid, state, 30)
    assert state.x < 24.0, "a terrace this tall has to be climbed, not strolled onto"
    assert state.z == pytest.approx(EYE_HEIGHT_M)


def test_a_jump_carries_the_player_onto_a_terrace():
    grid = stepped_grid(5)
    state = player_at(22.0, 10.0)
    state.z = EYE_HEIGHT_M
    for sequence in range(1, 40):
        move_player(
            state,
            command(forward=1.0, yaw=0.0, jump=sequence == 1, sequence=sequence),
            grid,
            STEP,
        )
    assert state.x > 25.0
    assert state.z == pytest.approx(EYE_HEIGHT_M + 5 * FLOOR_STEP_M)


def test_walking_off_a_terrace_falls_back_to_the_street():
    grid = stepped_grid(5)
    state = player_at(30.0, 10.0)
    state.z = EYE_HEIGHT_M + 5 * FLOOR_STEP_M
    for sequence in range(1, 60):
        move_player(state, command(forward=1.0, yaw=math.pi, sequence=sequence), grid, STEP)
    assert state.x < 23.0
    assert state.z == pytest.approx(EYE_HEIGHT_M)


def test_find_safe_position_pushes_out_of_geometry():
    grid = corridor_grid()
    # Dead centre of the pillar at cell (10, 10).
    x, y = find_safe_position(grid, 21.0, 21.0)
    assert grid.is_free_circle(x, y, PLAYER_RADIUS_M)


def test_find_safe_position_leaves_a_good_spot_alone():
    grid = corridor_grid()
    assert find_safe_position(grid, 10.0, 10.0) == (10.0, 10.0)


def test_non_finite_input_is_neutralised():
    grid = corridor_grid()
    state = player_at(10.0, 10.0)
    move_player(
        state,
        InputCommand.sanitised(
            sequence=1,
            forward=float("nan"),
            strafe=float("inf"),
            yaw=float("nan"),
            pitch=float("-inf"),
            sprint=False,
            jump=False,
            client_time=0,
        ),
        grid,
        STEP,
    )
    assert state.x == 10.0 and state.y == 10.0
    assert math.isfinite(state.yaw) and math.isfinite(state.pitch)
