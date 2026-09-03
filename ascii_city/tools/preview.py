"""Top-down preview of a generated district.

Run it while tuning the generator:

    python -m ascii_city.tools.preview --seed 0x5A17C17E --tiles 2 2
"""

from __future__ import annotations

import argparse
import time

from ..domain.constants import (
    CATEGORY_NAMES,
    CELL_BLOCKED,
    CELL_BUILDING,
    CELL_INTERACTIVE,
    CELL_ROAD,
    CELL_SIDEWALK,
    CELL_SIZE_M,
    TILE_CELLS,
)
from ..domain.world import World, WorldDescriptor
from ..infrastructure.generator import DistrictGenerator
from ..infrastructure.tile_codec import decode_tile, encode_tile

# Buildings are drawn by height band so the skyline is visible from above.
_HEIGHT_RAMP = " .:-=+*#%@"


def _glyph(code: int, height: int) -> str:
    if code == CELL_ROAD:
        return "\u00b7"
    if code == CELL_SIDEWALK:
        return ","
    if code == CELL_INTERACTIVE:
        return "o"
    if code == CELL_BLOCKED:
        return "T"
    if code == CELL_BUILDING:
        index = min(len(_HEIGHT_RAMP) - 1, 1 + height * (len(_HEIGHT_RAMP) - 2) // 120)
        return _HEIGHT_RAMP[index]
    return " "


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Preview a procedural ASCII City district.")
    parser.add_argument("--seed", default="0x5A17C17E")
    parser.add_argument("--tiles", nargs=2, type=int, default=(2, 2), metavar=("X", "Y"))
    parser.add_argument("--step", type=int, default=2, help="Sample every Nth cell.")
    parser.add_argument("--no-map", action="store_true")
    args = parser.parse_args(argv)

    descriptor = WorldDescriptor(
        id="preview",
        version=1,
        seed=int(args.seed, 0) & 0xFFFFFFFF,
        tiles_x=args.tiles[0],
        tiles_y=args.tiles[1],
        tile_cells=TILE_CELLS,
        cell_size=CELL_SIZE_M,
        source="procedural",
    )

    started = time.perf_counter()
    tiles = list(DistrictGenerator().generate_tiles(descriptor))
    generated_ms = (time.perf_counter() - started) * 1000

    started = time.perf_counter()
    payloads = [encode_tile(tile) for tile in tiles]
    encoded_ms = (time.perf_counter() - started) * 1000
    for payload, tile in zip(payloads, tiles):
        decoded = decode_tile(payload)
        assert decoded.collision == tile.collision, "tile codec round trip diverged"

    world = World.from_tiles(descriptor, tiles)
    grid = world.grid

    if not args.no_map:
        for y in range(0, grid.height, args.step):
            print(
                "".join(
                    _glyph(grid.code_at(x, y), grid.height_at(x, y))
                    for x in range(0, grid.width, args.step)
                )
            )

    counts: dict[str, int] = {}
    for tile in tiles:
        for building in tile.buildings:
            name = CATEGORY_NAMES[building.category]
            counts[name] = counts.get(name, 0) + 1
    heights = [b.height for tile in tiles for b in tile.buildings]
    walkable = sum(
        1
        for y in range(grid.height)
        for x in range(grid.width)
        if not grid.is_solid_cell(x, y)
    )

    print()
    print(f"world        {grid.width}x{grid.height} cells  ({grid.width_m:.0f}x{grid.height_m:.0f} m)")
    print(f"generate     {generated_ms:.0f} ms")
    print(f"encode       {encoded_ms:.0f} ms")
    print(f"tile bytes   {sum(len(p) for p in payloads) // len(payloads)} avg raw")
    print(f"buildings    {sum(counts.values())}  {dict(sorted(counts.items()))}")
    print(f"heights      min {min(heights)} m, max {max(heights)} m, mean {sum(heights) / len(heights):.1f} m")
    print(f"roads        {sum(len(tile.roads) for tile in tiles) // len(tiles)} per tile")
    print(f"props        {sum(len(tile.props) for tile in tiles)}")
    print(f"spawns       {len(world.spawn_points)}")
    print(f"walkable     {walkable * 100 // (grid.width * grid.height)}% of cells")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
