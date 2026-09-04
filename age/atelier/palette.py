"""Palettes and shade ramps.

Pixel art reads as pixel art largely because of colour discipline: a small palette,
and shading that moves along a *ramp* rather than by darkening a colour. Naively
multiplying a colour by 0.6 gives muddy grey shadows; a ramp shifts hue towards
blue and drops saturation less than value, which is what gives hand-made pixel art
its warmth.

Ramps are generated rather than hand-listed so a whole biome can be recoloured from
one base colour, which is the practical difference between an authoring tool and a
spritesheet. The generator is mirrored in ``frontend/src/atelier/palette.ts``, so
the browser bakes the same colours the server does.
"""

from __future__ import annotations

import colorsys
from dataclasses import dataclass

RGB = tuple[int, int, int]
RGBA = tuple[int, int, int, int]

# How far up the shade ladder a ramp reaches. Five steps is the usual pixel-art
# working range: core, two shadows, two highlights.
RAMP_STEPS = 5

# Shadows drift towards blue and highlights towards yellow, in turns of hue. The
# classic hue-shifting rule, and the single biggest difference between generated ramps
# that look flat and ones that look painted.
#
# The magnitudes are small — eight degrees a step, sixteen across the shadow half —
# because the shift is a fixed delta rather than a rotation towards a target, and warm
# hues have no room. Orange sits about twenty degrees from red, so a larger step walks
# skin straight through red into magenta: at 0.055 a tan of bc8a64 shaded to a7463b,
# which on a face reads as an injury. Cool and neutral hues tolerate far more, but the
# constant has to suit the tightest case.
SHADOW_HUE_SHIFT = -0.022
HIGHLIGHT_HUE_SHIFT = 0.018

# How far each step moves lightness, as a multiple of ``spread``. Deliberately not
# linear: the outer steps are compressed so the top of the ramp does not reach white
# and the bottom does not reach black. A linear ladder made every highlight on a
# mid-lightness colour blow out to near-white, which flattens the whole tileset into
# glare, and the pale end is where that shows first.
LIGHTNESS_LADDER = (-2.0, -1.05, 0.0, 0.90, 1.65)


@dataclass(frozen=True, slots=True)
class Ramp:
    """Five shades of one colour, dark to light. Index 2 is the base."""

    shades: tuple[RGB, RGB, RGB, RGB, RGB]

    @property
    def base(self) -> RGB:
        return self.shades[2]

    def shade(self, level: int) -> RGB:
        """Clamped lookup, so a caller may over-shade without checking bounds."""
        if level < 0:
            level = 0
        elif level >= RAMP_STEPS:
            level = RAMP_STEPS - 1
        return self.shades[level]


def make_ramp(base: RGB, *, spread: float = 0.115, saturation_pull: float = 0.09) -> Ramp:
    """Build a hue-shifted ramp around a base colour.

    ``spread`` is how far value moves per step, ``saturation_pull`` how much
    saturation rises into the shadows and falls into the highlights. Shadows gain
    saturation because a dark area in shade is *more* colourful than a lit one, not
    less; getting that backwards is what makes generated ramps look like a
    brightness slider.
    """
    hue, lightness, saturation = colorsys.rgb_to_hls(
        base[0] / 255.0, base[1] / 255.0, base[2] / 255.0
    )

    shades: list[RGB] = []
    for step in range(RAMP_STEPS):
        distance = step - 2  # -2..+2, zero at the base
        if distance < 0:
            shifted_hue = (hue + SHADOW_HUE_SHIFT * abs(distance)) % 1.0
            shifted_saturation = min(1.0, saturation + saturation_pull * abs(distance) * 0.5)
        elif distance > 0:
            shifted_hue = (hue + HIGHLIGHT_HUE_SHIFT * distance) % 1.0
            shifted_saturation = max(0.0, saturation - saturation_pull * distance * 0.5)
        else:
            shifted_hue, shifted_saturation = hue, saturation

        shifted_lightness = _clamp(
            lightness + spread * LIGHTNESS_LADDER[step], 0.04, 0.93
        )
        red, green, blue = colorsys.hls_to_rgb(
            shifted_hue, shifted_lightness, shifted_saturation
        )
        shades.append((round(red * 255), round(green * 255), round(blue * 255)))

    return Ramp(tuple(shades))  # type: ignore[arg-type]


def _clamp(value: float, low: float, high: float) -> float:
    return low if value < low else (high if value > high else value)


# --- the project palette ----------------------------------------------------
#
# Warm earths, desaturated greens, and a cold blue for water and night. Chosen to
# sit with the UI colours from the design reference rather than fight them: the
# game view and the frame around it should look like one artefact.

BASE_COLOURS: dict[str, RGB] = {
    "soil": (104, 78, 56),
    "grass": (98, 130, 66),
    "dry_grass": (154, 148, 82),
    "sand": (196, 174, 122),
    "stone": (118, 118, 128),
    "dark_stone": (78, 78, 90),
    "snow": (222, 228, 236),
    "water": (56, 96, 138),
    "deep_water": (32, 58, 96),
    "wood": (120, 84, 52),
    "leaf": (74, 108, 60),
    "dead_leaf": (140, 106, 58),
    "path": (146, 124, 96),
    "plank": (158, 118, 76),
    "brick": (150, 96, 78),
    "cloth": (168, 84, 74),
    "metal": (150, 156, 168),
    "gold": (206, 168, 84),
    "ember": (214, 118, 62),
    "skin_light": (226, 184, 148),
    "skin_mid": (188, 138, 100),
    "skin_dark": (128, 88, 62),
    "hair_dark": (58, 46, 42),
    "hair_fair": (194, 158, 96),
    "hair_red": (162, 88, 52),
    "shadow": (38, 34, 44),
}

RAMPS: dict[str, Ramp] = {name: make_ramp(colour) for name, colour in BASE_COLOURS.items()}


def ramp(name: str) -> Ramp:
    """Look up a ramp, falling back to soil for an unknown name.

    A missing ramp is an authoring typo, and a brown tile is a far better way to
    surface one than a stack trace inside a bake loop.
    """
    return RAMPS.get(name, RAMPS["soil"])


def with_alpha(colour: RGB, alpha: int) -> RGBA:
    return (colour[0], colour[1], colour[2], alpha)


def tint(colour: RGB, target: RGB, amount: float) -> RGB:
    """Blend towards a target colour. Used for ambient and weather grading."""
    amount = _clamp(amount, 0.0, 1.0)
    return (
        round(colour[0] + (target[0] - colour[0]) * amount),
        round(colour[1] + (target[1] - colour[1]) * amount),
        round(colour[2] + (target[2] - colour[2]) * amount),
    )
