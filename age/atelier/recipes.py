"""The recipe format, and the project's own tile and prop recipes.

A recipe is a list of operations with parameters. It is plain JSON on purpose:
the browser editor at ``/age/atelier`` loads them, edits them live, and posts them
back, and the same list drives the Python bake used for PNG export. One format, no
translation step, and a recipe is diffable in review.

Terrain is drawn in two layers, which is the decision that keeps the tilemap clean.
Every tile has a *ground* recipe: a seamless 32x32 carpet. Tiles that are really
objects — a tree, a rock, a wall — additionally have a *prop* recipe, taller than a
tile and anchored to its bottom edge. So a forest tile is grass with a tree standing
on it rather than a 32x32 picture of a tree, which is what lets trees overlap the
tile above them and cast shadow onto it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from ..domain.tiles import Tile
from . import canvas as ops
from . import palette
from .canvas import Canvas

Step = dict[str, Any]

TILE_PX = 32


@dataclass(frozen=True, slots=True)
class Recipe:
    """A bakeable sprite description.

    ``frames`` above one makes it animated; the bake receives a frame index and
    animated operations read their phase from it. ``seamless`` tells the normal-map
    pass to wrap its gradient sampling, which is required for ground and wrong for
    anything with a silhouette.
    """

    key: str
    kind: str
    width: int
    height: int
    steps: tuple[Step, ...]
    frames: int = 1
    seamless: bool = False
    # How far the sprite's bottom sits below the anchor tile's bottom edge. Zero for
    # ground, positive for a prop whose base should overlap the tile it stands on.
    anchor_y: int = 0
    label: str = ""

    def to_json(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "kind": self.kind,
            "width": self.width,
            "height": self.height,
            "frames": self.frames,
            "seamless": self.seamless,
            "anchorY": self.anchor_y,
            "label": self.label or self.key.replace("_", " ").title(),
            "steps": [dict(step) for step in self.steps],
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "Recipe":
        """Rebuild a recipe from the editor's payload.

        Dimensions are clamped rather than trusted: this arrives from a browser, and
        a recipe claiming to be 40000 px square would bake until the worker died.
        """
        width = _clamp_int(payload.get("width", TILE_PX), 1, 256)
        height = _clamp_int(payload.get("height", TILE_PX), 1, 256)
        steps = payload.get("steps") or []
        if not isinstance(steps, list):
            raise ValueError("steps must be a list")
        return cls(
            key=str(payload.get("key", "untitled"))[:64],
            kind=str(payload.get("kind", "prop"))[:16],
            width=width,
            height=height,
            steps=tuple(step for step in steps if isinstance(step, dict))[:64],
            frames=_clamp_int(payload.get("frames", 1), 1, 16),
            seamless=bool(payload.get("seamless", False)),
            anchor_y=_clamp_int(payload.get("anchorY", 0), -64, 64),
            label=str(payload.get("label", ""))[:64],
        )


def _clamp_int(value: Any, low: int, high: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return low
    return low if number < low else (high if number > high else number)


# --- baking -----------------------------------------------------------------


def bake(recipe: Recipe, *, seed: int = 0, frame: int = 0) -> Canvas:
    """Evaluate a recipe into a canvas.

    The phase is the frame's position around the animation loop, in ``[0, 1)``.
    Operations that animate take it as a sine so a cycle closes on itself; an
    animation that jumps on the wrap is the most common way procedural sprite
    animation looks wrong.
    """
    surface = Canvas(recipe.width, recipe.height)
    index_in_loop = frame % recipe.frames if recipe.frames > 0 else 0
    phase = index_in_loop / recipe.frames if recipe.frames > 1 else 0.0
    wave = math.sin(phase * math.tau)

    for index, step in enumerate(recipe.steps):
        surface = _apply(
            surface,
            step,
            seed=seed ^ (index * 0x9E37),
            wave=wave,
            phase=phase,
            frame=index_in_loop,
        )

    return surface


def _apply(
    surface: Canvas, step: Step, *, seed: int, wave: float, phase: float, frame: int
) -> Canvas:
    """Run one operation. Returns the canvas, which some operations replace."""
    op = str(step.get("op", ""))
    rect = _rect(step.get("rect"))

    if op == "fill":
        ops.fill(
            surface,
            str(step.get("ramp", "soil")),
            level=int(step.get("level", 2)),
            depth=int(step.get("depth", 0)),
            material=int(step.get("material", 0)),
            rect=rect,
        )
    elif op == "scatter":
        ops.scatter(
            surface,
            str(step.get("ramp", "soil")),
            seed=seed + int(step.get("seed", 0)),
            density=float(step.get("density", 0.1)),
            level=int(step.get("level", 1)),
            depth=step.get("depth") if step.get("depth") is None else int(step["depth"]),
            material=step.get("material") if step.get("material") is None else int(step["material"]),
            only_on_opaque=bool(step.get("onlyOnOpaque", True)),
        )
    elif op == "dither":
        ops.dither(
            surface,
            str(step.get("ramp", "soil")),
            from_level=int(step.get("from", 1)),
            to_level=int(step.get("to", 3)),
            vertical=bool(step.get("vertical", True)),
            rect=rect,
        )
    elif op == "blob":
        ops.blob(
            surface,
            str(step.get("ramp", "leaf")),
            seed=seed + int(step.get("seed", 0)),
            centre=(float(step.get("x", 16)), float(step.get("y", 16))),
            radius=float(step.get("radius", 8)),
            wobble=float(step.get("wobble", 0.35)),
            level=int(step.get("level", 2)),
            depth=int(step.get("depth", 160)),
            material=int(step.get("material", 0)),
            dome=bool(step.get("dome", True)),
        )
    elif op == "column":
        ops.column(
            surface,
            str(step.get("ramp", "wood")),
            rect=rect or (0, 0, surface.width, surface.height),
            level=int(step.get("level", 2)),
            depth=int(step.get("depth", 200)),
            material=int(step.get("material", 0)),
            lit_from_left=bool(step.get("litFromLeft", True)),
        )
    elif op == "line":
        ops.line(
            surface,
            str(step.get("ramp", "wood")),
            start=(int(step.get("x0", 0)), int(step.get("y0", 0))),
            end=(int(step.get("x1", 0)), int(step.get("y1", 0))),
            level=int(step.get("level", 2)),
            thickness=int(step.get("thickness", 1)),
            depth=int(step.get("depth", 120)),
            material=int(step.get("material", 0)),
        )
    elif op == "outline":
        ops.outline(
            surface,
            str(step.get("ramp", "shadow")),
            level=int(step.get("level", 1)),
            alpha=int(step.get("alpha", 235)),
            only_bottom=bool(step.get("onlyBottom", False)),
        )
    elif op == "contact_shadow":
        ops.contact_shadow(
            surface,
            rows=int(step.get("rows", 2)),
            amount=float(step.get("amount", 0.35)),
        )
    elif op == "mirror":
        ops.mirror_horizontal(surface)
    elif op == "sway":
        return ops.sway(
            surface,
            pivot_row=int(step.get("pivotRow", surface.height - 1)),
            shift=float(step.get("amplitude", 1.0)) * wave,
        )
    elif op == "bob":
        return ops.bob(surface, offset=round(float(step.get("amplitude", 1.0)) * wave))
    elif op == "flicker":
        # The frame goes into the seed rather than into an amplitude: a flame's outline
        # changes shape between frames, it does not move as a rigid body, so what varies
        # has to be *which* edge pixels are eroded rather than by how much.
        ops.flicker(
            surface,
            seed=seed ^ (frame * 0x27D4EB2D),
            above_row=int(step.get("aboveRow", surface.height)),
            amount=float(step.get("amount", 0.3)),
        )
    elif op == "ripple":
        # Water: shift a dithered band across the tile rather than deforming it, so
        # the tile stays seamless at every frame.
        _ripple(surface, step, phase)

    return surface


def _ripple(surface: Canvas, step: Step, phase: float) -> None:
    """Scroll sine-wave crests across the tile. Water and lava.

    Two crests at different wavelengths, both whole multiples of the tile width so
    they still meet at the seam. Deforming the tile instead would be cheaper to write
    and would break tiling, which on an open water surface is immediately obvious.
    """
    from .palette import ramp as lookup_ramp

    palette = lookup_ramp(str(step.get("ramp", "water")))
    crest = palette.shade(int(step.get("level", 4)))
    thickness = max(1, int(step.get("band", 2)))
    drift = phase * surface.height

    for x in range(surface.width):
        angle = x / surface.width * math.tau
        for wavelength, offset in ((1.0, 0.0), (2.0, surface.height * 0.5)):
            centre = (
                math.sin(angle * wavelength) * 2.2 + drift + offset + surface.height * 0.25
            ) % surface.height
            for step_y in range(thickness):
                y = int(centre + step_y) % surface.height
                if ops.BAYER_4X4[y & 3][x & 3] < 11:
                    surface.put(x, y, crest, depth=surface.depth[y * surface.width + x])


def _rect(raw: Any) -> tuple[int, int, int, int] | None:
    if not isinstance(raw, (list, tuple)) or len(raw) != 4:
        return None
    try:
        return (int(raw[0]), int(raw[1]), int(raw[2]), int(raw[3]))
    except (TypeError, ValueError):
        return None


# --- the project's recipes --------------------------------------------------
#
# Ground carpets first: seamless, 32x32, no silhouette. Every one starts from a flat
# fill so no pixel is ever left transparent, which would show as a hole in the
# tilemap.


def _ground(key: str, *steps: Step, frames: int = 1, label: str = "") -> Recipe:
    return Recipe(
        key=key,
        kind="tile",
        width=TILE_PX,
        height=TILE_PX,
        steps=tuple(steps),
        frames=frames,
        seamless=True,
        label=label,
    )


def _prop(
    key: str,
    height: int,
    *steps: Step,
    frames: int = 1,
    anchor_y: int = 0,
    label: str = "",
) -> Recipe:
    return Recipe(
        key=key,
        kind="prop",
        width=TILE_PX,
        height=height,
        steps=tuple(steps),
        frames=frames,
        anchor_y=anchor_y,
        label=label,
    )


def _pebbles() -> tuple[Step, ...]:
    """Fourteen small lumps at hash-scattered positions, wrapping at the edges.

    Positions come from the same hash the rest of the Atelier uses, so the layout is
    stable across bakes but does not look like a grid.
    """
    steps: list[Step] = []
    for index in range(14):
        x = int(ops.rand(0x9EB1, index, 1) * TILE_PX)
        y = int(ops.rand(0x9EB1, index, 2) * TILE_PX)
        steps.append(
            {
                "op": "blob",
                "ramp": "stone",
                "seed": index + 60,
                "x": x,
                "y": y,
                "radius": 1.6 + ops.rand(0x9EB1, index, 3) * 1.4,
                "wobble": 0.30,
                "level": 2 if index % 3 else 3,
                "depth": 30,
                "material": 4,
            }
        )
    return tuple(steps)


def _cobbles() -> tuple[Step, ...]:
    """Eight-pixel stones in a staggered grid, each domed in the depth channel."""
    steps: list[Step] = []
    for row in range(4):
        for col in range(4):
            offset = 4 if row % 2 else 0
            steps.append(
                {
                    "op": "blob",
                    "ramp": "stone",
                    "seed": row * 4 + col + 40,
                    "x": (col * 8 + offset + 4) % TILE_PX,
                    "y": row * 8 + 4,
                    "radius": 3.4,
                    "wobble": 0.16,
                    "level": 2,
                    "depth": 90,
                    "material": 6,
                }
            )
    return tuple(steps)


def _planks() -> tuple[Step, ...]:
    """Four horizontal boards with dark gaps and a lengthwise grain."""
    steps: list[Step] = []
    for index in range(4):
        top = index * 8
        steps.append(
            {
                "op": "dither",
                "ramp": "plank",
                "from": 3 if index % 2 else 2,
                "to": 2 if index % 2 else 1,
                "rect": [0, top, TILE_PX, top + 7],
            }
        )
        steps.append(
            {
                "op": "fill",
                "ramp": "wood",
                "level": 0,
                "depth": 0,
                "material": 7,
                "rect": [0, top + 7, TILE_PX, top + 8],
            }
        )
    steps.append({"op": "scatter", "ramp": "wood", "seed": 21, "density": 0.05, "level": 1})
    return tuple(steps)


def _flagstones() -> tuple[Step, ...]:
    """A 2x2 slab layout with recessed mortar."""
    steps: list[Step] = []
    for row in range(2):
        for col in range(2):
            steps.append(
                {
                    "op": "dither",
                    "ramp": "stone",
                    "from": 3,
                    "to": 1,
                    "rect": [col * 16 + 1, row * 16 + 1, col * 16 + 15, row * 16 + 15],
                }
            )
    steps.append({"op": "scatter", "ramp": "stone", "seed": 22, "density": 0.05, "level": 0})
    return tuple(steps)


def _grass_blades() -> tuple[Step, ...]:
    """Seven blades of varying height, fanning out from the base."""
    layout = ((5, 10), (9, 6), (13, 3), (16, 1), (20, 4), (24, 7), (28, 11))
    return tuple(
        {
            "op": "line",
            "ramp": "grass",
            "x0": 16 + (x - 16) // 3,
            "y0": 22,
            "x1": x,
            "y1": top,
            "level": 1 + (index % 3),
            "thickness": 1,
            "depth": 40,
        }
        for index, (x, top) in enumerate(layout)
    )


def _wall_boards() -> tuple[Step, ...]:
    """Vertical boards under a capping rail.

    Order matters more here than it looks. An earlier version drew the seams first and then
    dithered the whole face over them, which painted them out and left a flat speckled panel
    that read as a plank floor seen from above. The gradient has to go down before the lines
    that describe the boards go on top of it.
    """
    steps: list[Step] = [
        {"op": "dither", "ramp": "plank", "from": 3, "to": 1, "rect": [1, 15, 31, 44]},
    ]
    for x in (7, 15, 23):
        # The seam, then the lit edge of the board beginning to its right. Two adjacent
        # pixels of opposite value are what make one fill read as separate boards.
        steps.append(
            {"op": "fill", "ramp": "wood", "level": 0, "depth": 228, "rect": [x, 15, x + 1, 44]}
        )
        steps.append(
            {"op": "fill", "ramp": "plank", "level": 4, "depth": 232, "rect": [x + 1, 15, x + 2, 44]}
        )
    # The rail. A horizontal band at the top is the cheapest way to say "this is a wall,
    # and you are looking at it from the side".
    steps.append({"op": "fill", "ramp": "wood", "level": 2, "depth": 238, "rect": [0, 12, 32, 16]})
    steps.append({"op": "fill", "ramp": "wood", "level": 3, "depth": 238, "rect": [0, 12, 32, 14]})
    return tuple(steps)


def _wall_bricks() -> tuple[Step, ...]:
    steps: list[Step] = []
    for row in range(4):
        top = 12 + row * 8
        offset = 5 if row % 2 else 0
        for col in range(3):
            left = col * 11 + offset
            steps.append(
                {
                    "op": "dither",
                    "ramp": "brick",
                    "from": 3,
                    "to": 1,
                    "rect": [left, top, min(TILE_PX, left + 10), top + 7],
                }
            )
    return tuple(steps)


GROUND_RECIPES: dict[str, Recipe] = {
    recipe.key: recipe
    for recipe in (
        _ground(
            "bare_ground",
            {"op": "fill", "ramp": "soil", "level": 2, "material": 1},
            {"op": "scatter", "ramp": "soil", "seed": 1, "density": 0.20, "level": 1, "depth": 4},
            {"op": "scatter", "ramp": "soil", "seed": 2, "density": 0.10, "level": 3, "depth": 8},
        ),
        _ground(
            "grass",
            {"op": "fill", "ramp": "grass", "level": 2, "material": 2},
            {"op": "scatter", "ramp": "grass", "seed": 3, "density": 0.22, "level": 1, "depth": 6},
            {"op": "scatter", "ramp": "grass", "seed": 4, "density": 0.14, "level": 3, "depth": 10},
            {"op": "scatter", "ramp": "soil", "seed": 5, "density": 0.03, "level": 2},
        ),
        _ground(
            "sand",
            {"op": "fill", "ramp": "sand", "level": 2, "material": 3},
            # Two offset speckle passes read as wind-rippled sand; one reads as noise.
            {"op": "scatter", "ramp": "sand", "seed": 6, "density": 0.18, "level": 3, "depth": 6},
            {"op": "scatter", "ramp": "sand", "seed": 7, "density": 0.10, "level": 1, "depth": 2},
        ),
        _ground(
            "gravel",
            {"op": "fill", "ramp": "stone", "level": 1, "material": 4},
            # Clumps, not speckle. Per-pixel noise at any density reads as television
            # static; loose stone reads as stone because it comes in lumps of two or
            # three pixels with dark gaps between them.
            *_pebbles(),
            {"op": "scatter", "ramp": "dark_stone", "seed": 10, "density": 0.07, "level": 1},
        ),
        _ground(
            "dirt_road",
            {"op": "fill", "ramp": "path", "level": 2, "material": 5},
            {"op": "scatter", "ramp": "path", "seed": 11, "density": 0.20, "level": 1, "depth": 3},
            {"op": "scatter", "ramp": "soil", "seed": 12, "density": 0.06, "level": 2},
        ),
        _ground(
            "cobble_road",
            {"op": "fill", "ramp": "stone", "level": 1, "material": 6},
            # A 4x4 lattice of raised stones. The depth channel is what makes the
            # cobbles catch a moving light; the colour alone would look painted on.
            *_cobbles(),
        ),
        _ground(
            "floor_wood",
            {"op": "fill", "ramp": "plank", "level": 2, "material": 7},
            *_planks(),
        ),
        _ground(
            "floor_stone",
            {"op": "fill", "ramp": "stone", "level": 3, "material": 6},
            *_flagstones(),
        ),
        _ground(
            "snow",
            {"op": "fill", "ramp": "snow", "level": 3, "material": 8},
            {"op": "scatter", "ramp": "snow", "seed": 13, "density": 0.12, "level": 4, "depth": 10},
            {"op": "scatter", "ramp": "snow", "seed": 14, "density": 0.10, "level": 1, "depth": 4},
        ),
        _ground(
            "ash",
            {"op": "fill", "ramp": "dark_stone", "level": 2, "material": 9},
            {"op": "scatter", "ramp": "dark_stone", "seed": 15, "density": 0.20, "level": 1},
            {"op": "scatter", "ramp": "ember", "seed": 16, "density": 0.02, "level": 3, "depth": 6},
        ),
        _ground(
            "water",
            {"op": "fill", "ramp": "water", "level": 2, "material": 10},
            {"op": "dither", "ramp": "water", "from": 1, "to": 3},
            {"op": "ripple", "ramp": "water", "level": 4, "band": 3},
            frames=4,
        ),
        _ground(
            "deep_water",
            {"op": "fill", "ramp": "deep_water", "level": 2, "material": 10},
            {"op": "dither", "ramp": "deep_water", "from": 1, "to": 2},
            {"op": "ripple", "ramp": "deep_water", "level": 3, "band": 2},
            frames=4,
        ),
    )
}


PROP_RECIPES: dict[str, Recipe] = {
    recipe.key: recipe
    for recipe in (
        _prop(
            "tall_grass",
            24,
            *_grass_blades(),
            {"op": "sway", "pivotRow": 20, "amplitude": 1.6},
            frames=4,
            anchor_y=6,
        ),
        _prop(
            "bush",
            26,
            {"op": "blob", "ramp": "leaf", "seed": 30, "x": 11, "y": 17, "radius": 7.0, "level": 1},
            {"op": "blob", "ramp": "leaf", "seed": 31, "x": 21, "y": 18, "radius": 6.4, "level": 2},
            {"op": "blob", "ramp": "leaf", "seed": 32, "x": 16, "y": 13, "radius": 7.4, "level": 3},
            {"op": "scatter", "ramp": "leaf", "seed": 33, "density": 0.10, "level": 4},
            {"op": "outline", "ramp": "shadow", "level": 0, "alpha": 210},
            {"op": "contact_shadow", "rows": 2, "amount": 0.30},
            {"op": "sway", "pivotRow": 22, "amplitude": 1.0},
            frames=4,
            anchor_y=6,
        ),
        _prop(
            "sapling",
            30,
            {"op": "column", "ramp": "wood", "rect": [15, 16, 18, 30], "depth": 120},
            {"op": "blob", "ramp": "leaf", "seed": 34, "x": 16, "y": 12, "radius": 7.0, "level": 3},
            {"op": "blob", "ramp": "leaf", "seed": 35, "x": 12, "y": 15, "radius": 4.6, "level": 2},
            {"op": "outline", "ramp": "shadow", "level": 0, "alpha": 210},
            {"op": "sway", "pivotRow": 26, "amplitude": 1.2},
            frames=4,
            anchor_y=4,
        ),
        _prop(
            "tree",
            56,
            # Trunk first so the canopy overlaps it, then three canopy lobes at
            # different levels: a single blob reads as a lollipop.
            {"op": "column", "ramp": "wood", "rect": [13, 30, 20, 56], "depth": 210},
            {"op": "line", "ramp": "wood", "x0": 16, "y0": 34, "x1": 9, "y1": 27, "level": 1, "thickness": 2},
            {"op": "line", "ramp": "wood", "x0": 16, "y0": 32, "x1": 24, "y1": 25, "level": 1, "thickness": 2},
            {"op": "blob", "ramp": "leaf", "seed": 36, "x": 10, "y": 24, "radius": 9.0, "level": 1, "depth": 150},
            {"op": "blob", "ramp": "leaf", "seed": 37, "x": 22, "y": 23, "radius": 9.6, "level": 2, "depth": 165},
            {"op": "blob", "ramp": "leaf", "seed": 38, "x": 16, "y": 15, "radius": 11.0, "level": 3, "depth": 190},
            {"op": "scatter", "ramp": "leaf", "seed": 39, "density": 0.08, "level": 4},
            {"op": "outline", "ramp": "shadow", "level": 0, "alpha": 220},
            {"op": "contact_shadow", "rows": 3, "amount": 0.34},
            {"op": "sway", "pivotRow": 40, "amplitude": 2.2},
            frames=4,
            anchor_y=8,
        ),
        _prop(
            "dead_tree",
            50,
            {"op": "column", "ramp": "wood", "rect": [14, 22, 19, 50], "level": 1, "depth": 200},
            {"op": "line", "ramp": "wood", "x0": 16, "y0": 26, "x1": 6, "y1": 14, "level": 0, "thickness": 2},
            {"op": "line", "ramp": "wood", "x0": 16, "y0": 30, "x1": 27, "y1": 16, "level": 1, "thickness": 2},
            {"op": "line", "ramp": "wood", "x0": 16, "y0": 22, "x1": 19, "y1": 6, "level": 1, "thickness": 2},
            {"op": "outline", "ramp": "shadow", "level": 0, "alpha": 225},
            {"op": "contact_shadow", "rows": 3, "amount": 0.34},
            anchor_y=6,
        ),
        _prop(
            "rock",
            26,
            {"op": "blob", "ramp": "stone", "seed": 41, "x": 16, "y": 17, "radius": 10.0, "wobble": 0.22, "level": 2, "depth": 200},
            {"op": "blob", "ramp": "stone", "seed": 42, "x": 12, "y": 14, "radius": 5.0, "wobble": 0.20, "level": 3, "depth": 230},
            {"op": "scatter", "ramp": "dark_stone", "seed": 43, "density": 0.07, "level": 1},
            {"op": "outline", "ramp": "shadow", "level": 0, "alpha": 225},
            {"op": "contact_shadow", "rows": 2, "amount": 0.32},
            anchor_y=4,
        ),
        _prop(
            "cliff",
            44,
            # A rock outcrop, built as overlapping masses with a broken silhouette.
            #
            # Two earlier versions failed in instructive ways. The first dithered a
            # full-width rectangle from shade 2 to shade 0 and drew fissures as thin dark
            # lines: at this size per-pixel contrast destroys form, and it read as
            # television static. The second replaced the texture with clean planes — a
            # bright horizontal cap over a dark face with two vertical fissures — and read
            # as a radiator, because a rectangle with a bright bar on top and dark bars down
            # it is a radiator, whatever the ramp is called.
            #
            # What both were missing is an irregular outline. Rock is recognisable by its
            # silhouette long before its shading, so the mass is grown from wobbled blobs
            # and only the skirt where it meets the ground is straight.
            # The base sits at shade 3 rather than 1. At 1 the gaps between the lit facets
            # were nearly black, and the result read as pale rocks floating in tar instead
            # of as one body of stone with planes turned different ways.
            {"op": "blob", "ramp": "dark_stone", "seed": 50, "x": 9, "y": 29, "radius": 10.5, "wobble": 0.30, "level": 3, "depth": 244, "dome": False},
            {"op": "blob", "ramp": "dark_stone", "seed": 51, "x": 23, "y": 27, "radius": 11.5, "wobble": 0.28, "level": 3, "depth": 246, "dome": False},
            {"op": "blob", "ramp": "dark_stone", "seed": 52, "x": 16, "y": 37, "radius": 12.5, "wobble": 0.22, "level": 2, "depth": 242, "dome": False},
            {"op": "fill", "ramp": "dark_stone", "level": 2, "depth": 240, "rect": [2, 36, 30, 44]},
            # Facets. Each is a plane turned a different way, so their shared edges are the
            # lines that describe the form — no explicit outlines needed on the interior.
            {"op": "blob", "ramp": "stone", "seed": 53, "x": 11, "y": 25, "radius": 7.5, "wobble": 0.26, "level": 3, "depth": 250, "dome": False},
            {"op": "blob", "ramp": "stone", "seed": 54, "x": 23, "y": 23, "radius": 6.0, "wobble": 0.24, "level": 2, "depth": 248, "dome": False},
            {"op": "blob", "ramp": "stone", "seed": 55, "x": 7, "y": 37, "radius": 5.5, "wobble": 0.28, "level": 2, "depth": 234, "dome": False},
            {"op": "blob", "ramp": "stone", "seed": 56, "x": 25, "y": 38, "radius": 4.5, "wobble": 0.26, "level": 1, "depth": 232, "dome": False},
            # The topmost lit edge, where the sun clips the highest facet.
            {"op": "blob", "ramp": "stone", "seed": 57, "x": 12, "y": 20, "radius": 4.0, "wobble": 0.20, "level": 4, "depth": 254, "dome": False},
            # One crack, forked, running with the form rather than across it. A single
            # asymmetric line reads as geology; two parallel ones read as machinery.
            {"op": "line", "ramp": "dark_stone", "x0": 17, "y0": 22, "x1": 14, "y1": 38, "level": 0, "thickness": 1, "depth": 190},
            {"op": "line", "ramp": "dark_stone", "x0": 15, "y0": 31, "x1": 22, "y1": 39, "level": 0, "thickness": 1, "depth": 190},
            # Scree in shadow where the face meets the ground, then the silhouette edge.
            {"op": "fill", "ramp": "dark_stone", "level": 1, "depth": 238, "rect": [2, 42, 30, 44]},
            {"op": "outline", "ramp": "shadow", "level": 0, "alpha": 235},
            anchor_y=0,
        ),
        _prop(
            "cactus",
            40,
            {"op": "column", "ramp": "leaf", "rect": [13, 12, 20, 40], "level": 2, "depth": 190},
            {"op": "column", "ramp": "leaf", "rect": [6, 20, 11, 30], "level": 1, "depth": 150},
            {"op": "column", "ramp": "leaf", "rect": [22, 17, 27, 28], "level": 1, "depth": 150},
            {"op": "scatter", "ramp": "snow", "seed": 45, "density": 0.05, "level": 4},
            {"op": "outline", "ramp": "shadow", "level": 0, "alpha": 220},
            {"op": "contact_shadow", "rows": 2, "amount": 0.30},
            anchor_y=4,
        ),
        _prop(
            "wall_wood",
            44,
            {"op": "fill", "ramp": "plank", "level": 2, "depth": 240, "rect": [1, 12, 31, 44]},
            *_wall_boards(),
            {"op": "outline", "ramp": "shadow", "level": 0, "alpha": 235},
            {"op": "contact_shadow", "rows": 2, "amount": 0.30},
            anchor_y=0,
        ),
        _prop(
            "wall_stone",
            44,
            {"op": "fill", "ramp": "stone", "level": 2, "depth": 250, "rect": [0, 12, 32, 44]},
            *_wall_bricks(),
            {"op": "outline", "ramp": "shadow", "level": 0, "alpha": 235},
            {"op": "contact_shadow", "rows": 2, "amount": 0.30},
            anchor_y=0,
        ),
        _prop(
            "fence",
            28,
            {"op": "column", "ramp": "wood", "rect": [4, 10, 8, 28], "depth": 160},
            {"op": "column", "ramp": "wood", "rect": [24, 10, 28, 28], "depth": 160},
            {"op": "fill", "ramp": "wood", "level": 3, "depth": 130, "rect": [0, 14, 32, 17]},
            {"op": "fill", "ramp": "wood", "level": 1, "depth": 130, "rect": [0, 21, 32, 24]},
            {"op": "outline", "ramp": "shadow", "level": 0, "alpha": 220},
            anchor_y=0,
        ),
        # Hub dressing. Not terrain, placed by the location authoring tool, which is
        # what makes a hub feel built rather than generated.
        _prop(
            "lantern",
            46,
            # A cage lamp on a post. Built from rectangles rather than blobs, because a
            # lantern is a made object and its straight edges are half of what identifies
            # it — the first version drew three concentric wobbled circles on a stick and
            # read as a hand mirror, since a bright ring around a bright centre is a lens.
            #
            # Post first, then the housing over it: cap, glass, base, and two uprights.
            {"op": "column", "ramp": "metal", "rect": [14, 20, 18, 46], "level": 1, "depth": 170},
            # Glass, brightest at the flame and falling off to the frame. The dither is
            # what sells it as lit glass rather than as a painted panel.
            {"op": "fill", "ramp": "gold", "level": 1, "depth": 200, "rect": [10, 8, 23, 20]},
            {"op": "dither", "ramp": "gold", "from": 3, "to": 1, "rect": [10, 8, 23, 20]},
            {"op": "blob", "ramp": "ember", "seed": 47, "x": 16, "y": 15, "radius": 3.0, "wobble": 0.30, "level": 4, "depth": 205},
            # Frame. Dark metal against the glow, so the cage reads even at a distance.
            {"op": "fill", "ramp": "metal", "level": 0, "depth": 208, "rect": [10, 8, 12, 20]},
            {"op": "fill", "ramp": "metal", "level": 0, "depth": 208, "rect": [21, 8, 23, 20]},
            # Cap and base, each a pixel wider than the glass so they overhang it.
            {"op": "fill", "ramp": "metal", "level": 2, "depth": 214, "rect": [8, 5, 25, 9]},
            {"op": "fill", "ramp": "metal", "level": 3, "depth": 214, "rect": [10, 5, 23, 7]},
            {"op": "fill", "ramp": "metal", "level": 1, "depth": 212, "rect": [9, 19, 24, 22]},
            # The finial: what tells you which way is up.
            {"op": "fill", "ramp": "metal", "level": 2, "depth": 216, "rect": [15, 2, 18, 6]},
            {"op": "outline", "ramp": "shadow", "level": 0, "alpha": 215},
            {"op": "bob", "amplitude": 1.0},
            frames=4,
            anchor_y=2,
        ),
        _prop(
            "banner",
            48,
            {"op": "column", "ramp": "wood", "rect": [15, 6, 18, 48], "level": 1, "depth": 160},
            {"op": "fill", "ramp": "cloth", "level": 2, "depth": 120, "rect": [8, 10, 25, 34]},
            {"op": "dither", "ramp": "cloth", "from": 3, "to": 1, "rect": [8, 10, 25, 34]},
            {"op": "outline", "ramp": "shadow", "level": 0, "alpha": 210},
            {"op": "sway", "pivotRow": 34, "amplitude": 1.4},
            frames=4,
            anchor_y=2,
        ),
        _prop(
            "crate",
            26,
            # A box, not a plank: the lid plane on top, then the front face, then a
            # frame and a diagonal brace. The lid is what makes it a solid object —
            # without a second plane at a different value it is a rectangle, which is
            # what the first version was.
            {"op": "fill", "ramp": "plank", "level": 2, "depth": 190, "rect": [4, 10, 28, 26]},
            {"op": "fill", "ramp": "plank", "level": 3, "depth": 200, "rect": [4, 7, 28, 11]},
            {"op": "fill", "ramp": "plank", "level": 4, "depth": 202, "rect": [6, 7, 26, 9]},
            # Frame boards, one shade down, and a brace across the front. Corner joins
            # are what say "built" rather than "carved".
            {"op": "fill", "ramp": "wood", "level": 1, "depth": 194, "rect": [4, 11, 28, 13]},
            {"op": "fill", "ramp": "wood", "level": 1, "depth": 194, "rect": [4, 23, 28, 26]},
            {"op": "fill", "ramp": "wood", "level": 1, "depth": 194, "rect": [4, 11, 7, 26]},
            {"op": "fill", "ramp": "wood", "level": 1, "depth": 194, "rect": [25, 11, 28, 26]},
            {"op": "line", "ramp": "wood", "x0": 7, "y0": 23, "x1": 25, "y1": 13, "level": 0, "thickness": 2, "depth": 192},
            {"op": "outline", "ramp": "shadow", "level": 0, "alpha": 230},
            {"op": "contact_shadow", "rows": 2, "amount": 0.32},
            anchor_y=0,
        ),
        _prop(
            "campfire",
            24,
            # Stone ring, then logs, then flame. Flame last so the erosion pass only
            # touches the fire: the stones and logs are below `aboveRow` and stay put,
            # which is what they should do.
            {"op": "blob", "ramp": "stone", "seed": 53, "x": 16, "y": 20, "radius": 9.0, "wobble": 0.22, "level": 1, "depth": 50},
            {"op": "blob", "ramp": "dark_stone", "seed": 54, "x": 16, "y": 20, "radius": 6.0, "wobble": 0.20, "level": 0, "depth": 30},
            {"op": "line", "ramp": "wood", "x0": 10, "y0": 21, "x1": 22, "y1": 16, "level": 1, "thickness": 2, "depth": 70},
            {"op": "line", "ramp": "wood", "x0": 22, "y0": 21, "x1": 10, "y1": 16, "level": 2, "thickness": 2, "depth": 70},
            {"op": "blob", "ramp": "ember", "seed": 55, "x": 16, "y": 14, "radius": 4.4, "wobble": 0.40, "level": 2, "depth": 110},
            {"op": "blob", "ramp": "ember", "seed": 56, "x": 16, "y": 11, "radius": 2.8, "wobble": 0.50, "level": 4, "depth": 120},
            # A flame flickers rather than bending. `sway` shears with a squared falloff
            # that keeps a stem's base planted, which is right for grass and wrong here
            # twice: fire is not rigid, and at this pivot the falloff left the flame rows
            # shifting by zero, so all four frames baked identically.
            {"op": "flicker", "aboveRow": 15, "amount": 0.34},
            frames=4,
            anchor_y=2,
        ),
    )
}


# --- tile bindings ----------------------------------------------------------
#
# Which recipes render which tile. A tile always has ground; a prop is optional and
# drawn on the layer above, anchored to the bottom of its cell.

TILE_GROUND: dict[int, str] = {
    Tile.BARE_GROUND: "bare_ground",
    Tile.GRASS: "grass",
    Tile.TALL_GRASS: "grass",
    Tile.BUSH: "grass",
    Tile.SAPLING: "grass",
    Tile.SAND: "sand",
    Tile.GRAVEL: "gravel",
    Tile.DIRT_ROAD: "dirt_road",
    Tile.COBBLE_ROAD: "cobble_road",
    Tile.FLOOR_WOOD: "floor_wood",
    Tile.FLOOR_STONE: "floor_stone",
    Tile.SNOW: "snow",
    Tile.ASH: "ash",
    Tile.WATER: "water",
    Tile.DEEP_WATER: "deep_water",
    Tile.TREE: "grass",
    Tile.DEAD_TREE: "bare_ground",
    Tile.ROCK: "gravel",
    Tile.CLIFF: "gravel",
    Tile.WALL_WOOD: "bare_ground",
    Tile.WALL_STONE: "bare_ground",
    Tile.FENCE: "grass",
    Tile.CACTUS: "sand",
}

TILE_PROP: dict[int, str] = {
    Tile.TALL_GRASS: "tall_grass",
    Tile.BUSH: "bush",
    Tile.SAPLING: "sapling",
    Tile.TREE: "tree",
    Tile.DEAD_TREE: "dead_tree",
    Tile.ROCK: "rock",
    Tile.CLIFF: "cliff",
    Tile.WALL_WOOD: "wall_wood",
    Tile.WALL_STONE: "wall_stone",
    Tile.FENCE: "fence",
    Tile.CACTUS: "cactus",
}

# Which tiles animate their ground, and at how many frames per second. Only water: still
# water in a scene where the grass moves reads as a painted floor, and everything else that
# animates does so as a prop on the layer above.
TILE_ANIMATION: dict[int, int] = {
    Tile.WATER: 6,
    Tile.DEEP_WATER: 4,
}

# What an unmapped tile draws. A visibly wrong flat patch is much easier to diagnose than a
# hole, and much safer than raising in the renderer.
FALLBACK_GROUND = "bare_ground"

# Props with no tile of their own, placed by hand in the location editor.
DECOR_RECIPES = ("lantern", "banner", "crate", "campfire")

ALL_RECIPES: dict[str, Recipe] = {**GROUND_RECIPES, **PROP_RECIPES}


def catalogue() -> dict[str, Any]:
    """The whole recipe library as JSON, for the editor and the client bake."""
    return {
        "tilePx": TILE_PX,
        "recipes": [recipe.to_json() for recipe in ALL_RECIPES.values()],
        "tileGround": {str(int(tile)): key for tile, key in TILE_GROUND.items()},
        "tileProp": {str(int(tile)): key for tile, key in TILE_PROP.items()},
        "animated": {str(int(tile)): fps for tile, fps in TILE_ANIMATION.items()},
        "fallbackGround": FALLBACK_GROUND,
        "decor": list(DECOR_RECIPES),
        # The ramps the editor offers in its dropdowns, with their shades, so a colour picker
        # can show what it is picking. Served rather than duplicated in TypeScript: the palette
        # is the one table every recipe depends on, and an editor listing a ramp that does not
        # exist produces brown tiles with no explanation.
        "ramps": {
            name: ["#%02x%02x%02x" % ramp.shade(level) for level in range(palette.RAMP_STEPS)]
            for name, ramp in sorted(palette.RAMPS.items())
        },
        "rampSteps": palette.RAMP_STEPS,
    }
