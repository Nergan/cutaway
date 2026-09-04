"""Tiles, biomes, and the regrowth ladder.

Tile ids are small integers because a chunk is a flat ``bytearray`` of
``CHUNK_TILE_COUNT`` entries on the server and a ``Uint8Array`` on the client.
The renderer never switches on the id directly; it looks the tile up in the
atlas built from the Atelier recipes, so adding a tile is a data change.

Every table here is mirrored in ``frontend/src/domain/tiles.ts``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class Tile(IntEnum):
    """Terrain tile kinds.

    Ordering is deliberate: :class:`Tile` values below ``WATER`` are walkable, so
    a single comparison answers the collision question on the hot path.
    """

    BARE_GROUND = 0
    GRASS = 1
    TALL_GRASS = 2
    BUSH = 3
    SAPLING = 4
    SAND = 5
    GRAVEL = 6
    DIRT_ROAD = 7
    COBBLE_ROAD = 8
    FLOOR_WOOD = 9
    FLOOR_STONE = 10
    SNOW = 11
    ASH = 12

    # Everything from here on blocks movement.
    WATER = 13
    DEEP_WATER = 14
    TREE = 15
    DEAD_TREE = 16
    ROCK = 17
    CLIFF = 18
    WALL_WOOD = 19
    WALL_STONE = 20
    FENCE = 21
    CACTUS = 22


FIRST_BLOCKING_TILE = Tile.WATER


def is_walkable(tile: int) -> bool:
    """True when an entity may occupy this tile."""
    return tile < FIRST_BLOCKING_TILE


def blocks_sight(tile: int) -> bool:
    """True when the tile stops a line-of-sight raycast.

    Water is transparent even though it blocks movement, so archers can shoot
    across a river but nobody can walk over it.
    """
    return tile >= Tile.TREE


class Biome(IntEnum):
    """Biome classes, assigned from elevation, temperature and moisture."""

    MEADOW = 0
    FOREST = 1
    DEEP_FOREST = 2
    WETLAND = 3
    HEATH = 4
    DESERT = 5
    HIGHLAND = 6
    ASHLAND = 7


@dataclass(frozen=True, slots=True)
class BiomeProfile:
    """Everything the generator and the weather system need per biome.

    ``ground`` is the base carpet. ``scatter`` is an ordered list of
    ``(tile, cumulative_probability)`` pairs consumed by the generator: a single
    hash per tile is compared against the running total, which is why the
    probabilities are pre-accumulated rather than stored raw.
    """

    biome: Biome
    name: str
    ground: Tile
    scatter: tuple[tuple[Tile, float], ...]
    weather: tuple[tuple[int, float], ...]
    ambient_tint: tuple[int, int, int]
    danger: int


# Weather ids are the WEATHER_* constants; kept as plain ints to avoid a cyclic
# import between the tile table and the constants module.
_CLEAR, _CLOUDY, _RAIN, _STORM, _FOG, _SNOW = 0, 1, 2, 3, 4, 5


BIOME_PROFILES: dict[Biome, BiomeProfile] = {
    Biome.MEADOW: BiomeProfile(
        biome=Biome.MEADOW,
        name="meadow",
        ground=Tile.GRASS,
        scatter=((Tile.TALL_GRASS, 0.18), (Tile.BUSH, 0.24), (Tile.TREE, 0.28), (Tile.ROCK, 0.30)),
        weather=((_CLEAR, 0.55), (_CLOUDY, 0.80), (_RAIN, 0.95), (_FOG, 1.0)),
        ambient_tint=(255, 246, 224),
        danger=0,
    ),
    Biome.FOREST: BiomeProfile(
        biome=Biome.FOREST,
        name="forest",
        ground=Tile.GRASS,
        # GDD 16.8: roughly 60% grass, 20% trees, 10% bushes, 10% rock.
        scatter=((Tile.TREE, 0.20), (Tile.BUSH, 0.30), (Tile.TALL_GRASS, 0.38), (Tile.ROCK, 0.42)),
        weather=((_CLEAR, 0.35), (_CLOUDY, 0.65), (_RAIN, 0.90), (_FOG, 1.0)),
        ambient_tint=(226, 240, 214),
        danger=1,
    ),
    Biome.DEEP_FOREST: BiomeProfile(
        biome=Biome.DEEP_FOREST,
        name="deep forest",
        ground=Tile.GRASS,
        scatter=((Tile.TREE, 0.38), (Tile.BUSH, 0.48), (Tile.DEAD_TREE, 0.52), (Tile.ROCK, 0.56)),
        weather=((_CLOUDY, 0.30), (_RAIN, 0.60), (_FOG, 0.85), (_STORM, 1.0)),
        ambient_tint=(196, 216, 198),
        danger=3,
    ),
    Biome.WETLAND: BiomeProfile(
        biome=Biome.WETLAND,
        name="wetland",
        ground=Tile.GRASS,
        scatter=((Tile.WATER, 0.22), (Tile.TALL_GRASS, 0.40), (Tile.BUSH, 0.46), (Tile.DEAD_TREE, 0.50)),
        weather=((_FOG, 0.35), (_RAIN, 0.70), (_CLOUDY, 0.90), (_STORM, 1.0)),
        ambient_tint=(206, 226, 226),
        danger=2,
    ),
    Biome.HEATH: BiomeProfile(
        biome=Biome.HEATH,
        name="heath",
        ground=Tile.GRAVEL,
        scatter=((Tile.BUSH, 0.14), (Tile.ROCK, 0.22), (Tile.TALL_GRASS, 0.30), (Tile.DEAD_TREE, 0.32)),
        weather=((_CLEAR, 0.40), (_CLOUDY, 0.70), (_RAIN, 0.88), (_STORM, 1.0)),
        ambient_tint=(238, 232, 214),
        danger=2,
    ),
    Biome.DESERT: BiomeProfile(
        biome=Biome.DESERT,
        name="desert",
        ground=Tile.SAND,
        # GDD 16.8: roughly 70% sand, 15% rock, 10% cactus, 5% oasis.
        scatter=((Tile.ROCK, 0.15), (Tile.CACTUS, 0.25), (Tile.WATER, 0.28), (Tile.GRAVEL, 0.34)),
        weather=((_CLEAR, 0.82), (_CLOUDY, 0.96), (_STORM, 1.0)),
        ambient_tint=(255, 238, 198),
        danger=2,
    ),
    Biome.HIGHLAND: BiomeProfile(
        biome=Biome.HIGHLAND,
        name="highland",
        ground=Tile.GRAVEL,
        scatter=((Tile.ROCK, 0.20), (Tile.CLIFF, 0.30), (Tile.SNOW, 0.40), (Tile.DEAD_TREE, 0.43)),
        weather=((_SNOW, 0.35), (_CLOUDY, 0.65), (_FOG, 0.85), (_STORM, 1.0)),
        ambient_tint=(224, 234, 246),
        danger=3,
    ),
    Biome.ASHLAND: BiomeProfile(
        biome=Biome.ASHLAND,
        name="ashland",
        ground=Tile.ASH,
        scatter=((Tile.ROCK, 0.18), (Tile.DEAD_TREE, 0.28), (Tile.CLIFF, 0.33)),
        weather=((_CLOUDY, 0.40), (_FOG, 0.70), (_STORM, 1.0)),
        ambient_tint=(226, 210, 206),
        danger=4,
    ),
}


def classify_biome(elevation: float, temperature: float, moisture: float) -> Biome:
    """Assign a biome from three normalised noise fields.

    Ordering matters: elevation gates first because altitude dominates climate
    (GDD 16.8 and the Joe Duffy climate reference), then the temperature and
    moisture pair distinguishes the mid-altitude biomes. All three inputs are in
    ``[0, 1]``.
    """
    if elevation > 0.82:
        return Biome.HIGHLAND
    if elevation < 0.28:
        return Biome.WETLAND if moisture > 0.45 else Biome.HEATH
    if temperature > 0.70 and moisture < 0.32:
        return Biome.DESERT
    if temperature > 0.78 and moisture < 0.18:
        return Biome.ASHLAND
    if moisture > 0.62:
        return Biome.DEEP_FOREST if elevation > 0.5 else Biome.WETLAND
    if moisture > 0.40:
        return Biome.FOREST
    return Biome.MEADOW


# --- regrowth ---------------------------------------------------------------

# GDD 9.2: bare ground climbs back to mature forest one stage at a time. A tile
# not in this table has reached its terminal stage and stops advancing.
REGROWTH_LADDER: dict[int, int] = {
    Tile.BARE_GROUND: Tile.GRASS,
    Tile.GRASS: Tile.TALL_GRASS,
    Tile.TALL_GRASS: Tile.BUSH,
    Tile.BUSH: Tile.SAPLING,
    Tile.SAPLING: Tile.TREE,
}


def next_regrowth_stage(tile: int) -> int | None:
    """The stage this tile becomes after one regrowth interval, if any."""
    return REGROWTH_LADDER.get(tile)


# Tiles a player may dig or clear, and what they leave behind.
HARVEST_RESULTS: dict[int, tuple[int, str, int]] = {
    Tile.TREE: (Tile.BARE_GROUND, "wood", 4),
    Tile.DEAD_TREE: (Tile.BARE_GROUND, "wood", 2),
    Tile.SAPLING: (Tile.BARE_GROUND, "wood", 1),
    Tile.BUSH: (Tile.BARE_GROUND, "fibre", 2),
    Tile.TALL_GRASS: (Tile.GRASS, "fibre", 1),
    Tile.GRASS: (Tile.BARE_GROUND, "soil", 1),
    Tile.ROCK: (Tile.GRAVEL, "stone", 3),
    Tile.CLIFF: (Tile.GRAVEL, "stone", 5),
    Tile.CACTUS: (Tile.SAND, "fibre", 2),
}

# What a material places, and how much of it one tile costs.
BUILD_RECIPES: dict[str, tuple[int, int]] = {
    "wood": (Tile.WALL_WOOD, 2),
    "stone": (Tile.WALL_STONE, 3),
    "soil": (Tile.BARE_GROUND, 1),
    "fibre": (Tile.FENCE, 2),
    "plank": (Tile.FLOOR_WOOD, 1),
    "flagstone": (Tile.FLOOR_STONE, 1),
}

# Structures are removable; natural terrain is not, so a player cannot delete a
# cliff to shortcut through it.
PLAYER_PLACED_TILES = frozenset(
    {
        Tile.WALL_WOOD,
        Tile.WALL_STONE,
        Tile.FENCE,
        Tile.FLOOR_WOOD,
        Tile.FLOOR_STONE,
        Tile.DIRT_ROAD,
        Tile.COBBLE_ROAD,
    }
)
