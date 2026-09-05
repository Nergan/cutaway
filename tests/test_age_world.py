"""Server-side tests for Age: the accordion, movement, combat, AI, and the sandbox.

The parity suite in ``test_age_client_parity.py`` proves the client and the server
agree. This one proves the server is right in the first place, and it is organised
around the invariants the specs actually name rather than around the module list:
INV-2 and INV-5 for the accordion, "no stuck states" for the AI, "the server owns
every position" for movement, and the persistence tiering from TDD 9.1.

Everything here runs on :class:`ManualClock`. A simulation with an injected clock
is a pure function of its inputs, so a fifteen-minute tier cooldown costs one line
instead of fifteen minutes, and nothing in this file sleeps or flakes.
"""

from __future__ import annotations

import asyncio
from math import inf, nextafter

import pytest

from age.application import ai, chat, combat, movement, session, terrain, weather
from age.application.accordion import WorldManager
from age.application.events import EventQueue
from age.application.world import World, build_default_world
from age.domain import classes, coordinates, hashing, items
from age.domain.constants import (
    BASE_MAX_HEALTH,
    CHANNEL_GLOBAL,
    CHANNEL_LOCAL,
    CHANNEL_SYSTEM,
    CHAT_MAX_LENGTH,
    CHAT_RATE_LIMIT,
    CHUNK_TILES,
    COMPOSE_LEVEL,
    CONTRACTION_PLAYER_THRESHOLD,
    CORRIDOR_SEGMENTS,
    ENTITY_NPC,
    ENTITY_PLAYER,
    EXPANSION_PLAYER_THRESHOLD,
    HEALTH_PER_LEVEL,
    HUB_RADIUS_TILES,
    MAX_LEVEL,
    MAX_NAME_LENGTH,
    MAX_TIER,
    REGROWTH_STAGE_SECONDS,
    RESPAWN_DELAY_SECONDS,
    TICK_SECONDS,
    TIER_COOLDOWN_SECONDS,
    WALK_SPEED_TILES_S,
)
from age.domain.coordinates import ChunkAddress, LocationRef, SpaceType, WorldPoint
from age.domain.entities import Appearance, DirtyField, Entity
from age.domain.items import INVENTORY_SLOTS
from age.domain.npc import (
    AGGRO_RELEASE_FACTOR,
    ARCHETYPES,
    ARCHETYPES_BY_KEY,
    AISnapshot,
    AIState,
    next_state,
    speed_for_state,
)
from age.domain.tiles import BUILD_RECIPES, HARVEST_RESULTS, Tile, is_walkable
from age.domain.topology import (
    ChunkState,
    IllegalTransition,
    TopologyState,
    chunks_for_tier,
    lanes_for_tier,
    tier_min_for_lane,
)
from age.infrastructure.clock import ManualClock
from age.infrastructure.generator import WorldGenerator
from age.infrastructure.memory_repositories import (
    MemoryCharacterRepository,
    MemoryTopologyRepository,
)
from age.infrastructure import wire

WORLD_SEED = 20260904


# --- fixtures ---------------------------------------------------------------


@pytest.fixture
def clock() -> ManualClock:
    return ManualClock(start=1000.0)


@pytest.fixture
def world(clock: ManualClock) -> World:
    """A bootstrapped world with tier 0 active.

    Two corridor segments rather than the default eight. The accordion rules do
    not depend on how long the corridor is, and eight segments of pure-Python
    terrain would dominate the runtime of every test in this file.
    """
    built = build_default_world(
        world_seed=WORLD_SEED,
        clock=clock,
        generator=WorldGenerator(WORLD_SEED),
        segments=2,
    )
    built.topology.bootstrap(clock.now())
    return built


@pytest.fixture
def manager(world: World) -> WorldManager:
    """A manager with the real cooldown.

    Not zero: with no cooldown the automatic evaluation undoes a forced tier on the
    very next tick, because an empty corridor always argues for contracting. The
    world starts at clock 1000, which is past the cooldown, so the first change a
    test asks for still goes through.
    """
    return WorldManager(world, EventQueue(), cooldown_seconds=TIER_COOLDOWN_SECONDS)


def _player(world: World, *, at: WorldPoint | None = None, class_id: int = 0) -> Entity:
    character_class = classes.get_class(class_id)
    max_health = int(BASE_MAX_HEALTH * character_class.health_multiplier)
    entity = Entity(
        entity_id=world.allocate_entity_id(),
        kind=ENTITY_PLAYER,
        position=at or world.spawn_point_for(world.hubs[0]),
        name="Tester",
        class_id=class_id,
        health=max_health,
        max_health=max_health,
        resource=200,
        max_resource=200,
    )
    return world.add_entity(entity)


def _npc(world: World, key: str, at: WorldPoint) -> Entity:
    archetype = ARCHETYPES_BY_KEY[key]
    entity = Entity(
        entity_id=world.allocate_entity_id(),
        kind=ENTITY_NPC,
        position=at,
        name=archetype.name,
        class_id=archetype.npc_id,
        health=archetype.max_health,
        max_health=archetype.max_health,
        archetype=archetype,
        speed=archetype.patrol_speed,
        radius=0.35,
        patrol_anchor=at,
    )
    return world.add_entity(entity)


def _run(scenario):
    """Drive one coroutine to completion.

    The repository has no async pytest plugin and does not need one for a handful
    of awaits; this matches how the other suites here handle the same problem.
    """
    return asyncio.run(scenario())


def _open_ground(world: World, near: WorldPoint, span: int = 3) -> None:
    """Pave a patch so a movement test is about movement and not about scenery.

    Terrain is procedural, so a hand-picked coordinate is not reliably walkable
    across a seed change. Writing the tiles is honest here: the overlay is exactly
    the mechanism players use to clear ground themselves.
    """
    for dy in range(-span, span + 1):
        for dx in range(-span, span + 1):
            world.set_tile_at(
                WorldPoint(near.x + dx, near.y + dy), int(Tile.BARE_GROUND)
            )


# --- topology: the accordion invariants -------------------------------------


def test_a_chunk_cannot_skip_the_preparing_step():
    topology = TopologyState(edge_id="e", segments=1)
    address = chunks_for_tier("e", 0, 1)[0]

    with pytest.raises(IllegalTransition):
        topology.transition(address, ChunkState.ACTIVE, 0.0)


def test_a_chunk_cannot_go_straight_from_active_to_inactive():
    topology = TopologyState(edge_id="e", segments=1)
    address = chunks_for_tier("e", 0, 1)[0]
    topology.bootstrap(0.0)

    with pytest.raises(IllegalTransition):
        topology.transition(address, ChunkState.INACTIVE, 0.0)


def test_transitioning_to_the_current_state_is_a_no_op():
    topology = TopologyState(edge_id="e", segments=1)
    address = chunks_for_tier("e", 0, 1)[0]
    topology.bootstrap(0.0)

    record = topology.transition(address, ChunkState.ACTIVE, 99.0)

    assert record.state is ChunkState.ACTIVE
    assert record.entered_at == 0.0, "A no-op transition must not restart the timer."


def test_the_topology_version_only_ever_rises():
    """INV-2."""
    topology = TopologyState(edge_id="e", segments=2)
    seen = [topology.topology_version]

    topology.bootstrap(0.0)
    seen.append(topology.topology_version)
    topology.begin_expansion(1.0)
    seen.append(topology.topology_version)
    topology.begin_contraction(2.0)
    seen.append(topology.topology_version)
    topology.begin_expansion(3.0)
    seen.append(topology.topology_version)

    assert seen == sorted(seen)
    assert seen[-1] > seen[0]


def test_bootstrap_does_not_move_the_version():
    """Starting the world is not a topology change; there is nobody to resync."""
    topology = TopologyState(edge_id="e", segments=2)
    before = topology.topology_version

    topology.bootstrap(0.0)

    assert topology.topology_version == before


def test_a_chunk_is_active_exactly_when_the_tier_reaches_it():
    """INV-5."""
    topology = TopologyState(edge_id="e", segments=2)
    topology.bootstrap(0.0)

    for record in topology.chunks.values():
        expected = topology.should_be_active(record.address)
        assert (record.state is ChunkState.ACTIVE) is expected, record.address.key


def test_expansion_widens_the_corridor_without_lengthening_it():
    """INV-6: expansion adds lanes; it does not renumber what is already there."""
    topology = TopologyState(edge_id="e", segments=3)
    topology.bootstrap(0.0)
    before = {record.address.key for record in topology.active_chunks()}

    topology.begin_expansion(1.0)
    topology.advance_transitions(100.0)
    after = {record.address.key for record in topology.active_chunks()}

    assert before < after, "Every tier-0 chunk must still be active."
    assert lanes_for_tier(0) == (0,)
    assert set(lanes_for_tier(1)) == {-1, 0, 1}
    assert len(after) == 3 * len(lanes_for_tier(1))


def test_expansion_stops_at_the_maximum_tier():
    topology = TopologyState(edge_id="e", segments=1)
    topology.bootstrap(0.0)

    for step in range(MAX_TIER + 3):
        topology.begin_expansion(float(step))

    assert topology.current_tier == MAX_TIER


def test_the_thresholds_leave_a_gap_so_the_world_cannot_flicker():
    topology = TopologyState(edge_id="e", segments=1)

    assert CONTRACTION_PLAYER_THRESHOLD < EXPANSION_PLAYER_THRESHOLD

    for population in range(CONTRACTION_PLAYER_THRESHOLD + 1, EXPANSION_PLAYER_THRESHOLD):
        assert topology.desired_tier(population) == topology.current_tier, population


def test_contraction_needs_the_population_to_fall_below_its_own_threshold():
    topology = TopologyState(edge_id="e", segments=1)
    topology.bootstrap(0.0)
    topology.begin_expansion(1.0)

    assert topology.desired_tier(EXPANSION_PLAYER_THRESHOLD - 1) == 1
    assert topology.desired_tier(CONTRACTION_PLAYER_THRESHOLD) == 0


def test_a_pinned_chunk_aborts_the_whole_contraction():
    topology = TopologyState(edge_id="e", segments=2)
    topology.bootstrap(0.0)
    topology.begin_expansion(1.0)
    topology.advance_transitions(100.0)
    pinned = next(
        record.address.key
        for record in topology.active_chunks()
        if record.address.tier_min == 1
    )

    retiring = topology.begin_contraction(200.0, frozenset({pinned}))

    assert retiring == []
    assert topology.current_tier == 1, "An aborted contraction must not move the tier."


def test_a_chunk_waits_in_preparing_until_its_terrain_exists():
    topology = TopologyState(edge_id="e", segments=1)
    topology.bootstrap(0.0)
    topology.begin_expansion(1.0)

    activated, _ = topology.advance_transitions(1000.0, lambda address: False)
    assert activated == [], "The timer must not activate a chunk with no tiles."

    activated, _ = topology.advance_transitions(1000.0, lambda address: True)
    assert {record.address.tier_min for record in activated} == {1}


def test_a_tier_that_falls_back_abandons_its_half_built_chunks():
    topology = TopologyState(edge_id="e", segments=1)
    topology.bootstrap(0.0)
    topology.begin_expansion(1.0)
    topology.begin_contraction(2.0)

    topology.advance_transitions(100.0)

    assert topology.current_tier == 0
    assert all(
        record.state is ChunkState.INACTIVE
        for record in topology.chunks.values()
        if record.address.tier_min == 1
    )


def test_a_retiring_chunk_keeps_being_simulated_while_it_empties():
    topology = TopologyState(edge_id="e", segments=1)
    topology.bootstrap(0.0)
    topology.begin_expansion(1.0)
    topology.advance_transitions(100.0)
    topology.begin_contraction(200.0)

    retiring = [
        record for record in topology.chunks.values() if record.state is ChunkState.RETIRING
    ]
    assert retiring
    assert all(record.is_simulated for record in retiring)


def test_a_stale_client_version_is_refused():
    topology = TopologyState(edge_id="e", segments=1)
    current = topology.topology_version

    assert topology.accepts_version(current)
    assert not topology.accepts_version(current - 1)
    assert not topology.accepts_version(current + 1), "A future version is tampering."


def test_a_lane_keeps_the_tier_it_was_conceived_at():
    """Lane terrain is seeded by tier_min, so it does not depend on expansion order."""
    first = chunks_for_tier("e", 1, 2)
    second = chunks_for_tier("e", 1, 2)

    assert [address.key for address in first] == [address.key for address in second]
    assert {address.tier_min for address in first if address.lane_offset == 0} == {0}
    assert {address.tier_min for address in first if address.lane_offset != 0} == {1}


# --- the world manager: policy and side effects -----------------------------


def test_bootstrap_populates_the_hubs_with_guards(world: World, manager: WorldManager):
    manager.bootstrap(world.now)

    guards = [entity for entity in world.npcs if entity.archetype.key == "guard"]
    assert len(guards) == ai.GUARDS_PER_HUB * len(world.hubs)
    assert all(world.is_in_hub(guard.position) for guard in guards)


def test_hub_population_does_not_widen_the_wilderness(world: World, manager: WorldManager):
    """Accordion Spec 3.2: a crowded market is not a reason to open new lanes."""
    for _ in range(EXPANSION_PLAYER_THRESHOLD + 2):
        _player(world)

    assert manager.corridor_population() == 0


def test_a_crowd_in_the_corridor_does_widen_it(world: World, manager: WorldManager):
    corridor = world.chunk_centre(ChunkAddress.edge(world.edge.edge_id, 0, 0, 0))
    for _ in range(EXPANSION_PLAYER_THRESHOLD):
        _player(world, at=corridor)

    assert manager.corridor_population() == EXPANSION_PLAYER_THRESHOLD

    report = manager.tick(world.now)

    assert report.tier_changed
    assert report.current_tier == 1


def test_the_dead_do_not_count_towards_expansion(world: World, manager: WorldManager):
    corridor = world.chunk_centre(ChunkAddress.edge(world.edge.edge_id, 0, 0, 0))
    for _ in range(EXPANSION_PLAYER_THRESHOLD):
        _player(world, at=corridor).health = 0

    assert manager.corridor_population() == 0


def test_expansion_queues_terrain_instead_of_generating_it_inline(
    world: World, manager: WorldManager, clock: ManualClock
):
    """Accordion Spec 7.6: a widening corridor must not stall the tick loop."""
    manager.force_tier(1, clock.now())

    assert manager.warmup_pending() > 0
    preparing = [
        record
        for record in world.topology.chunks.values()
        if record.state is ChunkState.PREPARING
    ]
    assert preparing
    assert all(not world.is_chunk_loaded(record.address) for record in preparing)


def test_a_chunk_does_not_go_active_before_its_terrain_is_built(
    world: World, manager: WorldManager, clock: ManualClock
):
    manager.force_tier(1, clock.now())
    clock.advance(600.0)

    report = manager.tick(clock.now())
    assert report.activated == [], "Nothing may activate while the queue is untouched."

    while manager.warm_next() is not None:
        pass
    report = manager.tick(clock.now())

    assert report.activated, "Once terrain exists the chunks must fade in."
    assert all(
        world.is_chunk_loaded(world.topology.chunks[key].address)
        for key in report.activated
    )


def test_urgent_warmups_jump_the_speculative_queue(world: World, manager: WorldManager):
    manager.enqueue_warmup(world.hub_chunk_addresses())
    lane = ChunkAddress.edge(world.edge.edge_id, 0, 1, 1)

    manager.enqueue_warmup([lane], urgent=True)

    assert manager.warm_next() == lane


def test_a_chunk_is_never_queued_twice(world: World, manager: WorldManager):
    lane = ChunkAddress.edge(world.edge.edge_id, 0, 1, 1)

    manager.enqueue_warmup([lane, lane])
    manager.enqueue_warmup([lane])

    assert manager.warmup_pending() == 1


def test_an_already_built_chunk_is_not_queued(world: World, manager: WorldManager):
    address = ChunkAddress.hub(0, 0, 0)
    world.chunk(address)

    manager.enqueue_warmup([address])

    assert manager.warmup_pending() == 0


def test_the_measured_chunk_cost_is_reported_to_the_tick_loop(
    world: World, manager: WorldManager
):
    manager.enqueue_warmup([ChunkAddress.hub(0, 4, 4)])
    assert manager.chunk_cost_seconds > 0.0, "The estimate must be usable before measuring."

    manager.warm_next()

    assert manager.chunk_cost_seconds > 0.0


def test_contraction_evacuates_players_to_a_hub(
    world: World, manager: WorldManager, clock: ManualClock
):
    """Accordion Spec 7.6: nobody is ever left standing in an unsimulated chunk."""
    manager.force_tier(1, clock.now())
    while manager.warm_next() is not None:
        pass
    clock.advance(600.0)
    manager.tick(clock.now())

    lane = ChunkAddress.edge(world.edge.edge_id, 0, 1, 1)
    stranded = _player(world, at=world.chunk_centre(lane))
    assert stranded.chunk_key == lane.key

    report = manager.force_tier(0, clock.now())

    assert report.evacuated == 1
    assert world.is_in_hub(stranded.position)
    assert stranded.dirty & DirtyField.POSITION


def test_a_retired_chunk_takes_its_creatures_with_it(
    world: World, manager: WorldManager, clock: ManualClock
):
    manager.force_tier(1, clock.now())
    while manager.warm_next() is not None:
        pass
    clock.advance(600.0)
    manager.tick(clock.now())
    outer = [entity for entity in world.npcs if entity.chunk_key.endswith("1")]
    assert outer, "The new lanes should have been populated on activation."

    manager.force_tier(0, clock.now())
    clock.advance(600.0)
    manager.tick(clock.now())

    assert all(entity.entity_id not in world.entities for entity in outer)


def test_a_lane_holding_player_work_gets_a_reprieve(
    world: World, manager: WorldManager, clock: ManualClock
):
    manager.force_tier(1, clock.now())
    while manager.warm_next() is not None:
        pass
    clock.advance(600.0)
    manager.tick(clock.now())

    lane = ChunkAddress.edge(world.edge.edge_id, 0, 1, 1)
    world.chunk(lane).set_tile(0, int(Tile.WALL_WOOD))

    report = manager.force_tier(0, clock.now())

    assert not report.tier_changed
    assert world.topology.current_tier == 1


def test_topology_survives_a_restart(world: World, manager: WorldManager):
    repository = MemoryTopologyRepository()
    manager.topology_repository = repository
    manager.force_tier(1, world.now)

    async def scenario():
        await manager.persist()
        return await repository.load(world.edge.edge_id)

    stored = _run(scenario)
    assert stored is not None
    world.topology.current_tier = 0
    world.topology.topology_version = 1
    WorldManager(world, EventQueue(), cooldown_seconds=0.0).restore(stored, world.now)

    assert world.topology.current_tier == 1
    assert world.topology.topology_version > 1


def test_a_restart_does_not_trust_the_stored_wall_clock(world: World):
    """The monotonic clock restarted with the process, so the timestamp is meaningless."""
    manager = WorldManager(world, EventQueue(), cooldown_seconds=0.0)

    manager.restore({"current_tier": 1, "topology_version": 9, "last_tier_change_at": 1e12}, 500.0)

    assert world.topology.last_tier_change_at == 500.0


# --- movement ---------------------------------------------------------------


def test_a_walled_tile_stops_a_player(world: World):
    spawn = world.spawn_point_for(world.hubs[0])
    _open_ground(world, spawn)
    player = _player(world, at=spawn)
    world.set_tile_at(WorldPoint(spawn.x + 1.0, spawn.y), int(Tile.WALL_STONE))

    result = movement.apply_input(world, player, (1.0, 0.0), False, 0.0, 1.0)

    assert result.collided
    assert result.position.x < spawn.x + 1.0


def test_a_player_slides_along_a_wall_rather_than_sticking_to_it(world: World):
    """A diagonal walk into a wall should keep the component that is not blocked."""
    spawn = world.spawn_point_for(world.hubs[0])
    _open_ground(world, spawn, span=6)
    player = _player(world, at=spawn)
    for offset in range(-4, 5):
        world.set_tile_at(
            WorldPoint(spawn.x + 1.0, spawn.y + offset), int(Tile.WALL_STONE)
        )

    result = movement.apply_input(world, player, (0.7071, 0.7071), False, 0.0, 0.25)

    assert result.collided
    assert result.position.x == spawn.x, "The blocked axis must not move at all."
    assert result.position.y > spawn.y, "The unblocked axis must still move."


def test_an_absurd_frame_time_cannot_teleport_a_player(world: World):
    """The simplest speed hack there is: claim a ten-second frame."""
    spawn = world.spawn_point_for(world.hubs[0])
    _open_ground(world, spawn, span=12)
    player = _player(world, at=spawn)

    movement.apply_input(world, player, (1.0, 0.0), True, 0.0, 10.0)

    travelled = player.position.distance_to(spawn)
    assert travelled <= movement.speed_for(player, True) * 0.25 + 1e-6


def test_a_plausible_prediction_is_accepted_verbatim(world: World):
    spawn = world.spawn_point_for(world.hubs[0])
    _open_ground(world, spawn, span=6)
    player = _player(world, at=spawn)
    predicted = WorldPoint(spawn.x + WALK_SPEED_TILES_S * TICK_SECONDS, spawn.y)

    result = movement.apply_input(
        world, player, (1.0, 0.0), False, 0.0, TICK_SECONDS, predicted
    )

    assert not result.corrected
    assert result.position == predicted


def test_a_prediction_that_drifts_too_far_is_overruled(world: World):
    spawn = world.spawn_point_for(world.hubs[0])
    _open_ground(world, spawn, span=12)
    player = _player(world, at=spawn)
    predicted = WorldPoint(spawn.x + 40.0, spawn.y)

    result = movement.apply_input(
        world, player, (1.0, 0.0), False, 0.0, TICK_SECONDS, predicted
    )

    assert result.corrected
    assert result.position != predicted


def test_a_prediction_inside_a_wall_is_never_accepted(world: World):
    spawn = world.spawn_point_for(world.hubs[0])
    _open_ground(world, spawn, span=6)
    player = _player(world, at=spawn)
    for offset in range(-2, 3):
        world.set_tile_at(
            WorldPoint(spawn.x + 1.0, spawn.y + offset), int(Tile.WALL_STONE)
        )
    inside_the_wall = WorldPoint(spawn.x + 1.5, spawn.y)

    result = movement.apply_input(
        world, player, (1.0, 0.0), False, 0.0, TICK_SECONDS, inside_the_wall
    )

    assert result.position != inside_the_wall
    assert world.is_walkable_at(result.position)


def test_a_class_speed_multiplier_reaches_the_integrator(world: World):
    rogue = _player(world, class_id=classes.CLASSES_BY_KEY["rogue"].class_id)
    warrior = _player(world, class_id=classes.CLASSES_BY_KEY["warrior"].class_id)

    assert movement.speed_for(rogue, False) > movement.speed_for(warrior, False)


def test_the_spawn_search_finds_ground_next_to_a_blocked_point(world: World):
    spawn = world.spawn_point_for(world.hubs[0])
    _open_ground(world, spawn)
    world.set_tile_at(spawn, int(Tile.WALL_STONE))

    found = movement.find_walkable_near(world, spawn)

    assert found != spawn
    assert world.is_walkable_at(found)


def test_the_spawn_search_gives_up_rather_than_looping(world: World):
    marooned = WorldPoint(1e9, 1e9)

    assert movement.find_walkable_near(world, marooned, max_radius=3.0) == marooned


def test_a_creature_that_meets_a_rock_goes_around_it(world: World):
    """The "no stuck states" acceptance test from the TDD."""
    spawn = world.spawn_point_for(world.hubs[0])
    _open_ground(world, spawn, span=6)
    wolf = _npc(world, "wolf", spawn)
    for offset in (-2, -1, 0, 1, 2):
        world.set_tile_at(
            WorldPoint(spawn.x + 1.0, spawn.y + offset), int(Tile.WALL_STONE)
        )

    for _ in range(10):
        movement.step_towards(
            world, wolf, WorldPoint(spawn.x + 6.0, spawn.y), 4.0, TICK_SECONDS
        )

    assert wolf.position.distance_to(spawn) > 0.1, "It should have slid, not ground."


# --- combat -----------------------------------------------------------------


def test_an_unknown_ability_is_refused(world: World):
    player = _player(world)

    outcome = combat.resolve_action(world, player, 9999, player.position, 0, world.now)

    assert not outcome.ok
    assert outcome.error == wire.ERROR_INVALID


def test_a_class_cannot_cast_outside_its_own_kit(world: World):
    player = _player(world, class_id=classes.CLASSES_BY_KEY["warrior"].class_id)
    foreign = classes.ABILITIES["ember_bolt"]
    assert foreign not in player.character_class.abilities

    outcome = combat.resolve_action(
        world, player, foreign.ability_id, player.position, 0, world.now
    )

    assert not outcome.ok
    assert outcome.error == wire.ERROR_INVALID


def test_a_dead_player_cannot_act(world: World):
    player = _player(world)
    player.health = 0
    cleave = classes.ABILITIES["cleave"]

    outcome = combat.resolve_action(
        world, player, cleave.ability_id, player.position, 0, world.now
    )

    assert outcome.error == wire.ERROR_DEAD


def test_an_ability_on_cooldown_says_so(world: World):
    corridor = world.chunk_centre(ChunkAddress.edge(world.edge.edge_id, 0, 0, 0))
    _open_ground(world, corridor)
    player = _player(world, at=corridor)
    cleave = classes.ABILITIES["cleave"]
    player.cooldowns[cleave.ability_id] = world.now + 5.0

    outcome = combat.resolve_action(
        world, player, cleave.ability_id, corridor, 0, world.now
    )

    assert outcome.error == wire.ERROR_ON_COOLDOWN


def test_spamming_is_rate_limited_separately_from_cooldowns(world: World):
    corridor = world.chunk_centre(ChunkAddress.edge(world.edge.edge_id, 0, 0, 0))
    _open_ground(world, corridor)
    player = _player(world, at=corridor)
    cleave = classes.ABILITIES["cleave"]
    player.last_ability_at = world.now

    outcome = combat.resolve_action(
        world, player, cleave.ability_id, corridor, 0, world.now
    )

    assert outcome.error == wire.ERROR_RATE_LIMITED


def test_a_hub_refuses_anything_that_could_hurt_another_player(world: World):
    """GDD 11.1."""
    player = _player(world)
    assert world.is_in_hub(player.position)
    cleave = classes.ABILITIES["cleave"]

    outcome = combat.resolve_action(
        world, player, cleave.ability_id, player.position, 0, world.now
    )

    assert outcome.error == wire.ERROR_SAFE_ZONE


def test_healing_still_works_inside_a_hub(world: World):
    healer = _player(world, class_id=classes.CLASSES_BY_KEY["healer"].class_id)
    wounded = _player(world, at=healer.position)
    wounded.health = 10
    mend = classes.ABILITIES["mend"]

    outcome = combat.resolve_action(
        world, healer, mend.ability_id, wounded.position, wounded.entity_id, world.now
    )

    assert outcome.ok
    assert outcome.total_healing > 0
    assert wounded.health > 10


def test_an_ability_with_no_resource_left_is_refused(world: World):
    corridor = world.chunk_centre(ChunkAddress.edge(world.edge.edge_id, 0, 0, 0))
    _open_ground(world, corridor)
    player = _player(world, at=corridor)
    player.resource = 0
    cleave = classes.ABILITIES["cleave"]

    outcome = combat.resolve_action(
        world, player, cleave.ability_id, corridor, 0, world.now
    )

    assert outcome.error == wire.ERROR_NO_RESOURCE


def test_an_out_of_range_aim_is_clamped_rather_than_swallowed(world: World):
    corridor = world.chunk_centre(ChunkAddress.edge(world.edge.edge_id, 0, 0, 0))
    _open_ground(world, corridor, span=8)
    player = _player(world, at=corridor)
    cleave = classes.ABILITIES["cleave"]
    far = WorldPoint(corridor.x + 50.0, corridor.y)

    outcome = combat.resolve_action(world, player, cleave.ability_id, far, 0, world.now)

    assert outcome.ok
    assert outcome.impact is not None
    assert outcome.impact.distance_to(corridor) == pytest.approx(cleave.range_tiles)


def test_a_wall_between_the_caster_and_the_impact_blocks_the_cast(world: World):
    corridor = world.chunk_centre(ChunkAddress.edge(world.edge.edge_id, 0, 0, 0))
    _open_ground(world, corridor, span=8)
    player = _player(world, at=corridor)
    bolt = classes.ABILITIES["ember_bolt"]
    player.class_id = classes.CLASSES_BY_KEY["mage"].class_id
    for offset in (-1, 0, 1):
        world.set_tile_at(
            WorldPoint(corridor.x + 3.0, corridor.y + offset), int(Tile.WALL_STONE)
        )

    outcome = combat.resolve_action(
        world, player, bolt.ability_id, WorldPoint(corridor.x + 6.0, corridor.y), 0, world.now
    )

    assert outcome.error == wire.ERROR_OUT_OF_RANGE


def test_hitting_a_creature_makes_it_care_even_from_out_of_earshot(world: World):
    corridor = world.chunk_centre(ChunkAddress.edge(world.edge.edge_id, 0, 0, 0))
    _open_ground(world, corridor, span=8)
    player = _player(world, at=corridor)
    wolf = _npc(world, "wolf", WorldPoint(corridor.x + 1.0, corridor.y))
    assert wolf.ai_target is None
    cleave = classes.ABILITIES["cleave"]

    outcome = combat.resolve_action(
        world, player, cleave.ability_id, wolf.position, wolf.entity_id, world.now
    )

    assert outcome.ok
    assert outcome.total_damage > 0
    assert wolf.ai_target == player.entity_id


def test_a_kill_is_reported_as_such(world: World):
    corridor = world.chunk_centre(ChunkAddress.edge(world.edge.edge_id, 0, 0, 0))
    _open_ground(world, corridor, span=8)
    player = _player(world, at=corridor)
    slime = _npc(world, "slime", WorldPoint(corridor.x + 1.0, corridor.y))
    slime.health = 1
    cleave = classes.ABILITIES["cleave"]

    outcome = combat.resolve_action(
        world, player, cleave.ability_id, slime.position, slime.entity_id, world.now
    )

    assert outcome.hits
    assert outcome.hits[0][3] is True
    assert not slime.is_alive


def test_lag_compensation_rewinds_only_as_far_as_the_window_allows(world: World):
    corridor = world.chunk_centre(ChunkAddress.edge(world.edge.edge_id, 0, 0, 0))
    _open_ground(world, corridor, span=10)
    player = _player(world, at=corridor)
    slime = _npc(world, "slime", WorldPoint(corridor.x + 1.0, corridor.y))
    slime.record_history(world.now)
    slime.move_to(corridor.x + 40.0, corridor.y)
    slime.record_history(world.now + 0.05)
    world.reindex(slime)
    cleave = classes.ABILITIES["cleave"]

    stale = combat.resolve_action(
        world,
        player,
        cleave.ability_id,
        WorldPoint(corridor.x + 1.0, corridor.y),
        0,
        world.now + 0.05,
        client_time_offset=100.0,
    )

    assert stale.ok
    assert stale.hits == [], "A request older than the window resolves in the present."


def test_a_regeneration_rate_below_one_point_per_tick_still_heals(world: World):
    """Truncating each tick independently would leave a slow regen at zero forever."""
    player = _player(world)
    player.health = 50
    naive = int(0.5 * TICK_SECONDS)
    assert naive == 0, "One tick of this rate rounds to nothing on its own."

    for _ in range(int(4.0 / TICK_SECONDS)):
        combat.regenerate(player, TICK_SECONDS, 0.5, 0.0)

    assert player.health == 52


def test_regeneration_tracks_its_nominal_rate(world: World):
    player = _player(world)
    player.health = 50
    player.resource = 50

    for _ in range(int(10.0 / TICK_SECONDS)):
        combat.regenerate(player, TICK_SECONDS, 3.0, 6.0)

    assert player.health == pytest.approx(80, abs=1)
    assert player.resource == pytest.approx(110, abs=1)


def test_regeneration_stops_at_the_cap_and_forgets_its_carry(world: World):
    player = _player(world)
    player.health = player.max_health - 1
    player.health_carry = 0.9

    for _ in range(60):
        combat.regenerate(player, TICK_SECONDS, 30.0, 0.0)

    assert player.health == player.max_health
    assert player.health_carry == 0.0


def test_the_dead_do_not_regenerate(world: World):
    player = _player(world)
    player.health = 0
    player.health_carry = 0.9

    combat.regenerate(player, 1.0, 100.0, 100.0)

    assert player.health == 0
    assert player.health_carry == 0.0


def test_every_class_kit_is_castable(world: World):
    """A class whose abilities are not in the catalogue would be unplayable."""
    for character_class in classes.CLASSES:
        for ability in character_class.abilities:
            assert classes.get_ability(ability.ability_id) is ability


def test_a_pure_class_does_not_hold_the_same_ability_twice():
    for character_class in classes.CLASSES:
        keys = [ability.key for ability in character_class.abilities]
        assert len(keys) == len(set(keys)), character_class.key


def test_all_fourteen_classes_exist_and_are_named_distinctly():
    assert len(classes.CLASSES) == 14
    assert len({entry.class_id for entry in classes.CLASSES}) == 14
    assert len({entry.key for entry in classes.CLASSES}) == 14


def test_every_pairing_of_halves_has_its_own_signature_ability():
    """4 base + 4 pure + 6 hybrid signatures is what makes 14 kits from 14 abilities."""
    signatures = set(classes.PURE_ABILITY.values()) | set(classes.HYBRID_ABILITY.values())

    assert len(classes.PURE_ABILITY) == 4
    assert len(classes.HYBRID_ABILITY) == 6
    assert len(signatures) == 10, "No signature may be shared between two pairings."


def test_a_hybrid_holds_both_halves_plus_its_signature():
    paladin = classes.CLASSES_BY_KEY["paladin"]
    keys = {ability.key for ability in paladin.abilities}

    assert not paladin.is_pure
    # The origin half brings its whole pair, the added half its opener, and the
    # pairing its signature — on top of the basic attack every class has.
    assert keys == {"strike", "cleave", "shield_bash", "mend", "consecrate"}


def test_only_the_four_base_classes_are_offered_at_creation():
    """GDD 6.3: hybrids are earned at level-up, not chosen from a menu."""
    assert [entry.key for entry in classes.BASE_CLASSES] == [
        "warrior",
        "healer",
        "mage",
        "rogue",
    ]
    assert all(entry.chosen is None for entry in classes.BASE_CLASSES)


@pytest.mark.parametrize("entry", classes.CLASSES, ids=lambda entry: entry.key)
def test_every_class_has_between_three_and_five_abilities(entry):
    """GDD 7.2 budgets 3-5 per class, and counts the basic attack among them."""
    abilities = entry.abilities

    assert 3 <= len(abilities) <= 5
    assert len(set(abilities)) == len(abilities), "no ability twice in one kit"
    assert abilities[0].resource_cost == 0, "the basic attack is free"
    assert abilities[0] is classes.BASIC_ATTACK[entry.origin]


def test_a_base_class_composes_into_the_pairing_class():
    warrior = classes.CLASSES_BY_KEY["warrior"]

    assert classes.compose(warrior.class_id, classes.BaseClass.HEALER).key == "paladin"
    assert classes.compose(warrior.class_id, classes.BaseClass.WARRIOR).key == "warmaster"


def test_a_pairing_is_the_same_class_from_either_side():
    """A warrior who studies healing and a healer who takes up the sword agree."""
    from_warrior = classes.compose(classes.CLASSES_BY_KEY["warrior"].class_id, classes.BaseClass.HEALER)
    from_healer = classes.compose(classes.CLASSES_BY_KEY["healer"].class_id, classes.BaseClass.WARRIOR)

    assert from_warrior is from_healer


def test_an_already_composed_class_cannot_compose_again():
    """The MVP has two halves, so there is exactly one composition per character."""
    paladin = classes.CLASSES_BY_KEY["paladin"]

    assert classes.compose(paladin.class_id, classes.BaseClass.MAGE) is None


def test_a_hybrid_class_id_requested_at_creation_collapses_to_its_origin():
    """A client that offers the wrong menu must not be able to skip the level-up."""
    shaman = classes.CLASSES_BY_KEY["shaman"]

    resolved = classes.base_class_or_default(shaman.class_id)

    assert resolved.key == "healer", "Shaman is Healer + Mage, so it starts as a Healer."
    assert resolved.is_base


def test_an_unknown_class_id_falls_back_rather_than_raising():
    """It arrives from an untrusted client or a stale row; neither is fatal."""
    assert classes.get_class(9999).class_id == 0


# --- levelling and the composition choice ------------------------------------


def _character(**overrides) -> Entity:
    """A bare player entity. No world needed: progression touches nothing but the entity."""
    base = {
        "entity_id": 1,
        "kind": ENTITY_PLAYER,
        "position": WorldPoint(0.0, 0.0),
        "name": "Rowan",
        "class_id": 0,
    }
    base.update(overrides)
    return Entity(**base)


def test_a_fresh_character_is_not_yet_owed_a_class_choice():
    assert not _character(level=1).can_compose


def test_the_first_level_up_owes_the_character_a_class_choice():
    assert _character(level=COMPOSE_LEVEL).can_compose


def test_a_composed_character_is_never_owed_the_choice_again():
    """Derived from the class rather than stored, so it cannot be spent twice."""
    paladin = classes.CLASSES_BY_KEY["paladin"]

    assert not _character(level=COMPOSE_LEVEL + 5, class_id=paladin.class_id).can_compose


def test_an_npc_is_never_owed_a_class_choice():
    assert not _character(kind=ENTITY_NPC, level=9).can_compose


def _simulation(world: World):
    from age.application.simulation import Simulation

    events = EventQueue()
    return Simulation(
        world=world,
        manager=WorldManager(world, events, cooldown_seconds=TIER_COOLDOWN_SECONDS),
        sessions=session.SessionService(world),
        chat=chat.ChatService(),
        events=events,
    )


def test_experience_accumulates_without_a_level_up_below_the_threshold(world: World):
    from age.application.simulation import TickReport

    sim = _simulation(world)
    entity = _character()
    report = TickReport(tick=0)

    sim.grant_experience(entity, 10, report)

    assert entity.level == 1
    assert entity.experience == 10
    assert entity.entity_id in report.progressed


def test_filling_the_bar_levels_up_and_carries_the_remainder(world: World):
    from age.application.simulation import TickReport

    sim = _simulation(world)
    entity = _character()
    threshold = classes.experience_for_level(1)

    sim.grant_experience(entity, threshold + 7, TickReport(tick=0))

    assert entity.level == 2
    assert entity.experience == 7, "the overflow counts towards the next level"


def test_one_grant_can_cross_several_levels(world: World):
    from age.application.simulation import TickReport

    sim = _simulation(world)
    entity = _character()
    enough = classes.experience_for_level(1) + classes.experience_for_level(2)

    sim.grant_experience(entity, enough, TickReport(tick=0))

    assert entity.level == 3


def test_levelling_never_passes_the_cap(world: World):
    from age.application.simulation import TickReport

    sim = _simulation(world)
    entity = _character()

    sim.grant_experience(entity, 10_000_000, TickReport(tick=0))

    assert entity.level == MAX_LEVEL


def test_killing_an_npc_pays_its_experience_and_drops_its_loot(world: World):
    """The whole reward path, end to end, through the real action handler.

    The combat tests above stop at :func:`combat.resolve_action` and the progression tests
    below start at :meth:`grant_experience`, and the join between the two was where a real
    bug lived: the kill branch passed the wrong number of arguments on to
    ``grant_experience``, so the first time anything actually died the tick raised. Nothing
    covered that one line, because no test went in through the command queue.

    In the corridor rather than the hub, since a hub refuses anything harmful.
    """
    corridor = world.chunk_centre(ChunkAddress.edge(world.edge.edge_id, 0, 0, 0))
    _open_ground(world, corridor, span=8)

    sim = _simulation(world)

    async def scenario():
        return await sim.sessions.join(
            session_id="s-kill", character_name="Rowan", class_id=0, appearance=(0,) * 5
        )

    attacker = _run(scenario).entity
    attacker.move_to(corridor.x, corridor.y)
    world.reindex(attacker)

    victim = _npc(world, "slime", WorldPoint(corridor.x + 1.0, corridor.y))
    victim.health = 1

    sim.enqueue(
        "s-kill",
        wire.ActionCommand(
            sequence=1,
            topology_version=world.topology.topology_version,
            ability_id=classes.get_class(attacker.class_id).abilities[0].ability_id,
            target_entity=victim.entity_id,
            target_x=victim.position.x,
            target_y=victim.position.y,
        ),
    )
    report = sim.tick()

    assert not victim.is_alive, "a one-health target hit by a basic attack has to die"
    assert attacker.experience > 0, "a kill has to pay experience"
    assert attacker.inventory, "a kill has to drop the archetype's loot"
    assert attacker.entity_id in report.progressed
    assert attacker.entity_id in report.inventories, (
        "the owner has to be told their pack changed, or the loot is invisible"
    )


def test_an_ability_reaches_the_client_as_a_combat_event_and_a_spent_cooldown(world: World):
    """The complaint was that skills do nothing, so this covers every link at once.

    Command queue in, damage out, and — the part that was actually missing — a combat
    event on the tick report for the transport to send. The server was resolving casts
    correctly all along and telling nobody, which from a player's seat is the same
    thing as not resolving them.
    """
    corridor = world.chunk_centre(ChunkAddress.edge(world.edge.edge_id, 0, 0, 0))
    _open_ground(world, corridor, span=8)

    sim = _simulation(world)

    async def scenario():
        return await sim.sessions.join(
            session_id="s-cast", character_name="Rowan", class_id=0, appearance=(0,) * 5
        )

    caster = _run(scenario).entity
    caster.move_to(corridor.x, corridor.y)
    world.reindex(caster)

    victim = _npc(world, "golem", WorldPoint(corridor.x + 1.0, corridor.y))
    ability = classes.get_class(caster.class_id).abilities[0]
    before = caster.resource

    sim.enqueue(
        "s-cast",
        wire.ActionCommand(
            sequence=1,
            topology_version=world.topology.topology_version,
            ability_id=ability.ability_id,
            target_entity=victim.entity_id,
            target_x=victim.position.x,
            target_y=victim.position.y,
        ),
    )
    report = sim.tick()

    assert report.actions_resolved == 1
    assert not report.rejections
    assert victim.health < victim.max_health, "the cast has to actually land"

    hits = [event for event in report.events.combat if event.damage > 0]
    assert hits, "a hit that is never reported is a skill that does nothing"
    assert hits[0].attacker_id == caster.entity_id
    assert hits[0].target_id == victim.entity_id
    assert hits[0].ability_id == ability.ability_id

    assert caster.cooldowns[ability.ability_id] > world.now, (
        "the button has nothing to sweep without a cooldown to sweep over"
    )
    if ability.resource_cost > 0:
        assert caster.resource == before - ability.resource_cost


def test_a_missed_ability_is_still_reported(world: World):
    """Otherwise a bad aim is indistinguishable from a broken skill."""
    corridor = world.chunk_centre(ChunkAddress.edge(world.edge.edge_id, 0, 0, 0))
    _open_ground(world, corridor, span=8)

    sim = _simulation(world)

    async def scenario():
        return await sim.sessions.join(
            session_id="s-miss", character_name="Rowan", class_id=0, appearance=(0,) * 5
        )

    caster = _run(scenario).entity
    caster.move_to(corridor.x, corridor.y)
    world.reindex(caster)
    ability = classes.get_class(caster.class_id).abilities[0]

    sim.enqueue(
        "s-miss",
        wire.ActionCommand(
            sequence=1,
            topology_version=world.topology.topology_version,
            ability_id=ability.ability_id,
            target_entity=0,
            target_x=corridor.x + 1.0,
            target_y=corridor.y,
        ),
    )
    report = sim.tick()

    assert report.events.combat, "an empty swing still has to be answered"
    assert report.events.combat[0].damage == 0


def test_a_level_up_restores_the_character_to_full(world: World):
    """A level-up that left someone injured would read as a punishment."""
    from age.application.simulation import TickReport

    sim = _simulation(world)
    entity = _character()
    entity.health = 3
    entity.resource = 1

    sim.grant_experience(entity, classes.experience_for_level(1), TickReport(tick=0))

    assert entity.health == entity.max_health
    assert entity.resource == entity.max_resource


def test_composing_swaps_the_class_and_its_pools(world: World):
    from age.application.simulation import TickReport

    sim = _simulation(world)
    entity = _character(level=COMPOSE_LEVEL)
    report = TickReport(tick=0)

    sim._apply_compose(entity, wire.ComposeRequest(half=int(classes.BaseClass.HEALER)), report)

    paladin = classes.CLASSES_BY_KEY["paladin"]
    assert entity.class_id == paladin.class_id
    assert entity.max_health == (
        int(BASE_MAX_HEALTH * paladin.health_multiplier)
        + HEALTH_PER_LEVEL * (COMPOSE_LEVEL - 1)
    ), "composing must take the new multiplier without spending the levels already earned"
    assert entity.entity_id in report.progressed


def test_composing_without_the_level_is_ignored(world: World):
    """A stale client that has not seen its own level yet, or a forged packet."""
    from age.application.simulation import TickReport

    sim = _simulation(world)
    entity = _character(level=1)

    sim._apply_compose(entity, wire.ComposeRequest(half=int(classes.BaseClass.MAGE)), TickReport(tick=0))

    assert entity.class_id == 0


def test_composing_twice_is_ignored(world: World):
    from age.application.simulation import TickReport

    sim = _simulation(world)
    entity = _character(level=COMPOSE_LEVEL)

    sim._apply_compose(entity, wire.ComposeRequest(half=int(classes.BaseClass.HEALER)), TickReport(tick=0))
    sim._apply_compose(entity, wire.ComposeRequest(half=int(classes.BaseClass.MAGE)), TickReport(tick=0))

    assert entity.class_id == classes.CLASSES_BY_KEY["paladin"].class_id


def test_a_half_outside_the_enum_is_ignored(world: World):
    from age.application.simulation import TickReport

    sim = _simulation(world)
    entity = _character(level=COMPOSE_LEVEL)

    sim._apply_compose(entity, wire.ComposeRequest(half=200), TickReport(tick=0))

    assert entity.class_id == 0


# --- items, the pack, and what wearing something is worth --------------------


def test_every_item_in_the_catalogue_has_its_own_id():
    """Ids are protocol constants, so a collision is a client showing the wrong thing."""
    ids = [item.item_id for item in items.ITEMS.values()]

    assert len(ids) == len(set(ids))
    assert 0 not in ids, "id zero is reserved for an empty equipment slot on the wire"


def test_an_item_is_equippable_exactly_when_it_names_a_slot():
    for item in items.ITEMS.values():
        wearable = item.kind is items.ItemKind.EQUIPMENT
        assert wearable == (item.slot is not items.EquipmentSlot.NONE), (
            f"{item.key} disagrees with itself about whether it can be worn"
        )


def test_every_material_the_world_yields_or_spends_is_in_the_catalogue():
    """The catalogue is what the client draws from; a gap there is an invisible stack."""
    from_harvest = {material for _, material, _ in HARVEST_RESULTS.values()}
    from_recipes = set(BUILD_RECIPES)
    from_loot = {key for archetype in ARCHETYPES for key, _ in archetype.loot}

    assert (from_harvest | from_recipes | from_loot) <= set(items.ITEMS)


def test_every_drop_table_belongs_to_an_archetype_that_exists():
    """A typo here would be a table that never rolls, which nothing else would notice."""
    assert set(items.DROP_TABLES) <= set(ARCHETYPES_BY_KEY)


def test_every_drop_names_an_item_that_exists():
    for table in items.DROP_TABLES.values():
        for drop in table:
            assert drop.item_key in items.ITEMS


def test_the_same_corpse_always_rolls_the_same_loot():
    """Seeded from the victim, so a replayed tick pays out identically."""
    once = items.roll_drops("bandit", 4242)
    twice = items.roll_drops("bandit", 4242)

    assert once == twice


def test_a_creature_with_no_drop_table_rolls_nothing():
    assert items.roll_drops("townsfolk", 1) == ()


def test_a_pack_tops_up_an_existing_stack_before_opening_a_new_slot():
    entity = _character()

    entity.give("wood", 30)
    entity.give("wood", 12)

    assert entity.count_of("wood") == 42
    assert len(entity.inventory) == 1


def test_a_pack_splits_across_slots_once_a_stack_is_full():
    entity = _character()

    entity.give("wood", 150)

    assert entity.count_of("wood") == 150
    assert [stack.count for stack in entity.inventory] == [99, 51]


def test_a_full_pack_reports_how_much_it_could_not_take():
    """The caller has to know, or the rest of a drop vanishes without a word."""
    entity = _character()
    for index in range(INVENTORY_SLOTS):
        entity.give("rusted_blade", 1)
        assert len(entity.inventory) == index + 1

    stored = entity.give("bandit_helm", 1)

    assert stored == 0
    assert entity.count_of("bandit_helm") == 0


def test_taking_more_than_is_carried_takes_nothing_at_all():
    entity = _character()
    entity.give("wood", 3)

    assert not entity.take("wood", 5)
    assert entity.count_of("wood") == 3


def test_wearing_a_helm_raises_the_health_pool_and_taking_it_off_lowers_it():
    entity = _character()
    entity.refresh_stats()
    bare = entity.max_health
    entity.give("bandit_helm", 1)

    assert entity.equip(0)
    assert entity.max_health == bare + items.BANDIT_HELM.bonus_health

    assert entity.unequip(int(items.EquipmentSlot.HEAD))
    assert entity.max_health == bare
    assert entity.count_of("bandit_helm") == 1


def test_equipment_bonuses_stack_across_slots():
    entity = _character()
    entity.refresh_stats()
    bare = entity.max_health
    entity.give("bandit_helm", 1)
    entity.give("padded_jerkin", 1)

    entity.equip(0)
    entity.equip(0)

    assert entity.max_health == (
        bare + items.BANDIT_HELM.bonus_health + items.PADDED_JERKIN.bonus_health
    )


def test_wearing_something_into_an_occupied_slot_returns_the_old_piece_to_the_pack():
    entity = _character()
    entity.give("leather_hood", 1)
    entity.give("bandit_helm", 1)

    entity.equip(0)
    entity.equip(0)

    assert entity.equipment[int(items.EquipmentSlot.HEAD)] == "bandit_helm"
    assert entity.count_of("leather_hood") == 1


def test_a_swap_still_works_with_no_free_slot_left():
    """The incoming piece vacates its slot before the outgoing one needs one."""
    entity = _character()
    entity.give("leather_hood", 1)
    entity.equip(0)
    for _ in range(INVENTORY_SLOTS - 1):
        entity.give("wood", 99)
    entity.give("bandit_helm", 1)
    assert len(entity.inventory) == INVENTORY_SLOTS

    assert entity.equip(entity.inventory.index(next(
        stack for stack in entity.inventory if stack.key == "bandit_helm"
    )))
    assert entity.count_of("leather_hood") == 1


def test_losing_a_health_bonus_cannot_leave_a_character_over_full():
    entity = _character()
    entity.give("padded_jerkin", 1)
    entity.equip(0)
    entity.health = entity.max_health

    entity.unequip(int(items.EquipmentSlot.CHEST))

    assert entity.health == entity.max_health


def test_a_material_cannot_be_worn():
    entity = _character()
    entity.give("wood", 1)

    assert not entity.equip(0)
    assert entity.equipment == {}


def test_equipping_an_empty_slot_is_ignored():
    """A stale client indexing past the end of a pack it has already spent."""
    entity = _character()

    assert not entity.equip(0)
    assert not entity.equip(-1)
    assert not entity.unequip(int(items.EquipmentSlot.HEAD))


def test_eating_a_ration_heals_and_spends_one_from_the_stack():
    entity = _character()
    entity.refresh_stats()
    entity.give("field_ration", 3)
    entity.health = 1

    assert entity.consume(0)
    assert entity.health == 1 + items.FIELD_RATION.restores_health
    assert entity.count_of("field_ration") == 2


def test_eating_at_full_health_is_refused_rather_than_wasted():
    entity = _character()
    entity.refresh_stats()
    entity.give("field_ration", 1)
    entity.health = entity.max_health

    assert not entity.consume(0)
    assert entity.count_of("field_ration") == 1


def test_a_weapon_bonus_reaches_the_blow(world: World):
    """The point of the whole feature: a blade has to show up in the damage number."""
    corridor = world.chunk_centre(ChunkAddress.edge(world.edge.edge_id, 0, 0, 0))
    _open_ground(world, corridor, span=6)

    attacker = _player(world, at=corridor)
    attacker.refresh_stats()
    victim = _npc(world, "slime", WorldPoint(corridor.x + 1.0, corridor.y))
    victim.health = victim.max_health = 500
    ability = classes.get_class(attacker.class_id).abilities[0]

    def strike() -> int:
        before = victim.health
        combat.resolve_action(
            world,
            attacker,
            ability.ability_id,
            victim.position,
            victim.entity_id,
            now=world.clock.now(),
        )
        return before - victim.health

    bare = strike()
    attacker.cooldowns.clear()
    attacker.last_ability_at = 0.0
    attacker.resource = attacker.max_resource
    attacker.give("golem_maul", 1)
    attacker.equip(0)
    armed = strike()

    assert armed == bare + items.GOLEM_MAUL.bonus_damage


def test_boots_reach_the_movement_integrator(world: World):
    entity = _player(world)
    entity.refresh_stats()
    bare = movement.speed_for(entity, running=False)

    entity.give("travellers_boots", 1)
    entity.equip(0)

    assert movement.speed_for(entity, running=False) == pytest.approx(
        bare + items.TRAVELLERS_BOOTS.bonus_speed
    )


def test_an_npc_pool_is_never_recomputed_from_a_class_it_does_not_have(world: World):
    """Archetype health is tuning, and a class multiplier applied to it is nonsense."""
    wolf = _npc(world, "wolf", world.spawn_point_for(world.hubs[0]))
    tuned = wolf.max_health

    wolf.refresh_stats()

    assert wolf.max_health == tuned


def _inventory_command(sim, entity: Entity, action: int, slot: int, count: int = 1):
    """One inventory command through the handler, returning the tick report."""
    from age.application.simulation import TickReport

    report = TickReport(tick=0)
    sim._apply_inventory(
        entity, wire.InventoryCommand(action=action, slot=slot, count=count), report
    )
    return report


def test_an_equip_command_wears_the_item_and_tells_its_owner(world: World):
    sim = _simulation(world)
    entity = _character()
    entity.refresh_stats()
    entity.give("bandit_helm", 1)

    report = _inventory_command(sim, entity, wire.INVENTORY_EQUIP, 0)

    assert entity.equipment[int(items.EquipmentSlot.HEAD)] == "bandit_helm"
    assert entity.entity_id in report.inventories


def test_an_unequip_command_names_the_body_slot_not_the_pack_slot(world: World):
    """The two index different things, and confusing them takes off the wrong item."""
    sim = _simulation(world)
    entity = _character()
    entity.refresh_stats()
    entity.give("bandit_helm", 1)
    entity.equip(0)

    _inventory_command(sim, entity, wire.INVENTORY_UNEQUIP, int(items.EquipmentSlot.HEAD))

    assert entity.equipment == {}
    assert entity.count_of("bandit_helm") == 1


def test_a_use_command_spends_a_consumable(world: World):
    sim = _simulation(world)
    entity = _character()
    entity.refresh_stats()
    entity.give("field_ration", 1)
    entity.health = 1

    _inventory_command(sim, entity, wire.INVENTORY_USE, 0)

    assert entity.health > 1
    assert entity.count_of("field_ration") == 0


def test_a_drop_command_throws_the_stack_away(world: World):
    sim = _simulation(world)
    entity = _character()
    entity.refresh_stats()
    entity.give("wood", 5)

    _inventory_command(sim, entity, wire.INVENTORY_DROP, 0, count=5)

    assert entity.count_of("wood") == 0


def test_an_inventory_command_that_cannot_be_honoured_still_answers(world: World):
    """The reply is the client's correction; silence would leave it showing a lie."""
    sim = _simulation(world)
    entity = _character()
    entity.refresh_stats()

    report = _inventory_command(sim, entity, wire.INVENTORY_EQUIP, 11)

    assert entity.entity_id in report.inventories


# --- the NPC state machine --------------------------------------------------


def _snapshot(**overrides) -> AISnapshot:
    base = {
        "state": AIState.IDLE,
        "health_fraction": 1.0,
        "target_distance": None,
        "has_target": False,
        "target_alive": False,
        "time_in_state": 0.0,
        "enemy_nearby": False,
    }
    base.update(overrides)
    return AISnapshot(**base)


@pytest.mark.parametrize("archetype", ARCHETYPES, ids=lambda entry: entry.key)
def test_no_health_means_dead_whatever_else_is_happening(archetype):
    resolved = next_state(
        archetype, _snapshot(state=AIState.ATTACK, health_fraction=0.0, has_target=True)
    )

    assert resolved is AIState.DEAD


@pytest.mark.parametrize("archetype", ARCHETYPES, ids=lambda entry: entry.key)
def test_death_is_terminal_until_the_driver_intervenes(archetype):
    assert next_state(archetype, _snapshot(state=AIState.DEAD)) is AIState.DEAD


@pytest.mark.parametrize("archetype", ARCHETYPES, ids=lambda entry: entry.key)
def test_every_state_resolves_to_a_legal_state(archetype):
    """Exhaustive: the table must never return something the driver cannot execute."""
    for state in AIState:
        for health in (0.0, 0.05, 0.2, 0.5, 1.0):
            for distance in (None, 0.5, 2.0, 7.0, 30.0, 300.0):
                resolved = next_state(
                    archetype,
                    _snapshot(
                        state=state,
                        health_fraction=health,
                        target_distance=distance,
                        has_target=distance is not None,
                        target_alive=distance is not None,
                        time_in_state=10.0,
                        enemy_nearby=distance is not None and distance < 10.0,
                    ),
                )
                assert resolved in set(AIState)


def test_a_creature_at_the_edge_of_aggro_does_not_flicker():
    """Hysteresis: leaving takes half again the distance that entering did."""
    wolf = ARCHETYPES_BY_KEY["wolf"]
    edge = wolf.detection_radius + 0.1

    entering = next_state(
        wolf,
        _snapshot(state=AIState.PATROL, target_distance=edge, has_target=True, target_alive=True),
    )
    leaving = next_state(
        wolf,
        _snapshot(state=AIState.AGGRO, target_distance=edge, has_target=True, target_alive=True),
    )

    assert entering is AIState.PATROL, "Just outside detection, it should not notice."
    assert leaving is AIState.AGGRO, "Already chasing, it should not give up yet."


def test_aggro_is_released_once_the_target_is_far_enough():
    wolf = ARCHETYPES_BY_KEY["wolf"]
    beyond = wolf.detection_radius * AGGRO_RELEASE_FACTOR + 0.1

    resolved = next_state(
        wolf,
        _snapshot(
            state=AIState.AGGRO, target_distance=beyond, has_target=True, target_alive=True
        ),
    )

    assert resolved is AIState.PATROL


def test_a_wounded_creature_flees_and_needs_real_recovery_to_stop():
    bandit = ARCHETYPES_BY_KEY["bandit"]
    just_under = bandit.flee_threshold * 1.2

    started = next_state(
        bandit, _snapshot(state=AIState.ATTACK, health_fraction=bandit.flee_threshold * 0.5)
    )
    still_going = next_state(
        bandit, _snapshot(state=AIState.FLEE, health_fraction=just_under)
    )

    assert started is AIState.FLEE
    assert still_going is AIState.FLEE, "Recovery needs the threshold beaten by half again."


def test_a_guard_never_flees():
    guard = ARCHETYPES_BY_KEY["guard"]
    assert guard.flee_threshold == 0.0

    resolved = next_state(
        guard, _snapshot(state=AIState.ATTACK, health_fraction=0.01, has_target=True, target_alive=True, target_distance=1.0)
    )

    assert resolved is not AIState.FLEE


def test_a_creature_whose_target_dies_stands_down():
    for state in (AIState.AGGRO, AIState.ATTACK):
        resolved = next_state(
            ARCHETYPES_BY_KEY["bandit"],
            _snapshot(state=state, has_target=True, target_alive=False, target_distance=1.0),
        )
        assert resolved is AIState.IDLE


def test_idling_eventually_becomes_patrolling():
    slime = ARCHETYPES_BY_KEY["slime"]

    assert next_state(slime, _snapshot(time_in_state=0.0)) is AIState.IDLE
    assert (
        next_state(slime, _snapshot(time_in_state=slime.idle_duration_s + 1.0))
        is AIState.PATROL
    )


def test_only_moving_states_have_a_speed():
    wolf = ARCHETYPES_BY_KEY["wolf"]

    assert speed_for_state(wolf, AIState.IDLE) == 0.0
    assert speed_for_state(wolf, AIState.ATTACK) == 0.0
    assert speed_for_state(wolf, AIState.PATROL) == wolf.patrol_speed
    assert speed_for_state(wolf, AIState.AGGRO) == wolf.aggro_speed
    assert speed_for_state(wolf, AIState.FLEE) == wolf.aggro_speed


# --- the AI driver ----------------------------------------------------------


def test_a_chunk_is_populated_deterministically(world: World):
    address = ChunkAddress.edge(world.edge.edge_id, 0, 0, 0)

    first = ai.spawn_for_chunk(world, address, world.now)
    for entity in first:
        world.remove_entity(entity.entity_id)
    second = ai.spawn_for_chunk(world, address, world.now)

    assert [entity.name for entity in first] == [entity.name for entity in second]
    assert [entity.position for entity in first] == [entity.position for entity in second]


def test_hubs_are_left_to_their_guards(world: World):
    assert ai.spawn_for_chunk(world, ChunkAddress.hub(0, 0, 0), world.now) == []


def test_a_guard_will_not_leave_its_hub_to_chase_someone(world: World):
    """It exists to make the hub safe, not to depopulate the corridor."""
    guard = _npc(world, "guard", world.spawn_point_for(world.hubs[0]))
    corridor = world.chunk_centre(ChunkAddress.edge(world.edge.edge_id, 0, 0, 0))
    _open_ground(world, corridor)
    runaway = _player(world, at=corridor)
    guard.ai_target = runaway.entity_id

    ai._decide(world, guard, guard.archetype, world.now)

    assert guard.ai_target is None
    assert guard.ai_state in (AIState.IDLE, AIState.PATROL)


def test_a_guard_does_not_murder_a_player_on_the_plaza(world: World):
    """The spawn square is a safe zone, including against the garrison.

    Guards acquire players by default — ``nearest_enemy(..., hostile_to_players=False)``
    means "look for players" — and a 24-damage swing every 1.2 s empties a fresh
    warrior in six hits. That is why a demo character died on load.
    """
    spawn = world.spawn_point_for(world.hubs[0])
    player = _player(world, at=spawn)
    guard = _npc(world, "guard", WorldPoint(spawn.x + 1.0, spawn.y))
    guard.ai_target = player.entity_id
    guard.enter_ai_state(AIState.ATTACK, world.now)

    ai._decide(world, guard, guard.archetype, world.now)
    ai._try_attack(world, guard, guard.archetype, player, world.now, EventQueue())

    assert player.health == player.max_health
    assert guard.ai_target is None


def test_a_dead_creature_comes_back_where_it_started(world: World, clock: ManualClock):
    spawn = world.spawn_point_for(world.hubs[0])
    _open_ground(world, spawn, span=6)
    slime = _npc(world, "slime", spawn)
    slime.health = 0
    slime.enter_ai_state(AIState.DEAD, clock.now())
    slime.move_to(spawn.x + 4.0, spawn.y)

    ai.tick(world, clock.now(), TICK_SECONDS, EventQueue())
    clock.advance(60.0)
    ai.tick(world, clock.now(), TICK_SECONDS, EventQueue())

    assert slime.is_alive
    assert slime.position == spawn
    assert slime.ai_state is AIState.IDLE


def test_a_creature_lands_a_hit_and_the_event_is_recorded(world: World, clock: ManualClock):
    corridor = world.chunk_centre(ChunkAddress.edge(world.edge.edge_id, 0, 0, 0))
    _open_ground(world, corridor, span=6)
    victim = _player(world, at=corridor)
    wolf = _npc(world, "wolf", WorldPoint(corridor.x + 1.0, corridor.y))
    wolf.ai_target = victim.entity_id
    wolf.enter_ai_state(AIState.ATTACK, clock.now())
    events = EventQueue()

    ai._execute(world, wolf, wolf.archetype, clock.now(), TICK_SECONDS, events)

    assert victim.health < victim.max_health
    assert len(events.combat) == 1
    assert events.combat[0].target_id == victim.entity_id
    assert events.combat[0].damage > 0


def test_creature_attacks_respect_their_own_cooldown(world: World, clock: ManualClock):
    corridor = world.chunk_centre(ChunkAddress.edge(world.edge.edge_id, 0, 0, 0))
    _open_ground(world, corridor, span=6)
    victim = _player(world, at=corridor)
    wolf = _npc(world, "wolf", WorldPoint(corridor.x + 1.0, corridor.y))
    wolf.ai_target = victim.entity_id
    wolf.enter_ai_state(AIState.ATTACK, clock.now())

    ai._execute(world, wolf, wolf.archetype, clock.now(), TICK_SECONDS, EventQueue())
    after_first = victim.health
    ai._execute(world, wolf, wolf.archetype, clock.now(), TICK_SECONDS, EventQueue())

    assert victim.health == after_first


def test_decisions_run_at_a_fraction_of_the_tick_rate(world: World, clock: ManualClock):
    """An NPC re-deciding 30 times a second reaches the same answer 29 times."""
    corridor = world.chunk_centre(ChunkAddress.edge(world.edge.edge_id, 0, 0, 0))
    _open_ground(world, corridor, span=6)
    _player(world, at=corridor)
    wolf = _npc(world, "wolf", WorldPoint(corridor.x + 1.0, corridor.y))

    world.tick_count = 1
    ai.tick(world, clock.now(), TICK_SECONDS, EventQueue())
    assert wolf.ai_state is AIState.IDLE, "An off-beat tick must not re-decide."

    world.tick_count = 0
    ai.tick(world, clock.now(), TICK_SECONDS, EventQueue())
    assert wolf.ai_state is not AIState.IDLE


# --- the sandbox: harvest, build, regrowth ----------------------------------


def test_harvesting_gives_the_material_and_clears_the_tile(world: World):
    spawn = world.spawn_point_for(world.hubs[0])
    player = _player(world, at=spawn)
    target = WorldPoint(spawn.x + 1.0, spawn.y)
    world.set_tile_at(target, int(Tile.TREE))

    outcome = terrain.harvest(world, player, target, world.now)

    assert outcome.ok
    assert outcome.gained
    material, quantity = next(iter(outcome.gained.items()))
    assert player.count_of(material) == quantity
    assert world.tile_at(target) != int(Tile.TREE)


def test_you_cannot_harvest_what_you_cannot_reach(world: World):
    spawn = world.spawn_point_for(world.hubs[0])
    player = _player(world, at=spawn)
    far = WorldPoint(spawn.x + 40.0, spawn.y)

    outcome = terrain.harvest(world, player, far, world.now)

    assert outcome.error == wire.ERROR_OUT_OF_RANGE


def test_bare_ground_yields_nothing(world: World):
    spawn = world.spawn_point_for(world.hubs[0])
    player = _player(world, at=spawn)
    target = WorldPoint(spawn.x + 1.0, spawn.y)
    world.set_tile_at(target, int(Tile.BARE_GROUND))

    outcome = terrain.harvest(world, player, target, world.now)

    assert outcome.error == wire.ERROR_INVALID


def test_building_costs_material_and_writes_the_tile(world: World):
    spawn = world.spawn_point_for(world.hubs[0])
    _open_ground(world, spawn)
    player = _player(world, at=spawn)
    tile, cost = BUILD_RECIPES["wood"]
    player.give("wood", cost)
    target = WorldPoint(spawn.x + 1.0, spawn.y)

    outcome = terrain.place(world, player, target, "wood", world.now)

    assert outcome.ok
    assert player.count_of("wood") == 0
    assert world.tile_at(target) == int(tile)


def test_building_without_the_material_is_refused(world: World):
    spawn = world.spawn_point_for(world.hubs[0])
    _open_ground(world, spawn)
    player = _player(world, at=spawn)

    outcome = terrain.place(world, player, WorldPoint(spawn.x + 1.0, spawn.y), "wood", world.now)

    assert outcome.error == wire.ERROR_NO_MATERIAL


def test_an_unknown_recipe_is_refused(world: World):
    spawn = world.spawn_point_for(world.hubs[0])
    player = _player(world, at=spawn)

    outcome = terrain.place(
        world, player, WorldPoint(spawn.x + 1.0, spawn.y), "unobtainium", world.now
    )

    assert outcome.error == wire.ERROR_INVALID


def test_you_cannot_wall_another_player_in(world: World):
    spawn = world.spawn_point_for(world.hubs[0])
    _open_ground(world, spawn)
    builder = _player(world, at=spawn)
    tile, cost = BUILD_RECIPES["wood"]
    builder.give("wood", cost)
    target = WorldPoint(spawn.x + 1.0, spawn.y)
    _player(world, at=target)

    outcome = terrain.place(world, builder, target, "wood", world.now)

    assert outcome.error == wire.ERROR_INVALID


def test_a_misplaced_wall_can_be_taken_back_down(world: World):
    spawn = world.spawn_point_for(world.hubs[0])
    _open_ground(world, spawn)
    player = _player(world, at=spawn)
    target = WorldPoint(spawn.x + 1.0, spawn.y)
    world.set_tile_at(target, int(Tile.WALL_WOOD))

    outcome = terrain.harvest(world, player, target, world.now)

    assert outcome.ok
    assert outcome.gained


def test_a_harvested_tile_grows_back_one_stage_at_a_time(world: World, clock: ManualClock):
    spawn = world.spawn_point_for(world.hubs[0])
    player = _player(world, at=spawn)
    target = WorldPoint(spawn.x + 2.0, spawn.y)
    world.set_tile_at(target, int(Tile.TREE))
    terrain.harvest(world, player, target, clock.now())
    stripped = world.tile_at(target)

    clock.advance(REGROWTH_STAGE_SECONDS + 1.0)
    advanced = terrain.tick_regrowth(world, clock.now(), EventQueue())

    assert advanced >= 1
    assert world.tile_at(target) != stripped


def test_regrowth_waits_for_its_timer(world: World, clock: ManualClock):
    spawn = world.spawn_point_for(world.hubs[0])
    player = _player(world, at=spawn)
    target = WorldPoint(spawn.x + 2.0, spawn.y)
    world.set_tile_at(target, int(Tile.TREE))
    terrain.harvest(world, player, target, clock.now())
    stripped = world.tile_at(target)

    clock.advance(REGROWTH_STAGE_SECONDS * 0.5)
    terrain.tick_regrowth(world, clock.now(), EventQueue())

    assert world.tile_at(target) == stripped


def test_nothing_grows_through_a_player_standing_on_it(world: World, clock: ManualClock):
    spawn = world.spawn_point_for(world.hubs[0])
    player = _player(world, at=spawn)
    target = WorldPoint(spawn.x + 1.0, spawn.y)
    world.set_tile_at(target, int(Tile.TREE))
    terrain.harvest(world, player, target, clock.now())
    stripped = world.tile_at(target)
    player.move_to(target.x, target.y)
    world.reindex(player)

    clock.advance(REGROWTH_STAGE_SECONDS + 1.0)
    terrain.tick_regrowth(world, clock.now(), EventQueue())

    assert world.tile_at(target) == stripped


def test_a_built_tile_is_protected_from_regrowth(world: World, clock: ManualClock):
    spawn = world.spawn_point_for(world.hubs[0])
    _open_ground(world, spawn)
    player = _player(world, at=spawn)
    target = WorldPoint(spawn.x + 2.0, spawn.y)
    world.set_tile_at(target, int(Tile.TREE))
    terrain.harvest(world, player, target, clock.now())
    tile, cost = BUILD_RECIPES["wood"]
    player.give("wood", cost)

    terrain.place(world, player, target, "wood", clock.now())
    clock.advance(REGROWTH_STAGE_SECONDS * 4)
    terrain.tick_regrowth(world, clock.now(), EventQueue())

    assert world.tile_at(target) == int(tile)


def test_a_batch_of_regrowth_produces_one_event_per_chunk(world: World, clock: ManualClock):
    spawn = world.spawn_point_for(world.hubs[0])
    player = _player(world, at=spawn)
    for offset in range(1, 4):
        target = WorldPoint(spawn.x + offset, spawn.y + 1.0)
        world.set_tile_at(target, int(Tile.TREE))
        assert terrain.harvest(world, player, target, clock.now()).ok
    events = EventQueue()

    clock.advance(REGROWTH_STAGE_SECONDS + 1.0)
    terrain.tick_regrowth(world, clock.now(), events)

    assert len(events.tiles) == 1, "Three tiles in one chunk is one delta, not three."
    assert len(events.tiles[0].changes) == 3


def test_editing_a_tile_back_to_its_generated_value_drops_the_overlay(world: World):
    address = ChunkAddress.hub(0, 0, 0)
    view = world.chunk(address)
    original = view.base[0]
    view.set_tile(0, int(Tile.WALL_STONE))
    assert view.overlay

    view.set_tile(0, original)

    assert view.overlay == {}, "A no-op edit must not be stored forever."


def test_the_flush_hands_over_the_edits_and_clears_the_flag(world: World):
    spawn = world.spawn_point_for(world.hubs[0])
    world.set_tile_at(spawn, int(Tile.WALL_STONE))

    pending = terrain.collect_dirty_overlays(world)

    assert pending
    assert terrain.collect_dirty_overlays(world) == {}


def test_every_harvestable_tile_leaves_something_walkable_behind(world: World):
    """Otherwise a player can strip a tile and be stuck standing in it."""
    for source, (replacement, material, quantity) in HARVEST_RESULTS.items():
        assert is_walkable(replacement), source
        assert material
        assert quantity > 0


def test_every_build_recipe_places_a_real_tile():
    for material, (tile, cost) in BUILD_RECIPES.items():
        assert tile in set(Tile), material
        assert cost > 0


# --- interest management and replication -------------------------------------
#
# This module went uncovered and paid for it. An entity is introduced by one spawn packet
# and afterwards described only by the fields that changed, so a field the introduction
# omits is not one the client waits for — it is one the client makes up, for as long as
# that entity lives. The state byte was omitted, clients defaulted it to zero, and bit 0
# of zero means dead: every entity in the world arrived reading as a corpse and was drawn
# in the single-frame hurt pose, which is why nothing in the game animated. The bug was
# invisible from either side alone. These tests look at the packet.


def _spawn_packet_for(world: World, viewer: Entity, subject: Entity) -> bytes:
    """The introduction the viewer would receive for ``subject``."""
    from age.application.interest import build_update

    update = build_update(
        world, _session(world, viewer), viewer, tick=1, server_time=world.now
    )
    for payload in update.spawns:
        # The id is the first field after the one-byte message type.
        if int.from_bytes(payload[1:5], "little") == subject.entity_id:
            return payload
    raise AssertionError(f"no spawn packet for entity {subject.entity_id}")


def _introduced_state(payload: bytes) -> int:
    """The state byte out of a spawn packet.

    Counted from the end rather than the start, because everything before it is
    variable-length once the name is in there, and the tail is fixed: one state byte
    followed by the five appearance bytes.
    """
    return payload[-6]


def test_an_introduction_says_a_living_entity_is_alive(world: World):
    """Bit 0 of the state byte, the field whose absence made every character a corpse."""
    from age.application.interest import _state_byte

    spawn = world.spawn_point_for(world.hubs[0])
    viewer = _player(world, at=spawn)
    other = _player(world, at=WorldPoint(spawn.x + 2.0, spawn.y))

    assert other.is_alive
    assert _introduced_state(_spawn_packet_for(world, viewer, other)) & 1
    assert _introduced_state(_spawn_packet_for(world, viewer, other)) == _state_byte(other)


def test_an_introduction_carries_the_state_of_a_dead_entity_too(world: World):
    """The same byte has to be able to say the opposite, or it is a constant."""
    spawn = world.spawn_point_for(world.hubs[0])
    viewer = _player(world, at=spawn)
    corpse = _npc(world, "wolf", WorldPoint(spawn.x + 2.0, spawn.y))
    corpse.health = 0

    assert not _introduced_state(_spawn_packet_for(world, viewer, corpse)) & 1


def test_an_introduction_decodes_field_for_field_with_nothing_left_over(world: World):
    """Read the packet back the way the client reads it, and check it comes out even.

    This is the shape of test the missing state byte needed. Asserting a field is present
    by listing the fields is a tautology — the list is the thing that was wrong. Reading
    the packet in order and requiring it to end exactly where the layout says is not: drop
    a field and every field after it decodes as the neighbouring one's bytes, and the
    surplus at the end gives it away.
    """
    spawn = world.spawn_point_for(world.hubs[0])
    viewer = _player(world, at=spawn)
    other = _player(world, at=WorldPoint(spawn.x + 2.5, spawn.y - 1.5), class_id=1)
    other.level = 7
    other.appearance = Appearance(1, 2, 0, 4, 3)

    reader = wire.Reader(_spawn_packet_for(world, viewer, other))
    assert reader.u8() == wire.SERVER_SPAWN
    assert reader.u32() == other.entity_id
    assert reader.u8() == other.kind
    assert reader.u8() == other.class_id
    assert reader.text(MAX_NAME_LENGTH * 4) == other.name
    assert wire.decode_position(reader.i32()) == pytest.approx(other.position.x, abs=0.01)
    assert wire.decode_position(reader.i32()) == pytest.approx(other.position.y, abs=0.01)
    reader.u16()  # facing, quantised to an angle scale of its own
    assert reader.u8() == wire.encode_percent(other.health, other.max_health)
    assert reader.u16() == other.level
    assert reader.u8() & 1, "the introduction says a living entity is dead"
    assert tuple(reader.u8() for _ in range(5)) == other.appearance.pack()
    assert reader.remaining == 0, "the introduction has bytes the layout does not account for"


# --- chat -------------------------------------------------------------------


def _session(world: World, entity: Entity) -> "session.PlayerSession":
    from age.domain.entities import PlayerSession

    return PlayerSession(
        session_id=f"s{entity.entity_id}",
        entity_id=entity.entity_id,
        character_name=entity.name,
        last_seen_at=world.now,
    )


def test_a_local_line_reaches_only_the_neighbours(world: World):
    spawn = world.spawn_point_for(world.hubs[0])
    speaker = _player(world, at=spawn)
    near = _player(world, at=WorldPoint(spawn.x + 2.0, spawn.y))
    far = _player(world, at=world.chunk_centre(ChunkAddress.hub(1, 0, 0)))
    service = chat.ChatService()

    decision = service.submit(
        world, _session(world, speaker), speaker, CHANNEL_LOCAL, "over here", world.now
    )

    assert decision.accepted
    assert near.entity_id in decision.recipients
    assert far.entity_id not in decision.recipients


def test_a_global_line_reaches_everyone(world: World):
    speaker = _player(world)
    far = _player(world, at=world.chunk_centre(ChunkAddress.hub(1, 0, 0)))
    service = chat.ChatService()

    decision = service.submit(
        world, _session(world, speaker), speaker, CHANNEL_GLOBAL, "hello all", world.now
    )

    assert far.entity_id in decision.recipients


def test_an_empty_line_is_dropped(world: World):
    speaker = _player(world)
    service = chat.ChatService()

    decision = service.submit(
        world, _session(world, speaker), speaker, CHANNEL_LOCAL, "   ", world.now
    )

    assert not decision.accepted
    assert decision.reason == "empty"


def test_a_client_cannot_speak_on_the_system_channel(world: World):
    speaker = _player(world)
    service = chat.ChatService()

    decision = service.submit(
        world, _session(world, speaker), speaker, CHANNEL_SYSTEM, "server here", world.now
    )

    assert not decision.accepted
    assert decision.reason == "bad_channel"


def test_a_flood_is_cut_off_but_a_burst_is_not(world: World):
    speaker = _player(world)
    player_session = _session(world, speaker)
    service = chat.ChatService()

    accepted = sum(
        service.submit(
            world, player_session, speaker, CHANNEL_LOCAL, f"line {index}", world.now
        ).accepted
        for index in range(CHAT_RATE_LIMIT + 3)
    )

    assert accepted == CHAT_RATE_LIMIT


def test_the_rate_window_slides(world: World):
    speaker = _player(world)
    player_session = _session(world, speaker)
    service = chat.ChatService()
    for index in range(CHAT_RATE_LIMIT):
        service.submit(world, player_session, speaker, CHANNEL_LOCAL, f"{index}", world.now)

    later = service.submit(
        world, player_session, speaker, CHANNEL_LOCAL, "later", world.now + 60.0
    )

    assert later.accepted


def test_newlines_cannot_take_over_the_chat_pane():
    assert chat.sanitise("one\ntwo\r\nthree") == "one two three"


def test_control_characters_are_removed_rather_than_escaped():
    assert "\x00" not in chat.sanitise("hel\x00lo")
    assert "\x1b" not in chat.sanitise("\x1b[31mred")


def test_a_long_line_is_clipped_to_the_protocol_limit():
    assert len(chat.sanitise("x" * 5000)) == CHAT_MAX_LENGTH


def test_system_lines_are_never_rate_limited():
    service = chat.ChatService()

    for index in range(CHAT_RATE_LIMIT * 5):
        service.system(f"notice {index}", float(index))

    assert service.history
    assert all(message.channel == CHANNEL_SYSTEM for message in service.history)


def test_history_is_bounded(world: World):
    from age.domain.constants import CHAT_HISTORY_SIZE

    service = chat.ChatService()
    for index in range(CHAT_HISTORY_SIZE * 2):
        service.system(f"line {index}", float(index))

    assert len(service.history) == CHAT_HISTORY_SIZE


# --- sessions and persistence ----------------------------------------------


def test_joining_places_a_new_character_on_a_plaza(world: World):
    service = session.SessionService(world)

    async def scenario():
        return await service.join(
            session_id="abc", character_name="Rowan", class_id=4, appearance=(1, 2, 3, 4, 5)
        )

    result = _run(scenario)

    assert not result.returning
    assert world.is_in_hub(result.entity.position)
    # Class 4 is Paladin, a hybrid. A new character cannot be one, so the request
    # collapses to the base class of its origin half.
    assert result.entity.class_id == classes.CLASSES_BY_KEY["warrior"].class_id
    assert world.sessions["abc"].entity_id == result.entity.entity_id


def test_a_blank_name_still_produces_a_playable_character(world: World):
    service = session.SessionService(world)

    async def scenario():
        return await service.join(
            session_id="deadbeef", character_name="   ", class_id=0, appearance=(0,) * 5
        )

    assert _run(scenario).entity.name


def test_health_follows_the_class_multiplier(world: World):
    service = session.SessionService(world)
    warrior = classes.CLASSES_BY_KEY["warrior"]

    async def scenario():
        return await service.join(
            session_id="w",
            character_name="Bruna",
            class_id=warrior.class_id,
            appearance=(0,) * 5,
        )

    entity = _run(scenario).entity

    assert entity.max_health == int(BASE_MAX_HEALTH * warrior.health_multiplier)


def test_a_returning_character_keeps_its_class_and_inventory(world: World):
    service = session.SessionService(world, MemoryCharacterRepository())

    shaman = classes.CLASSES_BY_KEY["shaman"]

    async def scenario():
        first = await service.join(
            session_id="a", character_name="Rowan", class_id=1, appearance=(1, 2, 3, 4, 5)
        )
        first.entity.give("wood", 12)
        # Composed in play, the way a character actually reaches a hybrid.
        first.entity.class_id = shaman.class_id
        await service.leave("a")
        return await service.join(
            session_id="b", character_name="Rowan", class_id=0, appearance=(9,) * 5
        )

    again = _run(scenario)

    assert again.returning
    assert again.entity.class_id == shaman.class_id, (
        "A returning character keeps the hybrid they composed, and the client's "
        "requested class is ignored."
    )
    assert again.entity.count_of("wood") == 12
    assert again.entity.appearance.pack() == (1, 2, 3, 4, 5)


def test_a_returning_character_is_still_wearing_what_it_had_on(world: World):
    """Equipment that did not survive a logout would make the whole slot pointless."""
    service = session.SessionService(world, MemoryCharacterRepository())

    async def scenario():
        first = await service.join(
            session_id="a", character_name="Rowan", class_id=0, appearance=(0,) * 5
        )
        first.entity.give("bandit_helm", 1)
        first.entity.give("travellers_boots", 1)
        first.entity.equip(0)
        armoured = first.entity.max_health
        await service.leave("a")
        return armoured, await service.join(
            session_id="b", character_name="Rowan", class_id=0, appearance=(0,) * 5
        )

    armoured, again = _run(scenario)

    assert again.entity.equipment == {int(items.EquipmentSlot.HEAD): "bandit_helm"}
    assert again.entity.count_of("travellers_boots") == 1
    assert again.entity.max_health == armoured, (
        "the bonus has to be folded back in, not just the item remembered"
    )


def test_a_stored_item_the_catalogue_has_forgotten_does_not_lock_anyone_out(world: World):
    """Retiring an item must not be the same thing as banning whoever was holding it."""
    characters = MemoryCharacterRepository()
    service = session.SessionService(world, characters)

    async def scenario():
        first = await service.join(
            session_id="a", character_name="Rowan", class_id=0, appearance=(0,) * 5
        )
        await service.persist(first.entity)
        stored = await characters.load("Rowan")
        assert stored is not None
        stored["inventory"] = [{"key": "moon_cheese", "count": 3}]
        stored["equipment"] = {str(int(items.EquipmentSlot.HEAD)): "moon_cheese"}
        await characters.save("Rowan", stored)
        await service.leave("a")
        return await service.join(
            session_id="b", character_name="Rowan", class_id=0, appearance=(0,) * 5
        )

    again = _run(scenario)

    assert again.entity.equipment == {}, "an unknown key cannot be worn"


def test_a_character_is_stored_as_a_location_not_as_coordinates(world: World):
    """Accordion Spec 3.1: a tier change must not silently move everybody."""
    characters = MemoryCharacterRepository()
    service = session.SessionService(world, characters)

    async def scenario():
        result = await service.join(
            session_id="a", character_name="Rowan", class_id=0, appearance=(0,) * 5
        )
        await service.persist(result.entity)
        return await characters.load("Rowan")

    stored = _run(scenario)

    assert stored is not None
    assert set(stored["location"]) >= {"space", "tile_x", "tile_y"}
    assert "x" not in stored["location"]


def test_a_character_saved_in_a_retired_lane_falls_back_to_a_hub(world: World):
    characters = MemoryCharacterRepository()
    service = session.SessionService(world, characters)
    assert world.topology.current_tier == 0, "Lane 1 does not exist at tier 0."

    async def scenario():
        await characters.save(
            "Rowan",
            {
                "class_id": 0,
                "location": {
                    "space": int(SpaceType.EDGE),
                    "edge_id": world.edge.edge_id,
                    "segment_index": 0,
                    "lane_offset": 1,
                    "tile_x": 4.0,
                    "tile_y": 4.0,
                },
            },
        )
        return await service.join(
            session_id="a", character_name="Rowan", class_id=0, appearance=(0,) * 5
        )

    assert world.is_in_hub(_run(scenario).entity.position)


def test_a_malformed_stored_location_is_not_worth_refusing_a_login_over(world: World):
    characters = MemoryCharacterRepository()
    service = session.SessionService(world, characters)

    async def scenario():
        await characters.save("Rowan", {"class_id": 0, "location": {"space": "nonsense"}})
        return await service.join(
            session_id="a", character_name="Rowan", class_id=0, appearance=(0,) * 5
        )

    assert world.is_in_hub(_run(scenario).entity.position)


def test_leaving_removes_the_character_and_frees_the_session(world: World):
    service = session.SessionService(world, MemoryCharacterRepository())

    async def scenario():
        result = await service.join(
            session_id="a", character_name="Rowan", class_id=0, appearance=(0,) * 5
        )
        return result.entity.entity_id, await service.leave("a")

    joined, freed = _run(scenario)

    assert freed == joined
    assert joined not in world.entities
    assert "a" not in world.sessions


def test_leaving_a_session_that_never_joined_is_harmless(world: World):
    service = session.SessionService(world)

    async def scenario():
        return await service.leave("ghost")

    assert _run(scenario) is None


def test_death_costs_time_and_position_but_not_progress(world: World, clock: ManualClock):
    """GDD 8.4: the penalty is the walk back."""
    corridor = world.chunk_centre(ChunkAddress.edge(world.edge.edge_id, 0, 0, 0))
    _open_ground(world, corridor)
    player = _player(world, at=corridor)
    player.give("wood", 5)
    player.experience = 250
    player.health = 0
    service = session.SessionService(world)

    assert not service.respawn(player, clock.now()), "The delay starts on the first look."
    clock.advance(RESPAWN_DELAY_SECONDS + 1.0)
    assert service.respawn(player, clock.now())

    assert player.health == player.max_health
    assert world.is_in_hub(player.position)
    assert player.experience == 250
    assert player.count_of("wood") == 5


def test_respawning_early_is_refused(world: World, clock: ManualClock):
    player = _player(world)
    player.health = 0
    service = session.SessionService(world)
    service.respawn(player, clock.now())

    clock.advance(RESPAWN_DELAY_SECONDS * 0.5)

    assert not service.respawn(player, clock.now())


def test_a_living_player_cannot_respawn(world: World):
    player = _player(world)

    assert not session.SessionService(world).respawn(player, world.now)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  Rowan  ", "Rowan"),
        ("Rowan   Ash", "Rowan Ash"),
        ("<script>alert(1)</script>", "scriptalert1script"),
        ("Ro\u200bwan", "Rowan"),
        ("Anne-Marie O'Shea", "Anne-Marie O'Shea"),
        ("x" * 200, "x" * MAX_NAME_LENGTH),
    ],
)
def test_a_name_is_cleaned_rather_than_escaped_at_every_use_site(raw, expected):
    assert session.normalise_name(raw) == expected


# --- the world aggregate ----------------------------------------------------


def test_the_edge_of_the_world_stops_you_rather_than_crashing(world: World):
    beyond = WorldPoint(1e7, 1e7)

    assert not world.contains(beyond)
    assert not world.is_walkable_at(beyond)


def test_a_lane_that_does_not_exist_yet_is_outside_the_world(world: World):
    lane = ChunkAddress.edge(world.edge.edge_id, 0, 1, 1)
    point = world.chunk_centre(lane)

    assert world.topology.current_tier == 0
    assert not world.contains(point)


def test_a_hub_rim_counts_as_a_hub_even_where_it_meets_the_corridor(world: World):
    hub = world.hubs[0]
    rim = WorldPoint(hub.centre.x + hub.radius_tiles - 0.5, hub.centre.y)

    assert world.is_in_hub(rim)
    assert world.chunk_address_at(rim).space_type is SpaceType.HUB


def test_a_seam_reads_ground_rather_than_nothing(world: World):
    """A point projected onto a chunk seam must land inside a chunk, not past one.

    ``world_to_edge`` normalises by subtracting the chunk origin back off, and on a
    seam that subtraction cancels to exactly ``CHUNK_TILES`` — one row too far, or
    off the end of the array on the last one. A read past the end is not terrain,
    and terrain that is not there stops the player on ground that renders as open.
    """
    world.topology.begin_expansion(world.now)
    world.topology.advance_transitions(world.now + 1000.0)
    seams = [
        coordinates.edge_to_world(world.edge, segment, lane, tile_x, tile_y)
        for segment in range(world.topology.segments)
        for lane in lanes_for_tier(1)
        for tile_x, tile_y in ((0.0, 0.0), (0.0, 0.5), (0.5, 0.0), (31.5, 0.0), (0.0, 31.5))
    ]

    for point in seams:
        resolved = world._tile_index(point)

        assert resolved is not None, f"{point} fell out of the world"
        assert 0 <= resolved[1] < CHUNK_TILES * CHUNK_TILES, f"{point} is past the end"


def test_the_corridor_centre_line_is_inside_the_world_before_it_widens(world: World):
    """The same seams on the world as it actually starts: one lane, nothing beside it.

    This is the case that matters and the one that is easy to lose, because widening the
    world first makes it pass for the wrong reason. Lane 0's near edge is where ``across``
    comes out at zero, and zero is the boundary between lane 0 and lane -1. The projection
    is not exact — the direction vector is normalised, so it carries a rounding error — and
    an ``across`` of -8e-19 floors into lane -1. At tier 0 lane -1 does not exist yet, so
    the point reads as outside the world, and outside the world is impassable.

    The result was a wall one float wide running the length of the corridor's centre line,
    over ground that draws as open grass. Asserting the lane rather than just "resolved to
    something" is deliberate: activating lane -1 at tier 0 would also make this point
    resolve, and would be a different world, not a fix.
    """
    assert world.topology.current_tier == 0

    for segment in range(world.topology.segments):
        for tile_x in (0.0, 0.5, 16.0, 31.5):
            point = coordinates.edge_to_world(world.edge, segment, 0, tile_x, 0.0)
            resolved = world._tile_index(point)

            assert resolved is not None, f"{point} on the centre line fell out of the world"
            assert resolved[0].lane_offset == 0, f"{point} was pushed off the only lane"
            assert world.contains(point)


def test_a_hub_chunk_boundary_splits_the_same_way_on_both_axes(world: World):
    """One floor then an exact split, not a floor of the chunk and a floor of the rest.

    A hub centre is not at an integer, so the point one float step below it is a hair
    under zero in hub-local space: the negative chunk, last tile. Deriving the chunk
    and the offset from the float independently rounds that back to tile 0 of the
    chunk above, which reads terrain from the wrong side of the seam.
    """
    centre = world.hubs[0].centre
    below = WorldPoint(nextafter(centre.x, -inf), nextafter(centre.y, -inf))

    resolved = world._tile_index(below)

    assert resolved is not None
    assert (resolved[0].chunk_x, resolved[0].chunk_y) == (-1, -1)
    assert resolved[1] == (CHUNK_TILES - 1) * CHUNK_TILES + (CHUNK_TILES - 1)


def test_a_lane_is_addressed_by_the_tier_that_first_named_it(world: World):
    """The lane's ``tier_min`` is part of its key, so it cannot be assumed to be 0.

    A flanking lane addressed as tier 0 is a key the topology never wrote, which reads
    as outside the world: solid and unrendered down the lane's whole length from the
    moment the accordion widens.
    """
    world.topology.begin_expansion(world.now)
    world.topology.advance_transitions(world.now + 1000.0)
    active = {record.address.key for record in world.topology.active_chunks()}

    for lane in lanes_for_tier(1):
        point = coordinates.edge_to_world(world.edge, 0, lane, 16.5, 16.5)
        resolved = world._tile_index(point)

        assert resolved is not None, f"lane {lane} fell out of the world"
        assert resolved[0].tier_min == tier_min_for_lane(lane)
        assert resolved[0].key in active


def test_a_moving_entity_changes_spatial_bucket_exactly_once(world: World):
    spawn = world.spawn_point_for(world.hubs[0])
    player = _player(world, at=spawn)
    first = player.chunk_key

    player.move_to(spawn.x + 0.5, spawn.y)
    world.reindex(player)
    assert player.chunk_key == first, "A small step must not touch the index."

    player.move_to(spawn.x + CHUNK_TILES * 2.0, spawn.y)
    world.reindex(player)
    assert player.chunk_key != first
    assert player in world.entities_in_chunk(player.chunk_key)
    assert player not in world.entities_in_chunk(first)


def test_a_proximity_query_spans_chunk_boundaries(world: World):
    spawn = world.spawn_point_for(world.hubs[0])
    anchor = _player(world, at=spawn)
    over_the_line = _player(world, at=WorldPoint(spawn.x + CHUNK_TILES + 2.0, spawn.y))

    found = world.entities_near(anchor.position, CHUNK_TILES + 4.0)

    assert over_the_line in found


def test_a_removed_entity_leaves_no_trace_in_the_index(world: World):
    player = _player(world)
    key = player.chunk_key

    world.remove_entity(player.entity_id)

    assert world.entities_in_chunk(key) == []
    assert world.entities_near(player.position, 50.0) == []


def test_soft_aim_finds_a_creature_but_not_another_player(world: World):
    corridor = world.chunk_centre(ChunkAddress.edge(world.edge.edge_id, 0, 0, 0))
    player = _player(world, at=corridor)
    bystander = _player(world, at=WorldPoint(corridor.x + 1.0, corridor.y))
    slime = _npc(world, "slime", WorldPoint(corridor.x + 2.0, corridor.y))

    assert world.nearest_enemy(player, 10.0, hostile_to_players=True) is slime
    assert world.nearest_enemy(player, 10.0, hostile_to_players=False) is bystander


def test_the_dead_are_not_valid_targets(world: World):
    corridor = world.chunk_centre(ChunkAddress.edge(world.edge.edge_id, 0, 0, 0))
    player = _player(world, at=corridor)
    slime = _npc(world, "slime", WorldPoint(corridor.x + 1.0, corridor.y))
    slime.health = 0

    assert world.nearest_enemy(player, 10.0) is None


def test_water_is_not_cover(world: World):
    """`blocks_sight` lets water through on purpose: a river should not be a wall."""
    spawn = world.spawn_point_for(world.hubs[0])
    for offset in range(1, 5):
        world.set_tile_at(WorldPoint(spawn.x + offset, spawn.y), int(Tile.WATER))
    assert not world.is_walkable_at(WorldPoint(spawn.x + 2.0, spawn.y))

    assert world.has_line_of_sight(spawn, WorldPoint(spawn.x + 5.0, spawn.y))


def test_a_wall_is_cover(world: World):
    spawn = world.spawn_point_for(world.hubs[0])
    world.set_tile_at(WorldPoint(spawn.x + 2.0, spawn.y), int(Tile.WALL_STONE))

    assert not world.has_line_of_sight(spawn, WorldPoint(spawn.x + 5.0, spawn.y))


def test_two_adjacent_points_always_see_each_other(world: World):
    spawn = world.spawn_point_for(world.hubs[0])
    world.set_tile_at(spawn, int(Tile.WALL_STONE))

    assert world.has_line_of_sight(spawn, WorldPoint(spawn.x + 0.2, spawn.y))


def test_a_spawn_plaza_is_always_walkable(world: World):
    for hub in world.hubs.values():
        assert world.is_walkable_at(world.spawn_point_for(hub)), hub.name


def test_hub_warmup_is_ordered_outward_from_the_plaza(world: World):
    addresses = world.hub_chunk_addresses()
    first = addresses[0]

    assert (first.chunk_x, first.chunk_y) == (0, 0)
    rings = [max(abs(a.chunk_x), abs(a.chunk_y)) for a in addresses if a.hub_id == first.hub_id]
    assert rings == sorted(rings)


def test_the_day_advances_and_wraps(world: World, clock: ManualClock):
    from age.domain.constants import DAY_LENGTH_SECONDS

    dawn = world.day_phase
    clock.advance(DAY_LENGTH_SECONDS * 0.5)
    noon = world.day_phase
    clock.advance(DAY_LENGTH_SECONDS * 0.5)

    assert noon > dawn
    assert world.day_phase == pytest.approx(dawn, abs=1e-6)


def test_weather_holds_for_its_spell_then_rolls_again(world: World, clock: ManualClock):
    world.update_weather(clock.now(), weather.choose)
    settled = world.weather

    assert not world.update_weather(clock.now(), weather.choose)
    assert world.weather == settled

    clock.advance(3600.0)
    world.update_weather(clock.now(), weather.choose)
    assert isinstance(world.weather, int)


def test_weather_is_deterministic_for_a_given_world(world: World, clock: ManualClock):
    world.update_weather(clock.now(), weather.choose)
    first = world.weather
    world._weather_until = 0.0

    world.update_weather(clock.now(), weather.choose)

    assert world.weather == first


def test_persisted_edits_survive_an_unload(world: World):
    address = ChunkAddress.hub(0, 0, 0)
    world.chunk(address).set_tile(5, int(Tile.WALL_STONE))
    overlay = world.chunk(address).snapshot_overlay()
    world.unload_chunk(address)

    world.apply_overlay(address, overlay)

    assert world.chunk(address).tile(5) == int(Tile.WALL_STONE)
    assert not world.chunk(address).dirty, "A restore is not an edit."


def test_the_description_is_serialisable(world: World):
    import json

    assert json.loads(json.dumps(world.describe()))["world_seed"] == WORLD_SEED


# --- coordinates ------------------------------------------------------------


def test_a_corridor_tile_projects_out_and_back_to_itself(world: World):
    """``world_to_edge`` is declared the inverse of ``edge_to_world``, so check that it is.

    Floating point makes an exact inverse unavailable: the direction vector is normalised,
    so a corridor running due east has a y component of -6.1e-17 and every projection
    through it carries a little error. Everywhere except a boundary that error is harmless,
    because it lands well inside the tile it belongs to. On a boundary it decides which side
    the point falls on, and one of those sides can be a lane the world has not opened.

    The two halves of the answer are held to different standards, and deliberately so. The
    segment and the lane are discrete: they name a chunk, a chunk key is looked up in the
    topology, and being one out is the whole bug — so they have to come back exactly. The
    tile offsets are continuous and only have to be accurate; a millionth of a tile off is
    a position, not a different tile. Halves are in the sample as a control, to show the
    snap does not reach into the middle of a tile to tidy values that were never at risk.
    """
    interesting = (0.0, 0.5, 1.0, 16.0, 31.0, 31.5)

    for segment in range(world.topology.segments):
        for lane in (-1, 0, 1):
            for tile_x in interesting:
                for tile_y in interesting:
                    point = coordinates.edge_to_world(world.edge, segment, lane, tile_x, tile_y)
                    back_segment, back_lane, back_x, back_y = coordinates.world_to_edge(
                        world.edge, point
                    )
                    where = f"segment {segment} lane {lane} tile ({tile_x}, {tile_y})"

                    assert (back_segment, back_lane) == (segment, lane), (
                        f"{where} came back addressing chunk ({back_segment}, {back_lane})"
                    )
                    assert back_x == pytest.approx(tile_x, abs=1e-9), f"{where} moved across"
                    assert back_y == pytest.approx(tile_y, abs=1e-9), f"{where} moved along"


def test_a_hub_location_round_trips_through_the_plane(world: World):
    hub = world.hubs[1]
    point = WorldPoint(hub.centre.x + 3.25, hub.centre.y - 7.5)

    location = world.locate(point)
    back = world.resolve(location)

    assert location.space_type is SpaceType.HUB
    assert location.hub_id == 1
    assert back.x == pytest.approx(point.x)
    assert back.y == pytest.approx(point.y)


def test_a_corridor_location_round_trips_through_the_plane(world: World):
    point = world.chunk_centre(ChunkAddress.edge(world.edge.edge_id, 1, 0, 0))

    location = world.locate(point)
    back = world.resolve(location)

    assert location.space_type is SpaceType.EDGE
    assert back.x == pytest.approx(point.x, abs=1e-6)
    assert back.y == pytest.approx(point.y, abs=1e-6)


def test_a_chunk_key_carries_everything_needed_to_rebuild_it(world: World):
    """The key is a persistence key, so its shape is part of the storage contract."""
    assert ChunkAddress.hub(1, -2, 3).key == "hub:1:-2:3"
    assert ChunkAddress.edge("e", 5, -1, 1).key == "edge:e:5:-1:1"
    assert ChunkAddress.hub(0, 0, 0).key != ChunkAddress.hub(1, 0, 0).key


def test_the_two_hubs_are_far_enough_apart_for_the_corridor(world: World):
    a, b = world.hubs[0], world.hubs[1]

    separation = a.centre.distance_to(b.centre)

    assert separation >= HUB_RADIUS_TILES * 2 + world.topology.segments * CHUNK_TILES - 1e-6


def test_a_lane_offset_shifts_across_the_corridor_not_along_it(world: World):
    centre = world.chunk_centre(ChunkAddress.edge(world.edge.edge_id, 0, 0, 0))
    left = world.chunk_centre(ChunkAddress.edge(world.edge.edge_id, 0, -1, 1))
    right = world.chunk_centre(ChunkAddress.edge(world.edge.edge_id, 0, 1, 1))

    assert left.distance_to(centre) == pytest.approx(right.distance_to(centre))
    assert left.distance_to(right) == pytest.approx(2 * CHUNK_TILES, abs=1e-6)


def test_hashing_is_stable_across_argument_order():
    """Chunk seeds are combined from coordinates; order has to matter."""
    assert hashing.combine(1, 2, 3) != hashing.combine(3, 2, 1)
    assert hashing.combine(1, 2, 3) == hashing.combine(1, 2, 3)
