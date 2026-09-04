"""Deterministic gradient noise, reproducible bit-for-bit in the browser.

GDD 16.8 asks for OpenSimplex-family noise. This implements gradient noise with
a quintic fade and domain rotation, which is the practical equivalent for 2D
fields and, more importantly, is exactly reproducible in JavaScript.

That last part is the constraint that drove the design. The client generates its
own copy of every chunk from the seed, so terrain costs nothing on the wire; that
only works if Python and JavaScript agree on every bit. So this module uses:

* only ``+``, ``-``, ``*``, ``/`` and ``math.floor`` on floats, all of which are
  IEEE 754 operations with identical results in both languages,
* integer hashing masked to 64 bits, which the TypeScript mirror does in BigInt,
* gradient constants written as decimal literals that parse to the same double.

No ``sin``, ``cos``, ``exp`` or ``pow`` anywhere: those come from libm and are not
guaranteed to agree across platforms, let alone across languages.
"""

from __future__ import annotations

import math
from functools import lru_cache

from ..domain.hashing import combine, unit_float

# Sixteen unit-ish gradients. Using a power-of-two count means the selection is a
# mask rather than a modulo, and the diagonals are written as the literal decimal
# expansion of the relevant irrational so both languages parse the same double.
_D = 0.7071067811865476  # sqrt(2)/2
_A = 0.9238795325112867  # cos(22.5 degrees)
_B = 0.3826834323650898  # sin(22.5 degrees)

_GRADIENTS: tuple[tuple[float, float], ...] = (
    (1.0, 0.0), (_A, _B), (_D, _D), (_B, _A),
    (0.0, 1.0), (-_B, _A), (-_D, _D), (-_A, _B),
    (-1.0, 0.0), (-_A, -_B), (-_D, -_D), (-_B, -_A),
    (0.0, -1.0), (_B, -_A), (_D, -_D), (_A, -_B),
)
_GRADIENT_MASK = 15

# Domain rotation. Sampling an axis-aligned lattice leaves visible horizontal and
# vertical streaks; rotating the input by an angle with no rational relationship
# to the grid removes them without costing a second noise call. These are the
# decimal expansions of cos/sin of roughly 31.7 degrees.
_ROT_COS = 0.8507035
_ROT_SIN = 0.5257311


def _fade(t: float) -> float:
    """Quintic ease, ``6t^5 - 15t^4 + 10t^3``.

    Has zero first and second derivatives at both ends, so adjacent lattice cells
    join without the visible creasing a cubic fade leaves behind.
    """
    return t * t * t * (t * (t * 6.0 - 15.0) + 10.0)


@lru_cache(maxsize=1 << 16)
def _gradient_at(seed: int, x: int, y: int) -> tuple[float, float]:
    """The gradient vector assigned to one lattice corner.

    Memoised because the caller is a sampling loop and lattice corners are shared:
    the climate fields have wavelengths of over a hundred tiles, so an entire chunk
    of samples sits inside a handful of cells and asks for the same four corners
    thousands of times. The cache is pure memoisation of a pure function, so it
    changes only the cost, never the result — which matters, because the browser
    mirror has to agree bit for bit.
    """
    return _GRADIENTS[combine(seed, x, y) & _GRADIENT_MASK]


def gradient_noise(seed: int, x: float, y: float) -> float:
    """Single-octave gradient noise in roughly ``[-1, 1]``.

    Values slightly exceed the nominal range at lattice diagonals, which is normal
    for gradient noise and is why callers normalise through :func:`fractal` rather
    than trusting the bound.
    """
    rx = x * _ROT_COS - y * _ROT_SIN
    ry = x * _ROT_SIN + y * _ROT_COS

    x0 = math.floor(rx)
    y0 = math.floor(ry)
    fx = rx - x0
    fy = ry - y0

    g00 = _gradient_at(seed, x0, y0)
    g10 = _gradient_at(seed, x0 + 1, y0)
    g01 = _gradient_at(seed, x0, y0 + 1)
    g11 = _gradient_at(seed, x0 + 1, y0 + 1)

    n00 = g00[0] * fx + g00[1] * fy
    n10 = g10[0] * (fx - 1.0) + g10[1] * fy
    n01 = g01[0] * fx + g01[1] * (fy - 1.0)
    n11 = g11[0] * (fx - 1.0) + g11[1] * (fy - 1.0)

    u = _fade(fx)
    v = _fade(fy)

    bottom = n00 + (n10 - n00) * u
    top = n01 + (n11 - n01) * u
    return bottom + (top - bottom) * v


def fractal(
    seed: int,
    x: float,
    y: float,
    octaves: int = 4,
    frequency: float = 1.0,
    persistence: float = 0.5,
    lacunarity: float = 2.0,
) -> float:
    """Fractal summation, normalised to ``[0, 1]``.

    Defaults match GDD 16.8: four octaves, persistence 0.5, lacunarity 2.0. Each
    octave gets a different seed rather than a different offset, so octaves are
    genuinely independent instead of being correlated copies of one field.
    """
    total = 0.0
    amplitude = 1.0
    total_amplitude = 0.0
    current = frequency

    for octave in range(octaves):
        total += gradient_noise(seed + octave * 0x9E37, x * current, y * current) * amplitude
        total_amplitude += amplitude
        amplitude *= persistence
        current *= lacunarity

    if total_amplitude == 0.0:
        return 0.5
    normalised = (total / total_amplitude) * 0.5 + 0.5
    # Clamp because gradient noise overshoots slightly at the diagonals.
    if normalised < 0.0:
        return 0.0
    if normalised > 1.0:
        return 1.0
    return normalised


def ridged(seed: int, x: float, y: float, octaves: int = 3, frequency: float = 1.0) -> float:
    """Ridged noise in ``[0, 1]``, for cliff lines and river channels.

    Folding the absolute value produces creases where the underlying field crosses
    zero, which reads as a ridge or a valley depending on which way it is used.
    """
    total = 0.0
    amplitude = 1.0
    total_amplitude = 0.0
    current = frequency

    for octave in range(octaves):
        value = gradient_noise(seed + octave * 0x85EB, x * current, y * current)
        folded = 1.0 - (value if value >= 0.0 else -value)
        total += folded * folded * amplitude
        total_amplitude += amplitude
        amplitude *= 0.5
        current *= 2.0

    if total_amplitude == 0.0:
        return 0.0
    result = total / total_amplitude
    if result < 0.0:
        return 0.0
    if result > 1.0:
        return 1.0
    return result


def scatter_value(seed: int, tile_x: int, tile_y: int, salt: int = 0) -> float:
    """A stable per-tile random number in ``[0, 1)``.

    Used for scatter decisions, which want no spatial correlation at all: a tree
    should not know that its neighbour is a tree.
    """
    return unit_float(combine(seed, tile_x, tile_y, salt))
