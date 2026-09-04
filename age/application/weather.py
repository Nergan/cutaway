"""Weather selection, driven by the biome under the player.

GDD 16.3 argues for local, biome-dependent weather: a corridor crossing a forest
and a desert should not have one sky. This slice implements the per-edge
simplification named as the fallback in the same section, with the biome chosen at
the corridor's midpoint, because the vertical slice has one corridor and a single
coherent sky is what a visitor actually reads as weather.

The structure is the part that generalises: a weather roll is a pure function of a
biome profile and a hash, so making it per-chunk later is a change of *where* it is
called, not of what it does.
"""

from __future__ import annotations

from ..domain.constants import (
    WEATHER_MAX_DURATION_SECONDS,
    WEATHER_MIN_DURATION_SECONDS,
)
from ..domain.hashing import combine, unit_float
from ..domain.tiles import BIOME_PROFILES, Biome
from .world import World


def choose(world: World) -> tuple[int, float]:
    """Roll the next weather state and how long it lasts.

    Returns ``(weather_id, duration_seconds)``. Deterministic in the world seed and
    the tick, so a replay of the same session sees the same sky.
    """
    biome = _dominant_biome(world)
    profile = BIOME_PROFILES[biome]

    seed = combine(world.world_seed, world.tick_count, 0x57EA)
    roll = unit_float(seed)

    weather = profile.weather[-1][0]
    for candidate, cumulative in profile.weather:
        if roll < cumulative:
            weather = candidate
            break

    span = WEATHER_MAX_DURATION_SECONDS - WEATHER_MIN_DURATION_SECONDS
    duration = WEATHER_MIN_DURATION_SECONDS + unit_float(combine(seed, 1)) * span
    return weather, duration


def _dominant_biome(world: World) -> Biome:
    """The biome that should set the sky.

    Sampled at the middle of the centre lane: the deepest part of the corridor, and
    the part a player is most likely to be looking at when they notice the weather.
    """
    from ..domain.coordinates import ChunkAddress

    middle = world.topology.segments // 2
    address = ChunkAddress.edge(world.edge.edge_id, middle, 0, 0)
    return Biome(world.generator.biome_of(address))


def ambient_for(world: World, biome: Biome) -> tuple[int, int, int]:
    """The biome's ambient tint, for the client's colour grading."""
    return BIOME_PROFILES[biome].ambient_tint
