"""Rounding that means the same thing in Python and in JavaScript.

Python's built-in :func:`round` rounds halves to even, while JavaScript's
``Math.round`` rounds halves towards positive infinity. Every quantised field
in the wire and tile formats is produced by one language and consumed by the
other, so a value landing exactly on a half would otherwise encode to two
different bytes depending on who did the encoding.

``floor(value + 0.5)`` is exactly ``Math.round``, including its treatment of
negative halves, which is why the codecs call this instead of ``round``.
"""

from __future__ import annotations

import math


def round_half_up(value: float) -> int:
    """Round to the nearest integer, halves towards positive infinity."""
    return math.floor(value + 0.5)
