"""NPC archetypes and the finite state machine that drives them.

GDD 16.5 chose an FSM over a behaviour tree for the MVP: five behaviours per NPC
is squarely where an enum plus a switch wins, and "which state am I in?" is a
question you can answer while looking at a log.

The transition table is data, and every transition that could oscillate has
hysteresis built into it, which is the failure mode FSMs are actually known for.
The ``behaviour_driver`` seam described in TDD 12.4 is the :class:`AIState` enum
plus :func:`next_state`; swapping in a behaviour tree means implementing the same
signature, not rewriting the callers.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class AIState(IntEnum):
    IDLE = 0
    PATROL = 1
    AGGRO = 2
    ATTACK = 3
    FLEE = 4
    DEAD = 5


@dataclass(frozen=True, slots=True)
class NpcArchetype:
    """Tuning for one kind of NPC. All values are placeholders, not balance.

    ``detection_radius`` is where aggro starts; the NPC only gives up at
    ``detection_radius * AGGRO_RELEASE_FACTOR``, so a player hovering exactly at
    the edge does not make it flicker between states.
    """

    npc_id: int
    key: str
    name: str
    max_health: int
    detection_radius: float
    attack_range: float
    attack_damage: int
    attack_cooldown_ms: int
    flee_threshold: float
    patrol_speed: float
    aggro_speed: float
    idle_duration_s: float
    experience: int
    loot: tuple[tuple[str, int], ...] = ()
    # Whether this archetype ever looks for something to fight. False for townsfolk,
    # who exist to be in the way and to be talked to. Without this they would have to
    # be given a zero detection radius, which is a different thing: a radius of zero
    # still runs target acquisition every decision tick for every villager in the hub,
    # and it still lets them retaliate, so a stray hit would turn a market square into
    # a brawl.
    hostile: bool = True
    # How far this archetype strays from where it was placed. Townsfolk keep to their
    # own patch of the square; a merchant who wanders off is no longer at their stall.
    patrol_radius_tiles: float = 10.0


# Values from TDD 12.3.
ARCHETYPES: tuple[NpcArchetype, ...] = (
    NpcArchetype(
        0, "bandit", "Bandit",
        max_health=60, detection_radius=8.0, attack_range=1.5, attack_damage=10,
        attack_cooldown_ms=1500, flee_threshold=0.15,
        patrol_speed=2.0, aggro_speed=3.4, idle_duration_s=3.0,
        experience=14, loot=(("coin", 6), ("fibre", 1)),
    ),
    NpcArchetype(
        1, "wolf", "Wolf",
        max_health=45, detection_radius=12.0, attack_range=1.5, attack_damage=6,
        attack_cooldown_ms=800, flee_threshold=0.10,
        patrol_speed=3.0, aggro_speed=4.6, idle_duration_s=2.0,
        experience=10, loot=(("hide", 2),),
    ),
    NpcArchetype(
        2, "golem", "Golem",
        max_health=180, detection_radius=6.0, attack_range=2.0, attack_damage=20,
        attack_cooldown_ms=3000, flee_threshold=0.05,
        patrol_speed=1.0, aggro_speed=1.6, idle_duration_s=5.0,
        experience=34, loot=(("stone", 6),),
    ),
    NpcArchetype(
        3, "archer", "Archer",
        max_health=50, detection_radius=10.0, attack_range=8.0, attack_damage=8,
        attack_cooldown_ms=2000, flee_threshold=0.25,
        patrol_speed=2.0, aggro_speed=3.0, idle_duration_s=3.5,
        experience=16, loot=(("coin", 8), ("wood", 1)),
    ),
    NpcArchetype(
        4, "slime", "Slime",
        max_health=28, detection_radius=5.0, attack_range=1.0, attack_damage=3,
        attack_cooldown_ms=1200, flee_threshold=0.30,
        patrol_speed=1.5, aggro_speed=2.0, idle_duration_s=2.5,
        experience=5, loot=(("fibre", 1),),
    ),
    NpcArchetype(
        5, "guard", "Hub Guard",
        # Guards never flee and never leave: they exist to make the hub feel safe
        # and to answer anyone who breaks that (GDD 11.1).
        max_health=220, detection_radius=9.0, attack_range=1.8, attack_damage=24,
        attack_cooldown_ms=1200, flee_threshold=0.0,
        patrol_speed=1.8, aggro_speed=3.6, idle_duration_s=4.0,
        experience=0,
    ),
    # Townsfolk. No combat statistics that matter — they are scenery that moves, and
    # that is the point: a hub with four guards standing at compass points reads as a
    # checkpoint, and the same square with a dozen people crossing it reads as a town.
    # They keep a nominal health pool so nothing downstream has to special-case a
    # zero-health entity, and give no experience so they are worthless to kill.
    NpcArchetype(
        6, "villager", "Villager",
        max_health=40, detection_radius=0.0, attack_range=0.0, attack_damage=0,
        attack_cooldown_ms=0, flee_threshold=0.0,
        # Slower than a player walks. Townsfolk moving at player pace look like they
        # are all late for something.
        patrol_speed=1.1, aggro_speed=1.1, idle_duration_s=6.0,
        experience=0, hostile=False, patrol_radius_tiles=7.0,
    ),
    NpcArchetype(
        7, "merchant", "Merchant",
        max_health=40, detection_radius=0.0, attack_range=0.0, attack_damage=0,
        attack_cooldown_ms=0, flee_threshold=0.0,
        # Tied to a stall, so barely moves at all: a step behind the counter and back.
        patrol_speed=0.7, aggro_speed=0.7, idle_duration_s=9.0,
        experience=0, hostile=False, patrol_radius_tiles=1.5,
    ),
    NpcArchetype(
        8, "smith", "Blacksmith",
        max_health=60, detection_radius=0.0, attack_range=0.0, attack_damage=0,
        attack_cooldown_ms=0, flee_threshold=0.0,
        patrol_speed=0.8, aggro_speed=0.8, idle_duration_s=8.0,
        experience=0, hostile=False, patrol_radius_tiles=2.0,
    ),
    NpcArchetype(
        9, "child", "Child",
        max_health=20, detection_radius=0.0, attack_range=0.0, attack_damage=0,
        attack_cooldown_ms=0, flee_threshold=0.0,
        # Fast and rarely still, which is most of what distinguishes a child from a
        # villager when both are twenty pixels tall.
        patrol_speed=2.6, aggro_speed=2.6, idle_duration_s=1.2,
        experience=0, hostile=False, patrol_radius_tiles=9.0,
    ),
)

ARCHETYPES_BY_ID: dict[int, NpcArchetype] = {entry.npc_id: entry for entry in ARCHETYPES}
ARCHETYPES_BY_KEY: dict[str, NpcArchetype] = {entry.key: entry for entry in ARCHETYPES}

# Hostile spawns for the wilds, weighted by how deep into the corridor they are.
# Index is the danger rating of the biome the chunk landed in.
SPAWN_TABLE: tuple[tuple[str, ...], ...] = (
    ("slime",),
    ("slime", "wolf"),
    ("wolf", "bandit", "slime"),
    ("bandit", "archer", "wolf"),
    ("golem", "bandit", "archer"),
)

# Leaving aggro takes 50% more distance than entering it.
AGGRO_RELEASE_FACTOR = 1.5
# Recovering out of FLEE needs the health threshold beaten by 50%.
FLEE_RECOVERY_FACTOR = 1.5


@dataclass(slots=True)
class AISnapshot:
    """The inputs a transition decision needs, gathered by the caller.

    Passing a value object rather than the live world keeps :func:`next_state`
    pure, which is what lets the FSM be unit-tested without a world at all.
    """

    state: AIState
    health_fraction: float
    target_distance: float | None
    has_target: bool
    target_alive: bool
    time_in_state: float
    enemy_nearby: bool


def next_state(archetype: NpcArchetype, snapshot: AISnapshot) -> AIState:
    """The transition table from GDD 16.5, hysteresis included.

    Ordered by priority: death first because it overrides everything, then the
    flee check because being about to die outranks whatever else was happening.
    """
    if snapshot.health_fraction <= 0.0:
        return AIState.DEAD
    if snapshot.state is AIState.DEAD:
        return AIState.DEAD

    fleeing_now = snapshot.state is AIState.FLEE
    flee_floor = archetype.flee_threshold * (FLEE_RECOVERY_FACTOR if fleeing_now else 1.0)
    if archetype.flee_threshold > 0.0 and snapshot.health_fraction < flee_floor:
        return AIState.FLEE

    if fleeing_now:
        # Health has recovered past the hysteresis band; where it goes next
        # depends on whether the thing it fled from is still around.
        return AIState.PATROL if not snapshot.enemy_nearby else AIState.AGGRO

    if snapshot.state in (AIState.AGGRO, AIState.ATTACK):
        if not snapshot.has_target or not snapshot.target_alive:
            return AIState.IDLE
        distance = snapshot.target_distance
        if distance is None or distance > archetype.detection_radius * AGGRO_RELEASE_FACTOR:
            return AIState.PATROL
        return AIState.ATTACK if distance <= archetype.attack_range else AIState.AGGRO

    # IDLE and PATROL both watch for something to notice.
    if snapshot.has_target and snapshot.target_alive:
        distance = snapshot.target_distance
        if distance is not None and distance <= archetype.detection_radius:
            return AIState.ATTACK if distance <= archetype.attack_range else AIState.AGGRO

    if snapshot.state is AIState.IDLE and snapshot.time_in_state >= archetype.idle_duration_s:
        return AIState.PATROL
    return snapshot.state


def speed_for_state(archetype: NpcArchetype, state: AIState) -> float:
    """How fast the NPC moves in a given state."""
    if state in (AIState.AGGRO, AIState.FLEE):
        return archetype.aggro_speed
    if state is AIState.PATROL:
        return archetype.patrol_speed
    return 0.0


def get_archetype(npc_id: int) -> NpcArchetype:
    return ARCHETYPES_BY_ID.get(npc_id, ARCHETYPES_BY_ID[4])
