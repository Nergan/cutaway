"""The OpenStreetMap import path.

The point of these tests is not that the sample district looks nice. It is that
:class:`OsmDistrictImporter` is a real second implementation of the world
generator port: everything downstream — the codec, the collision grid, the
room — accepts its output without knowing where it came from.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from ascii_city.domain.constants import (
    CATEGORY_APARTMENT,
    CATEGORY_HOUSE,
    CATEGORY_OTHER,
    CATEGORY_SHOP,
    CATEGORY_SKYSCRAPER,
    CATEGORY_STATION,
    CATEGORY_WAREHOUSE,
    CELL_BUILDING,
    CELL_ROAD,
    CELL_SIZE_M,
    LEVEL_HEIGHT_M,
    MAX_BUILDING_HEIGHT_M,
    PLAYER_RADIUS_M,
    ROAD_AVENUE,
    ROAD_PATH,
    ROAD_PLAZA,
    ROAD_STREET,
    ROOF_ANTENNA,
    ROOF_FLAT,
    ROOF_GABLED,
    TILE_CELLS,
)
from ascii_city.domain.errors import WorldDataError
from ascii_city.domain.world import World, WorldDescriptor
from ascii_city.infrastructure.osm import (
    SPAWN_MARGIN_CELLS,
    GeoOrigin,
    OsmDistrictImporter,
    bounds_of,
    classify_building,
    classify_highway,
    classify_roof,
    fill_polygon,
    parse_measure,
    resolve_height,
    resolve_road_width,
)
from ascii_city.infrastructure.canvas import Canvas
from ascii_city.infrastructure.tile_codec import decode_tile, encode_tile

SAMPLE = Path(__file__).resolve().parents[1] / "ascii_city" / "docs" / "samples" / "osm-district.geojson"


@pytest.fixture(scope="module")
def sample() -> dict:
    return json.loads(SAMPLE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def imported(sample) -> tuple[WorldDescriptor, list]:
    descriptor = WorldDescriptor(
        id="osm-sample",
        version=1,
        seed=0,
        tiles_x=1,
        tiles_y=1,
        tile_cells=TILE_CELLS,
        cell_size=CELL_SIZE_M,
        source="osm",
    )
    tiles = list(OsmDistrictImporter(sample).generate_tiles(descriptor))
    return descriptor, tiles


# --- tag parsing ------------------------------------------------------------


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("12", 12.0),
        ("12.5", 12.5),
        ("12 m", 12.0),
        ("12m", 12.0),
        ("12 metres", 12.0),
        ("40 ft", 40 * 0.3048),
        ("40'", 40 * 0.3048),
        ("12'6\"", (12 + 0.5) * 0.3048),
        (7, 7.0),
    ],
)
def test_lengths_parse_in_every_spelling_osm_permits(raw, expected):
    assert parse_measure(raw) == pytest.approx(expected)


@pytest.mark.parametrize("raw", [None, "", "tall", "approximately 20", "-3", "0", float("nan")])
def test_a_nonsense_length_is_treated_as_absent(raw):
    """One malformed tag in a city-sized extract must not stop the import."""
    assert parse_measure(raw) is None


# --- the height ladder ------------------------------------------------------


def test_an_explicit_height_wins_over_everything():
    height, _, _ = resolve_height({"height": "31", "building:levels": "2"}, CATEGORY_OTHER)
    assert height == 31


def test_levels_become_metres_when_no_height_is_tagged():
    height, _, levels = resolve_height({"building:levels": "9"}, CATEGORY_APARTMENT)
    assert height == int(9 * LEVEL_HEIGHT_M)
    assert levels == 9


def test_a_separately_tagged_roof_is_added_to_the_levels():
    """Levels count storeys, which stop at the eaves."""
    plain, _, _ = resolve_height({"building:levels": "2"}, CATEGORY_WAREHOUSE)
    roofed, _, _ = resolve_height({"building:levels": "2", "roof:height": "3"}, CATEGORY_WAREHOUSE)
    assert roofed == plain + 3


def test_an_untagged_building_falls_back_to_its_category():
    house, _, _ = resolve_height({"building": "house"}, CATEGORY_HOUSE)
    tower, _, _ = resolve_height({"building": "skyscraper"}, CATEGORY_SKYSCRAPER)
    assert house == 8 and tower == 80


def test_levels_are_inferred_when_only_a_height_is_tagged():
    _, _, levels = resolve_height({"height": "30"}, CATEGORY_OTHER)
    assert levels == 10


def test_a_height_beyond_the_byte_is_clamped_not_wrapped():
    height, _, _ = resolve_height({"height": "900"}, CATEGORY_SKYSCRAPER)
    assert height == MAX_BUILDING_HEIGHT_M


def test_min_height_is_kept_below_the_roof():
    """An overhang tagged taller than its building would fail validation."""
    height, minimum, _ = resolve_height({"height": "10", "min_height": "40"}, CATEGORY_OTHER)
    assert minimum < height


# --- classification ---------------------------------------------------------


@pytest.mark.parametrize(
    "value, category",
    [
        ("house", CATEGORY_HOUSE),
        ("apartments", CATEGORY_APARTMENT),
        ("retail", CATEGORY_SHOP),
        ("warehouse", CATEGORY_WAREHOUSE),
        ("train_station", CATEGORY_STATION),
        ("skyscraper", CATEGORY_SKYSCRAPER),
        ("yes", CATEGORY_OTHER),
        ("something_new", CATEGORY_OTHER),
    ],
)
def test_building_tags_map_to_categories(value, category):
    assert classify_building({"building": value}) == category


@pytest.mark.parametrize(
    "value, road_type",
    [
        ("primary", ROAD_AVENUE),
        ("motorway", ROAD_AVENUE),
        ("residential", ROAD_STREET),
        ("footway", ROAD_PATH),
        ("pedestrian", ROAD_PLAZA),
        ("some_new_classification", ROAD_STREET),
    ],
)
def test_highway_tags_map_to_road_types(value, road_type):
    assert classify_highway({"highway": value}) == road_type


def test_a_feature_without_a_highway_tag_is_not_a_road():
    assert classify_highway({"building": "house"}) is None


def test_road_width_prefers_the_tag_then_lanes_then_the_default():
    assert resolve_road_width({"width": "18 m"}, ROAD_STREET) == pytest.approx(18.0)
    assert resolve_road_width({"lanes": "4"}, ROAD_STREET) == pytest.approx(14.0)
    assert resolve_road_width({}, ROAD_STREET) == pytest.approx(8.0)


def test_roof_shape_and_height_decide_the_roof():
    assert classify_roof({"roof:shape": "gabled"}, 8) == ROOF_GABLED
    assert classify_roof({}, 120) == ROOF_ANTENNA
    assert classify_roof({}, 12) == ROOF_FLAT


# --- projection -------------------------------------------------------------


def test_the_origin_projects_to_the_origin():
    origin = GeoOrigin(lat=55.75, lon=37.61)
    assert origin.project(37.61, 55.75) == (0.0, 0.0)


def test_north_and_east_are_positive():
    origin = GeoOrigin(lat=55.75, lon=37.61)
    east, north = origin.project(37.62, 55.76)
    assert east > 0 and north > 0


def test_a_degree_of_latitude_is_about_a_hundred_and_eleven_kilometres():
    origin = GeoOrigin(lat=0.0, lon=0.0)
    _, north = origin.project(0.0, 1.0)
    assert north == pytest.approx(111_319, rel=0.001)


def test_longitude_shrinks_with_latitude():
    """The projection has to account for meridian convergence or a northern
    district comes out stretched east to west."""
    equator, _ = GeoOrigin(lat=0.0, lon=0.0).project(1.0, 0.0)
    north, _ = GeoOrigin(lat=60.0, lon=0.0).project(1.0, 60.0)
    assert north == pytest.approx(equator * 0.5, rel=0.01)


def test_bounds_cover_every_geometry_kind(sample):
    min_lon, min_lat, max_lon, max_lat = bounds_of(sample["features"])
    assert min_lon < max_lon and min_lat < max_lat


# --- rasterisation ----------------------------------------------------------


def test_a_square_fills_the_cells_it_covers():
    canvas = Canvas(16, 16)
    painted = fill_polygon(canvas, [(2, 2), (6, 2), (6, 6), (2, 6)], CELL_BUILDING, 10, 3)
    assert painted == 16
    assert canvas.get(3, 3) == CELL_BUILDING
    assert canvas.get(7, 7) != CELL_BUILDING


def test_a_concave_polygon_does_not_bleed_across_its_notch():
    """Even-odd fill, so an L-shape must leave the inner corner empty."""
    canvas = Canvas(16, 16)
    fill_polygon(canvas, [(2, 2), (10, 2), (10, 5), (5, 5), (5, 10), (2, 10)], CELL_BUILDING, 10, 0)
    assert canvas.get(3, 8) == CELL_BUILDING
    assert canvas.get(8, 8) != CELL_BUILDING


def test_geometry_outside_the_canvas_is_clipped_not_wrapped():
    canvas = Canvas(16, 16)
    fill_polygon(canvas, [(-40, -40), (-30, -40), (-30, -30), (-40, -30)], CELL_BUILDING, 10, 0)
    assert not any(canvas.collision)


def test_a_degenerate_polygon_paints_nothing():
    canvas = Canvas(16, 16)
    assert fill_polygon(canvas, [(1, 1), (2, 2)], CELL_BUILDING, 10, 0) == 0


# --- the district as a whole ------------------------------------------------


def test_the_sample_imports_into_a_playable_district(imported):
    descriptor, tiles = imported
    world = World.from_tiles(descriptor, tiles)
    assert world.grid.width == TILE_CELLS
    assert any(code == CELL_BUILDING for code in tiles[0].collision)
    assert any(code == CELL_ROAD for code in tiles[0].collision)
    assert world.spawn_points, "an imported district still has to be joinable"


def test_every_spawn_point_stands_on_open_ground(imported):
    descriptor, tiles = imported
    world = World.from_tiles(descriptor, tiles)
    assert len(world.spawn_points) == len(tiles[0].roads)
    for x, y, _heading in world.spawn_points:
        assert world.grid.is_free_circle(x, y, PLAYER_RADIUS_M)


def test_no_one_spawns_pressed_against_the_district_boundary(imported):
    descriptor, tiles = imported
    world = World.from_tiles(descriptor, tiles)
    margin = SPAWN_MARGIN_CELLS * CELL_SIZE_M
    for x, y, _heading in world.spawn_points:
        assert margin <= x <= world.grid.width_m - margin
        assert margin <= y <= world.grid.height_m - margin


def test_the_imported_tile_survives_the_same_codec(imported):
    """The whole point of the port: downstream cannot tell the source apart."""
    _, tiles = imported
    restored = decode_tile(encode_tile(tiles[0]))
    assert restored.collision == tiles[0].collision
    assert restored.heights == tiles[0].heights
    assert [b.height for b in restored.buildings] == [b.height for b in tiles[0].buildings]


def test_the_sample_exercises_every_rung_of_the_height_ladder(imported):
    _, tiles = imported
    by_source = {b.source_id: b for b in tiles[0].buildings}
    assert by_source["way/2002"].height == 64            # explicit metres
    assert by_source["way/2001"].height == 27            # nine levels
    assert by_source["way/2004"].height == 12            # forty feet
    assert by_source["way/2003"].height == 8             # category default


def test_a_tall_office_is_promoted_to_a_skyscraper(imported):
    """Sixty metres reads as a tower whatever the `building` tag says."""
    _, tiles = imported
    tower = next(b for b in tiles[0].buildings if b.source_id == "way/2002")
    assert tower.category == CATEGORY_SKYSCRAPER


def test_named_roads_keep_their_names(imported):
    _, tiles = imported
    names = {road.name for road in tiles[0].roads}
    assert "Grand Avenue" in names and "Cutaway Passage" in names


def test_building_heights_reach_the_raster(imported):
    """A tile stores height per cell; a tower has to be tall on the grid too."""
    descriptor, tiles = imported
    world = World.from_tiles(descriptor, tiles)
    assert max(tiles[0].heights) == 120
    spire = next(b for b in tiles[0].buildings if b.source_id == "way/2008")
    cx = sum(spire.footprint[0::2]) // spire.vertex_count
    cy = sum(spire.footprint[1::2]) // spire.vertex_count
    assert world.grid.height_at(cx, cy) == 120


def test_the_importer_reports_itself_as_an_osm_source(sample):
    assert OsmDistrictImporter(sample).source == "osm"


def test_a_footprint_is_capped_at_what_one_byte_can_count():
    """A traced building can carry hundreds of nodes; the tile counts them in
    a byte, so the importer decimates rather than overflowing."""
    ring = [
        [37.61 + 0.0002 * math.cos(index / 300 * math.tau), 55.75 + 0.0002 * math.sin(index / 300 * math.tau)]
        for index in range(300)
    ]
    ring.append(ring[0])
    payload = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {"building": "yes"}, "geometry": {"type": "Polygon", "coordinates": [ring]}}
        ],
    }
    descriptor = WorldDescriptor(
        id="ring", version=1, seed=0, tiles_x=1, tiles_y=1,
        tile_cells=TILE_CELLS, cell_size=CELL_SIZE_M, source="osm",
    )
    tiles = list(OsmDistrictImporter(payload).generate_tiles(descriptor))
    assert tiles[0].buildings[0].vertex_count <= 255
    assert encode_tile(tiles[0])


def test_an_empty_collection_is_rejected_rather_than_producing_a_void():
    with pytest.raises(WorldDataError):
        OsmDistrictImporter({"type": "FeatureCollection", "features": []})


def test_something_that_is_not_a_feature_collection_is_rejected():
    with pytest.raises(WorldDataError):
        OsmDistrictImporter({"type": "Polygon", "coordinates": []})
