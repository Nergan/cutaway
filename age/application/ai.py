"""The NPC AI system: spawning, target acquisition, and FSM execution.

The state *decisions* live in :mod:`age.domain.npc` as a pure function. This module
is the driver that gathers the inputs, calls it, and executes whatever state comes
back. Keeping the two apart is what lets the transition table be tested
exhaustively without a world, and it is the ``behaviour_driver`` seam TDD 12.4
wants for swapping in a behaviour tree later.

Decisions run at a third of the simulation rate; movement runs every tick. An NPC
that re-evaluated its whole situation 30 times a second would burn most of the
frame budget to reach the same conclusion 29 times.
"""

from __future__ import annotations

import math

from ..domain.constants import AI_DECISION_DIVISOR, CHUNK_TILES, TICK_SECONDS
from ..domain.coordinates import ChunkAddress, WorldPoint
from ..domain.entities import DirtyField, Entity, EntityId
from ..domain.hashing import combine, unit_float
from ..domain.npc import (
    AISnapshot,
    AIState,
    ARCHETYPES_BY_KEY,
    SPAWN_TABLE,
    NpcArchetype,
    next_state,
    speed_for_state,
)
from ..domain.tiles import BIOME_PROFILES, Biome
from ..infrastructure import wire
from .movement import find_walkable_near, step_towards
from .world import World

# How far an NPC wanders from where it spawned. Keeping patrols local means a
# chunk's population stays roughly where the spawner put it.
PATROL_RADIUS_TILES = 10.0

# NPCs per corridor chunk, before the biome's danger rating scales it.
BASE_SPAWN_COUNT = 3

# Guards per hub, spread around the plaza.
GUARDS_PER_HUB = 4


def spawn_for_chunk(world: World, address: ChunkAddress, now: float) -> list[Entity]:
    """Populate a newly activated corridor chunk.

    Deterministic from the chunk seed: the same chunk always gets the same
    creatures in the same places, so retiring and reactivating a lane does not
    reroll its inhabitants.
    """
    if address.space_type.name == "HUB":
        return []

    biome = Biome(world.generator.biome_of(address))
    danger = BIOME_PROFILES[biome].danger
    table = SPAWN_TABLE[min(danger, len(SPAWN_TABLE) - 1)]

    seed = combine(world.world_seed, hash_key(address.key), 0x5A1D)
    count = BASE_SPAWN_COUNT + danger // 2

    spawned: list[Entity] = []
    for slot in range(count):
        roll = unit_float(combine(seed, slot, 1))
        archetype = ARCHETYPES_BY_KEY[table[int(roll * len(table)) % len(table)]]

        tile_x = 2.0 + unit_float(combine(seed, slot, 2)) * (CHUNK_TILES - 4)
        tile_y = 2.0 + unit_float(combine(seed, slot, 3)) * (CHUNK_TILES - 4)
        from ..domain.coordinates import edge_to_world

        point = edge_to_world(
            world.edge, address.segment_index, address.lane_offset, tile_x, tile_y
        )
        point = find_walkable_near(world, point)

        spawned.append(_make_npc(world, archetype, point, now))

    return spawned


def spawn_hub_guards(world: World, now: float) -> list[Entity]:
    """Place guards around each hub plaza.

    Guards are what make the safe zone feel enforced rather than merely declared
    (GDD 11.1). They never flee and never leave their hub.
    """
    archetype = ARCHETYPES_BY_KEY["guard"]
    spawned: list[Entity] = []

    for hub in world.hubs.values():
        centre = hub.centre
        for index in range(GUARDS_PER_HUB):
            angle = (index / GUARDS_PER_HUB) * math.tau
            point = find_walkable_near(
                world,
                WorldPoint(centre.x + math.cos(angle) * 9.0, centre.y + math.sin(angle) * 9.0),
            )
            spawned.append(_make_npc(world, archetype, point, now))

    return spawned


def _make_npc(
    world: World, archetype: NpcArchetype, point: WorldPoint, now: float
) -> Entity:
    from ..domain.constants import ENTITY_NPC

    entity = Entity(
        entity_id=world.allocate_entity_id(),
        kind=ENTITY_NPC,
        position=point,
        facing=0.0,
        health=archetype.max_health,
        max_health=archetype.max_health,
        resource=0,
        max_resource=0,
        name=archetype.name,
        class_id=archetype.npc_id,
        archetype=archetype,
        speed=archetype.patrol_speed,
        radius=0.35,
        patrol_anchor=point,
        ai_state_entered_at=now,
    )
    return world.add_entity(entity)


def despawn_for_chunk(world: World, chunk_key: str) -> list[EntityId]:
    """Remove the NPCs belonging to a retiring chunk."""
    removed: list[EntityId] = []
    for entity in world.entities_in_chunk(chunk_key):
        if entity.is_npc:
            world.remove_entity(entity.entity_id)
            removed.append(entity.entity_id)
    return removed


def tick(world: World, now: float, delta_time: float, events) -> None:
    """Advance every NPC by one simulation step."""
    run_decisions = world.tick_count % AI_DECISION_DIVISOR == 0

    for entity in world.npcs:
        archetype = entity.archetype
        if archetype is None:
            continue

        if entity.ai_state is AIState.DEAD:
            _maybe_respawn(world, entity, now)
            continue

        if run_decisions:
            _decide(world, entity, archetype, now)

        _execute(world, entity, archetype, now, delta_time, events)


def _decide(world: World, entity: Entity, archetype: NpcArchetype, now: float) -> None:
    """Acquire a target if needed, then apply the transition table."""
    target = world.entities.get(entity.ai_target) if entity.ai_target else None

    if target is None or not target.is_alive:
        target = world.nearest_enemy(
            entity, archetype.detection_radius, hostile_to_players=False
        )
        entity.ai_target = target.entity_id if target else None

    distance = target.position.distance_to(entity.position) if target else None

    # A guard only engages inside its own hub, so it never abandons its post to
    # chase someone down the corridor.
    if archetype.key == "guard" and target is not None:
        if not world.is_in_hub(target.position):
            target = None
            distance = None
            entity.ai_target = None

    snapshot = AISnapshot(
        state=entity.ai_state,
        health_fraction=entity.health_fraction,
        target_distance=distance,
        has_target=target is not None,
        target_alive=bool(target and target.is_alive),
        time_in_state=now - entity.ai_state_entered_at,
        enemy_nearby=distance is not None and distance <= archetype.detection_radius * 1.5,
    )

    resolved = next_state(archetype, snapshot)
    if resolved is not entity.ai_state:
        entity.enter_ai_state(resolved, now)
        # A new state wants a fresh destination rather than the last one's.
        entity.patrol_target = None


def _execute(
    world: World,
    entity: Entity,
    archetype: NpcArchetype,
    now: float,
    delta_time: float,
    events,
) -> None:
    """Do whatever the current state means."""
    state = entity.ai_state
    speed = speed_for_state(archetype, state)

    if state is AIState.IDLE:
        if entity.velocity != (0.0, 0.0):
            entity.velocity = (0.0, 0.0)
            entity.mark(DirtyField.VELOCITY)
        return

    if state is AIState.PATROL:
        if entity.patrol_target is None or entity.position.distance_to(entity.patrol_target) < 0.8:
            entity.patrol_target = _pick_patrol_point(world, entity, now)
            if entity.patrol_target is None:
                entity.enter_ai_state(AIState.IDLE, now)
                return
        step_towards(world, entity, entity.patrol_target, speed, delta_time)
        return

    target = world.entities.get(entity.ai_target) if entity.ai_target else None
    if target is None:
        entity.enter_ai_state(AIState.IDLE, now)
        return

    if state is AIState.AGGRO:
        step_towards(world, entity, target.position, speed, delta_time)
        return

    if state is AIState.ATTACK:
        _face(entity, target.position)
        if entity.velocity != (0.0, 0.0):
            entity.velocity = (0.0, 0.0)
            entity.mark(DirtyField.VELOCITY)
        _try_attack(world, entity, archetype, target, now, events)
        return

    if state is AIState.FLEE:
        # Run directly away from the threat.
        dx = entity.position.x - target.position.x
        dy = entity.position.y - target.position.y
        length = math.hypot(dx, dy) or 1.0
        retreat = WorldPoint(
            entity.position.x + (dx / length) * 6.0,
            entity.position.y + (dy / length) * 6.0,
        )
        step_towards(world, entity, retreat, speed, delta_time)


def _try_attack(
    world: World,
    entity: Entity,
    archetype: NpcArchetype,
    target: Entity,
    now: float,
    events,
) -> None:
    """Land an attack if the cooldown and the geometry both allow it."""
    if (now - entity.last_attack_at) * 1000.0 < archetype.attack_cooldown_ms:
        return
    if target.position.distance_to(entity.position) > archetype.attack_range + target.radius:
        return
    if not world.has_line_of_sight(entity.position, target.position):
        return

    entity.last_attack_at = now
    damage = target.apply_damage(archetype.attack_damage)
    killed = not target.is_alive

    events.combat_resolved(
        entity.entity_id, target.entity_id, 0, damage, 0, killed
    )

    if killed and target.is_player:
        events.system_message(f"{target.name} was slain by a {archetype.name}.")


def _pick_patrol_point(world: World, entity: Entity, now: float) -> WorldPoint | None:
    """A random walkable point near the spawn anchor."""
    anchor = entity.patrol_anchor or entity.position
    seed = combine(entity.entity_id, int(now * 4.0), 0x9A71)

    for attempt in range(6):
        angle = unit_float(combine(seed, attempt, 1)) * math.tau
        radius = 2.0 + unit_float(combine(seed, attempt, 2)) * PATROL_RADIUS_TILES
        candidate = WorldPoint(
            anchor.x + math.cos(angle) * radius, anchor.y + math.sin(angle) * radius
        )
        if world.is_walkable_at(candidate):
            return candidate
    return None


def _face(entity: Entity, point: WorldPoint) -> None:
    facing = math.atan2(point.y - entity.position.y, point.x - entity.position.x)
    if abs(facing - entity.facing) > 0.01:
        entity.facing = facing
        entity.mark(DirtyField.FACING)


def _maybe_respawn(world: World, entity: Entity, now: float) -> None:
    """Bring a dead NPC back where it started, after a delay.

    Respawning in place rather than deleting keeps chunk population stable without
    the spawner having to run again, and keeps entity ids stable for anyone
    watching.
    """
    if entity.dead_until == 0.0:
        entity.dead_until = now + 20.0
        return
    if now < entity.dead_until:
        return

    archetype = entity.archetype
    if archetype is None:
        return

    entity.health = archetype.max_health
    entity.dead_until = 0.0
    entity.ai_target = None
    entity.patrol_target = None
    anchor = entity.patrol_anchor or entity.position
    entity.move_to(anchor.x, anchor.y)
    entity.enter_ai_state(AIState.IDLE, now)
    entity.mark(DirtyField.ALL)
    world.reindex(entity)


def hash_key(text: str) -> int:
    """Local string hash, so this module does not import the whole hashing API."""
    from ..domain.hashing import hash_string

    return hash_string(text)
