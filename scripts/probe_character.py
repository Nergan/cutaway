"""Blow up a few character frames so individual pixels can be judged.

    python scripts/probe_character.py [outdir]
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from age.atelier import character, png  # noqa: E402
from age.atelier.canvas import Canvas  # noqa: E402

SCALE = 10


def _blow_up(frames: list[Canvas]) -> bytes:
    cell = character.SPRITE_WIDTH * SCALE + SCALE
    out = Canvas(cell * len(frames), character.SPRITE_HEIGHT * SCALE + SCALE)

    for y in range(out.height):
        for x in range(out.width):
            shade = 70 if ((x // SCALE) + (y // SCALE)) % 2 else 46
            out.put(x, y, (shade, shade, shade))

    for index, frame in enumerate(frames):
        ox = index * cell + SCALE // 2
        oy = SCALE // 2
        for y in range(frame.height):
            for x in range(frame.width):
                r, g, b, a = frame.get(x, y)
                if not a:
                    continue
                for dy in range(SCALE):
                    for dx in range(SCALE):
                        out.put(ox + x * SCALE + dx, oy + y * SCALE + dy, (r, g, b), alpha=a)
    return png.encode(out.width, out.height, out.colour)


def main() -> None:
    outdir = Path(sys.argv[1] if len(sys.argv) > 1 else ".pytest-tmp/atelier")
    outdir.mkdir(parents=True, exist_ok=True)
    look = character.Appearance(body=1, hair=0, palette=1, outfit=2, accent=1)

    for name, frames in {
        "facings": [
            character.bake(look, facing, character.Pose.IDLE, 0) for facing in character.Facing
        ],
        "walk-down": [
            character.bake(look, character.Facing.DOWN, character.Pose.WALK, f) for f in range(4)
        ],
        "walk-side": [
            character.bake(look, character.Facing.SIDE, character.Pose.WALK, f) for f in range(4)
        ],
        "attack": [
            character.bake(look, character.Facing.SIDE, character.Pose.ATTACK, f) for f in range(3)
        ],
    }.items():
        (outdir / f"big-{name}.png").write_bytes(_blow_up(frames))
        print(f"wrote big-{name}.png")


if __name__ == "__main__":
    main()
