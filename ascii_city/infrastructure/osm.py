"""OpenStreetMap import. ``docs/osm-import.md`` is the pipeline reference.

This is the second implementation of :class:`WorldGeneratorPort`, and it exists
to prove the port is real: the room, the codecs, the client and the renderer
cannot tell an imported district from a generated one, because both hand back
the same :class:`~ascii_city.domain.world.WorldTile`.

Input is GeoJSON, which is what every OSM extraction tool can emit — `osmium
export`, Overpass, or a QGIS save. Parsing `.osm.pbf` directly would drag a
binary dependency into a project that does not otherwise need one, so the
conversion stays outside and this module starts from features.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from ..domain.constants import (
    CATEGORY_APARTMENT,
    CATEGORY_DEFAULT_HEIGHT_M,
    CATEGORY_HOUSE,
    CATEGORY_OFFICE,
    CATEGORY_OTHER,
    CATEGORY_SHOP,
    CATEGORY_SKYSCRAPER,
    CATEGORY_STATION,
    CATEGORY_WAREHOUSE,
    CELL_BUILDING,
    CELL_ROAD,
    CELL_SIDEWALK,
    LEVEL_HEIGHT_M,
    MAX_BUILDING_HEIGHT_M,
    ROAD_AVENUE,
    ROAD_PATH,
    ROAD_PLAZA,
    ROAD_STREET,
    ROOF_ANTENNA,
    ROOF_FLAT,
    ROOF_GABLED,
)
from ..domain.errors import WorldDataError
from ..domain.ports import WorldGeneratorPort
from ..domain.world import Building, Road, SpawnPoint, WorldDescriptor, WorldTile
from .canvas import Canvas, pack_style, slice_into_tiles

EARTH_RADIUS_M = 6_378_137.0

# --- tag vocabularies -------------------------------------------------------

BUILDING_CATEGORIES: Mapping[str, int] = {
    "house": CATEGORY_HOUSE,
    "detached": CATEGORY_HOUSE,
    "semidetached_house": CATEGORY_HOUSE,
    "bungalow": CATEGORY_HOUSE,
    "cabin": CATEGORY_HOUSE,
    "terrace": CATEGORY_HOUSE,
    "retail": CATEGORY_SHOP,
    "shop": CATEGORY_SHOP,
    "commercial": CATEGORY_SHOP,
    "kiosk": CATEGORY_SHOP,
    "supermarket": CATEGORY_SHOP,
    "apartments": CATEGORY_APARTMENT,
    "residential": CATEGORY_APARTMENT,
    "dormitory": CATEGORY_APARTMENT,
    "hotel": CATEGORY_APARTMENT,
    "office": CATEGORY_OFFICE,
    "government": CATEGORY_OFFICE,
    "civic": CATEGORY_OFFICE,
    "university": CATEGORY_OFFICE,
    "skyscraper": CATEGORY_SKYSCRAPER,
    "tower": CATEGORY_SKYSCRAPER,
    "warehouse": CATEGORY_WAREHOUSE,
    "industrial": CATEGORY_WAREHOUSE,
    "hangar": CATEGORY_WAREHOUSE,
    "train_station": CATEGORY_STATION,
    "transportation": CATEGORY_STATION,
}

HIGHWAY_TYPES: Mapping[str, int] = {
    "motorway": ROAD_AVENUE,
    "trunk": ROAD_AVENUE,
    "primary": ROAD_AVENUE,
    "secondary": ROAD_AVENUE,
    "tertiary": ROAD_STREET,
    "residential": ROAD_STREET,
    "unclassified": ROAD_STREET,
    "living_street": ROAD_STREET,
    "service": ROAD_STREET,
    "footway": ROAD_PATH,
    "path": ROAD_PATH,
    "steps": ROAD_PATH,
    "cycleway": ROAD_PATH,
    "pedestrian": ROAD_PLAZA,
}

DEFAULT_ROAD_WIDTH_M: Mapping[int, float] = {
    ROAD_AVENUE: 14.0,
    ROAD_STREET: 8.0,
    ROAD_PATH: 3.0,
    ROAD_PLAZA: 12.0,
}

SKYSCRAPER_THRESHOLD_M = 60.0
"""Above this a building reads as a tower whatever its `building` tag claims."""

LANE_WIDTH_M = 3.5

_MEASURE = re.compile(
    r"^\s*(?P<value>-?\d+(?:\.\d+)?)\s*(?P<unit>m|metres?|meters?|ft|feet|')?\s*$",
    re.IGNORECASE,
)
_FEET_INCHES = re.compile(r"^\s*(?P<feet>\d+)\s*'\s*(?P<inches>\d+(?:\.\d+)?)\s*\"?\s*$")

FOOT_M = 0.3048


def parse_measure(raw: str | float | int | None) -> float | None:
    """Parse an OSM length. Metres unless the value says otherwise.

    OSM permits bare numbers (metres), explicit units, and the imperial
    ``12'6"`` form. A value that parses to nonsense is treated as absent so the
    ladder falls through to a defensible default rather than raising on one
    malformed tag in a city-sized extract.
    """
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw) if math.isfinite(raw) and raw > 0 else None

    imperial = _FEET_INCHES.match(raw)
    if imperial is not None:
        feet = int(imperial.group("feet")) + float(imperial.group("inches")) / 12.0
        return feet * FOOT_M

    match = _MEASURE.match(raw)
    if match is None:
        return None
    value = float(match.group("value"))
    if value <= 0:
        return None
    unit = (match.group("unit") or "m").lower()
    return value * FOOT_M if unit in {"ft", "feet", "'"} else value


def parse_levels(raw: str | float | int | None) -> int | None:
    if raw is None:
        return None
    try:
        levels = int(float(raw))
    except (TypeError, ValueError):
        return None
    return levels if levels > 0 else None


def classify_building(tags: Mapping[str, Any]) -> int:
    value = str(tags.get("building", "") or "").strip().lower()
    return BUILDING_CATEGORIES.get(value, CATEGORY_OTHER)


def resolve_height(tags: Mapping[str, Any], category: int) -> tuple[int, int, int]:
    """Height, minimum height and level count in metres, by priority ladder.

    1. ``height``, the only tag that states the answer outright.
    2. ``building:levels`` times three metres, plus ``roof:height`` when the
       roof is tagged separately, since levels exclude it.
    3. A per-category default, because a building with neither tag still has to
       stand somewhere sensible rather than at zero.

    Returned heights are whole metres because that is what a tile stores. The
    level count is kept even when the height came from a tag, so a client can
    still band the facade by storey.
    """
    roof = parse_measure(tags.get("roof:height")) or 0.0
    minimum = parse_measure(tags.get("min_height")) or 0.0
    levels = parse_levels(tags.get("building:levels"))

    height = parse_measure(tags.get("height"))
    if height is None and levels is not None:
        height = levels * LEVEL_HEIGHT_M + roof
    if height is None:
        height = float(CATEGORY_DEFAULT_HEIGHT_M[category])

    height = max(LEVEL_HEIGHT_M, min(float(MAX_BUILDING_HEIGHT_M), height))
    minimum = max(0.0, min(height - 1.0, minimum))
    if levels is None:
        levels = max(1, int(round((height - roof) / LEVEL_HEIGHT_M)))
    return int(round(height)), int(round(minimum)), levels


def classify_roof(tags: Mapping[str, Any], height: int) -> int:
    shape = str(tags.get("roof:shape", "") or "").strip().lower()
    if shape in {"gabled", "hipped", "pyramidal", "gambrel", "half-hipped"}:
        return ROOF_GABLED
    if height >= SKYSCRAPER_THRESHOLD_M or tags.get("man_made") == "communications_tower":
        return ROOF_ANTENNA
    return ROOF_FLAT


def classify_highway(tags: Mapping[str, Any]) -> int | None:
    value = str(tags.get("highway", "") or "").strip().lower()
    if not value:
        return None
    return HIGHWAY_TYPES.get(value, ROAD_STREET)


def resolve_road_width(tags: Mapping[str, Any], road_type: int) -> float:
    explicit = parse_measure(tags.get("width"))
    if explicit is not None:
        return explicit
    lanes = parse_levels(tags.get("lanes"))
    if lanes is not None:
        return lanes * LANE_WIDTH_M
    return DEFAULT_ROAD_WIDTH_M[road_type]


# --- projection -------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class GeoOrigin:
    """South-west corner of the district in WGS84 degrees."""

    lat: float
    lon: float

    def project(self, lon: float, lat: float) -> tuple[float, float]:
        """Longitude and latitude to local metres, x east and y north.

        Equirectangular around the origin's latitude. Over a district a few
        hundred metres across the error against a proper projection is under a
        centimetre, which is a twentieth of a cell, so anything more elaborate
        would be precision the raster cannot represent.
        """
        x = math.radians(lon - self.lon) * EARTH_RADIUS_M * math.cos(math.radians(self.lat))
        y = math.radians(lat - self.lat) * EARTH_RADIUS_M
        return x, y


def bounds_of(features: Iterable[Mapping[str, Any]]) -> tuple[float, float, float, float]:
    """Longitude and latitude extent of a feature collection."""
    lons: list[float] = []
    lats: list[float] = []
    for feature in features:
        for lon, lat in _coordinates(feature.get("geometry") or {}):
            lons.append(lon)
            lats.append(lat)
    if not lons:
        raise WorldDataError("The feature collection has no coordinates.")
    return min(lons), min(lats), max(lons), max(lats)


def _ring(points: Sequence[Sequence[float]]) -> list[tuple[float, float]]:
    """A GeoJSON ring repeats its first point; the tile format does not."""
    out = [(float(p[0]), float(p[1])) for p in points]
    if len(out) > 1 and out[0] == out[-1]:
        out.pop()
    return out


def _coordinates(geometry: Mapping[str, Any]) -> list[tuple[float, float]]:
    kind = geometry.get("type")
    coordinates = geometry.get("coordinates") or []
    if kind == "LineString":
        return [(float(p[0]), float(p[1])) for p in coordinates]
    if kind == "Polygon":
        return _ring(coordinates[0]) if coordinates else []
    if kind == "MultiPolygon":
        # Only the outer ring of the largest part; holes and courtyards are
        # detail a two-metre grid cannot hold anyway.
        parts = [_ring(polygon[0]) for polygon in coordinates if polygon]
        return max(parts, key=len) if parts else []
    if kind == "Point":
        return [(float(coordinates[0]), float(coordinates[1]))] if coordinates else []
    return []


MAX_VERTICES = 64
"""The tile format counts vertices in one byte, and a grid this coarse cannot
show more detail than this anyway."""


def _decimate(points: Sequence[tuple[float, float]], limit: int = MAX_VERTICES) -> list[tuple[float, float]]:
    if len(points) <= limit:
        return list(points)
    stride = len(points) / limit
    kept = [points[int(index * stride)] for index in range(limit)]
    return kept


# --- rasterisation ----------------------------------------------------------


def fill_polygon(
    canvas: Canvas,
    points: Sequence[tuple[float, float]],
    code: int,
    height: int,
    style: int,
) -> int:
    """Even-odd scanline fill. Returns the number of cells painted.

    Cell centres decide membership, which is what keeps a shared wall between
    two terraced houses one cell thick instead of two.
    """
    if len(points) < 3:
        return 0
    ys = [p[1] for p in points]
    top = max(0, int(math.floor(min(ys))))
    bottom = min(canvas.height - 1, int(math.ceil(max(ys))))
    painted = 0

    for y in range(top, bottom + 1):
        centre = y + 0.5
        crossings: list[float] = []
        for index in range(len(points)):
            x0, y0 = points[index]
            x1, y1 = points[(index + 1) % len(points)]
            if (y0 > centre) == (y1 > centre):
                continue
            crossings.append(x0 + (centre - y0) / (y1 - y0) * (x1 - x0))
        crossings.sort()
        for pair in range(0, len(crossings) - 1, 2):
            start = max(0, int(math.ceil(crossings[pair] - 0.5)))
            end = min(canvas.width - 1, int(math.floor(crossings[pair + 1] - 0.5)))
            for x in range(start, end + 1):
                canvas.paint(x, y, code, height, style)
                painted += 1
    return painted


def stroke_line(
    canvas: Canvas,
    start: tuple[float, float],
    end: tuple[float, float],
    half_width: float,
    code: int,
    style: int,
) -> None:
    """Paint a thick segment by sampling along it. Cheap and good enough.

    A road is a handful of cells wide, so a proper polygon offset would resolve
    detail the grid throws away. Sampling at half-cell steps leaves no gaps.
    """
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length = math.hypot(dx, dy)
    if length == 0:
        return
    steps = max(1, int(length * 2))
    radius = int(math.ceil(half_width))
    for step in range(steps + 1):
        t = step / steps
        cx = start[0] + dx * t
        cy = start[1] + dy * t
        for oy in range(-radius, radius + 1):
            for ox in range(-radius, radius + 1):
                x = int(cx) + ox
                y = int(cy) + oy
                if math.hypot(x + 0.5 - cx, y + 0.5 - cy) <= half_width:
                    canvas.paint(x, y, code, 0, style)


# --- the importer -----------------------------------------------------------


class OsmDistrictImporter(WorldGeneratorPort):
    """Builds a district from GeoJSON features carrying OSM tags.

    The descriptor still decides the district's size; features falling outside
    it are clipped by the canvas rather than resizing the world, so the same
    extract can be rendered at whatever tile count the deployment allows.
    """

    def __init__(
        self,
        features: Sequence[Mapping[str, Any]] | Mapping[str, Any],
        origin: GeoOrigin | None = None,
        *,
        attribution: str = "© OpenStreetMap contributors, ODbL 1.0",
    ) -> None:
        self.features = _as_features(features)
        self.attribution = attribution
        if origin is None:
            min_lon, min_lat, _, _ = bounds_of(self.features)
            origin = GeoOrigin(lat=min_lat, lon=min_lon)
        self.origin = origin

    @property
    def source(self) -> str:
        return "osm"

    def generate_tiles(self, descriptor: WorldDescriptor) -> Sequence[WorldTile]:
        cells = descriptor.tile_cells
        canvas = Canvas(descriptor.tiles_x * cells, descriptor.tiles_y * cells)
        scale = 1.0 / descriptor.cell_size

        roads = self._paint_roads(canvas, scale)
        buildings = self._paint_buildings(canvas, scale)
        _paint_sidewalks(canvas)
        spawns = _spawn_points(canvas, roads)
        return slice_into_tiles(descriptor, canvas, buildings, roads, (), spawns)

    # --- passes ---------------------------------------------------------

    def _paint_roads(self, canvas: Canvas, scale: float) -> list[Road]:
        """Roads go down first so a building may overwrite a mis-tagged verge."""
        roads: list[Road] = []
        for index, feature in enumerate(self.features):
            tags = feature.get("properties") or {}
            road_type = classify_highway(tags)
            if road_type is None:
                continue
            points = self._project(feature, scale)
            if len(points) < 2:
                continue

            width = resolve_road_width(tags, road_type)
            half = max(0.5, width * scale / 2.0)
            surface = ROAD_TYPE_SURFACE[road_type]
            for segment in range(len(points) - 1):
                stroke_line(canvas, points[segment], points[segment + 1], half, CELL_ROAD, surface)

            roads.append(
                Road(
                    id=index & 0xFFFF,
                    centerline=tuple(
                        value
                        for point in points
                        for value in (int(round(point[0])), int(round(point[1])))
                    ),
                    width=width,
                    type=road_type,
                    walkable=True,
                    surface_style=surface,
                    name=str(tags.get("name") or "") or None,
                )
            )
        return roads

    def _paint_buildings(self, canvas: Canvas, scale: float) -> list[Building]:
        buildings: list[Building] = []
        for index, feature in enumerate(self.features):
            tags = feature.get("properties") or {}
            if not tags.get("building"):
                continue
            points = self._project(feature, scale)
            if len(points) < 3:
                continue

            category = classify_building(tags)
            height, minimum, levels = resolve_height(tags, category)
            if height >= SKYSCRAPER_THRESHOLD_M and category in (CATEGORY_OTHER, CATEGORY_OFFICE):
                category = CATEGORY_SKYSCRAPER
            facade = (index * 7) % 8
            window = levels % 4
            style = pack_style(category, facade, window)

            if fill_polygon(canvas, points, CELL_BUILDING, min(255, height), style) == 0:
                continue

            buildings.append(
                Building(
                    id=index & 0xFFFF,
                    footprint=tuple(
                        value
                        for point in points
                        for value in (int(round(point[0])), int(round(point[1])))
                    ),
                    height=height,
                    min_height=minimum,
                    levels=levels,
                    roof_type=classify_roof(tags, height),
                    category=category,
                    facade_style=facade,
                    window_style=window,
                    color=category,
                    walkable=False,
                    source_id=str(tags.get("id") or tags.get("@id") or "") or None,
                )
            )
        return buildings

    def _project(self, feature: Mapping[str, Any], scale: float) -> list[tuple[float, float]]:
        points = [
            (x * scale, y * scale)
            for x, y in (
                self.origin.project(lon, lat)
                for lon, lat in _coordinates(feature.get("geometry") or {})
            )
        ]
        return _decimate(points)


ROAD_TYPE_SURFACE: Mapping[int, int] = {
    ROAD_AVENUE: 1,
    ROAD_STREET: 0,
    ROAD_PATH: 2,
    ROAD_PLAZA: 3,
}


def _as_features(payload: Sequence[Mapping[str, Any]] | Mapping[str, Any]) -> list[Mapping[str, Any]]:
    if isinstance(payload, Mapping):
        if payload.get("type") != "FeatureCollection":
            raise WorldDataError("Expected a GeoJSON FeatureCollection.")
        payload = payload.get("features") or []
    features = list(payload)
    if not features:
        raise WorldDataError("The feature collection is empty.")
    return features


def _paint_sidewalks(canvas: Canvas) -> None:
    """One cell of pavement wherever open ground meets a road."""
    edges: list[int] = []
    for y in range(canvas.height):
        for x in range(canvas.width):
            index = y * canvas.width + x
            if canvas.collision[index] != 0:
                continue
            if any(
                canvas.get(x + dx, y + dy) == CELL_ROAD
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
            ):
                edges.append(index)
    for index in edges:
        canvas.collision[index] = CELL_SIDEWALK


SPAWN_MARGIN_CELLS = 3
"""Nobody should arrive facing the void at the district boundary."""


def _densify(points: Sequence[tuple[int, int]]) -> list[tuple[int, int]]:
    """Cell-by-cell samples along a polyline, duplicates removed."""
    out: list[tuple[int, int]] = []
    for index in range(len(points) - 1):
        (x0, y0), (x1, y1) = points[index], points[index + 1]
        steps = max(1, int(math.hypot(x1 - x0, y1 - y0)))
        for step in range(steps + 1):
            t = step / steps
            cell = (int(round(x0 + (x1 - x0) * t)), int(round(y0 + (y1 - y0) * t)))
            if not out or out[-1] != cell:
                out.append(cell)
    return out


def _spawn_points(canvas: Canvas, roads: Sequence[Road]) -> list[SpawnPoint]:
    """One spawn per road, on open tarmac as near its middle as possible.

    A centreline's endpoints usually sit on the district boundary, where half
    the view is nothing, so the search starts at the centre and works outwards.
    """
    spawns: list[SpawnPoint] = []
    for road in roads:
        samples = _densify(list(zip(road.centerline[0::2], road.centerline[1::2])))
        if len(samples) < 2:
            continue
        middle = len(samples) // 2
        for index in sorted(range(len(samples)), key=lambda i: abs(i - middle)):
            x, y = samples[index]
            if canvas.get(x, y) != CELL_ROAD:
                continue
            if not (
                SPAWN_MARGIN_CELLS <= x < canvas.width - SPAWN_MARGIN_CELLS
                and SPAWN_MARGIN_CELLS <= y < canvas.height - SPAWN_MARGIN_CELLS
            ):
                continue
            ahead = samples[min(index + 1, len(samples) - 1)]
            heading = math.atan2(ahead[1] - y, ahead[0] - x) if ahead != (x, y) else 0.0
            spawns.append(SpawnPoint(x=x, y=y, heading=heading % math.tau))
            break
    return spawns
