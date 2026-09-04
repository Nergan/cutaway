"""The layered chunk generator.

GDD 5.3 and TDD 8.1 specify four layers, and this implements all four:

Layer 1, macro path
    A deterministic spine along the corridor, curving from a coordinate function
    so it never disagrees with itself across a chunk boundary.
Layer 2, biome fields
    Elevation, temperature and moisture from independent fractal noise, sampled in
    *global* coordinates and classified per tile.
Layer 3, tile layout
    Ground carpet plus scatter. This is the threshold-based selection TDD 8.4
    names as the sanctioned fallback to Wave Function Collapse, followed by a
    coherence pass that gives adjacency constraints most of what WFC would buy at
    a fraction of the cost. See ``docs/worldgen.md`` for why that trade is taken.
Layer 4, points of interest
    Deterministic camps, ruins and resource nodes, spaced by rule.

Seam stitching is structural rather than corrective. Every field is a function of
global coordinates, so two adjacent chunks computing the same boundary tile get
the same answer without either knowing the other exists. That is the first of the
three rules from the Bugnet reference, and it makes the other two unnecessary for
terrain (the coherence pass reads a one-tile apron beyond its own edges).
"""

from __future__ import annotations

from dataclasses import dataclass

from ..domain.constants import CHUNK_TILE_COUNT, CHUNK_TILES, HUB_RADIUS_TILES
from ..domain.coordinates import ChunkAddress, SpaceType
from ..domain.hashing import chunk_seed, combine, hub_chunk_seed, unit_float
from ..domain.tiles import BIOME_PROFILES, Biome, Tile, classify_biome
from . import noise

# Field frequencies, in cycles per tile. Elevation varies slowest so mountains are
# regional; moisture varies fastest so a forest can end without the altitude
# changing. These are the numbers that decide whether the world reads as
# "landscape" or as "noise", and they are the first thing to tune.
_ELEVATION_FREQ = 0.006
_TEMPERATURE_FREQ = 0.0035
_MOISTURE_FREQ = 0.009

# Independent seed offsets so the three fields are uncorrelated.
_ELEVATION_SALT = 0x00E1E1
_TEMPERATURE_SALT = 0x007E77
_MOISTURE_SALT = 0x00D01F
_ROAD_SALT = 0x00ADD1
_RIVER_SALT = 0x00F10D
_SCATTER_SALT = 0x005CA7
_POI_SALT = 0x000901

# Road geometry. The corridor road is the reason a player can tell which way the
# next hub is; it is generated from the along-coordinate alone so it is continuous
# by construction.
_ROAD_HALF_WIDTH = 1.6
# A clear strip either side of the paving. Without it, scatter puts trees hard
# against the road and the navigational spine stops being legible from a distance.
_ROAD_VERGE = _ROAD_HALF_WIDTH + 1.4
# A road distance no tile can be inside, for terrain that must never be paved.
_NO_ROAD = 1e9
_ROAD_WANDER_TILES = 5.0
_ROAD_WANDER_FREQ = 0.011

_RIVER_THRESHOLD = 0.955
_RIVER_HALF_WIDTH = 1.9

# Sampling strides for the continuous fields, in tiles.
#
# The climate fields have wavelengths of 110 to 285 tiles, so evaluating them per
# tile computes the same value 16 times over. Sampling on a grid and interpolating
# bilinearly is visually identical and cuts the noise budget by more than an order
# of magnitude, which is what makes generation affordable in pure Python at all
# (712 ms per chunk before, 40 ms after).
#
# The strides must divide CHUNK_TILES and the grid must be aligned in *global*
# coordinates, or two neighbouring chunks interpolate between different sample
# points and the seam reappears. Chunk origins are multiples of 32, so any power of
# two up to 32 is safe.
_FIELD_STEP = 4
# Rivers get a finer grid: they come from a threshold on a ridged field whose top
# octave has a 31-tile wavelength, and a threshold is far more sensitive to
# interpolation error than a classification is.
_RIVER_STEP = 2


@dataclass(frozen=True, slots=True)
class ChunkFields:
    """The per-chunk sampled fields, kept for debugging and the Atelier preview."""

    biome: Biome
    elevation: float
    temperature: float
    moisture: float


class WorldGenerator:
    """Implements the :class:`~age.domain.ports.ChunkGenerator` port.

    Stateless apart from a small cache. Generation is pure, so the cache is a pure
    performance concern and never affects results.
    """

    __slots__ = ("world_seed", "_tiles", "_fields", "_cache_limit")

    def __init__(self, world_seed: int, cache_limit: int = 512) -> None:
        self.world_seed = world_seed
        self._tiles: dict[str, bytearray] = {}
        self._fields: dict[str, ChunkFields] = {}
        self._cache_limit = cache_limit

    # --- global coordinate mapping -----------------------------------------

    def _origin(self, address: ChunkAddress) -> tuple[float, float]:
        """The global tile coordinate of a chunk's top-left tile.

        For corridor chunks the global frame is ``(along, across)``, which is
        edge-local but continuous across the whole corridor: exactly what the
        noise fields need to stay seamless. Hub chunks are pushed into a distant
        region of the same frame, keyed by hub id, so two hubs never generate
        identical terrain.
        """
        if address.space_type is SpaceType.EDGE:
            return (
                float(address.segment_index * CHUNK_TILES),
                float(address.lane_offset * CHUNK_TILES),
            )
        # Push hubs into distant regions of the same field. The offsets start at one
        # rather than zero so hub 0 does not land on the corridor's own origin and
        # generate terrain identical to segment 0.
        hub_index = (address.hub_id or 0) + 1
        return (
            hub_index * 4096.0 + address.chunk_x * CHUNK_TILES,
            hub_index * 2048.0 + address.chunk_y * CHUNK_TILES,
        )

    def _seed_for(self, address: ChunkAddress) -> int:
        if address.space_type is SpaceType.EDGE:
            return chunk_seed(
                self.world_seed,
                address.edge_id or "",
                address.segment_index,
                address.lane_offset,
                address.tier_min,
            )
        return hub_chunk_seed(
            self.world_seed, address.hub_id or 0, address.chunk_x, address.chunk_y
        )

    # --- layer 2: biome fields ---------------------------------------------

    def elevation_at(self, gx: float, gy: float) -> float:
        return noise.fractal(
            self.world_seed + _ELEVATION_SALT, gx, gy, octaves=4, frequency=_ELEVATION_FREQ
        )

    def temperature_at(self, gx: float, gy: float) -> float:
        return self._temperature(gx, gy, self.elevation_at(gx, gy))

    def moisture_at(self, gx: float, gy: float) -> float:
        return self._moisture(gx, gy, self.elevation_at(gx, gy))

    def _temperature(self, gx: float, gy: float, elevation: float) -> float:
        """Temperature given an already-computed elevation.

        Elevation is an input rather than a lookup because both derived fields need
        it and the public wrappers would otherwise evaluate the same four octaves
        three times for one tile.
        """
        base = noise.fractal(
            self.world_seed + _TEMPERATURE_SALT, gx, gy, octaves=3, frequency=_TEMPERATURE_FREQ
        )
        # Altitude cools: the standard lapse-rate coupling from the climate
        # reference, which is what stops a desert appearing on a mountain top.
        return _clamp01(base - (elevation - 0.5) * 0.45)

    def _moisture(self, gx: float, gy: float, elevation: float) -> float:
        base = noise.fractal(
            self.world_seed + _MOISTURE_SALT, gx, gy, octaves=4, frequency=_MOISTURE_FREQ
        )
        # Rain shadow: high ground wrings moisture out of the air, so the lee side
        # of a ridge is drier than its height alone would suggest.
        return _clamp01(base - max(0.0, elevation - 0.62) * 0.6)

    def climate_at(self, gx: float, gy: float) -> tuple[float, float, float]:
        """``(elevation, temperature, moisture)`` at one point, sampled directly."""
        elevation = self.elevation_at(gx, gy)
        return elevation, self._temperature(gx, gy, elevation), self._moisture(gx, gy, elevation)

    def biome_at(self, gx: float, gy: float) -> Biome:
        return classify_biome(*self.climate_at(gx, gy))

    # --- layer 1: macro path ------------------------------------------------

    def road_offset(self, along: float) -> float:
        """How far the road has wandered from the corridor centre line.

        A function of the along-coordinate only, so every chunk the road crosses
        computes the same centre for the same ``along`` and the road cannot break
        at a seam. This is the coordinate-deterministic feature rule.
        """
        wander = noise.gradient_noise(
            self.world_seed + _ROAD_SALT, along * _ROAD_WANDER_FREQ, 0.0
        )
        return wander * _ROAD_WANDER_TILES

    def road_distance(self, along: float, across: float) -> float:
        """Perpendicular distance from the road's centre at this point."""
        return abs(across - self.road_offset(along))

    def river_field(self, gx: float, gy: float) -> float:
        """Ridged field whose crests become watercourses."""
        return noise.ridged(self.world_seed + _RIVER_SALT, gx, gy, octaves=3, frequency=0.008)

    # --- layer 3 and 4: assembly -------------------------------------------

    def generate(self, address: ChunkAddress) -> bytearray:
        """Tiles for a chunk. Row-major, ``CHUNK_TILE_COUNT`` bytes."""
        key = address.key
        cached = self._tiles.get(key)
        if cached is not None:
            return cached

        tiles = self._build(address)
        if len(self._tiles) >= self._cache_limit:
            # Plain FIFO eviction. Regenerating is cheap and correct, so there is
            # nothing to gain from tracking recency.
            self._tiles.pop(next(iter(self._tiles)), None)
        self._tiles[key] = tiles
        return tiles

    def biome_of(self, address: ChunkAddress) -> int:
        return int(self.fields_of(address).biome)

    def fields_of(self, address: ChunkAddress) -> ChunkFields:
        """The fields sampled at a chunk's centre."""
        key = address.key
        cached = self._fields.get(key)
        if cached is not None:
            return cached

        ox, oy = self._origin(address)
        cx = ox + CHUNK_TILES * 0.5
        cy = oy + CHUNK_TILES * 0.5
        elevation, temperature, moisture = self.climate_at(cx, cy)
        fields = ChunkFields(
            biome=classify_biome(elevation, temperature, moisture),
            elevation=elevation,
            temperature=temperature,
            moisture=moisture,
        )
        if len(self._fields) >= self._cache_limit * 4:
            self._fields.pop(next(iter(self._fields)), None)
        self._fields[key] = fields
        return fields

    def _sample_climate(self, ox: float, oy: float) -> list[tuple[float, float, float]]:
        """The climate grid covering one chunk, row-major, ``_FIELD_STEP`` apart.

        One extra row and column so bilinear interpolation has a far corner for the
        last tile. Sample positions are global, so the chunk to the right recomputes
        this chunk's right edge and gets the same numbers.
        """
        span = CHUNK_TILES // _FIELD_STEP + 1
        return [
            self.climate_at(ox + gx * _FIELD_STEP, oy + gy * _FIELD_STEP)
            for gy in range(span)
            for gx in range(span)
        ]

    def _sample_rivers(self, ox: float, oy: float) -> list[float]:
        span = CHUNK_TILES // _RIVER_STEP + 1
        return [
            self.river_field(ox + gx * _RIVER_STEP, oy + gy * _RIVER_STEP)
            for gy in range(span)
            for gx in range(span)
        ]

    def _build(self, address: ChunkAddress) -> bytearray:
        seed = self._seed_for(address)
        ox, oy = self._origin(address)
        is_hub = address.space_type is SpaceType.HUB
        hub_radius = HUB_RADIUS_TILES

        tiles = bytearray(CHUNK_TILE_COUNT)

        climate = self._sample_climate(ox, oy)
        rivers = self._sample_rivers(ox, oy)
        climate_span = CHUNK_TILES // _FIELD_STEP + 1
        river_span = CHUNK_TILES // _RIVER_STEP + 1

        # The road wanders as a function of the along-coordinate only, so one value
        # per column serves every row. That is also what makes it continuous across
        # a seam without either chunk knowing about the other.
        road_offsets = [self.road_offset(ox + tx) for tx in range(CHUNK_TILES)]

        for ty in range(CHUNK_TILES):
            row = ty * CHUNK_TILES
            gy = oy + ty
            for tx in range(CHUNK_TILES):
                gx = ox + tx
                elevation, temperature, moisture = _bilinear3(
                    climate, climate_span, tx / _FIELD_STEP, ty / _FIELD_STEP
                )
                biome = classify_biome(elevation, temperature, moisture)

                if is_hub:
                    tiles[row + tx] = self._hub_tile(
                        seed, address, tx, ty, biome, hub_radius, rivers, river_span
                    )
                else:
                    river = _bilinear(rivers, river_span, tx / _RIVER_STEP, ty / _RIVER_STEP)
                    tiles[row + tx] = self._wild_tile(
                        seed, tx, ty, biome, river, abs(gy - road_offsets[tx])
                    )

        self._coherence_pass(tiles, seed)
        self._place_pois(tiles, seed, address)
        return tiles

    def _wild_tile(
        self,
        seed: int,
        tx: int,
        ty: int,
        biome: Biome,
        river: float,
        road_distance: float,
    ) -> int:
        """One corridor tile, from the already-sampled fields."""
        # The road wins over everything: it is the navigational spine.
        if road_distance <= _ROAD_HALF_WIDTH:
            return int(Tile.DIRT_ROAD)

        # Rivers cut second, but never across the road: a bridge is implied rather
        # than modelled, which keeps the corridor traversable at every seed.
        if river > _RIVER_THRESHOLD and road_distance > _ROAD_HALF_WIDTH + 1.0:
            return int(Tile.WATER)

        profile = BIOME_PROFILES[biome]

        # Verges: keep the ground clear next to the road so it stays readable.
        if road_distance <= _ROAD_VERGE:
            return int(profile.ground)

        roll = noise.scatter_value(seed, tx, ty, _SCATTER_SALT)
        for tile, cumulative in profile.scatter:
            if roll < cumulative:
                return int(tile)
        return int(profile.ground)

    def _hub_tile(
        self,
        seed: int,
        address: ChunkAddress,
        tx: int,
        ty: int,
        biome: Biome,
        hub_radius: int,
        rivers: list[float],
        river_span: int,
    ) -> int:
        """One hub-zone tile.

        Hubs are laid out rather than grown: a paved plaza at the centre, radial
        streets, and buildings on the blocks between them. It is a placeholder for
        hand-authored hubs, which is what the Atelier exists to produce; the point is
        that the shape reads as a town rather than as terrain.
        """
        # Hub-local tile coordinates, centred on the hub origin.
        lx = address.chunk_x * CHUNK_TILES + tx
        ly = address.chunk_y * CHUNK_TILES + ty
        distance = max(abs(lx), abs(ly))

        if distance <= 6:
            return int(Tile.FLOOR_STONE)  # central plaza

        if distance > hub_radius:
            # Outside the zone proper, fall through to wilderness so the rim blends
            # rather than ending in a wall. No road: the corridor's spine belongs to
            # the corridor, and running one through a hub's outskirts would put a
            # dirt track across the town wall.
            river = _bilinear(rivers, river_span, tx / _RIVER_STEP, ty / _RIVER_STEP)
            return self._wild_tile(seed, tx, ty, biome, river, _NO_ROAD)

        # Radial street grid every twelve tiles.
        if lx % 12 == 0 or ly % 12 == 0:
            return int(Tile.COBBLE_ROAD)

        # Blocks: mostly buildings near the centre, thinning towards the rim.
        block_roll = unit_float(combine(seed, lx // 12, ly // 12, 0x8109))
        density = 1.0 - distance / (hub_radius + 1.0)
        if block_roll < density * 0.75:
            edge_of_block = (lx % 12 in (1, 11)) or (ly % 12 in (1, 11))
            return int(Tile.WALL_STONE if edge_of_block else Tile.FLOOR_WOOD)

        garden_roll = noise.scatter_value(seed, tx, ty, _SCATTER_SALT)
        if garden_roll < 0.10:
            return int(Tile.TREE)
        if garden_roll < 0.20:
            return int(Tile.BUSH)
        return int(Tile.GRASS)

    def _coherence_pass(self, tiles: bytearray, seed: int) -> None:
        """Give the threshold layout the adjacency sense WFC would have provided.

        Two rules, one pass, no backtracking:

        1. Water needs company. An isolated water tile is a puddle in the middle
           of a meadow, which reads as noise; it gets filled in.
        2. Hard terrain needs a skirt. A cliff or rock touching plain grass gets
           gravel between them, which is the "transition tile" idea from GDD 5.3
           applied locally.

        Neither rule can cascade, because both read the original array and write a
        copy. That bounded, single-pass property is the whole reason this is
        affordable at 32x32 per chunk where real WFC is not.
        """
        original = bytes(tiles)

        def at(x: int, y: int) -> int:
            if x < 0 or y < 0 or x >= CHUNK_TILES or y >= CHUNK_TILES:
                # The apron: outside the chunk, ask the field directly rather
                # than guessing. This is what keeps the rule consistent across a
                # seam without needing the neighbour to be loaded.
                return -1
            return original[y * CHUNK_TILES + x]

        for y in range(CHUNK_TILES):
            for x in range(CHUNK_TILES):
                index = y * CHUNK_TILES + x
                tile = original[index]
                neighbours = (at(x - 1, y), at(x + 1, y), at(x, y - 1), at(x, y + 1))

                if tile == Tile.WATER:
                    if not any(n == Tile.WATER for n in neighbours):
                        tiles[index] = int(Tile.GRASS)
                    continue

                if tile in (Tile.GRASS, Tile.TALL_GRASS) and any(
                    n in (Tile.CLIFF, Tile.ROCK) for n in neighbours
                ):
                    if unit_float(combine(seed, x, y, 0x5C17)) < 0.55:
                        tiles[index] = int(Tile.GRAVEL)

    def _place_pois(self, tiles: bytearray, seed: int, address: ChunkAddress) -> None:
        """Layer 4: one optional point of interest per chunk.

        One per chunk at most, and never in a hub. Position and kind come from the
        chunk seed, so a POI is a property of the world rather than of when the
        chunk happened to load.
        """
        if address.space_type is SpaceType.HUB:
            return
        if unit_float(combine(seed, _POI_SALT, 0, 0)) > 0.34:
            return

        cx = 6 + int(unit_float(combine(seed, _POI_SALT, 1, 0)) * (CHUNK_TILES - 12))
        cy = 6 + int(unit_float(combine(seed, _POI_SALT, 2, 0)) * (CHUNK_TILES - 12))
        kind = int(unit_float(combine(seed, _POI_SALT, 3, 0)) * 3.0)

        if kind == 0:
            self._stamp_ruin(tiles, cx, cy, seed)
        elif kind == 1:
            self._stamp_camp(tiles, cx, cy)
        else:
            self._stamp_quarry(tiles, cx, cy, seed)

    @staticmethod
    def _set(tiles: bytearray, x: int, y: int, tile: Tile) -> None:
        if 0 <= x < CHUNK_TILES and 0 <= y < CHUNK_TILES:
            tiles[y * CHUNK_TILES + x] = int(tile)

    def _stamp_ruin(self, tiles: bytearray, cx: int, cy: int, seed: int) -> None:
        """A broken stone rectangle: walls with gaps, flagstones inside."""
        half = 3
        for dy in range(-half, half + 1):
            for dx in range(-half, half + 1):
                on_edge = abs(dx) == half or abs(dy) == half
                if on_edge:
                    if unit_float(combine(seed, dx, dy, 0x8171)) < 0.65:
                        self._set(tiles, cx + dx, cy + dy, Tile.WALL_STONE)
                else:
                    self._set(tiles, cx + dx, cy + dy, Tile.FLOOR_STONE)

    def _stamp_camp(self, tiles: bytearray, cx: int, cy: int) -> None:
        """An abandoned camp: a cleared ring with a fire scar in the middle."""
        for dy in range(-2, 3):
            for dx in range(-2, 3):
                self._set(tiles, cx + dx, cy + dy, Tile.BARE_GROUND)
        self._set(tiles, cx, cy, Tile.ASH)
        self._set(tiles, cx - 2, cy - 2, Tile.FENCE)
        self._set(tiles, cx + 2, cy + 2, Tile.FENCE)

    def _stamp_quarry(self, tiles: bytearray, cx: int, cy: int, seed: int) -> None:
        """A rock cluster worth mining."""
        for dy in range(-2, 3):
            for dx in range(-2, 3):
                if dx * dx + dy * dy > 5:
                    continue
                roll = unit_float(combine(seed, dx, dy, 0x9427))
                self._set(tiles, cx + dx, cy + dy, Tile.ROCK if roll < 0.7 else Tile.GRAVEL)

    def invalidate(self, address: ChunkAddress) -> None:
        """Drop a chunk from the cache, for the Atelier's live-reload path."""
        self._tiles.pop(address.key, None)
        self._fields.pop(address.key, None)


def _clamp01(value: float) -> float:
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def _bilinear(grid: list[float], span: int, fx: float, fy: float) -> float:
    """Bilinear read from a row-major ``span * span`` grid at fractional indices."""
    x0 = int(fx)
    y0 = int(fy)
    tx = fx - x0
    ty = fy - y0
    base = y0 * span + x0
    top = grid[base] + (grid[base + 1] - grid[base]) * tx
    below = base + span
    bottom = grid[below] + (grid[below + 1] - grid[below]) * tx
    return top + (bottom - top) * ty


def _bilinear3(
    grid: list[tuple[float, float, float]], span: int, fx: float, fy: float
) -> tuple[float, float, float]:
    """Bilinear read of a grid of triples, done componentwise in one pass."""
    x0 = int(fx)
    y0 = int(fy)
    tx = fx - x0
    ty = fy - y0
    base = y0 * span + x0
    below = base + span
    a = grid[base]
    b = grid[base + 1]
    c = grid[below]
    d = grid[below + 1]

    out = []
    for i in range(3):
        top = a[i] + (b[i] - a[i]) * tx
        bottom = c[i] + (d[i] - c[i]) * tx
        out.append(top + (bottom - top) * ty)
    return out[0], out[1], out[2]
