"""The Atelier's drawing surface and its operation set.

A canvas carries three channels, and the third is the reason this is not just a
paint program:

``colour``
    RGBA, what gets drawn.
``depth``
    0-255 per pixel, how far the surface stands out of the ground. Nothing renders
    it directly; :mod:`age.atelier.normals` differentiates it into a normal map,
    which is what lets a torch light a wall from the side (TDD 14.4). Authoring
    height alongside colour is much easier than authoring normals, and it is the
    only way a *generated* sprite can get plausible normals at all.
``material``
    An index used by the autotiler, and by footstep sounds later. Cheap to carry
    and impossible to reconstruct afterwards.

Operations are deterministic in the seed they are given, so two bakes of one recipe
are byte-identical. That is what lets the client bake its own atlas at boot and get
the same art the server exports.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .palette import RGB, RGBA, ramp as lookup_ramp

# Ordered Bayer 4x4, values 0-15. Ordered rather than error-diffused: pixel art
# needs a stable tileable pattern, and Floyd-Steinberg produces speckle that
# crawls when the sprite moves.
BAYER_4X4 = (
    (0, 8, 2, 10),
    (12, 4, 14, 6),
    (3, 11, 1, 9),
    (15, 7, 13, 5),
)


def rand(seed: int, *values: int) -> float:
    """A reproducible float in ``[0, 1)``. Mirrors ``domain.hashing``."""
    state = seed & 0xFFFFFFFFFFFFFFFF
    for value in values:
        state = (state * 0x9E3779B97F4A7C15 + (value & 0xFFFFFFFFFFFFFFFF)) & 0xFFFFFFFFFFFFFFFF
    state ^= state >> 30
    state = (state * 0xBF58476D1CE4E5B9) & 0xFFFFFFFFFFFFFFFF
    state ^= state >> 27
    state = (state * 0x94D049BB133111EB) & 0xFFFFFFFFFFFFFFFF
    state ^= state >> 31
    return (state >> 11) / 9007199254740992.0


@dataclass(slots=True)
class Canvas:
    """A fixed-size RGBA + depth + material raster."""

    width: int
    height: int
    colour: bytearray = field(default_factory=bytearray)
    depth: bytearray = field(default_factory=bytearray)
    material: bytearray = field(default_factory=bytearray)

    def __post_init__(self) -> None:
        count = self.width * self.height
        if not self.colour:
            self.colour = bytearray(count * 4)
        if not self.depth:
            self.depth = bytearray(count)
        if not self.material:
            self.material = bytearray(count)

    def inside(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height

    def get(self, x: int, y: int) -> RGBA:
        offset = (y * self.width + x) * 4
        return (
            self.colour[offset],
            self.colour[offset + 1],
            self.colour[offset + 2],
            self.colour[offset + 3],
        )

    def alpha_at(self, x: int, y: int) -> int:
        if not self.inside(x, y):
            return 0
        return self.colour[(y * self.width + x) * 4 + 3]

    def put(
        self,
        x: int,
        y: int,
        colour: RGB,
        *,
        alpha: int = 255,
        depth: int | None = None,
        material: int | None = None,
    ) -> None:
        """Write one pixel, compositing onto whatever is there.

        Depth and material are written only for pixels at least half opaque: a soft
        edge is not a surface, and treating it as one gives every sprite a halo of
        bogus normals.
        """
        if not self.inside(x, y) or alpha <= 0:
            return

        index = y * self.width + x
        offset = index * 4

        if alpha >= 255:
            self.colour[offset : offset + 3] = bytes(colour)
            self.colour[offset + 3] = 255
        else:
            existing = self.colour[offset + 3]
            out_alpha = alpha + existing * (255 - alpha) // 255
            if out_alpha == 0:
                return
            for channel in range(3):
                source = colour[channel] * alpha
                behind = self.colour[offset + channel] * existing * (255 - alpha) // 255
                self.colour[offset + channel] = (source + behind) // out_alpha
            self.colour[offset + 3] = out_alpha

        if alpha >= 128:
            if depth is not None:
                self.depth[index] = 0 if depth < 0 else (255 if depth > 255 else depth)
            if material is not None:
                self.material[index] = material & 0xFF

    def clear(self, x: int, y: int) -> None:
        """Erase one pixel back to transparent, depth and material included.

        Rounding a corner in pixel art means taking pixels away, and :meth:`put`
        cannot do it: an alpha of zero composites to nothing. Every domed skull and
        bevelled edge in here goes through this.
        """
        if not self.inside(x, y):
            return
        index = y * self.width + x
        offset = index * 4
        self.colour[offset : offset + 4] = b"\x00\x00\x00\x00"
        self.depth[index] = 0
        self.material[index] = 0

    def copy(self) -> "Canvas":
        return Canvas(
            self.width,
            self.height,
            bytearray(self.colour),
            bytearray(self.depth),
            bytearray(self.material),
        )

    def blit(self, other: "Canvas", at_x: int = 0, at_y: int = 0) -> None:
        """Composite another canvas on top, carrying depth and material across."""
        for y in range(other.height):
            for x in range(other.width):
                alpha = other.alpha_at(x, y)
                if not alpha:
                    continue
                index = y * other.width + x
                self.put(
                    at_x + x,
                    at_y + y,
                    other.get(x, y)[:3],
                    alpha=alpha,
                    depth=other.depth[index],
                    material=other.material[index],
                )


# --- operations -------------------------------------------------------------
#
# Grouped the way a pixel artist works: cover the surface, build the form, finish
# the edge. Recipes list them in that order.


def fill(
    canvas: Canvas,
    ramp_name: str,
    *,
    level: int = 2,
    depth: int = 0,
    material: int = 0,
    rect: tuple[int, int, int, int] | None = None,
) -> None:
    """Flat fill, optionally bounded to a rectangle."""
    colour = lookup_ramp(ramp_name).shade(level)
    x0, y0, x1, y1 = rect or (0, 0, canvas.width, canvas.height)
    for y in range(max(0, y0), min(canvas.height, y1)):
        for x in range(max(0, x0), min(canvas.width, x1)):
            canvas.put(x, y, colour, depth=depth, material=material)


def scatter(
    canvas: Canvas,
    ramp_name: str,
    *,
    seed: int,
    density: float,
    level: int = 1,
    depth: int | None = None,
    material: int | None = None,
    only_on_opaque: bool = True,
) -> None:
    """Sprinkle single pixels. The workhorse for ground texture.

    ``only_on_opaque`` keeps the speckle inside what is already drawn, so
    scattering lichen over a rock does not spray pixels into the surround.
    """
    colour = lookup_ramp(ramp_name).shade(level)
    for y in range(canvas.height):
        for x in range(canvas.width):
            if only_on_opaque and not canvas.alpha_at(x, y):
                continue
            if rand(seed, x, y) < density:
                canvas.put(x, y, colour, depth=depth, material=material)


def dither(
    canvas: Canvas,
    ramp_name: str,
    *,
    from_level: int,
    to_level: int,
    vertical: bool = True,
    rect: tuple[int, int, int, int] | None = None,
    material: int | None = None,
) -> None:
    """Ordered-dither a gradient between two ramp levels.

    The pixel-art substitute for a smooth gradient, which would need more colours
    than the palette has and would stop reading as pixel art.
    """
    palette = lookup_ramp(ramp_name)
    x0, y0, x1, y1 = rect or (0, 0, canvas.width, canvas.height)
    span = ((y1 - y0) if vertical else (x1 - x0)) - 1 or 1

    for y in range(max(0, y0), min(canvas.height, y1)):
        for x in range(max(0, x0), min(canvas.width, x1)):
            progress = ((y - y0) if vertical else (x - x0)) / span
            level = from_level + (to_level - from_level) * progress
            whole = math.floor(level)
            if (level - whole) > BAYER_4X4[y & 3][x & 3] / 16.0:
                whole += 1
            canvas.put(x, y, palette.shade(whole), material=material)


def blob(
    canvas: Canvas,
    ramp_name: str,
    *,
    seed: int,
    centre: tuple[float, float],
    radius: float,
    wobble: float = 0.35,
    level: int = 2,
    depth: int = 160,
    material: int = 0,
    dome: bool = True,
) -> None:
    """An organic lump: a circle with a noisy radius.

    Tree canopies, rocks, bushes. Eight radial control points interpolated smoothly,
    rather than per-pixel noise, which would fray the silhouette instead of shaping
    it. ``dome`` shapes the depth channel into a hemisphere so lighting rounds it,
    which is the difference between a lit boulder and a lit sticker of a boulder.
    """
    cx, cy = centre
    controls = [1.0 + (rand(seed, index) - 0.5) * 2.0 * wobble for index in range(8)]
    palette = lookup_ramp(ramp_name)
    reach = radius * (1.0 + wobble) + 1.0

    for y in range(max(0, int(cy - reach)), min(canvas.height, int(cy + reach) + 1)):
        for x in range(max(0, int(cx - reach)), min(canvas.width, int(cx + reach) + 1)):
            dx = x + 0.5 - cx
            dy = y + 0.5 - cy
            distance = math.hypot(dx, dy)
            if distance > reach:
                continue

            position = ((math.atan2(dy, dx) / math.tau) % 1.0) * 8.0
            low = int(position) % 8
            blend = position - int(position)
            limit = radius * (controls[low] * (1.0 - blend) + controls[(low + 1) % 8] * blend)
            if distance > limit or limit <= 0.0:
                continue

            ratio = distance / limit
            shade = level + (1 if ratio < 0.45 else (-1 if ratio > 0.86 else 0))
            surface = int(depth * math.sqrt(max(0.0, 1.0 - ratio * ratio))) if dome else depth
            canvas.put(x, y, palette.shade(shade), depth=surface, material=material)


def column(
    canvas: Canvas,
    ramp_name: str,
    *,
    rect: tuple[int, int, int, int],
    level: int = 2,
    depth: int = 200,
    material: int = 0,
    lit_from_left: bool = True,
) -> None:
    """A vertical shaft with a lit and a shadowed side: trunks, posts, pillars.

    One pixel of highlight and one of shadow is all the room a four-pixel trunk has,
    and it is exactly what makes it read as round.
    """
    palette = lookup_ramp(ramp_name)
    x0, y0, x1, y1 = rect
    width = max(1, x1 - x0)

    for y in range(max(0, y0), min(canvas.height, y1)):
        for x in range(max(0, x0), min(canvas.width, x1)):
            position = (x - x0) / width
            if lit_from_left:
                shade = level + (1 if position < 0.34 else (-1 if position > 0.72 else 0))
            else:
                shade = level + (1 if position > 0.66 else (-1 if position < 0.28 else 0))
            surface = int(depth * (0.55 + 0.45 * math.sin(math.pi * position)))
            canvas.put(x, y, palette.shade(shade), depth=surface, material=material)


def line(
    canvas: Canvas,
    ramp_name: str,
    *,
    start: tuple[int, int],
    end: tuple[int, int],
    level: int = 2,
    thickness: int = 1,
    depth: int = 120,
    material: int = 0,
) -> None:
    """A Bresenham line. Branches, ropes, fence rails, cracks."""
    colour = lookup_ramp(ramp_name).shade(level)
    x0, y0 = start
    x1, y1 = end
    dx, dy = abs(x1 - x0), abs(y1 - y0)
    step_x = 1 if x0 < x1 else -1
    step_y = 1 if y0 < y1 else -1
    error = dx - dy
    reach = thickness // 2

    while True:
        for oy in range(-reach, reach + 1):
            for ox in range(-reach, reach + 1):
                canvas.put(x0 + ox, y0 + oy, colour, depth=depth, material=material)
        if x0 == x1 and y0 == y1:
            return
        doubled = error * 2
        if doubled > -dy:
            error -= dy
            x0 += step_x
        if doubled < dx:
            error += dx
            y0 += step_y


def outline(
    canvas: Canvas,
    ramp_name: str = "shadow",
    *,
    level: int = 1,
    alpha: int = 235,
    only_bottom: bool = False,
) -> None:
    """Ring the silhouette with a dark edge.

    The most recognisable pixel-art convention there is, and the reason a sprite
    stays legible over busy ground. Collected first and written after, so the new
    edge pixels do not seed further edge pixels.
    """
    colour = lookup_ramp(ramp_name).shade(level)
    neighbours = ((0, -1),) if only_bottom else ((1, 0), (-1, 0), (0, 1), (0, -1))
    additions: list[tuple[int, int]] = []

    for y in range(canvas.height):
        for x in range(canvas.width):
            if canvas.alpha_at(x, y):
                continue
            for ox, oy in neighbours:
                if canvas.alpha_at(x + ox, y + oy) >= 128:
                    additions.append((x, y))
                    break

    for x, y in additions:
        canvas.put(x, y, colour, alpha=alpha, depth=0)


def contact_shadow(canvas: Canvas, *, rows: int = 2, amount: float = 0.35) -> None:
    """Darken the lowest opaque rows: occlusion where a thing meets the ground."""
    edges: list[tuple[int, int, float]] = []

    for y in range(canvas.height):
        for x in range(canvas.width):
            if not canvas.alpha_at(x, y):
                continue
            below = sum(1 for step in range(1, rows + 1) if canvas.alpha_at(x, y + step))
            if below < rows:
                edges.append((x, y, amount * (1.0 - below / (rows + 1))))

    for x, y, strength in edges:
        red, green, blue, alpha = canvas.get(x, y)
        canvas.put(
            x,
            y,
            (
                int(red * (1.0 - strength)),
                int(green * (1.0 - strength)),
                int(blue * (1.0 - strength)),
            ),
            alpha=alpha,
        )


def mirror_horizontal(canvas: Canvas) -> None:
    """Reflect the left half onto the right. Symmetric props and faces."""
    for y in range(canvas.height):
        for x in range(canvas.width // 2):
            source = y * canvas.width + x
            target = y * canvas.width + (canvas.width - 1 - x)
            canvas.colour[target * 4 : target * 4 + 4] = canvas.colour[
                source * 4 : source * 4 + 4
            ]
            canvas.depth[target] = canvas.depth[source]
            canvas.material[target] = canvas.material[source]


def sway(canvas: Canvas, *, pivot_row: int, shift: float) -> Canvas:
    """Shear rows sideways above a pivot, more the further up they are.

    Wind on grass, banners, and hair. Returns a new canvas because shifting in place
    would overwrite pixels still to be read. The shift is squared with height so the
    base stays planted and the tip moves most, which is how a stem actually bends.
    """
    result = Canvas(canvas.width, canvas.height)
    span = max(1, pivot_row)

    for y in range(canvas.height):
        progress = (pivot_row - y) / span if y < pivot_row else 0.0
        row_shift = round(shift * progress * progress)
        for x in range(canvas.width):
            alpha = canvas.alpha_at(x, y)
            if not alpha:
                continue
            index = y * canvas.width + x
            result.put(
                x + row_shift,
                y,
                canvas.get(x, y)[:3],
                alpha=alpha,
                depth=canvas.depth[index],
                material=canvas.material[index],
            )
    return result


def bob(canvas: Canvas, *, offset: int) -> Canvas:
    """Shift the whole canvas vertically. Idle breathing and hover cycles."""
    result = Canvas(canvas.width, canvas.height)
    result.blit(canvas, 0, offset)
    return result


def shift(
    canvas: Canvas,
    *,
    by: int,
    rect: tuple[int, int, int, int] | None = None,
) -> None:
    """Translate part of the canvas sideways as a rigid body.

    The fourth kind of animation, and the one for a thing hanging from a fixed point.
    :func:`sway` shears with a falloff squared from a pivot, so the movement is largest
    furthest from it — correct for a stem rooted in the ground, and backwards for a shop
    sign hanging off a bracket, where the top is what is pinned. The first attempt at the
    sign used sway anyway, with the pivot below the board, and the falloff put the board's
    displacement under half a pixel: all four frames baked identically, which the atelier
    test suite noticed. A board on two chains barely deforms; it translates.

    Pixels shifted out of the rect are dropped rather than wrapped, so the caller must
    leave a margin.
    """
    if by == 0:
        return

    x0, y0, x1, y1 = rect or (0, 0, canvas.width, canvas.height)
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(canvas.width, x1), min(canvas.height, y1)

    # Read the whole region before writing any of it: shifting in place overwrites pixels
    # that have not been copied yet.
    carried: list[tuple[int, int, RGB, int, int, int]] = []
    for y in range(y0, y1):
        for x in range(x0, x1):
            alpha = canvas.alpha_at(x, y)
            if not alpha:
                continue
            index = y * canvas.width + x
            red, green, blue, _ = canvas.get(x, y)
            carried.append(
                (x, y, (red, green, blue), alpha, canvas.depth[index], canvas.material[index])
            )
            canvas.clear(x, y)

    for x, y, colour, alpha, depth, material in carried:
        moved = x + by
        if moved < x0 or moved >= x1:
            continue
        canvas.put(moved, y, colour, alpha=alpha, depth=depth, material=material)


def glow(
    canvas: Canvas,
    *,
    amount: float,
    rect: tuple[int, int, int, int] | None = None,
) -> None:
    """Scale the brightness of what is already drawn, in place.

    The third kind of animation, after :func:`sway` and :func:`flicker`, and the one a lit
    object needs. A lantern hung on a post does not move and its silhouette does not dance:
    what changes frame to frame is how hard the flame is burning. The first version of the
    lantern used :func:`bob`, which shifts the entire canvas — so the post, the cap and the
    bracket all hopped up and down together, as if the lamp were a balloon on a string. That
    was the single most obviously wrong animation in the scene.

    Multiplies rather than adds so a dark frame stays dark and only lit pixels brighten;
    adding a constant washes the shadowed side of the housing out to grey.
    """
    x0, y0, x1, y1 = rect or (0, 0, canvas.width, canvas.height)
    scale = 1.0 + amount

    for y in range(max(0, y0), min(canvas.height, y1)):
        for x in range(max(0, x0), min(canvas.width, x1)):
            alpha = canvas.alpha_at(x, y)
            if not alpha:
                continue
            red, green, blue, _ = canvas.get(x, y)
            index = y * canvas.width + x
            canvas.put(
                x,
                y,
                (
                    min(255, int(red * scale)),
                    min(255, int(green * scale)),
                    min(255, int(blue * scale)),
                ),
                alpha=alpha,
                depth=canvas.depth[index],
                material=canvas.material[index],
            )


def flicker(canvas: Canvas, *, seed: int, above_row: int, amount: float) -> None:
    """Erase a seeded scatter of pixels above a row, so a flame's silhouette dances.

    Fire is the case :func:`sway` cannot cover. Sway shears rows sideways with a squared
    falloff, which keeps a stem's base planted — correct for grass and banners, and wrong
    for flame twice over: a fire does not bend as a rigid body, and the falloff means the
    shift is negligible anywhere except the very top of the canvas, so a short sprite with
    its flame in the middle does not move at all.

    What actually changes between two frames of a fire is its outline. Removing a different
    subset of its edge pixels each frame reproduces that directly, and because the subset
    comes from a hash of the position and the seed, it is deterministic: frame 2 of a
    campfire is the same every time the atlas is baked.

    Only pixels with empty space above them are eligible, so the erosion happens at the
    silhouette and cannot punch holes through the middle of the flame.
    """
    doomed: list[tuple[int, int]] = []

    for y in range(min(above_row, canvas.height)):
        for x in range(canvas.width):
            if not canvas.alpha_at(x, y):
                continue
            # Only erode the outline: a lit pixel with nothing above it is on the edge.
            if y > 0 and canvas.alpha_at(x, y - 1):
                continue
            if rand(seed, x, y) < amount:
                doomed.append((x, y))

    for x, y in doomed:
        canvas.clear(x, y)
