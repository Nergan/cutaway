"""Movement integration, collision, and the anti-cheat checks around them.

The server is authoritative (TDD 15.1): it integrates every entity itself and only
uses the client's predicted position to decide whether a correction is needed. A
client that lies gets rubber-banded; it never gets to place itself.

Collision resolves each axis separately. That is what lets a player slide along a
wall instead of sticking to it, and it is the same routine the client runs during
prediction, so the two agree on the geometry rather than fighting over it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from ..domain.constants import (
    POSITION_TOLERANCE_TILES,
    RUN_SPEED_TILES_S,
    SPEED_HACK_FACTOR,
    WALK_SPEED_TILES_S,
)
from ..domain.coordinates import WorldPoint
from ..domain.entities import DirtyField, Entity
from .world import World


@dataclass(frozen=True, slots=True)
class MoveResult:
    """What happened when an entity tried to move."""

    position: WorldPoint
    collided: bool
    corrected: bool


def resolve_collision(
    world: World, entity: Entity, from_point: WorldPoint, dx: float, dy: float
) -> tuple[WorldPoint, bool]:
    """Apply a movement delta, sliding along whatever blocks it.

    Each axis is attempted independently: if the combined move is blocked but the
    horizontal component alone is not, the entity moves horizontally. Without this
    a player walking diagonally into a wall stops dead, which feels broken even
    though it is technically correct.
    """
    radius = entity.radius
    collided = False

    x = from_point.x
    y = from_point.y

    if dx:
        candidate = x + dx
        if _fits(world, candidate, y, radius):
            x = candidate
        else:
            collided = True

    if dy:
        candidate = y + dy
        if _fits(world, x, candidate, radius):
            y = candidate
        else:
            collided = True

    return WorldPoint(x, y), collided


def _fits(world: World, x: float, y: float, radius: float) -> bool:
    """Whether a circle at ``(x, y)`` clears every tile it overlaps.

    Tests the four extremes of the bounding box rather than the centre. A centre
    test lets a body's edges sink into walls at high speed, and testing every
    covered tile is unnecessary at these radii because a body under one tile wide
    cannot straddle more than the four corners.
    """
    for probe_x, probe_y in (
        (x - radius, y - radius),
        (x + radius, y - radius),
        (x - radius, y + radius),
        (x + radius, y + radius),
    ):
        if not world.is_walkable_at(WorldPoint(probe_x, probe_y)):
            return False
    return True


def speed_for(entity: Entity, running: bool) -> float:
    """An entity's current speed, class multiplier included."""
    base = RUN_SPEED_TILES_S if running else WALK_SPEED_TILES_S
    if entity.is_player:
        return base * entity.character_class.speed_multiplier
    return entity.speed


def apply_input(
    world: World,
    entity: Entity,
    axis: tuple[float, float],
    running: bool,
    facing: float,
    delta_time: float,
    predicted: WorldPoint | None = None,
) -> MoveResult:
    """Integrate one input command against the authoritative world.

    ``delta_time`` is clamped before use. An unclamped value is the simplest speed
    hack there is: send one input claiming a ten-second frame and cross the map.
    """
    step = _clamp(delta_time, 0.0, 0.25)
    speed = speed_for(entity, running)

    dx = axis[0] * speed * step
    dy = axis[1] * speed * step

    position, collided = resolve_collision(world, entity, entity.position, dx, dy)

    corrected = False
    if predicted is not None:
        # Trust the client's own answer when it is close enough to ours, because
        # accepting it is what makes the client's prediction feel authoritative.
        # Beyond the tolerance the server's value stands and the client will
        # reconcile to it.
        drift = position.distance_to(predicted)
        if drift <= POSITION_TOLERANCE_TILES and not collided:
            if _fits(world, predicted.x, predicted.y, entity.radius):
                travelled = entity.position.distance_to(predicted)
                if travelled <= speed * step * SPEED_HACK_FACTOR + 0.05:
                    position = predicted
                else:
                    corrected = True
            else:
                corrected = True
        elif drift > POSITION_TOLERANCE_TILES:
            corrected = True

    entity.move_to(position.x, position.y)
    if facing != entity.facing:
        entity.facing = facing
        entity.mark(DirtyField.FACING)

    velocity = (dx / step if step else 0.0, dy / step if step else 0.0)
    if velocity != entity.velocity:
        entity.velocity = velocity
        entity.mark(DirtyField.VELOCITY)

    world.reindex(entity)
    return MoveResult(position=position, collided=collided, corrected=corrected)


def step_towards(
    world: World, entity: Entity, target: WorldPoint, speed: float, delta_time: float
) -> MoveResult:
    """Move an entity towards a point, used by NPC steering.

    On collision it tries a perpendicular slide before giving up. This is not
    pathfinding, and it is not pretending to be: it is enough for a patrol that
    meets a rock to go around it rather than grind against it forever, which was
    the actual failure mode in the "no stuck states" acceptance test.
    """
    dx = target.x - entity.position.x
    dy = target.y - entity.position.y
    distance = math.hypot(dx, dy)
    if distance < 1e-6:
        return MoveResult(position=entity.position, collided=False, corrected=False)

    travel = min(speed * delta_time, distance)
    ux, uy = dx / distance, dy / distance

    position, collided = resolve_collision(world, entity, entity.position, ux * travel, uy * travel)

    if collided and position.distance_squared_to(entity.position) < 1e-9:
        # Fully stuck. Try both perpendiculars; whichever clears wins.
        for side_x, side_y in ((-uy, ux), (uy, -ux)):
            position, collided = resolve_collision(
                world, entity, entity.position, side_x * travel, side_y * travel
            )
            if position.distance_squared_to(entity.position) > 1e-9:
                break

    entity.move_to(position.x, position.y)

    new_facing = math.atan2(uy, ux)
    if abs(new_facing - entity.facing) > 0.01:
        entity.facing = new_facing
        entity.mark(DirtyField.FACING)

    velocity = (ux * speed, uy * speed)
    if velocity != entity.velocity:
        entity.velocity = velocity
        entity.mark(DirtyField.VELOCITY)

    world.reindex(entity)
    return MoveResult(position=position, collided=collided, corrected=False)


def find_walkable_near(
    world: World, origin: WorldPoint, max_radius: float = 8.0
) -> WorldPoint:
    """The nearest walkable point to ``origin``, spiralling outward.

    Used for spawning and for evacuating a retiring chunk. Searches rings of
    increasing radius at eight compass points each, which is coarse but converges
    fast and cannot loop forever.
    """
    if world.is_walkable_at(origin):
        return origin

    offsets = (
        (1.0, 0.0), (-1.0, 0.0), (0.0, 1.0), (0.0, -1.0),
        (0.7071067811865476, 0.7071067811865476),
        (-0.7071067811865476, 0.7071067811865476),
        (0.7071067811865476, -0.7071067811865476),
        (-0.7071067811865476, -0.7071067811865476),
    )

    radius = 1.0
    while radius <= max_radius:
        for ox, oy in offsets:
            candidate = WorldPoint(origin.x + ox * radius, origin.y + oy * radius)
            if world.is_walkable_at(candidate):
                return candidate
        radius += 1.0

    # Nothing walkable nearby. Returning the origin is wrong but survivable; the
    # caller will try again next tick and terrain is mutable.
    return origin


def _clamp(value: float, low: float, high: float) -> float:
    if value < low:
        return low
    if value > high:
        return high
    return value
