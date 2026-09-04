"""The world aggregate: entities, spatial index, and tile access.

This is the object every system takes as its first argument. It owns the entity
registry, the spatial hash used for area-of-interest queries, the topology state,
and the composition of generated terrain with player edits.

It deliberately owns no timers, no sockets and no persistence. The clock arrives
as a port and writes leave through repositories the simulation never calls
directly, which is what keeps a full world constructible in a test with three
lines and no async.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from ..domain.constants import (
    CHUNK_TILES,
    CORRIDOR_SEGMENTS,
    DAY_LENGTH_SECONDS,
    HUB_RADIUS_TILES,
)
from ..domain.coordinates import (
    ChunkAddress,
    EdgeDefinition,
    HubDefinition,
    LocationRef,
    SpaceType,
    WorldPoint,
    edge_to_world,
    locate,
    resolve,
    world_to_edge,
)
from ..domain.entities import Entity, EntityId, EntityIdAllocator, PlayerSession
from ..domain.ports import ChunkGenerator, Clock
from ..domain.tiles import Biome, Tile, blocks_sight, is_walkable
from ..domain.topology import ChunkState, TopologyState


@dataclass(slots=True)
class ChunkView:
    """A loaded chunk: generated tiles plus the overlay of player edits.

    The overlay is kept separate rather than merged so the generated base stays
    regenerable and only the diff needs persisting. ``dirty`` marks the chunk as
    having unflushed edits.
    """

    address: ChunkAddress
    base: bytearray
    overlay: dict[int, int] = field(default_factory=dict)
    # Tile index to the timestamp at which it may advance one regrowth stage.
    regrowth_due: dict[int, float] = field(default_factory=dict)
    dirty: bool = False

    def tile(self, index: int) -> int:
        overlaid = self.overlay.get(index)
        return self.base[index] if overlaid is None else overlaid

    def set_tile(self, index: int, tile: int) -> None:
        if self.base[index] == tile:
            # Edited back to what the generator would produce: drop the overlay
            # entry rather than storing a no-op forever.
            self.overlay.pop(index, None)
        else:
            self.overlay[index] = tile
        self.dirty = True

    def snapshot_overlay(self) -> dict[int, int]:
        return dict(self.overlay)


def _split_hub_tile(tile_x: float, tile_y: float) -> tuple[tuple[int, int], tuple[int, int]]:
    """Split hub-local tile coordinates into ``((chunk_x, x), (chunk_y, y))``.

    One integer ``divmod`` per axis rather than a separate floor for the chunk and
    for the offset. Deriving the two independently lets float error at a chunk
    boundary produce an offset of exactly ``CHUNK_TILES``, which is one past the end
    of the chunk — and a hub plaza sits on the origin, where those boundaries are.
    """
    return (
        divmod(math.floor(tile_x), CHUNK_TILES),
        divmod(math.floor(tile_y), CHUNK_TILES),
    )


class World:
    """Authoritative world state for one edge and its two hubs."""

    __slots__ = (
        "world_seed",
        "clock",
        "generator",
        "hubs",
        "edges",
        "topology",
        "entities",
        "sessions",
        "_ids",
        "_chunks",
        "_spatial",
        "tick_count",
        "weather",
        "_weather_until",
        "started_at",
    )

    def __init__(
        self,
        *,
        world_seed: int,
        clock: Clock,
        generator: ChunkGenerator,
        hubs: list[HubDefinition],
        edge: EdgeDefinition,
        segments: int = CORRIDOR_SEGMENTS,
    ) -> None:
        self.world_seed = world_seed
        self.clock = clock
        self.generator = generator
        self.hubs: dict[int, HubDefinition] = {hub.hub_id: hub for hub in hubs}
        self.edges: dict[str, EdgeDefinition] = {edge.edge_id: edge}
        self.topology = TopologyState(edge_id=edge.edge_id, segments=segments)

        self.entities: dict[EntityId, Entity] = {}
        self.sessions: dict[str, PlayerSession] = {}
        self._ids = EntityIdAllocator()
        self._chunks: dict[str, ChunkView] = {}
        # chunk key -> entity ids. Rebuilt incrementally as entities move, which
        # is the cacheability the Red Blob spatial-hash reference is about: small
        # movements do not change the bucket at all.
        self._spatial: dict[str, set[EntityId]] = {}

        self.tick_count = 0
        self.weather: int = 0
        self._weather_until = 0.0
        self.started_at = clock.now()

    # --- convenience --------------------------------------------------------

    @property
    def edge(self) -> EdgeDefinition:
        return next(iter(self.edges.values()))

    @property
    def now(self) -> float:
        return self.clock.now()

    @property
    def day_phase(self) -> float:
        """Position in the day/night cycle, ``0.0`` at dawn, wrapping at 1.0."""
        elapsed = self.now - self.started_at
        return (elapsed % DAY_LENGTH_SECONDS) / DAY_LENGTH_SECONDS

    @property
    def players(self) -> list[Entity]:
        return [entity for entity in self.entities.values() if entity.is_player]

    @property
    def npcs(self) -> list[Entity]:
        return [entity for entity in self.entities.values() if entity.is_npc]

    def allocate_entity_id(self) -> EntityId:
        return self._ids.allocate()

    # --- location plumbing --------------------------------------------------

    def locate(self, point: WorldPoint) -> LocationRef:
        return locate(point, self.hubs, self.edges)

    def resolve(self, location: LocationRef) -> WorldPoint:
        return resolve(location, self.hubs, self.edges)

    def chunk_address_at(self, point: WorldPoint) -> ChunkAddress:
        """Which chunk a plane point falls in, at the current tier.

        Hub zones take precedence where they overlap the corridor mouth, matching
        :func:`~age.domain.coordinates.locate`, so the safe-zone rules apply to
        anyone standing on the rim.
        """
        location = self.locate(point)
        if location.space_type is SpaceType.HUB:
            (chunk_x, _), (chunk_y, _) = _split_hub_tile(location.tile_x, location.tile_y)
            return ChunkAddress.hub(location.hub_id or 0, chunk_x, chunk_y)
        lane = location.lane_offset or 0
        return ChunkAddress.edge(
            location.edge_id or "",
            location.segment_index or 0,
            lane,
            0 if lane == 0 else 1,
        )

    def is_in_hub(self, point: WorldPoint) -> bool:
        """Whether a point is inside any hub's safe zone."""
        for hub in self.hubs.values():
            centre = hub.centre
            if max(abs(point.x - centre.x), abs(point.y - centre.y)) <= hub.radius_tiles:
                return True
        return False

    def nearest_hub(self, point: WorldPoint) -> HubDefinition:
        return min(self.hubs.values(), key=lambda hub: hub.centre.distance_squared_to(point))

    def spawn_point_for(self, hub: HubDefinition) -> WorldPoint:
        """A spot on the hub plaza. The plaza is paved, so always walkable."""
        centre = hub.centre
        return WorldPoint(centre.x, centre.y + 3.0)

    # --- chunk and tile access ---------------------------------------------

    def chunk(self, address: ChunkAddress) -> ChunkView:
        """Load a chunk, generating its base terrain on first touch."""
        key = address.key
        view = self._chunks.get(key)
        if view is None:
            view = ChunkView(address=address, base=self.generator.generate(address))
            self._chunks[key] = view
        return view

    def loaded_chunks(self) -> list[ChunkView]:
        return list(self._chunks.values())

    def is_chunk_loaded(self, address: ChunkAddress) -> bool:
        """Whether a chunk's terrain is already in memory.

        Cheap by design: the warm-up queue and the PREPARING gate both call it every
        tick, and neither wants to trigger the generation it is asking about.
        """
        return address.key in self._chunks

    def hub_chunk_addresses(self) -> list[ChunkAddress]:
        """Every chunk covering every hub zone, centre-out.

        Hubs sit outside the accordion — they are permanent, so the topology has no
        records for them — but their interiors still have to be built. Ordering by
        distance from the plaza means the warm-up queue produces the tiles around
        the spawn point before the ones behind the far wall.
        """
        addresses: list[ChunkAddress] = []
        for hub in self.hubs.values():
            span = hub.radius_tiles // CHUNK_TILES + 1
            ring = [
                (x, y)
                for x in range(-span, span + 1)
                for y in range(-span, span + 1)
            ]
            ring.sort(key=lambda xy: max(abs(xy[0]), abs(xy[1])))
            addresses.extend(ChunkAddress.hub(hub.hub_id, x, y) for x, y in ring)
        return addresses

    def apply_overlay(self, address: ChunkAddress, overlay: dict[int, int]) -> None:
        """Restore persisted edits onto a freshly generated chunk."""
        view = self.chunk(address)
        view.overlay.update(overlay)
        view.dirty = False

    def unload_chunk(self, address: ChunkAddress) -> ChunkView | None:
        """Drop a chunk from memory. The caller must have flushed it first."""
        return self._chunks.pop(address.key, None)

    def tile_at(self, point: WorldPoint) -> int:
        """The effective tile under a plane point, edits included."""
        index = self._tile_index(point)
        if index is None:
            return int(Tile.DEEP_WATER)
        address, tile_index = index
        return self.chunk(address).tile(tile_index)

    def set_tile_at(self, point: WorldPoint, tile: int) -> tuple[str, int] | None:
        """Write a tile, returning ``(chunk_key, tile_index)`` when it landed."""
        index = self._tile_index(point)
        if index is None:
            return None
        address, tile_index = index
        self.chunk(address).set_tile(tile_index, tile)
        return address.key, tile_index

    def _tile_index(self, point: WorldPoint) -> tuple[ChunkAddress, int] | None:
        """Resolve a plane point to a chunk and an index inside it.

        Returns ``None`` for a point that falls outside the active topology, which
        the caller treats as impassable rather than as an error: the edge of the
        world should stop you, not crash you.
        """
        location = self.locate(point)

        if location.space_type is SpaceType.HUB:
            # Not ``hub_id or -1``: hub 0 is a real hub and a falsy one, and
            # getting this wrong makes the whole first hub read as deep water.
            hub_id = location.hub_id
            hub = self.hubs.get(hub_id) if hub_id is not None else None
            if hub is None:
                return None
            (chunk_x, tx), (chunk_y, ty) = _split_hub_tile(location.tile_x, location.tile_y)
            return ChunkAddress.hub(hub.hub_id, chunk_x, chunk_y), ty * CHUNK_TILES + tx

        lane = location.lane_offset or 0
        segment = location.segment_index or 0
        tier_min = 0 if lane == 0 else 1
        if tier_min > self.topology.current_tier:
            return None
        if segment < 0 or segment >= self.topology.segments:
            return None
        if lane not in (-1, 0, 1):
            return None

        address = ChunkAddress.edge(location.edge_id or "", segment, lane, tier_min)
        record = self.topology.chunks.get(address.key)
        if record is None or record.state is ChunkState.INACTIVE:
            return None

        tx = int(location.tile_x)
        ty = int(location.tile_y)
        tx = 0 if tx < 0 else (CHUNK_TILES - 1 if tx >= CHUNK_TILES else tx)
        ty = 0 if ty < 0 else (CHUNK_TILES - 1 if ty >= CHUNK_TILES else ty)
        return address, ty * CHUNK_TILES + tx

    def contains(self, point: WorldPoint) -> bool:
        """Whether a point falls inside the currently active topology.

        A saved position in a lane that has since been retired resolves to a point
        that is geometrically fine and topologically gone; this is the check that
        tells the two apart.
        """
        return self._tile_index(point) is not None

    def is_walkable_at(self, point: WorldPoint) -> bool:
        return is_walkable(self.tile_at(point))

    def has_line_of_sight(self, origin: WorldPoint, target: WorldPoint) -> bool:
        """Whether nothing solid stands between two points.

        Samples along the segment at half-tile steps. A DDA walk would be exact,
        but at these distances the sampling error is smaller than a hitbox and the
        loop is a third of the length; ``blocks_sight`` deliberately lets water
        through so a river is not cover.
        """
        dx = target.x - origin.x
        dy = target.y - origin.y
        distance = math.hypot(dx, dy)
        if distance <= 0.5:
            return True

        steps = int(distance * 2.0)
        inv = 1.0 / steps
        for step in range(1, steps):
            t = step * inv
            probe = WorldPoint(origin.x + dx * t, origin.y + dy * t)
            if blocks_sight(self.tile_at(probe)):
                return False
        return True

    def biome_at(self, point: WorldPoint) -> Biome:
        address = self.chunk_address_at(point)
        return Biome(self.generator.biome_of(address))

    # --- entity registry ----------------------------------------------------

    def add_entity(self, entity: Entity) -> Entity:
        self.entities[entity.entity_id] = entity
        entity.chunk_key = self.chunk_address_at(entity.position).key
        self._spatial.setdefault(entity.chunk_key, set()).add(entity.entity_id)
        entity.record_history(self.now)
        return entity

    def remove_entity(self, entity_id: EntityId) -> Entity | None:
        entity = self.entities.pop(entity_id, None)
        if entity is None:
            return None
        bucket = self._spatial.get(entity.chunk_key)
        if bucket is not None:
            bucket.discard(entity_id)
            if not bucket:
                self._spatial.pop(entity.chunk_key, None)
        return entity

    def reindex(self, entity: Entity) -> None:
        """Move an entity between spatial buckets if it changed chunk.

        Called after every movement integration. The early return is the common
        case by a wide margin, which is exactly the property that makes a grid
        index worth having.
        """
        key = self.chunk_address_at(entity.position).key
        if key == entity.chunk_key:
            return
        previous = self._spatial.get(entity.chunk_key)
        if previous is not None:
            previous.discard(entity.entity_id)
            if not previous:
                self._spatial.pop(entity.chunk_key, None)
        entity.chunk_key = key
        self._spatial.setdefault(key, set()).add(entity.entity_id)

    def entities_in_chunk(self, chunk_key: str) -> list[Entity]:
        return [
            self.entities[entity_id]
            for entity_id in self._spatial.get(chunk_key, ())
            if entity_id in self.entities
        ]

    def entities_near(self, point: WorldPoint, radius: float) -> list[Entity]:
        """Every entity within ``radius`` tiles.

        Gathers the candidate chunks from the spatial hash, then filters by exact
        distance. The chunk sweep is bounded by the radius rather than by the
        world size, so this stays cheap as the corridor grows.
        """
        radius_squared = radius * radius
        span = int(radius // CHUNK_TILES) + 1
        found: list[Entity] = []
        seen: set[EntityId] = set()

        for key in self._candidate_chunk_keys(point, span):
            for entity_id in self._spatial.get(key, ()):
                if entity_id in seen:
                    continue
                seen.add(entity_id)
                entity = self.entities.get(entity_id)
                if entity is None:
                    continue
                if entity.position.distance_squared_to(point) <= radius_squared:
                    found.append(entity)
        return found

    def _candidate_chunk_keys(self, point: WorldPoint, span: int) -> list[str]:
        """Chunk keys within ``span`` chunks of a point, in both spaces."""
        keys: list[str] = []
        location = self.locate(point)

        if location.space_type is SpaceType.HUB:
            hub_id = location.hub_id or 0
            (base_x, _), (base_y, _) = _split_hub_tile(location.tile_x, location.tile_y)
            for dy in range(-span, span + 1):
                for dx in range(-span, span + 1):
                    keys.append(ChunkAddress.hub(hub_id, base_x + dx, base_y + dy).key)
            # A player near the rim can see into the corridor, so include the
            # corridor mouth as well.
            segment, lane, _, _ = world_to_edge(self.edge, point)
        else:
            segment = location.segment_index or 0
            lane = location.lane_offset or 0

        edge_id = self.edge.edge_id
        for lane_offset in range(lane - span, lane + span + 1):
            if lane_offset not in (-1, 0, 1):
                continue
            tier_min = 0 if lane_offset == 0 else 1
            if tier_min > self.topology.current_tier:
                continue
            for segment_index in range(segment - span, segment + span + 1):
                if 0 <= segment_index < self.topology.segments:
                    keys.append(
                        ChunkAddress.edge(edge_id, segment_index, lane_offset, tier_min).key
                    )
        return keys

    def nearest_enemy(
        self, origin: Entity, radius: float, hostile_to_players: bool = True
    ) -> Entity | None:
        """The closest valid target of the opposite allegiance.

        Used for soft aim and for NPC target selection, so allegiance is a
        parameter rather than a fixed rule.
        """
        best: Entity | None = None
        best_distance = radius * radius
        for candidate in self.entities_near(origin.position, radius):
            if candidate.entity_id == origin.entity_id or not candidate.is_alive:
                continue
            if hostile_to_players:
                if not candidate.is_npc:
                    continue
            elif not candidate.is_player:
                continue
            distance = candidate.position.distance_squared_to(origin.position)
            if distance <= best_distance:
                best_distance = distance
                best = candidate
        return best

    # --- weather ------------------------------------------------------------

    def update_weather(self, now: float, chooser) -> bool:
        """Roll new weather when the current spell expires.

        ``chooser`` is passed in rather than imported so the weather policy lives
        with the rest of the world simulation and this stays a state holder.
        Returns whether the weather actually changed.
        """
        if now < self._weather_until:
            return False
        previous = self.weather
        self.weather, duration = chooser(self)
        self._weather_until = now + duration
        return self.weather != previous

    # --- geometry helpers ---------------------------------------------------

    def corridor_length_tiles(self) -> float:
        return self.topology.segments * CHUNK_TILES

    def chunk_centre(self, address: ChunkAddress) -> WorldPoint:
        """The plane point at the middle of a chunk, for minimaps and spawning."""
        half = CHUNK_TILES * 0.5
        if address.space_type is SpaceType.HUB:
            hub = self.hubs[address.hub_id or 0]
            centre = hub.centre
            return WorldPoint(
                centre.x + address.chunk_x * CHUNK_TILES + half,
                centre.y + address.chunk_y * CHUNK_TILES + half,
            )
        return edge_to_world(
            self.edge, address.segment_index, address.lane_offset, half, half
        )

    def describe(self) -> dict[str, object]:
        """Human-readable state, for the debug endpoint and the README."""
        return {
            "world_seed": self.world_seed,
            "tick": self.tick_count,
            "players": len(self.players),
            "npcs": len(self.npcs),
            "loaded_chunks": len(self._chunks),
            "dirty_chunks": sum(1 for view in self._chunks.values() if view.dirty),
            "day_phase": round(self.day_phase, 4),
            "weather": self.weather,
            "topology": self.topology.snapshot(),
            "hubs": [
                {
                    "hub_id": hub.hub_id,
                    "name": hub.name,
                    "centre": [round(hub.centre.x, 2), round(hub.centre.y, 2)],
                    "radius_tiles": hub.radius_tiles,
                }
                for hub in self.hubs.values()
            ],
        }


def build_default_world(
    *, world_seed: int, clock: Clock, generator: ChunkGenerator, segments: int = CORRIDOR_SEGMENTS
) -> World:
    """The MVP world: two hubs facing each other across one corridor.

    Hub angles are opposite so the corridor runs through the origin, which makes
    the minimap readable and the coordinates easy to reason about while debugging.
    Long-term this becomes the sparse graph from Accordion Spec 7.3; the
    :class:`World` API already takes a list of hubs and a dict of edges for that
    reason.
    """
    separation = HUB_RADIUS_TILES * 2 + segments * CHUNK_TILES

    hub_a = HubDefinition(
        hub_id=0,
        name="Emberhold",
        angle_radians=math.pi,
        distance_tiles=separation / 2.0,
    )
    hub_b = HubDefinition(
        hub_id=1,
        name="Rookmarch",
        angle_radians=0.0,
        distance_tiles=separation / 2.0,
    )
    edge = EdgeDefinition(
        edge_id="emberhold-rookmarch",
        hub_a=hub_a,
        hub_b=hub_b,
        segments=segments,
    )
    return World(
        world_seed=world_seed,
        clock=clock,
        generator=generator,
        hubs=[hub_a, hub_b],
        edge=edge,
        segments=segments,
    )
