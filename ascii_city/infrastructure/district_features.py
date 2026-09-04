"""Tokyo-inspired district dressing layered on top of the procedural grid.

The base generator lays out avenues and blocks; this pass adds the street-level
detail that makes the place read as a city rather than a field of boxes:
covered arcades, shop doors you can walk through, neon signage, pedestrian
bridges and the narrow alleys between blocks.
"""

from __future__ import annotations

from typing import Sequence

from ..domain.constants import (
    CATEGORY_APARTMENT,
    CATEGORY_HOUSE,
    CATEGORY_OFFICE,
    CATEGORY_OTHER,
    CATEGORY_SHOP,
    CATEGORY_SKYSCRAPER,
    CATEGORY_STATION,
    CELL_BLOCKED,
    CELL_BUILDING,
    CELL_FREE,
    CELL_INTERACTIVE,
    CELL_ROAD,
    CELL_SIDEWALK,
    ROAD_AVENUE,
    ROAD_STREET,
)
from ..domain.world import Building, Prop
from .canvas import Canvas, pack_style
from .rng import Mulberry32

from ..domain.constants import (
    PROP_BANNER,
    PROP_BENCH,
    PROP_KIOSK,
    PROP_LAMP,
    PROP_PLANTER,
    PROP_SIGN,
    PROP_STALL,
    PROP_TREE,
    PROP_VENDING,
)

__all__ = ["enrich_district", "PROP_KIOSK", "PROP_LAMP", "PROP_SIGN", "PROP_TREE"]

INTERIOR_CATEGORIES = {CATEGORY_SHOP, CATEGORY_APARTMENT, CATEGORY_OFFICE}

"""Cell codes a door may open onto. Anything else is somebody else's wall."""
OPENS_ONTO = (CELL_ROAD, CELL_SIDEWALK, CELL_FREE)


def enrich_district(
    canvas: Canvas,
    buildings: list[Building],
    bands_x: Sequence[object],
    bands_y: Sequence[object],
    rng: Mulberry32,
) -> tuple[list[Building], list[Prop]]:
    """Return updated buildings and extra props to merge into the district."""
    buildings, interior_props = carve_interiors(canvas, buildings, rng.fork(0xA11))
    paint_covered_arcades(canvas, bands_x, bands_y, rng.fork(0xA12))
    paint_pedestrian_bridges(canvas, bands_x, bands_y, rng.fork(0xA13))
    paint_torii_gates(canvas, bands_x, bands_y, rng.fork(0xA14))
    paint_narrow_alleys(canvas, rng.fork(0xA15))
    props = add_neon_signage(canvas, buildings, rng.fork(0xA16))
    return buildings, props + interior_props


def carve_interiors(
    canvas: Canvas, buildings: list[Building], rng: Mulberry32
) -> tuple[list[Building], list[Prop]]:
    """Hollow large footprints, punch a street-facing door, and furnish them.

    An empty black box is worse than a solid one: it invites you in and then
    shows you nothing. Every carved room therefore gets a floor the renderer
    can tell from open ground, a lamp, and something along its walls.
    """
    updated: list[Building] = []
    furniture: list[Prop] = []
    next_id = 20_000
    for building in buildings:
        xs = building.footprint[0::2]
        ys = building.footprint[1::2]
        x0, x1 = min(xs), max(xs) + 1
        y0, y1 = min(ys), max(ys) + 1
        width = x1 - x0
        height = y1 - y0
        chance = {
            CATEGORY_SHOP: 1.0,
            CATEGORY_APARTMENT: 0.85,
            CATEGORY_OFFICE: 0.75,
            CATEGORY_STATION: 1.0,
            CATEGORY_HOUSE: 0.6,
        }.get(building.category, 0.0)
        if width < 4 or height < 4 or not rng.chance(chance):
            updated.append(building)
            continue

        # A door that opens onto the neighbour's wall is not a door. If nothing
        # on this footprint faces open ground, the building stays solid rather
        # than becoming a sealed room nobody can find the way into.
        found = _pick_doorway(canvas, x0, y0, x1, y1, rng)
        if found is None:
            updated.append(building)
            continue
        doorway, outward = found

        floor_style = pack_style(building.category, 2, 1)
        for y in range(y0 + 1, y1 - 1):
            for x in range(x0 + 1, x1 - 1):
                # An interior floor is walkable and lit, which is exactly what
                # CELL_INTERACTIVE already means to both simulation and client.
                canvas.paint(x, y, CELL_INTERACTIVE, 0, floor_style)

        _partition(canvas, x0, y0, x1, y1, building.category, rng)

        entrance_style = pack_style(building.category, 3, 3)
        for door_x, door_y in doorway:
            canvas.paint(door_x, door_y, CELL_INTERACTIVE, 0, entrance_style)

        for prop in _furnish(x0, y0, x1, y1, building.category, set(doorway), rng, next_id):
            furniture.append(prop)
            next_id += 1

        # A lit sign beside the door is what tells you from across the street
        # that this particular box is one you can walk into.
        for prop in _entrance_marks(doorway, outward, next_id):
            furniture.append(prop)
            next_id += 1

        interior_kind = {
            CATEGORY_SHOP: "shop",
            CATEGORY_APARTMENT: "flat",
            CATEGORY_OFFICE: "office",
            CATEGORY_STATION: "hall",
            CATEGORY_HOUSE: "house",
        }.get(building.category, "room")
        updated.append(
            Building(
                id=building.id,
                footprint=building.footprint,
                height=building.height,
                min_height=building.min_height,
                levels=building.levels,
                roof_type=building.roof_type,
                category=building.category,
                facade_style=building.facade_style,
                window_style=building.window_style,
                color=building.color,
                walkable=False,
                interior_id=f"{interior_kind}-{building.id}",
            )
        )
    return updated, furniture


def _partition(
    canvas: Canvas, x0: int, y0: int, x1: int, y1: int, category: int, rng: Mulberry32
) -> None:
    """Split a deep room with a back wall, so it is not one empty hall.

    The gap is two cells wide for the same reason the front door is: a single
    two-metre cell between two walls is a squeeze the player has to aim at.
    """
    inner_w = x1 - x0 - 2
    inner_h = y1 - y0 - 2
    if max(inner_w, inner_h) < 6 or min(inner_w, inner_h) < 3:
        return
    if not rng.chance(0.55):
        return

    style = pack_style(category, 1, 0)
    if inner_w >= inner_h:
        wall_x = x0 + 3 + rng.below(inner_w - 4)
        gap_y = y0 + 1 + rng.below(inner_h - 1)
        for y in range(y0 + 1, y1 - 1):
            if y in (gap_y, gap_y + 1):
                continue
            canvas.paint(wall_x, y, CELL_BUILDING, 4, style)
    else:
        wall_y = y0 + 3 + rng.below(inner_h - 4)
        gap_x = x0 + 1 + rng.below(inner_w - 1)
        for x in range(x0 + 1, x1 - 1):
            if x in (gap_x, gap_x + 1):
                continue
            canvas.paint(x, wall_y, CELL_BUILDING, 4, style)


def _furnish(
    x0: int,
    y0: int,
    x1: int,
    y1: int,
    category: int,
    doorway: set[tuple[int, int]],
    rng: Mulberry32,
    first_id: int,
) -> list[Prop]:
    """Light the room, then line its walls with whatever it sells."""
    props = [Prop(id=first_id, x=(x0 + x1) // 2, y=(y0 + y1) // 2, kind=PROP_LAMP)]
    against_wall = {
        CATEGORY_SHOP: (PROP_VENDING, PROP_SIGN, PROP_STALL),
        CATEGORY_APARTMENT: (PROP_PLANTER, PROP_BENCH),
        CATEGORY_OFFICE: (PROP_PLANTER, PROP_BANNER),
        CATEGORY_STATION: (PROP_VENDING, PROP_BENCH, PROP_BANNER),
        CATEGORY_HOUSE: (PROP_PLANTER, PROP_BENCH),
    }.get(category, (PROP_PLANTER,))
    next_id = first_id + 1
    for y in range(y0 + 1, y1 - 1):
        for x in range(x0 + 1, x1 - 1):
            on_wall = x in (x0 + 1, x1 - 2) or y in (y0 + 1, y1 - 2)
            # Standing in the doorway you want to see the room, not the back of
            # a vending machine parked across it.
            blocks_the_way = any(abs(x - dx) + abs(y - dy) <= 1 for dx, dy in doorway)
            if not on_wall or blocks_the_way or not rng.chance(0.26):
                continue
            props.append(
                Prop(id=next_id, x=x, y=y, kind=against_wall[rng.below(len(against_wall))])
            )
            next_id += 1
    return props


def _pick_doorway(
    canvas: Canvas, x0: int, y0: int, x1: int, y1: int, rng: Mulberry32
) -> tuple[list[tuple[int, int]], tuple[int, int]] | None:
    """Two adjacent perimeter cells that open onto ground you can stand on.

    Width is the whole point. A door one cell across is two metres of gap with
    a wall either side, and the player is seven tenths of a metre wide with a
    bounding box for a hitbox: you have to line the doorway up to get through
    it. Two cells is a gap you can walk into without aiming.
    """
    best_score = 99
    best: list[tuple[list[tuple[int, int]], tuple[int, int]]] = []
    for run, outward in _perimeter_runs(x0, y0, x1, y1):
        for index in range(len(run) - 1):
            pair = [run[index], run[index + 1]]
            if any(
                canvas.get(x + outward[0], y + outward[1]) not in OPENS_ONTO for x, y in pair
            ):
                continue
            score = min(_road_distance(canvas, x, y) for x, y in pair)
            if score < best_score:
                best_score = score
                best = []
            if score == best_score:
                best.append((pair, outward))
    if not best:
        return None
    return best[rng.below(len(best))]


def _perimeter_runs(
    x0: int, y0: int, x1: int, y1: int
) -> list[tuple[list[tuple[int, int]], tuple[int, int]]]:
    """Each wall of the footprint, corners excluded, with its outward normal."""
    return [
        ([(x, y0) for x in range(x0 + 1, x1 - 1)], (0, -1)),
        ([(x, y1 - 1) for x in range(x0 + 1, x1 - 1)], (0, 1)),
        ([(x0, y) for y in range(y0 + 1, y1 - 1)], (-1, 0)),
        ([(x1 - 1, y) for y in range(y0 + 1, y1 - 1)], (1, 0)),
    ]


def _entrance_marks(
    doorway: list[tuple[int, int]], outward: tuple[int, int], first_id: int
) -> list[Prop]:
    """A lamp and a sign on the pavement outside, flanking the way in."""
    ox, oy = outward
    front = [(x + ox, y + oy) for x, y in doorway]
    return [
        Prop(id=first_id, x=front[0][0], y=front[0][1], kind=PROP_LAMP),
        Prop(id=first_id + 1, x=front[-1][0], y=front[-1][1], kind=PROP_SIGN),
    ]


def _road_distance(canvas: Canvas, x: int, y: int) -> int:
    best = 99
    for radius in range(1, 8):
        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                if canvas.get(x + dx, y + dy) == CELL_ROAD:
                    return radius
        best = min(best, radius)
    return best


def paint_covered_arcades(
    canvas: Canvas, bands_x: Sequence[object], bands_y: Sequence[object], rng: Mulberry32
) -> None:
    """Paint sidewalk awnings along major avenues — a Tokyo shopping street staple."""
    for band in bands_x:
        if band.kind != ROAD_AVENUE:
            continue
        if not rng.chance(0.55):
            continue
        y = band.start + band.width // 2
        for x in range(2, canvas.width - 2, 3):
            # One riser above the road: an arcade floor you step up onto.
            if canvas.get(x, y - 1) == CELL_SIDEWALK:
                canvas.paint(x, y - 1, CELL_SIDEWALK, 1, pack_style(CATEGORY_SHOP, 1, 2))
            if canvas.get(x, y + 1) == CELL_SIDEWALK:
                canvas.paint(x, y + 1, CELL_SIDEWALK, 1, pack_style(CATEGORY_SHOP, 1, 2))


def paint_pedestrian_bridges(
    canvas: Canvas, bands_x: Sequence[object], bands_y: Sequence[object], rng: Mulberry32
) -> None:
    """Span some intersections with a low pedestrian deck."""
    avenues = [band for band in bands_x if band.kind == ROAD_AVENUE]
    streets = [band for band in bands_y if band.kind == ROAD_STREET]
    for avenue in avenues:
        for street in streets:
            if not rng.chance(0.18):
                continue
            cx = avenue.start + avenue.width // 2
            cy = street.start + street.width // 2
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    x, y = cx + dx, cy + dy
                    if canvas.get(x, y) == CELL_ROAD:
                        # Half a metre proud of the asphalt: a raised crossing
                        # you walk up onto rather than a deck overhead.
                        canvas.paint(x, y, CELL_SIDEWALK, 2, pack_style(CATEGORY_OFFICE, 3, 0))
            # Arch ribs on the long axis.
            for offset in range(-2, 3):
                canvas.paint(cx + offset, cy - 2, CELL_BUILDING, 5, pack_style(CATEGORY_STATION, 0, 0))
                canvas.paint(cx + offset, cy + 2, CELL_BUILDING, 5, pack_style(CATEGORY_STATION, 0, 0))


def paint_torii_gates(
    canvas: Canvas, bands_x: Sequence[object], bands_y: Sequence[object], rng: Mulberry32
) -> None:
    """Mark a few alley mouths with paired pillars."""
    for band in bands_y:
        if not rng.chance(0.08):
            continue
        x = band.start + band.width // 2
        y = rng.between(8, canvas.height - 8)
        if canvas.get(x, y) != CELL_ROAD:
            continue
        canvas.paint(x - 1, y, CELL_BUILDING, 6, pack_style(CATEGORY_SHOP, 4, 0))
        canvas.paint(x + 1, y, CELL_BUILDING, 6, pack_style(CATEGORY_SHOP, 4, 0))


def paint_relief(canvas: Canvas, rng: Mulberry32) -> None:
    """Raise open ground into terraces and stair the way up onto them.

    A flat district is a floor plan you walk around on. Lifting a forecourt by
    four risers and cutting a flight down to the kerb costs one byte a cell —
    the height layer is already there — and gives the street somewhere to look
    up at, somewhere to jump off, and a reason to look where you are going.

    Terraces stay under the height a player can clear from a standing jump, so
    even a plateau whose stairs were crowded out by a building is somewhere you
    can get down from rather than a trap.
    """
    style = pack_style(CATEGORY_OTHER, 2, 0)
    for _ in range(rng.between(150, 240)):
        width = rng.between(3, 10)
        height = rng.between(3, 10)
        x0 = rng.between(2, max(3, canvas.width - width - 2))
        y0 = rng.between(2, max(3, canvas.height - height - 2))
        x1, y1 = x0 + width, y0 + height
        if not _all_open(canvas, x0, y0, x1, y1):
            continue

        levels = rng.between(2, 6)
        # A terrace nobody can climb is a wall. At least one side has to have
        # room for the whole flight before the plateau goes down.
        flights = [
            (dx, dy)
            for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0))
            if _has_room_for_stairs(canvas, x0, y0, x1, y1, dx, dy, levels)
        ]
        if not flights:
            continue

        for y in range(y0, y1):
            for x in range(x0, x1):
                canvas.paint(x, y, CELL_SIDEWALK, levels, style)

        for dx, dy in flights:
            _cut_stairs(canvas, x0, y0, x1, y1, dx, dy, levels, style)


def _all_open(canvas: Canvas, x0: int, y0: int, x1: int, y1: int) -> bool:
    """Unbuilt ground only. Pushing a road up would cut the district in two."""
    return all(
        canvas.get(x, y) in (CELL_FREE, CELL_SIDEWALK) and canvas.height_at(x, y) == 0
        for y in range(y0, y1)
        for x in range(x0, x1)
    )


def _has_room_for_stairs(
    canvas: Canvas, x0: int, y0: int, x1: int, y1: int, dx: int, dy: int, levels: int
) -> bool:
    for cell_x, cell_y in _flight_cells(x0, y0, x1, y1, dx, dy, levels):
        if canvas.get(cell_x, cell_y) not in (CELL_FREE, CELL_SIDEWALK):
            return False
        if canvas.height_at(cell_x, cell_y) != 0:
            return False
    return True


def _cut_stairs(
    canvas: Canvas, x0: int, y0: int, x1: int, y1: int, dx: int, dy: int, levels: int, style: int
) -> None:
    """One riser per cell, walking down from the plateau to street level."""
    for index, (cell_x, cell_y) in enumerate(_flight_cells(x0, y0, x1, y1, dx, dy, levels)):
        canvas.paint(cell_x, cell_y, CELL_SIDEWALK, levels - 1 - index // _FLIGHT_WIDTH, style)


_FLIGHT_WIDTH = 2
"""Cells across. One is four metres of stair to aim at through a two metre gap."""


def _flight_cells(
    x0: int, y0: int, x1: int, y1: int, dx: int, dy: int, levels: int
) -> list[tuple[int, int]]:
    """The cells a flight off one side would occupy, nearest riser first."""
    if dx:
        edge_x = x1 - 1 if dx > 0 else x0
        start_y = (y0 + y1) // 2 - _FLIGHT_WIDTH // 2
        return [
            (edge_x + dx * (step + 1), start_y + across)
            for step in range(levels - 1)
            for across in range(_FLIGHT_WIDTH)
        ]
    edge_y = y1 - 1 if dy > 0 else y0
    start_x = (x0 + x1) // 2 - _FLIGHT_WIDTH // 2
    return [
        (start_x + across, edge_y + dy * (step + 1))
        for step in range(levels - 1)
        for across in range(_FLIGHT_WIDTH)
    ]


def paint_narrow_alleys(canvas: Canvas, rng: Mulberry32) -> None:
    """Cut footpaths through oversized blocks."""
    for _ in range(rng.between(6, 14)):
        x = rng.between(4, canvas.width - 5)
        y0 = rng.between(4, canvas.height - 20)
        length = rng.between(6, 18)
        for y in range(y0, min(canvas.height - 2, y0 + length)):
            if canvas.get(x, y) == CELL_FREE:
                canvas.paint(x, y, CELL_ROAD, 0, 2)


def add_neon_signage(canvas: Canvas, buildings: list[Building], rng: Mulberry32) -> list[Prop]:
    """Street-level signage and vending corners."""
    props: list[Prop] = []
    next_id = 10_000
    for building in buildings:
        if building.category not in (CATEGORY_SHOP, CATEGORY_SKYSCRAPER, CATEGORY_APARTMENT):
            continue
        if not rng.chance(0.75 if building.category == CATEGORY_SHOP else 0.35):
            continue
        xs = building.footprint[0::2]
        ys = building.footprint[1::2]
        x = int(sum(xs) / len(xs))
        # The sign hangs off the facade, so it goes on the free cell in front
        # of the wall rather than inside the building it advertises.
        for y in (min(ys) - 1, max(ys) + 1):
            if canvas.get(x, y) in (CELL_SIDEWALK, CELL_ROAD, CELL_FREE, CELL_INTERACTIVE):
                props.append(Prop(id=next_id, x=x, y=y, kind=PROP_SIGN))
                next_id += 1
                break
    for _ in range(rng.between(8, 20)):
        x = rng.between(2, canvas.width - 3)
        y = rng.between(2, canvas.height - 3)
        if canvas.get(x, y) == CELL_SIDEWALK:
            props.append(Prop(id=next_id, x=x, y=y, kind=PROP_KIOSK))
            next_id += 1
    return props

