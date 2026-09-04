"""Terrain mutation and regrowth.

The two halves of the sandbox: players change tiles, and the world slowly changes
them back. GDD 9.2 makes the second half the reason the first one feels alive
rather than permanent, and it is also the resource sink that stops the corridor
being stripped bare.

Regrowth is scheduled rather than swept. A per-tile due time in a dictionary means
the tick cost is proportional to the number of tiles actually waiting, not to the
number of tiles in the world, which matters because there are a thousand tiles per
chunk and only ever a handful mid-regrowth.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..domain.constants import BUILD_RANGE_TILES, CHUNK_TILES, REGROWTH_STAGE_SECONDS
from ..domain.coordinates import WorldPoint
from ..domain.entities import Entity
from ..domain.ports import EventSink
from ..domain.tiles import (
    BUILD_RECIPES,
    HARVEST_RESULTS,
    PLAYER_PLACED_TILES,
    Tile,
    next_regrowth_stage,
)
from ..infrastructure import wire
from .world import World


@dataclass(slots=True)
class BuildOutcome:
    ok: bool
    error: int = 0
    chunk_key: str = ""
    tile_index: int = -1
    tile: int = 0
    gained: dict[str, int] = field(default_factory=dict)
    spent: dict[str, int] = field(default_factory=dict)


def harvest(world: World, actor: Entity, point: WorldPoint, now: float) -> BuildOutcome:
    """Clear a tile and give the actor what it was made of."""
    if not actor.is_alive:
        return BuildOutcome(ok=False, error=wire.ERROR_DEAD)
    if actor.position.distance_to(point) > BUILD_RANGE_TILES:
        return BuildOutcome(ok=False, error=wire.ERROR_OUT_OF_RANGE)

    current = world.tile_at(point)
    result = HARVEST_RESULTS.get(current)

    if result is None:
        # Player-placed structures return their material rather than being
        # indestructible, so a misplaced wall is a mistake and not a monument.
        if current in PLAYER_PLACED_TILES:
            result = (int(Tile.BARE_GROUND), _material_of(current), 1)
        else:
            return BuildOutcome(ok=False, error=wire.ERROR_INVALID)

    replacement, material, quantity = result
    written = world.set_tile_at(point, replacement)
    if written is None:
        return BuildOutcome(ok=False, error=wire.ERROR_INVALID)

    chunk_key, tile_index = written
    actor.give(material, quantity)
    _schedule_regrowth(world, chunk_key, tile_index, now)

    return BuildOutcome(
        ok=True,
        chunk_key=chunk_key,
        tile_index=tile_index,
        tile=replacement,
        gained={material: quantity},
    )


def place(
    world: World, actor: Entity, point: WorldPoint, material: str, now: float
) -> BuildOutcome:
    """Spend material to place a tile."""
    if not actor.is_alive:
        return BuildOutcome(ok=False, error=wire.ERROR_DEAD)
    if actor.position.distance_to(point) > BUILD_RANGE_TILES:
        return BuildOutcome(ok=False, error=wire.ERROR_OUT_OF_RANGE)

    recipe = BUILD_RECIPES.get(material)
    if recipe is None:
        return BuildOutcome(ok=False, error=wire.ERROR_INVALID)

    tile, cost = recipe
    if actor.inventory.get(material, 0) < cost:
        return BuildOutcome(ok=False, error=wire.ERROR_NO_MATERIAL)

    # Refuse to build on top of someone. Without this a player can wall another
    # one into a tile they cannot leave.
    for occupant in world.entities_near(point, 0.8):
        if occupant.entity_id != actor.entity_id and occupant.is_alive:
            return BuildOutcome(ok=False, error=wire.ERROR_INVALID)

    existing = world.tile_at(point)
    if existing in (Tile.DEEP_WATER,):
        return BuildOutcome(ok=False, error=wire.ERROR_INVALID)

    written = world.set_tile_at(point, tile)
    if written is None:
        return BuildOutcome(ok=False, error=wire.ERROR_INVALID)

    actor.take(material, cost)
    chunk_key, tile_index = written
    # A built tile is protected: it does not regrow while it stands.
    _cancel_regrowth(world, chunk_key, tile_index)

    return BuildOutcome(
        ok=True,
        chunk_key=chunk_key,
        tile_index=tile_index,
        tile=int(tile),
        spent={material: cost},
    )


def _material_of(tile: int) -> str:
    for material, (placed, _) in BUILD_RECIPES.items():
        if placed == tile:
            return material
    return "soil"


def _schedule_regrowth(world: World, chunk_key: str, tile_index: int, now: float) -> None:
    view = _chunk_by_key(world, chunk_key)
    if view is not None:
        view.regrowth_due[tile_index] = now + REGROWTH_STAGE_SECONDS


def _cancel_regrowth(world: World, chunk_key: str, tile_index: int) -> None:
    view = _chunk_by_key(world, chunk_key)
    if view is not None:
        view.regrowth_due.pop(tile_index, None)


def _chunk_by_key(world: World, chunk_key: str):
    for view in world.loaded_chunks():
        if view.address.key == chunk_key:
            return view
    return None


def tick_regrowth(world: World, now: float, events: EventSink) -> int:
    """Advance every tile whose regrowth timer has elapsed.

    Batches the changes per chunk and emits one event each, so a chunk with twenty
    tiles regrowing at once produces a single delta rather than twenty.
    """
    advanced = 0

    for view in world.loaded_chunks():
        if not view.regrowth_due:
            continue

        changes: dict[int, int] = {}
        for tile_index, due in list(view.regrowth_due.items()):
            if now < due:
                continue

            current = view.tile(tile_index)
            following = next_regrowth_stage(current)
            if following is None:
                view.regrowth_due.pop(tile_index, None)
                continue

            # A tile with something standing on it stays where it is: nobody wants
            # a tree growing through them.
            if _occupied(world, view, tile_index):
                view.regrowth_due[tile_index] = now + REGROWTH_STAGE_SECONDS
                continue

            view.set_tile(tile_index, following)
            changes[tile_index] = following
            advanced += 1

            if next_regrowth_stage(following) is None:
                view.regrowth_due.pop(tile_index, None)
            else:
                view.regrowth_due[tile_index] = now + REGROWTH_STAGE_SECONDS

        if changes:
            events.tiles_changed(view.address.key, changes)

    return advanced


def _occupied(world: World, view, tile_index: int) -> bool:
    """Whether an entity is standing on a tile that wants to advance."""
    tile_x = tile_index % CHUNK_TILES
    tile_y = tile_index // CHUNK_TILES

    if view.address.space_type.name == "HUB":
        hub = world.hubs.get(view.address.hub_id or 0)
        if hub is None:
            return False
        centre = hub.centre
        point = WorldPoint(
            centre.x + view.address.chunk_x * CHUNK_TILES + tile_x + 0.5,
            centre.y + view.address.chunk_y * CHUNK_TILES + tile_y + 0.5,
        )
    else:
        from ..domain.coordinates import edge_to_world

        point = edge_to_world(
            world.edge,
            view.address.segment_index,
            view.address.lane_offset,
            tile_x + 0.5,
            tile_y + 0.5,
        )

    return any(entity.is_alive for entity in world.entities_near(point, 0.8))


def collect_dirty_overlays(world: World) -> dict[str, dict[int, int]]:
    """Gather unflushed edits and clear their dirty flags.

    The caller is expected to persist what it gets. Clearing here rather than after
    the write is a deliberate trade: a failed flush loses one interval of edits,
    which is inside the thirty-second budget, and the alternative is holding the
    flag until an async write returns while the simulation keeps mutating it.
    """
    pending: dict[str, dict[int, int]] = {}
    for view in world.loaded_chunks():
        if view.dirty:
            pending[view.address.key] = view.snapshot_overlay()
            view.dirty = False
    return pending
