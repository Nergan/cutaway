"""Import a GeoJSON extract into a district and preview it.

    python -m ascii_city.tools.import_osm ascii_city/docs/samples/osm-district.geojson

Prints the same top-down map as ``tools.preview`` so an imported district can
be eyeballed against a generated one. See ``docs/osm-import.md``.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from ..domain.constants import CATEGORY_NAMES, CELL_SIZE_M, TILE_CELLS
from ..domain.world import World, WorldDescriptor
from ..infrastructure.osm import GeoOrigin, OsmDistrictImporter, bounds_of
from ..infrastructure.tile_codec import decode_tile, encode_tile
from .preview import _glyph


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import GeoJSON into an ASCII City district.")
    parser.add_argument("path", type=Path, help="A GeoJSON FeatureCollection carrying OSM tags.")
    parser.add_argument("--tiles", nargs=2, type=int, default=(1, 1), metavar=("X", "Y"))
    parser.add_argument("--step", type=int, default=2, help="Sample every Nth cell.")
    parser.add_argument("--no-map", action="store_true")
    args = parser.parse_args(argv)

    payload = json.loads(args.path.read_text(encoding="utf-8"))
    importer = OsmDistrictImporter(payload)
    min_lon, min_lat, max_lon, max_lat = bounds_of(importer.features)

    descriptor = WorldDescriptor(
        id=args.path.stem,
        version=1,
        seed=0,
        tiles_x=args.tiles[0],
        tiles_y=args.tiles[1],
        tile_cells=TILE_CELLS,
        cell_size=CELL_SIZE_M,
        source=importer.source,
    )

    started = time.perf_counter()
    tiles = list(importer.generate_tiles(descriptor))
    imported_ms = (time.perf_counter() - started) * 1000

    payloads = [encode_tile(tile) for tile in tiles]
    for encoded, tile in zip(payloads, tiles):
        assert decode_tile(encoded).collision == tile.collision, "tile codec round trip diverged"

    world = World.from_tiles(descriptor, tiles)
    grid = world.grid
    if not args.no_map:
        for y in range(grid.height - 1, -1, -args.step):
            print(
                "".join(
                    _glyph(grid.code_at(x, y), grid.height_at(x, y))
                    for x in range(0, grid.width, args.step)
                )
            )

    corner = GeoOrigin(lat=min_lat, lon=min_lon).project(max_lon, max_lat)
    buildings = [b for tile in tiles for b in tile.buildings]
    print()
    print(f"source       {args.path}")
    print(f"origin       {min_lat:.5f}, {min_lon:.5f}")
    print(f"extent       {corner[0]:.0f} x {corner[1]:.0f} m of geometry")
    print(f"world        {grid.width}x{grid.height} cells ({grid.width_m:.0f}x{grid.height_m:.0f} m)")
    print(f"import       {imported_ms:.0f} ms")
    print(f"tile bytes   {sum(len(p) for p in payloads) // len(payloads)} avg raw")
    for building in sorted(buildings, key=lambda b: -b.height):
        print(
            f"  {building.height:>4} m  {building.levels:>2} lv  "
            f"{CATEGORY_NAMES[building.category]:<15} {building.source_id or ''}"
        )
    print(f"roads        {sum(len(tile.roads) for tile in tiles)}")
    print(f"spawns       {len(world.spawn_points)}")
    print(f"attribution  {importer.attribution}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
