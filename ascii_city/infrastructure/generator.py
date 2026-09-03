"""Procedural district generator.

The whole district is painted onto one canvas and then sliced into tiles, so
road networks stay continuous across tile seams. Output conforms to the same
:class:`~ascii_city.domain.world.WorldTile` an OSM import would produce.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

from ..domain.constants import (
    CATEGORY_APARTMENT,
    CATEGORY_HOUSE,
    CATEGORY_OFFICE,
    CATEGORY_OTHER,
    CATEGORY_SHOP,
    CATEGORY_SKYSCRAPER,
    CATEGORY_WAREHOUSE,
    CELL_BLOCKED,
    CELL_BUILDING,
    CELL_FREE,
    CELL_INTERACTIVE,
    CELL_ROAD,
    CELL_SIDEWALK,
    LEVEL_HEIGHT_M,
    MAX_BUILDING_HEIGHT_M,
    ROAD_AVENUE,
    ROAD_STREET,
    ROOF_ANTENNA,
    ROOF_FLAT,
    ROOF_GABLED,
)
from ..domain.ports import WorldGeneratorPort
from ..domain.world import (
    Building,
    Prop,
    Road,
    SpawnPoint,
    WorldDescriptor,
    WorldTile,
)
from .canvas import Canvas, pack_style, slice_into_tiles
from .district_features import enrich_district
from .rng import Mulberry32

__all__ = ["DistrictGenerator", "pack_style"]

AVENUE_WIDTH = 5
STREET_WIDTH = 3
MIN_BLOCK_SIDE = 8
MAX_FOOTPRINT_SIDE = 8
# Cells between parallel roads. Twenty to thirty-two cells is 40-64 m, which
# reads as a real city block from street level instead of a maze.
STREET_SPACING = (16, 28)
AVENUE_SPACING = (48, 72)

PROP_LAMP = 0
PROP_TREE = 1
PROP_KIOSK = 2


@dataclass(frozen=True, slots=True)
class _Band:
    """One road corridor, expressed as a half-open cell range on one axis."""

    start: int
    width: int
    kind: int

    @property
    def end(self) -> int:
        return self.start + self.width


def _height_ceiling_for_area(cells: int) -> int:
    """Stop a three-by-three footprint from becoming a two-hundred metre tower."""
    return min(MAX_BUILDING_HEIGHT_M, 10 + cells * 4)


class DistrictGenerator(WorldGeneratorPort):
    """Seeded generator for a dense night-time city district."""

    @property
    def source(self) -> str:
        return "procedural"

    def generate_tiles(self, descriptor: WorldDescriptor) -> Sequence[WorldTile]:
        cells = descriptor.tile_cells
        width = descriptor.tiles_x * cells
        height = descriptor.tiles_y * cells
        root = Mulberry32(descriptor.seed)

        canvas = Canvas(width, height)
        bands_x = self._bands(root.fork(0x1), width)
        bands_y = self._bands(root.fork(0x2), height)
        self._paint_roads(canvas, bands_x, bands_y)

        downtown = self._downtown(root.fork(0x3), width, height)
        buildings = self._fill_blocks(canvas, bands_x, bands_y, root.fork(0x4), downtown)
        buildings, extra_props = enrich_district(
            canvas, buildings, bands_x, bands_y, root.fork(0x7)
        )
        self._paint_sidewalks(canvas)

        roads = self._road_records(bands_x, bands_y, width, height)
        props = self._props(canvas, root.fork(0x5)) + extra_props
        spawns = self._spawn_points(canvas, root.fork(0x6))
        return slice_into_tiles(descriptor, canvas, buildings, roads, props, spawns)

    # --- layout ------------------------------------------------------------

    def _bands(self, rng: Mulberry32, extent: int) -> tuple[_Band, ...]:
        """Wide avenues first, then narrower streets filling every gap."""
        avenues: list[_Band] = []
        position = rng.between(3, 14)
        while position + AVENUE_WIDTH < extent - 8:
            avenues.append(_Band(position, AVENUE_WIDTH, ROAD_AVENUE))
            position += AVENUE_WIDTH + rng.between(*AVENUE_SPACING)

        bands = list(avenues)
        boundaries = [0] + [band.end for band in avenues]
        limits = [band.start for band in avenues] + [extent]
        for gap_start, gap_end in zip(boundaries, limits):
            cursor = gap_start + rng.between(*STREET_SPACING)
            while cursor + STREET_WIDTH + MIN_BLOCK_SIDE < gap_end:
                bands.append(_Band(cursor, STREET_WIDTH, ROAD_STREET))
                cursor += STREET_WIDTH + rng.between(*STREET_SPACING)
        bands.sort(key=lambda band: band.start)
        return tuple(bands)

    def _paint_roads(
        self, canvas: Canvas, bands_x: Sequence[_Band], bands_y: Sequence[_Band]
    ) -> None:
        for band in bands_x:
            canvas.fill(band.start, 0, band.end, canvas.height, CELL_ROAD, 0, band.kind)
        for band in bands_y:
            canvas.fill(0, band.start, canvas.width, band.end, CELL_ROAD, 0, band.kind)

    @staticmethod
    def _gaps(bands: Sequence[_Band], extent: int) -> list[tuple[int, int]]:
        gaps: list[tuple[int, int]] = []
        cursor = 0
        for band in bands:
            if band.start - cursor >= MIN_BLOCK_SIDE:
                gaps.append((cursor, band.start))
            cursor = max(cursor, band.end)
        if extent - cursor >= MIN_BLOCK_SIDE:
            gaps.append((cursor, extent))
        return gaps

    def _downtown(self, rng: Mulberry32, width: int, height: int) -> tuple[float, float]:
        """Offset the tall cluster from dead centre so the skyline is not symmetric."""
        return (
            width * 0.5 + (rng.next_float() - 0.5) * width * 0.18,
            height * 0.5 + (rng.next_float() - 0.5) * height * 0.18,
        )

    # --- blocks ------------------------------------------------------------

    def _fill_blocks(
        self,
        canvas: Canvas,
        bands_x: Sequence[_Band],
        bands_y: Sequence[_Band],
        rng: Mulberry32,
        downtown: tuple[float, float],
    ) -> list[Building]:
        buildings: list[Building] = []
        next_id = 1
        radius = 0.5 * min(canvas.width, canvas.height)
        for x0, x1 in self._gaps(bands_x, canvas.width):
            for y0, y1 in self._gaps(bands_y, canvas.height):
                # Leave a one-cell ring free; the sidewalk pass claims it later.
                inner = (x0 + 1, y0 + 1, x1 - 1, y1 - 1)
                if inner[2] - inner[0] < 3 or inner[3] - inner[1] < 3:
                    continue
                roll = rng.next_float()
                if roll < 0.07:
                    self._make_park(canvas, inner, rng)
                    continue
                if roll < 0.12:
                    canvas.fill(*inner, CELL_SIDEWALK)
                    continue
                for leaf in self._subdivide(inner, rng):
                    if rng.chance(0.10):
                        continue  # courtyard or service alley
                    building = self._make_building(canvas, leaf, next_id, rng, downtown, radius)
                    if building is not None:
                        buildings.append(building)
                        next_id += 1
        return buildings

    def _subdivide(
        self, rect: tuple[int, int, int, int], rng: Mulberry32, depth: int = 0
    ) -> list[tuple[int, int, int, int]]:
        x0, y0, x1, y1 = rect
        width = x1 - x0
        height = y1 - y0
        if depth >= 6 or (width <= MAX_FOOTPRINT_SIDE and height <= MAX_FOOTPRINT_SIDE):
            return [rect]
        if width >= height:
            if width < 7:
                return [rect]
            low = max(3, width // 3)
            cut = x0 + rng.between(low, width - low)
            return self._subdivide((x0, y0, cut, y1), rng, depth + 1) + self._subdivide(
                (cut, y0, x1, y1), rng, depth + 1
            )
        if height < 7:
            return [rect]
        low = max(3, height // 3)
        cut = y0 + rng.between(low, height - low)
        return self._subdivide((x0, y0, x1, cut), rng, depth + 1) + self._subdivide(
            (x0, cut, x1, y1), rng, depth + 1
        )

    def _make_park(
        self, canvas: Canvas, rect: tuple[int, int, int, int], rng: Mulberry32
    ) -> None:
        x0, y0, x1, y1 = rect
        canvas.fill(x0, y0, x1, y1, CELL_FREE)
        style = pack_style(CATEGORY_OTHER, 0, 0)
        for _ in range((x1 - x0) * (y1 - y0) // 12):
            tx = rng.between(x0, x1 - 1)
            ty = rng.between(y0, y1 - 1)
            canvas.paint(tx, ty, CELL_BLOCKED, rng.between(5, 9), style)

    def _make_building(
        self,
        canvas: Canvas,
        rect: tuple[int, int, int, int],
        building_id: int,
        rng: Mulberry32,
        downtown: tuple[float, float],
        radius: float,
    ) -> Building | None:
        x0, y0, x1, y1 = rect
        # Occasionally pull one edge in to break up perfectly flush block faces.
        if rng.chance(0.18):
            side = rng.below(4)
            if side == 0 and x1 - x0 > 3:
                x0 += 1
            elif side == 1 and x1 - x0 > 3:
                x1 -= 1
            elif side == 2 and y1 - y0 > 3:
                y0 += 1
            elif y1 - y0 > 3:
                y1 -= 1
        if x1 - x0 < 2 or y1 - y0 < 2:
            return None

        centre_x = (x0 + x1) * 0.5
        centre_y = (y0 + y1) * 0.5
        distance = math.hypot(centre_x - downtown[0], centre_y - downtown[1])
        norm = min(1.0, distance / radius) if radius > 0 else 1.0

        category = self._pick_category(rng, norm)
        area = (x1 - x0) * (y1 - y0)
        height = self._pick_height(rng, category, norm, area)
        levels = max(1, int(round(height / LEVEL_HEIGHT_M)))
        facade = rng.below(8)
        window = rng.below(4)
        roof = self._pick_roof(rng, category, height)

        style = pack_style(category, facade, window)
        canvas.fill(x0, y0, x1, y1, CELL_BUILDING, height, style)

        return Building(
            id=building_id,
            footprint=(x0, y0, x1, y0, x1, y1, x0, y1),
            height=height,
            min_height=0,
            levels=levels,
            roof_type=roof,
            category=category,
            facade_style=facade,
            window_style=window,
            color=category,
        )

    @staticmethod
    def _pick_category(rng: Mulberry32, norm: float) -> int:
        roll = rng.next_float()
        if norm < 0.22:
            return CATEGORY_SKYSCRAPER if roll < 0.62 else CATEGORY_OFFICE
        if norm < 0.45:
            if roll < 0.08:
                return CATEGORY_SKYSCRAPER
            if roll < 0.42:
                return CATEGORY_OFFICE
            if roll < 0.72:
                return CATEGORY_SHOP if roll < 0.58 else CATEGORY_APARTMENT
            return CATEGORY_SHOP
        if norm < 0.75:
            if roll < 0.40:
                return CATEGORY_APARTMENT
            if roll < 0.65:
                return CATEGORY_SHOP
            if roll < 0.90:
                return CATEGORY_HOUSE
            return CATEGORY_WAREHOUSE
        if roll < 0.45:
            return CATEGORY_HOUSE
        if roll < 0.65:
            return CATEGORY_SHOP
        if roll < 0.80:
            return CATEGORY_APARTMENT
        return CATEGORY_WAREHOUSE

    @staticmethod
    def _pick_height(rng: Mulberry32, category: int, norm: float, area: int) -> int:
        base = {
            CATEGORY_HOUSE: (6, 6),
            CATEGORY_SHOP: (5, 5),
            CATEGORY_APARTMENT: (12, 27),
            CATEGORY_OFFICE: (20, 34),
            CATEGORY_SKYSCRAPER: (65, 120),
            CATEGORY_WAREHOUSE: (8, 8),
        }.get(category, (12, 6))
        height = base[0] + rng.below(base[1] + 1)
        if category in (CATEGORY_SKYSCRAPER, CATEGORY_OFFICE):
            # Taper the skyline outwards from downtown.
            height = int(height * (1.0 - 0.45 * norm))
        return max(4, min(height, _height_ceiling_for_area(area)))

    @staticmethod
    def _pick_roof(rng: Mulberry32, category: int, height: int) -> int:
        if category in (CATEGORY_HOUSE, CATEGORY_SHOP) and rng.chance(0.45):
            return ROOF_GABLED
        if height >= 60 and rng.chance(0.5):
            return ROOF_ANTENNA
        return ROOF_FLAT

    def _paint_sidewalks(self, canvas: Canvas) -> None:
        """Every free cell touching a road becomes pavement."""
        width, height = canvas.width, canvas.height
        collision = canvas.collision
        promote: list[int] = []
        for y in range(height):
            row = y * width
            for x in range(width):
                index = row + x
                if collision[index] != CELL_FREE:
                    continue
                if (
                    (x > 0 and collision[index - 1] == CELL_ROAD)
                    or (x + 1 < width and collision[index + 1] == CELL_ROAD)
                    or (y > 0 and collision[index - width] == CELL_ROAD)
                    or (y + 1 < height and collision[index + width] == CELL_ROAD)
                ):
                    promote.append(index)
        for index in promote:
            collision[index] = CELL_SIDEWALK

    # --- vector records ----------------------------------------------------

    def _road_records(
        self,
        bands_x: Sequence[_Band],
        bands_y: Sequence[_Band],
        width: int,
        height: int,
    ) -> list[Road]:
        roads: list[Road] = []
        next_id = 1
        for band in bands_x:
            centre = band.start + band.width // 2
            roads.append(
                Road(
                    id=next_id,
                    centerline=(centre, 0, centre, height),
                    width=float(band.width),
                    type=band.kind,
                    walkable=True,
                    surface_style=band.kind,
                    name=f"{_ordinal(next_id)} Avenue" if band.kind == ROAD_AVENUE else None,
                )
            )
            next_id += 1
        for band in bands_y:
            centre = band.start + band.width // 2
            roads.append(
                Road(
                    id=next_id,
                    centerline=(0, centre, width, centre),
                    width=float(band.width),
                    type=band.kind,
                    walkable=True,
                    surface_style=band.kind,
                    name=f"{_ordinal(next_id)} Street" if band.kind == ROAD_AVENUE else None,
                )
            )
            next_id += 1
        return roads

    def _props(self, canvas: Canvas, rng: Mulberry32) -> list[Prop]:
        """Street lamps on pavement corners, plus the odd kiosk."""
        props: list[Prop] = []
        next_id = 1
        step = 7
        for y in range(1, canvas.height - 1, step):
            for x in range(1, canvas.width - 1, step):
                if canvas.get(x, y) != CELL_SIDEWALK:
                    continue
                touches_road = any(
                    canvas.get(x + dx, y + dy) == CELL_ROAD
                    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
                )
                if not touches_road or not rng.chance(0.55):
                    continue
                kind = PROP_KIOSK if rng.chance(0.08) else PROP_LAMP
                if kind == PROP_KIOSK:
                    canvas.paint(x, y, CELL_INTERACTIVE, 3, pack_style(CATEGORY_OTHER, 1, 0))
                props.append(Prop(id=next_id, x=x, y=y, kind=kind))
                next_id += 1
        return props

    def _spawn_points(self, canvas: Canvas, rng: Mulberry32) -> list[SpawnPoint]:
        """One safe road cell per region of a three-by-three partition."""
        spawns: list[SpawnPoint] = []
        regions_x = 3
        regions_y = 3
        region_w = canvas.width // regions_x
        region_h = canvas.height // regions_y
        for ry in range(regions_y):
            for rx in range(regions_x):
                found = self._find_open_road(
                    canvas,
                    rng,
                    rx * region_w,
                    ry * region_h,
                    (rx + 1) * region_w,
                    (ry + 1) * region_h,
                )
                if found is not None:
                    spawns.append(found)
        if len(spawns) < 4:
            # A degenerate seed still has to be playable.
            fallback = self._find_open_road(canvas, rng, 0, 0, canvas.width, canvas.height)
            while fallback is not None and len(spawns) < 4:
                spawns.append(fallback)
                fallback = self._find_open_road(canvas, rng, 0, 0, canvas.width, canvas.height)
        return spawns

    def _find_open_road(
        self, canvas: Canvas, rng: Mulberry32, x0: int, y0: int, x1: int, y1: int
    ) -> SpawnPoint | None:
        for _ in range(400):
            x = rng.between(x0 + 1, max(x0 + 1, x1 - 2))
            y = rng.between(y0 + 1, max(y0 + 1, y1 - 2))
            if canvas.get(x, y) != CELL_ROAD:
                continue
            if any(
                canvas.get(x + dx, y + dy) in (CELL_BUILDING, CELL_BLOCKED)
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
            ):
                continue
            return SpawnPoint(x=x, y=y, heading=self._road_heading(canvas, x, y))
        return None

    @staticmethod
    def _road_heading(canvas: Canvas, x: int, y: int) -> float:
        """Face along whichever axis of the road runs further without a wall."""
        def run(dx: int, dy: int) -> int:
            steps = 0
            while steps < 24 and canvas.get(x + dx * (steps + 1), y + dy * (steps + 1)) == CELL_ROAD:
                steps += 1
            return steps

        options = ((0.0, run(1, 0)), (math.pi, run(-1, 0)), (math.pi / 2, run(0, 1)), (3 * math.pi / 2, run(0, -1)))
        return max(options, key=lambda option: option[1])[0]

_ORDINALS = (
    "First",
    "Second",
    "Third",
    "Fourth",
    "Fifth",
    "Sixth",
    "Seventh",
    "Eighth",
    "Ninth",
    "Tenth",
)


def _ordinal(value: int) -> str:
    return _ORDINALS[(value - 1) % len(_ORDINALS)]
