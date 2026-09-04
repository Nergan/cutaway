"""Area-of-interest filtering and snapshot assembly.

Two jobs that belong together because they share the same expensive query. For
each player this decides which chunks it should hold, which entities it can see,
and which of those changed since last time; then it turns that into the packets to
send.

The design point from TDD 5.4 is that the AOI set is *cacheable*: a player taking a
step usually sees exactly the same entities in exactly the same chunks. Tracking
what the client already knows, in :class:`~age.domain.entities.PlayerSession`, is
what turns a per-tick recomputation into a per-tick diff.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..domain.constants import (
    AOI_PRELOAD_RADIUS_CHUNKS,
    AOI_UNLOAD_RADIUS_CHUNKS,
    AOI_VIEW_DISTANCE_TILES,
    CHUNK_TILES,
    MAX_ENTITIES_PER_SNAPSHOT,
)
from ..domain.coordinates import ChunkAddress, SpaceType
from ..domain.entities import DirtyField, Entity, EntityId, PlayerSession
from ..domain.npc import AIState
from ..infrastructure import wire
from .world import World


@dataclass(slots=True)
class ClientUpdate:
    """Everything to send one client this snapshot, in send order."""

    spawns: list[bytes] = field(default_factory=list)
    despawns: list[bytes] = field(default_factory=list)
    snapshot: bytes | None = None
    chunk_keys_added: list[str] = field(default_factory=list)
    chunk_keys_removed: list[str] = field(default_factory=list)

    @property
    def frames(self) -> list[bytes]:
        """Spawns before the snapshot: a delta for an unknown entity is useless."""
        frames = list(self.despawns)
        frames.extend(self.spawns)
        if self.snapshot is not None:
            frames.append(self.snapshot)
        return frames


def chunks_in_view(world: World, entity: Entity, radius: int) -> set[str]:
    """Chunk keys within ``radius`` chunks of an entity, in both spaces.

    Includes hub chunks and corridor chunks, because a player near the corridor
    mouth can see into both and needs terrain for both.
    """
    keys: set[str] = set()
    location = world.locate(entity.position)

    if location.space_type is SpaceType.HUB:
        hub_id = location.hub_id or 0
        base_x = int(location.tile_x // CHUNK_TILES)
        base_y = int(location.tile_y // CHUNK_TILES)
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                keys.add(ChunkAddress.hub(hub_id, base_x + dx, base_y + dy).key)

    from ..domain.coordinates import world_to_edge

    segment, lane, _, _ = world_to_edge(world.edge, entity.position)
    edge_id = world.edge.edge_id
    topology = world.topology

    for lane_offset in range(lane - radius, lane + radius + 1):
        if lane_offset not in (-1, 0, 1):
            continue
        tier_min = 0 if lane_offset == 0 else 1
        if tier_min > topology.current_tier:
            continue
        for segment_index in range(segment - radius, segment + radius + 1):
            if not (0 <= segment_index < topology.segments):
                continue
            address = ChunkAddress.edge(edge_id, segment_index, lane_offset, tier_min)
            record = topology.chunks.get(address.key)
            if record is not None and record.is_simulated:
                keys.add(address.key)

    return keys


def visible_entities(world: World, viewer: Entity) -> list[Entity]:
    """Entities the viewer may know about.

    Distance-limited rather than chunk-limited, so an entity two tiles away across
    a chunk boundary is visible and one on the far side of the same chunk is not.
    Capped so a crowd cannot blow the bandwidth budget; the cap keeps the nearest,
    because those are the ones the player is interacting with.
    """
    candidates = world.entities_near(viewer.position, AOI_VIEW_DISTANCE_TILES)
    if len(candidates) <= MAX_ENTITIES_PER_SNAPSHOT:
        return candidates

    candidates.sort(key=lambda entity: entity.position.distance_squared_to(viewer.position))
    return candidates[:MAX_ENTITIES_PER_SNAPSHOT]


def build_update(
    world: World,
    session: PlayerSession,
    viewer: Entity,
    *,
    tick: int,
    server_time: float,
) -> ClientUpdate:
    """Diff the viewer's world against what the session already knows."""
    update = ClientUpdate()

    # --- chunk streaming ---------------------------------------------------
    #
    # Loading uses the preload radius and unloading the (larger) unload radius.
    # The gap between them is hysteresis: a player pacing across a boundary would
    # otherwise thrash the same chunk in and out every step.
    wanted = chunks_in_view(world, viewer, AOI_PRELOAD_RADIUS_CHUNKS)
    keepable = chunks_in_view(world, viewer, AOI_UNLOAD_RADIUS_CHUNKS)

    for key in wanted - session.loaded_chunks:
        update.chunk_keys_added.append(key)
        session.loaded_chunks.add(key)

    for key in list(session.loaded_chunks):
        if key not in keepable:
            update.chunk_keys_removed.append(key)
            session.loaded_chunks.discard(key)

    # --- entity spawn and despawn ------------------------------------------

    visible = visible_entities(world, viewer)
    visible_ids = {entity.entity_id for entity in visible}

    for entity_id in session.known_entities - visible_ids:
        update.despawns.append(wire.encode_despawn(entity_id, wire.DESPAWN_OUT_OF_RANGE))
    session.known_entities &= visible_ids

    deltas: list[wire.EntityDelta] = []

    for entity in visible:
        if entity.entity_id not in session.known_entities:
            session.known_entities.add(entity.entity_id)
            update.spawns.append(
                wire.encode_spawn(
                    entity_id=entity.entity_id,
                    kind=entity.kind,
                    archetype_or_class=entity.class_id,
                    name=entity.name,
                    x=entity.position.x,
                    y=entity.position.y,
                    facing=entity.facing,
                    health_percent=wire.encode_percent(entity.health, entity.max_health),
                    level=entity.level,
                    appearance=entity.appearance.pack(),
                )
            )
            # Freshly spawned: the spawn packet already carried everything, so no
            # delta is needed this snapshot.
            continue

        if entity.dirty is DirtyField.NONE:
            continue

        deltas.append(_delta_for(entity))

    update.snapshot = wire.encode_snapshot(
        tick=tick,
        server_time=server_time,
        acknowledged_input=session.last_input_sequence,
        topology_version=world.topology.topology_version,
        day_phase=world.day_phase,
        weather=world.weather,
        deltas=deltas,
    )
    return update


def _delta_for(entity: Entity) -> wire.EntityDelta:
    return wire.EntityDelta(
        entity_id=entity.entity_id,
        fields=entity.dirty,
        x=entity.position.x,
        y=entity.position.y,
        vx=entity.velocity[0],
        vy=entity.velocity[1],
        facing=entity.facing,
        health_percent=wire.encode_percent(entity.health, entity.max_health),
        resource_percent=wire.encode_percent(entity.resource, entity.max_resource),
        state=_state_byte(entity),
        appearance=entity.appearance.pack(),
    )


def _state_byte(entity: Entity) -> int:
    """Pack animation-relevant state into one byte.

    Bit 0 is alive, bits 1-3 are the AI state (or a movement state for players).
    The client uses it to pick an animation, so it carries intent rather than raw
    fields: "attacking" rather than "cooldown timestamp".
    """
    alive = 1 if entity.is_alive else 0
    if entity.is_npc:
        return alive | (int(entity.ai_state) & 0x07) << 1

    moving = entity.velocity[0] != 0.0 or entity.velocity[1] != 0.0
    player_state = AIState.PATROL if moving else AIState.IDLE
    return alive | (int(player_state) & 0x07) << 1


def entities_hearing(world: World, origin: Entity, radius: float) -> list[Entity]:
    """Players within earshot, for proximity chat and combat effects."""
    return [
        entity
        for entity in world.entities_near(origin.position, radius)
        if entity.is_player
    ]


def clear_dirty(world: World) -> None:
    """Reset every dirty flag after a snapshot round.

    Called once after all clients have been served, not per client: clearing
    per client would mean the second client never sees the change.
    """
    for entity in world.entities.values():
        entity.dirty = DirtyField.NONE
