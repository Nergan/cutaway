"""District-wide raster and the cut into tiles.

Both world sources paint the whole district onto one canvas before slicing it,
because a road network has to stay continuous across a tile seam and a building
straddling one has to appear in both tiles. Keeping the machinery here means
the procedural generator and the OSM importer cut their output identically —
there is one definition of what a tile boundary does.
"""

from __future__ import annotations

from typing import Sequence

from ..domain.constants import CELL_BLOCKED
from ..domain.world import (
    Building,
    Prop,
    Road,
    SpawnPoint,
    WorldDescriptor,
    WorldTile,
    tile_id,
)


class Canvas:
    """Mutable district-wide layers before they are cut into tiles."""

    __slots__ = ("width", "height", "collision", "heights", "styles")

    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        size = width * height
        self.collision = bytearray(size)
        self.heights = bytearray(size)
        self.styles = bytearray(size)

    def index(self, x: int, y: int) -> int:
        return y * self.width + x

    def get(self, x: int, y: int) -> int:
        if x < 0 or y < 0 or x >= self.width or y >= self.height:
            return CELL_BLOCKED
        return self.collision[y * self.width + x]

    def height_at(self, x: int, y: int) -> int:
        if x < 0 or y < 0 or x >= self.width or y >= self.height:
            return 0
        return self.heights[y * self.width + x]

    def paint(self, x: int, y: int, code: int, height: int = 0, style: int = 0) -> None:
        if x < 0 or y < 0 or x >= self.width or y >= self.height:
            return
        index = y * self.width + x
        self.collision[index] = code
        self.heights[index] = height
        self.styles[index] = style

    def fill(self, x0: int, y0: int, x1: int, y1: int, code: int, height: int = 0, style: int = 0) -> None:
        for y in range(max(0, y0), min(self.height, y1)):
            for x in range(max(0, x0), min(self.width, x1)):
                index = y * self.width + x
                self.collision[index] = code
                self.heights[index] = height
                self.styles[index] = style


def pack_style(category: int, facade: int, window: int) -> int:
    """Three fields in one byte: category 0-7, facade 0-7, window pattern 0-3."""
    return (category & 0b111) | ((facade & 0b111) << 3) | ((window & 0b11) << 6)


def slice_into_tiles(
    descriptor: WorldDescriptor,
    canvas: Canvas,
    buildings: Sequence[Building],
    roads: Sequence[Road],
    props: Sequence[Prop],
    spawns: Sequence[SpawnPoint],
) -> list[WorldTile]:
    cells = descriptor.tile_cells
    tiles: list[WorldTile] = []
    for tile_y in range(descriptor.tiles_y):
        for tile_x in range(descriptor.tiles_x):
            base_x = tile_x * cells
            base_y = tile_y * cells
            collision = bytearray(cells * cells)
            heights = bytearray(cells * cells)
            styles = bytearray(cells * cells)
            for local_y in range(cells):
                src = (base_y + local_y) * canvas.width + base_x
                dst = local_y * cells
                collision[dst : dst + cells] = canvas.collision[src : src + cells]
                heights[dst : dst + cells] = canvas.heights[src : src + cells]
                styles[dst : dst + cells] = canvas.styles[src : src + cells]

            tiles.append(
                WorldTile(
                    id=tile_id(descriptor.id, tile_x, tile_y),
                    version=descriptor.version,
                    tile_x=tile_x,
                    tile_y=tile_y,
                    cells=cells,
                    cell_size=descriptor.cell_size,
                    collision=collision,
                    heights=heights,
                    styles=styles,
                    buildings=tuple(
                        localise_building(item, base_x, base_y)
                        for item in buildings
                        if owns(item.footprint, base_x, base_y, cells)
                    ),
                    roads=tuple(localise_road(item, base_x, base_y) for item in roads),
                    props=tuple(
                        Prop(id=item.id, x=item.x - base_x, y=item.y - base_y, kind=item.kind)
                        for item in props
                        if base_x <= item.x < base_x + cells and base_y <= item.y < base_y + cells
                    ),
                    spawn_points=tuple(
                        SpawnPoint(x=item.x - base_x, y=item.y - base_y, heading=item.heading)
                        for item in spawns
                        if base_x <= item.x < base_x + cells and base_y <= item.y < base_y + cells
                    ),
                )
            )
    return tiles


def centroid(footprint: Sequence[int]) -> tuple[float, float]:
    xs = footprint[0::2]
    ys = footprint[1::2]
    return sum(xs) / len(xs), sum(ys) / len(ys)


def owns(footprint: Sequence[int], base_x: int, base_y: int, cells: int) -> bool:
    """A building belongs to the tile that contains its centroid, and only that one."""
    cx, cy = centroid(footprint)
    return base_x <= cx < base_x + cells and base_y <= cy < base_y + cells


def localise_building(building: Building, base_x: int, base_y: int) -> Building:
    """Rebase to tile-local cells. Vertices may fall outside; the codec signs them."""
    footprint = tuple(
        value - (base_x if index % 2 == 0 else base_y)
        for index, value in enumerate(building.footprint)
    )
    return Building(
        id=building.id,
        footprint=footprint,
        height=building.height,
        min_height=building.min_height,
        levels=building.levels,
        roof_type=building.roof_type,
        category=building.category,
        facade_style=building.facade_style,
        window_style=building.window_style,
        color=building.color,
        walkable=building.walkable,
        interior_id=building.interior_id,
        source_id=building.source_id,
    )


def localise_road(road: Road, base_x: int, base_y: int) -> Road:
    centerline = tuple(
        value - (base_x if index % 2 == 0 else base_y)
        for index, value in enumerate(road.centerline)
    )
    return Road(
        id=road.id,
        centerline=centerline,
        width=road.width,
        type=road.type,
        walkable=road.walkable,
        surface_style=road.surface_style,
        name=road.name,
    )
