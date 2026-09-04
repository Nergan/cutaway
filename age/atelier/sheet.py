"""Atlas packing and export.

Turns baked frames into one colour page, one matching normal page, and a JSON
index. Two pages rather than one because the shader samples both at the same UV
(TDD 14.4): packing them identically means the normal lookup is the colour lookup,
with no second coordinate set to keep in sync.

The packer is a shelf packer: sort by height, fill rows left to right, start a new
row when the current one is full. Not optimal, but every frame here is between 24
and 56 pixels tall, and for near-uniform heights a shelf packer wastes only the
ragged end of each row. A guillotine packer would be more code to save a few percent
of a page that is already generously sized.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from ..domain.constants import ATLAS_PADDING_PX, ATLAS_SIZE_PX
from . import normals, png, recipes
from .canvas import Canvas


@dataclass(frozen=True, slots=True)
class Placement:
    """Where one frame ended up on the page."""

    name: str
    x: int
    y: int
    width: int
    height: int
    # Rows below the tile's bottom edge that this sprite occupies. The renderer
    # subtracts it to line a 56 px tree up with a 32 px cell.
    anchor_y: int = 0
    frame: int = 0


@dataclass(slots=True)
class Atlas:
    """A packed page pair plus its index."""

    width: int
    height: int
    colour: Canvas
    placements: list[Placement] = field(default_factory=list)

    def normal_map(self) -> bytes:
        """Derive the normal page from the packed depth channel.

        Derived after packing, not before: sampling a 3x3 neighbourhood on the packed
        page means the padding between frames provides the border, and a per-frame
        normal map would have to be packed a second time.
        """
        return normals.to_normal_map(self.colour)

    def index(self) -> dict[str, object]:
        return {
            "width": self.width,
            "height": self.height,
            "frames": [
                {
                    "name": placement.name,
                    "frame": placement.frame,
                    "x": placement.x,
                    "y": placement.y,
                    "w": placement.width,
                    "h": placement.height,
                    "anchorY": placement.anchor_y,
                }
                for placement in self.placements
            ],
        }


def pack(entries: list[tuple[str, int, int, Canvas]], *, page: int = ATLAS_SIZE_PX) -> Atlas:
    """Pack ``(name, frame, anchor_y, canvas)`` entries onto one page.

    Raises if they do not fit. Growing the page silently would push the atlas past
    what a low-end GPU guarantees, and a hard failure at build time is much better
    than a texture that fails to upload on someone's laptop.
    """
    ordered = sorted(entries, key=lambda entry: (-entry[3].height, entry[0], entry[1]))

    atlas = Atlas(width=page, height=page, colour=Canvas(page, page))
    cursor_x = ATLAS_PADDING_PX
    cursor_y = ATLAS_PADDING_PX
    row_height = 0

    for name, frame, anchor_y, art in ordered:
        if cursor_x + art.width + ATLAS_PADDING_PX > page:
            cursor_x = ATLAS_PADDING_PX
            cursor_y += row_height + ATLAS_PADDING_PX
            row_height = 0

        if cursor_y + art.height + ATLAS_PADDING_PX > page:
            raise ValueError(
                f"atlas overflow at {name}#{frame}: {len(ordered)} frames do not fit "
                f"in {page}x{page}"
            )

        atlas.colour.blit(art, cursor_x, cursor_y)
        atlas.placements.append(
            Placement(
                name=name,
                x=cursor_x,
                y=cursor_y,
                width=art.width,
                height=art.height,
                anchor_y=anchor_y,
                frame=frame,
            )
        )

        cursor_x += art.width + ATLAS_PADDING_PX
        row_height = max(row_height, art.height)

    atlas.placements.sort(key=lambda placement: (placement.name, placement.frame))
    return atlas


def bake_terrain_atlas(*, seed: int = 0) -> Atlas:
    """Bake and pack every ground and prop frame in the library."""
    entries: list[tuple[str, int, int, Canvas]] = []
    for recipe in recipes.ALL_RECIPES.values():
        for frame in range(recipe.frames):
            entries.append(
                (recipe.key, frame, recipe.anchor_y, recipes.bake(recipe, seed=seed, frame=frame))
            )
    return pack(entries)


def export(atlas: Atlas) -> tuple[bytes, bytes, bytes]:
    """Encode a packed atlas as ``(colour PNG, normal PNG, index JSON)``."""
    colour_png = png.encode(atlas.width, atlas.height, atlas.colour.colour)
    normal_png = png.encode(atlas.width, atlas.height, atlas.normal_map())
    index = json.dumps(atlas.index(), separators=(",", ":")).encode("utf-8")
    return colour_png, normal_png, index


def export_recipe(recipe: recipes.Recipe, *, seed: int = 0) -> tuple[bytes, bytes]:
    """Encode one recipe as a horizontal strip plus its normal strip.

    A strip rather than a page because this is what an external editor expects: drop
    it into Aseprite and every frame is a cel.
    """
    frames = [recipes.bake(recipe, seed=seed, frame=frame) for frame in range(recipe.frames)]
    strip = Canvas(recipe.width * recipe.frames, recipe.height)
    for index, art in enumerate(frames):
        strip.blit(art, index * recipe.width, 0)

    return (
        png.encode(strip.width, strip.height, strip.colour),
        png.encode(strip.width, strip.height, normals.to_normal_map(strip, wrap=recipe.seamless)),
    )
