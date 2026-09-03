"""Interest management: decide who each player is told about.

A brute-force scan is deliberate. The room caps at fifty players, so the worst
case is 2500 squared-distance comparisons per tick; a spatial hash would add
bucket maintenance that costs more than it saves at this size. The function
signature is the seam to replace when rooms grow past a few hundred players.
"""

from __future__ import annotations

from typing import Iterable

from ..domain.constants import FULL_DETAIL_RADIUS_M, SIMPLIFIED_RADIUS_M
from ..domain.player import PlayerState

MAX_SNAPSHOT_ENTRIES = 40
"""Hard cap so one crowded corner cannot inflate every snapshot in the room."""

_FULL_SQ = FULL_DETAIL_RADIUS_M * FULL_DETAIL_RADIUS_M
_SIMPLIFIED_SQ = SIMPLIFIED_RADIUS_M * SIMPLIFIED_RADIUS_M


def visible_players(
    viewer: PlayerState, everyone: Iterable[PlayerState]
) -> list[tuple[PlayerState, bool]]:
    """Return ``(player, simplified)`` pairs sorted nearest first."""
    scored: list[tuple[float, PlayerState, bool]] = []
    for other in everyone:
        if other.id == viewer.id:
            continue
        distance_sq = viewer.distance_squared_to(other)
        if distance_sq > _SIMPLIFIED_SQ:
            continue
        scored.append((distance_sq, other, distance_sq > _FULL_SQ))
    scored.sort(key=lambda item: item[0])
    return [(player, simplified) for _, player, simplified in scored[:MAX_SNAPSHOT_ENTRIES]]


def within_radius(
    origin: PlayerState, everyone: Iterable[PlayerState], radius: float
) -> list[PlayerState]:
    """Players inside ``radius`` metres of ``origin``, including ``origin``."""
    limit = radius * radius
    return [
        other
        for other in everyone
        if other.id == origin.id or origin.distance_squared_to(other) <= limit
    ]
