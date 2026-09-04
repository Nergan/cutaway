"""Bake the Atelier catalogue to PNGs on disk so the art can be looked at.

The browser editor does this over HTTP; this is the same call without a server, so
recipe tuning does not need a running world.

    python scripts/probe_atelier.py [outdir]
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from age.atelier import character, png, recipes, sheet  # noqa: E402
from age.atelier.canvas import Canvas  # noqa: E402


def _scale(canvas: Canvas, factor: int) -> Canvas:
    """Nearest-neighbour upscale, so pixels stay pixels."""
    if factor == 1:
        return canvas
    out = Canvas(canvas.width * factor, canvas.height * factor)
    for y in range(canvas.height):
        for x in range(canvas.width):
            r, g, b, a = canvas.get(x, y)
            if not a:
                continue
            for dy in range(factor):
                for dx in range(factor):
                    out.put(x * factor + dx, y * factor + dy, (r, g, b), alpha=a)
    return out


def _contact_sheet(entries: list[tuple[str, Canvas]], columns: int = 8, scale: int = 1) -> bytes:
    """Lay baked frames out on a grid over a checker.

    A checker rather than a flat colour because most of these have soft alpha at the
    edges, and on a flat background a halo is invisible until it is over terrain.
    """
    frames = [(name, _scale(canvas, scale)) for name, canvas in entries]
    cell_w = max(canvas.width for _, canvas in frames) + 4
    cell_h = max(canvas.height for _, canvas in frames) + 4
    rows = (len(frames) + columns - 1) // columns
    out = Canvas(cell_w * columns, cell_h * rows)

    for y in range(out.height):
        for x in range(out.width):
            shade = 64 if ((x >> 3) + (y >> 3)) % 2 else 40
            out.put(x, y, (shade, shade, shade))

    for index, (_, canvas) in enumerate(frames):
        out.blit(canvas, (index % columns) * cell_w + 2, (index // columns) * cell_h + 2)
    return png.encode(out.width, out.height, out.colour)


def _tiled(canvas: Canvas, times: int = 4) -> bytes:
    """Repeat a tile into a field, where a seam would actually show."""
    field = Canvas(canvas.width * times, canvas.height * times)
    for ty in range(times):
        for tx in range(times):
            field.blit(canvas, tx * canvas.width, ty * canvas.height)
    return png.encode(field.width, field.height, field.colour)


def main() -> None:
    outdir = Path(sys.argv[1] if len(sys.argv) > 1 else ".pytest-tmp/atelier")
    outdir.mkdir(parents=True, exist_ok=True)

    started = time.perf_counter()

    ground = [(name, recipes.bake(r, seed=0)) for name, r in recipes.GROUND_RECIPES.items()]
    props = [(name, recipes.bake(r, seed=0)) for name, r in recipes.PROP_RECIPES.items()]

    (outdir / "ground.png").write_bytes(_contact_sheet(ground))
    (outdir / "props.png").write_bytes(_contact_sheet(props))
    for name, canvas in ground:
        (outdir / f"tile-{name}.png").write_bytes(_tiled(canvas))

    atlas = sheet.bake_terrain_atlas()
    color, normal, index = sheet.export(atlas)
    (outdir / "atlas.png").write_bytes(color)
    (outdir / "atlas-normal.png").write_bytes(normal)
    (outdir / "atlas.json").write_bytes(index)

    walk = [
        (
            f"{facing.name}-{frame}",
            character.bake(character.Appearance(), facing, character.Pose.WALK, frame),
        )
        for facing in character.Facing
        for frame in range(4)
    ]
    (outdir / "character-walk.png").write_bytes(_contact_sheet(walk, columns=4, scale=4))

    looks = [
        (f"look-{i}", character.bake(
            character.Appearance(body=i, hair=i, palette=i, outfit=i, accent=i),
            character.Facing.DOWN,
            character.Pose.IDLE,
            0,
        ))
        for i in range(8)
    ]
    (outdir / "character-looks.png").write_bytes(_contact_sheet(looks, columns=8, scale=4))
    (outdir / "props-big.png").write_bytes(_contact_sheet(props, columns=8, scale=3))

    print(f"baked {len(ground)} tiles, {len(props)} props, {len(walk)} character frames")
    print(f"atlas {atlas.width}x{atlas.height}, {len(atlas.placements)} entries")
    print(f"took  {(time.perf_counter() - started) * 1000:.0f} ms")
    print(f"into  {outdir.resolve()}")


if __name__ == "__main__":
    main()
