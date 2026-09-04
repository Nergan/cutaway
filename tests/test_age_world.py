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

import pytest

from age.application import ai, chat, combat, movement, session, terrain, weather
from age.application.accordion import WorldManager
from age.application.events import EventQueue
from age.application.world import World, build_default_world
from age.domain import classes, coordinates, hashing
from age.domain.constants import (
    BASE_MAX_HEALTH,
    CHANNEL_GLOBAL,
    CHANNEL_LOCAL,
    CHANNEL_SYSTEM,
    CHAT_MAX_LENGTH,
    CHAT_RATE_LIMIT,
    CHUNK_TILES,
    CONTRACTION_PLAYER_THRESHOLD,
    CORRIDOR_SEGMENTS,
    ENTITY_NPC,
    ENTITY_PLAYER,
    EXPANSION_PLAYER_THRESHOLD,
    HUB_RADIUS_TILES,
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
    assert keys == {"cleave", "mend", "consecrate"}


def test_an_unknown_class_id_falls_back_rather_than_raising():
    """It arrives from an untrusted client or a stale row; neither is fatal."""
    assert classes.get_class(9999).class_id == 0


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
    assert player.inventory[material] == quantity
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
    assert player.inventory.get("wood", 0) == 0
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
    assert result.entity.class_id == 4
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
    warmaster = classes.CLASSES_BY_KEY["warmaster"]

    async def scenario():
        return await service.join(
            session_id="w",
            character_name="Bruna",
            class_id=warmaster.class_id,
            appearance=(0,) * 5,
        )

    entity = _run(scenario).entity

    assert entity.max_health == int(BASE_MAX_HEALTH * warmaster.health_multiplier)


def test_a_returning_character_keeps_its_class_and_inventory(world: World):
    service = session.SessionService(world, MemoryCharacterRepository())

    async def scenario():
        first = await service.join(
            session_id="a", character_name="Rowan", class_id=7, appearance=(1, 2, 3, 4, 5)
        )
        first.entity.give("wood", 12)
        await service.leave("a")
        return await service.join(
            session_id="b", character_name="Rowan", class_id=0, appearance=(9,) * 5
        )

    again = _run(scenario)

    assert again.returning
    assert again.entity.class_id == 7, "The stored class wins over the client's request."
    assert again.entity.inventory["wood"] == 12
    assert again.entity.appearance.pack() == (1, 2, 3, 4, 5)


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
    assert player.inventory["wood"] == 5


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
