"""World generation, the binary tile container and grid invariants."""

from __future__ import annotations

import gzip

import pytest

from ascii_city.config import DEFAULT_SEED, load_settings
from ascii_city.domain.constants import (
    CATEGORY_NAMES,
    CELL_BUILDING,
    CELL_SIZE_M,
    CELL_INTERACTIVE,
    CELL_ROAD,
    CELL_SIDEWALK,
    GRAVITY_MS2,
    JUMP_SPEED_MS,
    MAX_BUILDING_HEIGHT_M,
    MAX_ENCODABLE_POSITION_M,
    MAX_TILES_PER_AXIS,
    SOLID_CELLS,
    TILE_CELLS,
)
from ascii_city.domain.errors import WorldDataError
from ascii_city.domain.world import Building, World, WorldDescriptor
from ascii_city.infrastructure.generator import DistrictGenerator, pack_style
from ascii_city.infrastructure.rng import Mulberry32, digest_bytes
from ascii_city.infrastructure.tile_codec import decode_tile, encode_tile
from ascii_city.infrastructure.wire_codec import decode_position, encode_position


def test_generation_is_deterministic(small_descriptor):
    first = DistrictGenerator().generate_tiles(small_descriptor)
    second = DistrictGenerator().generate_tiles(small_descriptor)
    assert digest_bytes(first[0].collision, first[0].heights, first[0].styles) == digest_bytes(
        second[0].collision, second[0].heights, second[0].styles
    )
    assert [b.id for b in first[0].buildings] == [b.id for b in second[0].buildings]


def test_the_shipped_district_never_changes_by_accident():
    """The city players know has to be the city they get back tomorrow.

    Nothing about the layout may drift without someone deliberately editing
    this number, which also forces a matching ``world_version`` bump so cached
    tiles in browsers are invalidated rather than silently wrong.
    """
    descriptor = WorldDescriptor(
        id="demo",
        version=1,
        seed=DEFAULT_SEED,
        tiles_x=1,
        tiles_y=1,
        tile_cells=TILE_CELLS,
        cell_size=CELL_SIZE_M,
        source="procedural",
    )
    tile = DistrictGenerator().generate_tiles(descriptor)[0]
    assert digest_bytes(tile.collision, tile.heights, tile.styles) == 1000197402


def test_the_default_seed_is_not_left_to_chance():
    assert load_settings().world_seed == DEFAULT_SEED


def test_a_different_seed_produces_a_different_district(small_descriptor):
    other = WorldDescriptor(
        id=small_descriptor.id,
        version=small_descriptor.version,
        seed=small_descriptor.seed ^ 0xFFFF,
        tiles_x=small_descriptor.tiles_x,
        tiles_y=small_descriptor.tiles_y,
        tile_cells=small_descriptor.tile_cells,
        cell_size=small_descriptor.cell_size,
        source="procedural",
    )
    baseline = DistrictGenerator().generate_tiles(small_descriptor)[0]
    variant = DistrictGenerator().generate_tiles(other)[0]
    assert baseline.collision != variant.collision


def test_mulberry32_matches_the_reference_stream():
    """Pinned against the canonical JavaScript mulberry32.

    Reproduce with:
        node -e "function m(a){return function(){var t=a+=0x6D2B79F5;
                 t=Math.imul(t^t>>>15,t|1);t^=t+Math.imul(t^t>>>7,t|61);
                 return (t^t>>>14)>>>0}}var f=m(42);console.log([f(),f(),f(),f()])"

    Beyond guarding existing districts against a silent reshape, this keeps the
    door open for a client-side generator without a format negotiation.
    """
    rng = Mulberry32(42)
    assert [rng.next_u32() for _ in range(4)] == [
        2581720956,
        1925393290,
        3661312704,
        2876485805,
    ]


def test_district_contains_the_required_variety(small_world):
    tile = small_world.tiles[0]
    categories = {CATEGORY_NAMES[b.category] for b in tile.buildings}
    assert len(categories) >= 3, categories
    heights = {b.height for b in tile.buildings}
    assert len(heights) >= 10
    assert any(b.height >= 40 for b in tile.buildings), "no tall silhouettes"
    assert len(tile.roads) >= 4
    assert len(small_world.spawn_points) >= 4


def test_every_layer_is_consistent(small_world):
    grid = small_world.grid
    assert grid.width == TILE_CELLS and grid.height == TILE_CELLS
    building_cells = 0
    for y in range(grid.height):
        for x in range(grid.width):
            code = grid.code_at(x, y)
            height = grid.height_at(x, y)
            if code == CELL_BUILDING:
                building_cells += 1
                assert 0 < height <= MAX_BUILDING_HEIGHT_M
            elif code == CELL_ROAD:
                # Carriageways stay flat; a step in one would be a trip hazard
                # nobody put there on purpose.
                assert height == 0
    assert building_cells > grid.width * grid.height // 10


def test_no_terrace_is_taller_than_a_player_can_jump(small_world):
    """Relief has to be somewhere you can get out of, not somewhere you land.

    On a walkable cell the height byte counts risers, and the generator is free
    to stack them. A plateau higher than a standing jump with its stairs built
    over is a hole in the district, so the ceiling is checked rather than
    trusted.
    """
    reach = JUMP_SPEED_MS**2 / (2 * GRAVITY_MS2)
    grid = small_world.grid
    for y in range(grid.height):
        for x in range(grid.width):
            if grid.code_at(x, y) in SOLID_CELLS:
                continue
            assert grid.floor_at(x, y) <= reach, (x, y, grid.floor_at(x, y))


def test_out_of_bounds_reads_are_walls(small_world):
    grid = small_world.grid
    assert grid.code_at(-1, 5) in SOLID_CELLS
    assert grid.code_at(grid.width, 5) in SOLID_CELLS
    assert grid.is_solid_cell(5, -1)


def test_spawn_points_are_standable(small_world):
    from ascii_city.domain.constants import PLAYER_RADIUS_M

    for x, y, _heading in small_world.spawn_points:
        assert small_world.grid.is_free_circle(x, y, PLAYER_RADIUS_M), (x, y)


def test_every_spawn_can_walk_the_whole_district(small_world):
    """A spawn walled into a courtyard is a player with nothing to do.

    Nothing in the generator guarantees the road cell it picked is joined to
    the rest of the map, and an arcade or a terrace dropped in the wrong place
    can sever one. The cheapest guard is to walk it.
    """
    grid = small_world.grid
    assert small_world.spawn_points, "a district with nowhere to spawn is unplayable"
    reachable = [len(_walk_from(grid, x, y)) for x, y, _ in small_world.spawn_points]
    largest = max(reachable)
    for spawn, reached in zip(small_world.spawn_points, reachable):
        assert reached > largest * 0.9, (spawn, reached, largest)


def test_a_shop_is_a_short_walk_from_every_spawn(small_world):
    """Interiors nobody can find are the same as interiors that do not exist."""
    grid = small_world.grid
    rooms = {
        cy * grid.width + cx
        for cy in range(grid.height)
        for cx in range(grid.width)
        if grid.code_at(cx, cy) == CELL_INTERACTIVE
    }
    assert rooms, "the district has no interiors at all"
    for x, y, _ in small_world.spawn_points:
        walked = _walk_from(grid, x, y)
        assert walked & rooms, (x, y)


def _walk_from(grid, x: float, y: float) -> set[int]:
    """Every cell a player-sized circle can reach on foot from `x, y` metres."""
    from collections import deque

    from ascii_city.domain.constants import PLAYER_RADIUS_M

    size = grid.cell_size
    start = (int(x / size), int(y / size))
    seen = {start[1] * grid.width + start[0]}
    queue = deque([start])
    while queue:
        cx, cy = queue.popleft()
        feet = grid.ground_at((cx + 0.5) * size, (cy + 0.5) * size, PLAYER_RADIUS_M)
        for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
            index = ny * grid.width + nx
            if nx < 0 or ny < 0 or nx >= grid.width or ny >= grid.height or index in seen:
                continue
            if not grid.is_free_circle((nx + 0.5) * size, (ny + 0.5) * size, PLAYER_RADIUS_M, feet):
                continue
            seen.add(index)
            queue.append((nx, ny))
    return seen


def test_tile_codec_round_trip(small_world):
    original = small_world.tiles[0]
    restored = decode_tile(encode_tile(original))

    assert restored.id == original.id
    assert restored.cells == original.cells
    assert restored.cell_size == pytest.approx(original.cell_size)
    assert restored.collision == original.collision
    assert restored.heights == original.heights
    assert restored.styles == original.styles
    assert len(restored.buildings) == len(original.buildings)
    assert len(restored.roads) == len(original.roads)
    assert len(restored.props) == len(original.props)
    assert len(restored.spawn_points) == len(original.spawn_points)

    first_before, first_after = original.buildings[0], restored.buildings[0]
    assert first_after.footprint == first_before.footprint
    assert first_after.height == first_before.height
    assert first_after.category == first_before.category


def test_spawn_heading_survives_the_round_trip(small_world):
    restored = decode_tile(encode_tile(small_world.tiles[0]))
    for before, after in zip(small_world.tiles[0].spawn_points, restored.spawn_points):
        assert after.heading == pytest.approx(before.heading, abs=1e-4)


def test_tile_payload_compresses_for_transport(small_world):
    tile = small_world.tiles[0]
    layers = bytes(tile.collision) + bytes(tile.heights) + bytes(tile.styles)
    # The cell layers are the repetitive part and the part that scales with
    # tile size, so they are what has to stay compressible. Street furniture
    # is a list of coordinates and will never gzip well; measuring the whole
    # payload would just turn "we added detail" into a failure.
    assert len(gzip.compress(layers, compresslevel=6)) * 5 < len(layers)

    compressed = gzip.compress(encode_tile(tile), compresslevel=6)
    assert len(compressed) < 25_000, len(compressed)


def test_truncated_payload_is_rejected(small_world):
    payload = encode_tile(small_world.tiles[0])
    with pytest.raises(WorldDataError):
        decode_tile(payload[: len(payload) // 2])


def test_foreign_payload_is_rejected():
    with pytest.raises(WorldDataError):
        decode_tile(b"NOPE" + bytes(64))


def test_style_byte_packs_three_fields():
    assert pack_style(7, 7, 3) == 255
    assert pack_style(0, 0, 0) == 0
    packed = pack_style(3, 5, 2)
    assert packed & 0b111 == 3
    assert (packed >> 3) & 0b111 == 5
    assert (packed >> 6) & 0b11 == 2


def test_building_validates_its_own_shape():
    with pytest.raises(WorldDataError):
        Building(
            id=1,
            footprint=(0, 0, 1, 1),
            height=10,
            min_height=0,
            levels=3,
            roof_type=0,
            category=0,
            facade_style=0,
            window_style=0,
            color=0,
        )
    with pytest.raises(WorldDataError):
        Building(
            id=1,
            footprint=(0, 0, 1, 0, 1, 1),
            height=10,
            min_height=12,
            levels=3,
            roof_type=0,
            category=0,
            facade_style=0,
            window_style=0,
            color=0,
        )


def test_multi_tile_world_stitches_without_seams():
    descriptor = WorldDescriptor(
        id="seam",
        version=1,
        seed=99,
        tiles_x=2,
        tiles_y=1,
        tile_cells=TILE_CELLS,
        cell_size=2.0,
        source="procedural",
    )
    tiles = list(DistrictGenerator().generate_tiles(descriptor))
    world = World.from_tiles(descriptor, tiles)
    assert world.grid.width == TILE_CELLS * 2
    assert world.grid.height == TILE_CELLS
    # The column either side of the seam must match its owning tile exactly.
    for y in range(TILE_CELLS):
        assert world.grid.code_at(TILE_CELLS - 1, y) == tiles[0].collision[y * TILE_CELLS + TILE_CELLS - 1]
        assert world.grid.code_at(TILE_CELLS, y) == tiles[1].collision[y * TILE_CELLS]


# --- configuration ----------------------------------------------------------


def test_a_district_cannot_outgrow_the_addressable_world(monkeypatch):
    """A world wider than the wire would strand players silently at the edge."""
    monkeypatch.setenv("ASCII_CITY_TILES_X", "64")
    monkeypatch.setenv("ASCII_CITY_TILES_Y", "64")
    settings = load_settings()
    assert settings.tiles_x == MAX_TILES_PER_AXIS
    assert settings.world_width_m <= MAX_ENCODABLE_POSITION_M
    assert settings.world_height_m <= MAX_ENCODABLE_POSITION_M


def test_the_furthest_corner_of_a_full_district_still_encodes():
    reach = MAX_TILES_PER_AXIS * TILE_CELLS * 2.0
    assert decode_position(encode_position(reach)) == pytest.approx(reach)
