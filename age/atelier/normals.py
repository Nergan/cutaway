"""Height to normal map, and the light rig that consumes it.

TDD 14.4 asks for 2D dynamic lighting via normal mapping. Hand-authoring a normal
map per sprite is not something an author can reasonably do, so the Atelier authors
*height* and derives normals from it. That reduces the artist's job to "how far does
this stick out", which is a question about a shape rather than about a vector field.

The derivation is a Sobel gradient. The result is packed the way every 2D engine
expects it: ``x`` in red, ``y`` in green, ``z`` in blue, each mapped from
``[-1, 1]`` to ``[0, 255]``, with a flat surface at ``(128, 128, 255)``.

The one decision worth naming is the sign of green. This uses the OpenGL
convention, ``+y`` pointing up the screen, because that is what the PixiJS shader
in ``frontend/src/render/lighting.ts`` samples with. Getting it backwards produces
lighting that looks almost right and is inverted, which is much harder to spot than
lighting that is obviously broken, so it is asserted by a test.
"""

from __future__ import annotations

import math

from .canvas import Canvas

# How much a one-step height difference tilts the surface. Higher values exaggerate
# relief; 2.4 was chosen because it makes a 32 px tile's cobbles visible under a
# moving light without making flat ground look like corrugated iron.
DEFAULT_STRENGTH = 2.4

FLAT_NORMAL = (128, 128, 255, 255)


def to_normal_map(
    canvas: Canvas, *, strength: float = DEFAULT_STRENGTH, wrap: bool = False
) -> bytes:
    """Differentiate the depth channel into an RGBA normal map.

    ``wrap`` samples across the edges instead of clamping, which is required for a
    seamless ground tile: clamping leaves a one-pixel ridge where the tile repeats.
    Transparent pixels get a flat normal, so an unlit background does not pick up
    the relief of whatever was next to it.
    """
    width, height = canvas.width, canvas.height
    output = bytearray(width * height * 4)

    for y in range(height):
        for x in range(width):
            index = y * width + x
            offset = index * 4

            if canvas.colour[offset + 3] < 128:
                output[offset : offset + 4] = bytes(FLAT_NORMAL)
                continue

            # Sobel over the 3x3 neighbourhood. Sobel rather than a central
            # difference because pixel art is full of one-pixel steps, and a
            # two-tap derivative turns every one of them into a hard crease.
            top_left = _sample(canvas, x - 1, y - 1, wrap)
            top = _sample(canvas, x, y - 1, wrap)
            top_right = _sample(canvas, x + 1, y - 1, wrap)
            left = _sample(canvas, x - 1, y, wrap)
            right = _sample(canvas, x + 1, y, wrap)
            bottom_left = _sample(canvas, x - 1, y + 1, wrap)
            bottom = _sample(canvas, x, y + 1, wrap)
            bottom_right = _sample(canvas, x + 1, y + 1, wrap)

            gradient_x = (top_right + 2 * right + bottom_right) - (
                top_left + 2 * left + bottom_left
            )
            # Screen y grows downward while world y grows up, so this is inverted
            # relative to the raster order on purpose.
            gradient_y = (top_left + 2 * top + top_right) - (
                bottom_left + 2 * bottom + bottom_right
            )

            nx = -gradient_x / 1020.0 * strength
            ny = -gradient_y / 1020.0 * strength
            nz = 1.0

            length = math.sqrt(nx * nx + ny * ny + nz * nz)
            output[offset] = _pack(nx / length)
            output[offset + 1] = _pack(ny / length)
            output[offset + 2] = _pack(nz / length)
            output[offset + 3] = 255

    return bytes(output)


def _sample(canvas: Canvas, x: int, y: int, wrap: bool) -> int:
    """Read the depth channel, wrapping or clamping at the edges."""
    if wrap:
        x %= canvas.width
        y %= canvas.height
    else:
        x = 0 if x < 0 else (canvas.width - 1 if x >= canvas.width else x)
        y = 0 if y < 0 else (canvas.height - 1 if y >= canvas.height else y)
    return canvas.depth[y * canvas.width + x]


def _pack(component: float) -> int:
    """Map ``[-1, 1]`` onto a byte."""
    value = round((component * 0.5 + 0.5) * 255.0)
    return 0 if value < 0 else (255 if value > 255 else value)


def unpack(normal_map: bytes, width: int, x: int, y: int) -> tuple[float, float, float]:
    """Read one normal back as a unit vector. For tests and for the editor's probe."""
    offset = (y * width + x) * 4
    return (
        normal_map[offset] / 127.5 - 1.0,
        normal_map[offset + 1] / 127.5 - 1.0,
        normal_map[offset + 2] / 127.5 - 1.0,
    )


def lambert(
    normal: tuple[float, float, float], light_direction: tuple[float, float, float]
) -> float:
    """Diffuse response for one normal and one light, clamped at zero.

    The reference implementation of what the GLSL shader does per pixel. Having it
    in Python is what lets the lighting be unit-tested at all: a test can assert
    that a wall lit from the left is bright on its left face, which is precisely the
    bug an inverted green channel causes.
    """
    dot = (
        normal[0] * light_direction[0]
        + normal[1] * light_direction[1]
        + normal[2] * light_direction[2]
    )
    return max(0.0, dot)
