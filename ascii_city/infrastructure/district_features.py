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
    CATEGORY_OFFICE,
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
    PROP_TREE,
    PROP_VENDING,
)

__all__ = ["enrich_district", "PROP_KIOSK", "PROP_LAMP", "PROP_SIGN", "PROP_TREE"]

INTERIOR_CATEGORIES = {CATEGORY_SHOP, CATEGORY_APARTMENT, CATEGORY_OFFICE}


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
            CATEGORY_SHOP: 0.85,
            CATEGORY_APARTMENT: 0.5,
            CATEGORY_OFFICE: 0.35,
        }.get(building.category, 0.0)
        if width < 4 or height < 4 or not rng.chance(chance):
            updated.append(building)
            continue

        floor_style = pack_style(building.category, 2, 1)
        for y in range(y0 + 1, y1 - 1):
            for x in range(x0 + 1, x1 - 1):
                # An interior floor is walkable and lit, which is exactly what
                # CELL_INTERACTIVE already means to both simulation and client.
                canvas.paint(x, y, CELL_INTERACTIVE, 0, floor_style)

        for prop in _furnish(x0, y0, x1, y1, building.category, rng, next_id):
            furniture.append(prop)
            next_id += 1

        door_x, door_y = _pick_door(canvas, x0, y0, x1, y1, rng)
        canvas.paint(door_x, door_y, CELL_INTERACTIVE, 0, pack_style(building.category, 2, 1))
        interior_kind = {CATEGORY_SHOP: "shop", CATEGORY_APARTMENT: "flat", CATEGORY_OFFICE: "office"}.get(
            building.category, "room"
        )
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


def _furnish(
    x0: int, y0: int, x1: int, y1: int, category: int, rng: Mulberry32, first_id: int
) -> list[Prop]:
    """Light the room, then line its walls with whatever it sells."""
    props = [Prop(id=first_id, x=(x0 + x1) // 2, y=(y0 + y1) // 2, kind=PROP_LAMP)]
    against_wall = {
        CATEGORY_SHOP: (PROP_VENDING, PROP_SIGN),
        CATEGORY_APARTMENT: (PROP_PLANTER, PROP_BENCH),
        CATEGORY_OFFICE: (PROP_PLANTER, PROP_BANNER),
    }.get(category, (PROP_PLANTER,))
    next_id = first_id + 1
    for y in range(y0 + 1, y1 - 1):
        for x in range(x0 + 1, x1 - 1):
            on_wall = x in (x0 + 1, x1 - 2) or y in (y0 + 1, y1 - 2)
            if not on_wall or not rng.chance(0.22):
                continue
            props.append(
                Prop(id=next_id, x=x, y=y, kind=against_wall[rng.below(len(against_wall))])
            )
            next_id += 1
    return props


def _pick_door(
    canvas: Canvas, x0: int, y0: int, x1: int, y1: int, rng: Mulberry32
) -> tuple[int, int]:
    """Prefer a door cell that faces the nearest road."""
    candidates: list[tuple[int, int, int]] = []
    for x in range(x0, x1):
        candidates.append((x, y0, _road_distance(canvas, x, y0)))
        candidates.append((x, y1 - 1, _road_distance(canvas, x, y1 - 1)))
    for y in range(y0, y1):
        candidates.append((x0, y, _road_distance(canvas, x0, y)))
        candidates.append((x1 - 1, y, _road_distance(canvas, x1 - 1, y)))
    candidates.sort(key=lambda item: item[2])
    best = [item for item in candidates if item[2] == candidates[0][2]]
    pick = best[rng.below(len(best))]
    return pick[0], pick[1]


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
            if canvas.get(x, y - 1) == CELL_SIDEWALK:
                canvas.paint(x, y - 1, CELL_SIDEWALK, 3, pack_style(CATEGORY_SHOP, 1, 2))
            if canvas.get(x, y + 1) == CELL_SIDEWALK:
                canvas.paint(x, y + 1, CELL_SIDEWALK, 3, pack_style(CATEGORY_SHOP, 1, 2))


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
                        canvas.paint(x, y, CELL_SIDEWALK, 4, pack_style(CATEGORY_OFFICE, 3, 0))
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

