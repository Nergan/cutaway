"""World model: tiles, buildings, roads and the authoritative collision grid.

The same structures describe a procedurally generated district and a district
imported from OpenStreetMap. Only the producer differs, which is what keeps the
OSM pipeline in ``docs/osm-import.md`` a drop-in replacement.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Sequence

from .constants import (
    CATEGORY_NAMES,
    CELL_SIZE_M,
    MAX_BUILDING_HEIGHT_M,
    ROAD_TYPE_NAMES,
    SOLID_CELLS,
    TILE_CELLS,
)
from .errors import WorldDataError


@dataclass(frozen=True, slots=True)
class Building:
    """A single extruded footprint.

    ``footprint`` holds tile-local cell coordinates as a flat ``[x0, y0, x1,
    y1, ...]`` ring. Procedural buildings are rectangles, OSM buildings are
    arbitrary simple polygons; the binary format treats both identically.
    """

    id: int
    footprint: tuple[int, ...]
    height: int
    min_height: int
    levels: int
    roof_type: int
    category: int
    facade_style: int
    window_style: int
    color: int
    walkable: bool = False
    interior_id: str | None = None
    source_id: str | None = None

    def __post_init__(self) -> None:
        if len(self.footprint) < 6 or len(self.footprint) % 2:
            raise WorldDataError(f"Building {self.id} needs at least three (x, y) pairs.")
        if not 0 < self.height <= MAX_BUILDING_HEIGHT_M:
            raise WorldDataError(f"Building {self.id} height {self.height} is out of range.")
        if self.min_height >= self.height:
            raise WorldDataError(f"Building {self.id} min_height must sit below height.")

    @property
    def category_name(self) -> str:
        return CATEGORY_NAMES[self.category]

    @property
    def vertex_count(self) -> int:
        return len(self.footprint) // 2


@dataclass(frozen=True, slots=True)
class Road:
    """A road centreline in tile-local cell coordinates."""

    id: int
    centerline: tuple[int, ...]
    width: float
    type: int
    walkable: bool
    surface_style: int
    name: str | None = None

    def __post_init__(self) -> None:
        if len(self.centerline) < 4 or len(self.centerline) % 2:
            raise WorldDataError(f"Road {self.id} needs at least two (x, y) pairs.")

    @property
    def type_name(self) -> str:
        return ROAD_TYPE_NAMES[self.type]


@dataclass(frozen=True, slots=True)
class SpawnPoint:
    """A validated safe position, in tile-local cell coordinates."""

    x: int
    y: int
    heading: float


@dataclass(frozen=True, slots=True)
class Prop:
    """Street furniture. Purely decorative in the current renderer."""

    id: int
    x: int
    y: int
    kind: int


@dataclass(slots=True)
class WorldTile:
    """One 256 x 256 m square of the world."""

    id: str
    version: int
    tile_x: int
    tile_y: int
    cells: int
    cell_size: float
    collision: bytearray
    heights: bytearray
    styles: bytearray
    buildings: tuple[Building, ...] = ()
    roads: tuple[Road, ...] = ()
    props: tuple[Prop, ...] = ()
    spawn_points: tuple[SpawnPoint, ...] = ()

    def __post_init__(self) -> None:
        expected = self.cells * self.cells
        for name, layer in (
            ("collision", self.collision),
            ("heights", self.heights),
            ("styles", self.styles),
        ):
            if len(layer) != expected:
                raise WorldDataError(
                    f"Tile {self.id} layer {name} has {len(layer)} cells, expected {expected}."
                )

    @property
    def origin_x(self) -> float:
        return self.tile_x * self.cells * self.cell_size

    @property
    def origin_y(self) -> float:
        return self.tile_y * self.cells * self.cell_size

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        span = self.cells * self.cell_size
        return (self.origin_x, self.origin_y, self.origin_x + span, self.origin_y + span)


@dataclass(frozen=True, slots=True)
class WorldDescriptor:
    """Everything a client needs before it starts requesting tiles."""

    id: str
    version: int
    seed: int
    tiles_x: int
    tiles_y: int
    tile_cells: int
    cell_size: float
    source: str

    @property
    def width_m(self) -> float:
        return self.tiles_x * self.tile_cells * self.cell_size

    @property
    def height_m(self) -> float:
        return self.tiles_y * self.tile_cells * self.cell_size


class CollisionGrid:
    """Authoritative walkability for the whole district.

    Tiles are stitched into one flat grid because the server simulates a single
    contiguous district. Streaming worlds would keep per-tile grids and consult
    the tile that owns each sample; the query surface below would not change.
    """

    __slots__ = ("_cells", "_width", "_height", "_cell_size", "_heights")

    def __init__(
        self,
        width: int,
        height: int,
        cell_size: float = CELL_SIZE_M,
        *,
        cells: bytearray | None = None,
        heights: bytearray | None = None,
    ) -> None:
        if width <= 0 or height <= 0:
            raise WorldDataError("Collision grid dimensions must be positive.")
        self._width = width
        self._height = height
        self._cell_size = cell_size
        self._cells = cells if cells is not None else bytearray(width * height)
        self._heights = heights if heights is not None else bytearray(width * height)
        if len(self._cells) != width * height or len(self._heights) != width * height:
            raise WorldDataError("Collision grid buffers do not match the declared size.")

    @property
    def width(self) -> int:
        return self._width

    @property
    def height(self) -> int:
        return self._height

    @property
    def cell_size(self) -> float:
        return self._cell_size

    @property
    def width_m(self) -> float:
        return self._width * self._cell_size

    @property
    def height_m(self) -> float:
        return self._height * self._cell_size

    @property
    def cells(self) -> bytearray:
        return self._cells

    @property
    def heights(self) -> bytearray:
        return self._heights

    def code_at(self, cx: int, cy: int) -> int:
        """Out-of-bounds reads report a wall so the player cannot leave the map."""
        if cx < 0 or cy < 0 or cx >= self._width or cy >= self._height:
            return 3
        return self._cells[cy * self._width + cx]

    def height_at(self, cx: int, cy: int) -> int:
        if cx < 0 or cy < 0 or cx >= self._width or cy >= self._height:
            return 0
        return self._heights[cy * self._width + cx]

    def set(self, cx: int, cy: int, code: int, height: int = 0) -> None:
        if cx < 0 or cy < 0 or cx >= self._width or cy >= self._height:
            return
        index = cy * self._width + cx
        self._cells[index] = code
        self._heights[index] = height

    def is_solid_cell(self, cx: int, cy: int) -> bool:
        return self.code_at(cx, cy) in SOLID_CELLS

    def is_solid_point(self, x: float, y: float) -> bool:
        return self.is_solid_cell(int(x // self._cell_size), int(y // self._cell_size))

    def is_free_circle(self, x: float, y: float, radius: float) -> bool:
        """Approximate a capsule with the four extremes of its bounding box.

        Cells are 2 m and the player radius is 0.35 m, so the box can never span
        more than two cells per axis; checking the corners is exact here.
        """
        min_cx = int((x - radius) // self._cell_size)
        max_cx = int((x + radius) // self._cell_size)
        min_cy = int((y - radius) // self._cell_size)
        max_cy = int((y + radius) // self._cell_size)
        for cy in range(min_cy, max_cy + 1):
            for cx in range(min_cx, max_cx + 1):
                if self.is_solid_cell(cx, cy):
                    return False
        return True

    def clamp_to_world(self, x: float, y: float) -> tuple[float, float]:
        margin = self._cell_size * 0.5
        return (
            min(max(x, margin), self.width_m - margin),
            min(max(y, margin), self.height_m - margin),
        )


def stitch_tiles(tiles: Sequence[WorldTile], tiles_x: int, tiles_y: int) -> CollisionGrid:
    """Merge tile layers into the single grid the simulation walks on."""
    if not tiles:
        raise WorldDataError("Cannot stitch an empty tile set.")
    cells_per_tile = tiles[0].cells
    grid = CollisionGrid(
        tiles_x * cells_per_tile,
        tiles_y * cells_per_tile,
        tiles[0].cell_size,
    )
    for tile in tiles:
        if tile.cells != cells_per_tile:
            raise WorldDataError("All tiles in a world must share one resolution.")
        base_x = tile.tile_x * cells_per_tile
        base_y = tile.tile_y * cells_per_tile
        for local_y in range(cells_per_tile):
            src = local_y * cells_per_tile
            dst = (base_y + local_y) * grid.width + base_x
            grid.cells[dst : dst + cells_per_tile] = tile.collision[src : src + cells_per_tile]
            grid.heights[dst : dst + cells_per_tile] = tile.heights[src : src + cells_per_tile]
    return grid


def collect_spawn_points(tiles: Iterable[WorldTile]) -> tuple[tuple[float, float, float], ...]:
    """Convert tile-local spawn cells into world-space metres."""
    spawns: list[tuple[float, float, float]] = []
    for tile in tiles:
        for point in tile.spawn_points:
            spawns.append(
                (
                    tile.origin_x + (point.x + 0.5) * tile.cell_size,
                    tile.origin_y + (point.y + 0.5) * tile.cell_size,
                    point.heading,
                )
            )
    return tuple(spawns)


@dataclass(slots=True)
class World:
    """A loaded, simulation-ready district."""

    descriptor: WorldDescriptor
    tiles: tuple[WorldTile, ...]
    grid: CollisionGrid
    spawn_points: tuple[tuple[float, float, float], ...] = field(default=())

    @classmethod
    def from_tiles(
        cls, descriptor: WorldDescriptor, tiles: Sequence[WorldTile]
    ) -> "World":
        grid = stitch_tiles(tiles, descriptor.tiles_x, descriptor.tiles_y)
        spawns = collect_spawn_points(tiles)
        if not spawns:
            raise WorldDataError(f"World {descriptor.id} declares no spawn points.")
        return cls(descriptor=descriptor, tiles=tuple(tiles), grid=grid, spawn_points=spawns)

    def tile(self, tile_x: int, tile_y: int) -> WorldTile | None:
        for candidate in self.tiles:
            if candidate.tile_x == tile_x and candidate.tile_y == tile_y:
                return candidate
        return None


def tile_id(world_id: str, tile_x: int, tile_y: int) -> str:
    return f"{world_id}:{tile_x}:{tile_y}"


def cells_for_tile(cells: int = TILE_CELLS) -> int:
    return cells * cells
