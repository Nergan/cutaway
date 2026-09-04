"""What the shipped district actually contains, counted rather than guessed.

Run it after changing the generator: it reports how much of the map is raised,
how many rooms a player can reach on foot, and how much street furniture the
client will be asked to draw. Numbers here are the only honest answer to "is
the city detailed enough".
"""

from __future__ import annotations

import sys
from collections import Counter, deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ascii_city.config import load_settings
from ascii_city.domain import constants
from ascii_city.domain.constants import (
    CELL_INTERACTIVE,
    EYE_HEIGHT_M,
    FLOOR_STEP_M,
    PLAYER_RADIUS_M,
)
from ascii_city.domain.world import World, WorldDescriptor, collect_spawn_points
from ascii_city.infrastructure.generator import DistrictGenerator

PROP_NAMES = {
    value: name.removeprefix("PROP_").lower()
    for name, value in vars(constants).items()
    if name.startswith("PROP_") and name != "PROP_KIND_COUNT"
}


def main() -> None:
    settings = load_settings()
    descriptor = WorldDescriptor(
        id=settings.world_id,
        version=settings.world_version,
        seed=settings.world_seed,
        tiles_x=settings.tiles_x,
        tiles_y=settings.tiles_y,
        tile_cells=settings.tile_cells,
        cell_size=settings.cell_size,
        source="procedural",
    )
    tiles = list(DistrictGenerator().generate_tiles(descriptor))
    world = World.from_tiles(descriptor, tiles)
    grid = world.grid

    cells = grid.cells
    heights = grid.heights
    total = len(cells)

    codes = Counter(cells)
    print("cells by kind:")
    for code, count in codes.most_common():
        print(f"  {code:>3}  {count:>8}  {count / total:6.2%}")

    walkable = [i for i, code in enumerate(cells) if code not in constants.SOLID_CELLS]
    raised = [i for i in walkable if heights[i] > 0]
    print(f"\nwalkable cells: {len(walkable)}")
    print(f"  raised:       {len(raised)}  ({len(raised) / len(walkable):.2%})")
    if raised:
        tallest = max(heights[i] for i in raised)
        print(f"  tallest step: {tallest} risers = {tallest * FLOOR_STEP_M:.2f} m")

    props = Counter(prop.kind for tile in tiles for prop in tile.props)
    print(f"\nstreet furniture: {sum(props.values())}")
    for kind, count in props.most_common():
        print(f"  {PROP_NAMES.get(kind, kind):<12} {count:>6}")

    interiors = [i for i, code in enumerate(cells) if code == CELL_INTERACTIVE]
    print(f"\ninterior floor cells: {len(interiors)}")
    reached = flood(grid, grid.width, grid.height)
    inside = sum(1 for i in interiors if i in reached)
    print(f"  reachable on foot:  {inside}  ({inside / max(1, len(interiors)):.2%})")
    print(f"  reachable anywhere: {len(reached)}  ({len(reached) / len(walkable):.2%})")

    spawns = collect_spawn_points(tiles)
    print(f"\nspawn points: {len(spawns)}")
    for sx, sy, _ in spawns:
        walk = walking_distance(grid, sx, sy, set(interiors))
        pocket = flood(grid, grid.width, grid.height, start=(sx, sy))
        share = len(pocket) / len(walkable)
        print(
            f"  ({sx:6.0f},{sy:6.0f})  nearest room {walk:>12} steps  "
            f"can reach {share:6.2%} of the district"
        )

    # Somewhere to point the frame tool at, in metres, without hunting for it.
    print("\nplaces to look at, in metres:")
    for label, index in (
        ("a room you can walk into", next((i for i in interiors if i in reached), None)),
        ("a terrace", next((i for i in raised if i in reached), None)),
    ):
        if index is None:
            print(f"  {label:<26} none found")
            continue
        cx, cy = index % grid.width, index // grid.width
        step = heights[index]
        print(
            f"  {label:<26} --x {(cx + 0.5) * settings.cell_size:.0f} "
            f"--y {(cy + 0.5) * settings.cell_size:.0f}   (cell {cx},{cy} step {step})"
        )


def neighbours(cx: int, cy: int) -> tuple[tuple[int, int], ...]:
    return ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1))


def ground(grid: CollisionGrid, cx: int, cy: int) -> float:
    """What a player standing in the middle of this cell has under their feet."""
    size = grid.cell_size
    return grid.ground_at((cx + 0.5) * size, (cy + 0.5) * size, PLAYER_RADIUS_M)


def standable(grid: CollisionGrid, cx: int, cy: int, feet: float) -> bool:
    """Whether a player at `feet` height can step into the middle of this cell."""
    size = grid.cell_size
    return grid.is_free_circle((cx + 0.5) * size, (cy + 0.5) * size, PLAYER_RADIUS_M, feet)


def walking_distance(grid: CollisionGrid, x: float, y: float, targets: set[int]) -> int | str:
    """Cells a player must cross from `x, y` to stand on one of `targets`."""
    width = grid.width
    start = (int(x / grid.cell_size), int(y / grid.cell_size))
    seen = {start[1] * width + start[0]}
    queue = deque([(start, 0)])
    while queue:
        (cx, cy), steps = queue.popleft()
        if cy * width + cx in targets:
            return steps
        feet = ground(grid, cx, cy)
        for nx, ny in neighbours(cx, cy):
            index = ny * width + nx
            if nx < 0 or ny < 0 or nx >= width or ny >= grid.height or index in seen:
                continue
            if not standable(grid, nx, ny, feet):
                continue
            seen.add(index)
            queue.append(((nx, ny), steps + 1))
    return "unreachable"


def flood(
    grid: CollisionGrid,
    width: int,
    height: int,
    start: tuple[float, float] | None = None,
) -> set[int]:
    """Every cell centre a player-sized circle can walk to from `start`."""
    at = (
        (int(start[0] / grid.cell_size), int(start[1] / grid.cell_size))
        if start is not None
        else find_start(grid, width, height)
    )
    if at is None:
        return set()
    seen = {at[1] * width + at[0]}
    queue = deque([at])
    while queue:
        cx, cy = queue.popleft()
        feet = ground(grid, cx, cy)
        for nx, ny in neighbours(cx, cy):
            index = ny * width + nx
            if nx < 0 or ny < 0 or nx >= width or ny >= height or index in seen:
                continue
            if not standable(grid, nx, ny, feet):
                continue
            seen.add(index)
            queue.append((nx, ny))
    return seen


def find_start(grid: CollisionGrid, width: int, height: int) -> tuple[int, int] | None:
    for cy in range(height // 2, height):
        for cx in range(width // 2, width):
            if standable(grid, cx, cy, EYE_HEIGHT_M):
                return cx, cy
    return None


if __name__ == "__main__":
    main()
