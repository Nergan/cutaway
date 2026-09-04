"""Entities and their components.

GDD 16.6 chose a light ECS-inspired model over a framework: an entity is an id,
components are data-only, systems are functions. This file is the data half.

Python cannot give a struct-of-arrays layout any real cache benefit, so entities
here are ``slots``-based dataclasses with the components inlined. What matters is
the *shape*: components stay data-only and systems stay outside, so replacing this
module with a real SoA core in another language does not disturb the application
layer that reads it.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from enum import IntFlag

from .classes import CharacterClass, get_class
from .constants import (
    BASE_MAX_HEALTH,
    BASE_MAX_RESOURCE,
    ENTITY_NPC,
    ENTITY_PLAYER,
    POSITION_HISTORY_SECONDS,
    SIMULATION_HZ,
    WALK_SPEED_TILES_S,
)
from .coordinates import LocationRef, WorldPoint
from .npc import AIState, NpcArchetype

EntityId = int


class DirtyField(IntFlag):
    """Which parts of an entity changed since the last snapshot.

    Delta compression sends only the flagged fields (TDD 5.2). The flags are
    ordered the same way the encoder writes them, so the decoder can walk the
    bits without a lookup table.
    """

    NONE = 0
    POSITION = 1 << 0
    VELOCITY = 1 << 1
    FACING = 1 << 2
    HEALTH = 1 << 3
    RESOURCE = 1 << 4
    STATE = 1 << 5
    APPEARANCE = 1 << 6

    ALL = POSITION | VELOCITY | FACING | HEALTH | RESOURCE | STATE | APPEARANCE


@dataclass(slots=True)
class Appearance:
    """Everything the client needs to pick a rig and tint it.

    Deliberately a handful of small integers rather than a URL: the client builds
    its sprites procedurally from these, so a new character costs seven bytes on
    the wire instead of a texture download.
    """

    body: int = 0
    hair: int = 0
    palette: int = 0
    outfit: int = 0
    accent: int = 0

    def pack(self) -> tuple[int, int, int, int, int]:
        return (self.body, self.hair, self.palette, self.outfit, self.accent)


@dataclass(slots=True)
class Entity:
    """One simulated thing.

    ``position`` is layer-3 (continuous tile coordinates on the rendered plane)
    because that is what movement and combat need every tick. ``location`` is the
    layer-1/2 form, recomputed only when the entity is about to be persisted,
    which keeps the accordion-safe representation authoritative for storage
    without paying for the conversion 30 times a second.
    """

    entity_id: EntityId
    kind: int
    position: WorldPoint
    facing: float = 0.0
    velocity: tuple[float, float] = (0.0, 0.0)

    health: int = BASE_MAX_HEALTH
    max_health: int = BASE_MAX_HEALTH
    resource: int = BASE_MAX_RESOURCE
    max_resource: int = BASE_MAX_RESOURCE

    name: str = ""
    class_id: int = 0
    level: int = 1
    experience: int = 0
    appearance: Appearance = field(default_factory=Appearance)

    speed: float = WALK_SPEED_TILES_S
    radius: float = 0.35

    # NPC-only.
    archetype: NpcArchetype | None = None
    ai_state: AIState = AIState.IDLE
    ai_state_entered_at: float = 0.0
    ai_target: EntityId | None = None
    patrol_anchor: WorldPoint | None = None
    patrol_target: WorldPoint | None = None

    # Combat bookkeeping. Cooldowns map ability id to the timestamp it frees up.
    cooldowns: dict[int, float] = field(default_factory=dict)
    last_ability_at: float = 0.0
    last_attack_at: float = 0.0
    dead_until: float = 0.0

    # Regeneration carries a fractional remainder between ticks. Health and
    # resource are integers on the wire, and a rate below one point per tick would
    # otherwise truncate to zero every tick and never regenerate at all.
    health_carry: float = 0.0
    resource_carry: float = 0.0

    # Position history for lag compensation (TDD 10.2). One second at the
    # simulation rate; a deque so the oldest sample falls off for free.
    history: deque[tuple[float, float, float]] = field(
        default_factory=lambda: deque(maxlen=max(2, int(POSITION_HISTORY_SECONDS * SIMULATION_HZ)))
    )

    dirty: DirtyField = DirtyField.ALL
    chunk_key: str = ""
    inventory: dict[str, int] = field(default_factory=dict)

    # --- derived ------------------------------------------------------------

    @property
    def is_alive(self) -> bool:
        return self.health > 0

    @property
    def is_player(self) -> bool:
        return self.kind == ENTITY_PLAYER

    @property
    def is_npc(self) -> bool:
        return self.kind == ENTITY_NPC

    @property
    def health_fraction(self) -> float:
        return self.health / self.max_health if self.max_health else 0.0

    @property
    def character_class(self) -> CharacterClass:
        return get_class(self.class_id)

    # --- mutation -----------------------------------------------------------

    def mark(self, fields: DirtyField) -> None:
        self.dirty |= fields

    def move_to(self, x: float, y: float) -> None:
        if x != self.position.x or y != self.position.y:
            self.position = WorldPoint(x, y)
            self.dirty |= DirtyField.POSITION

    def record_history(self, now: float) -> None:
        self.history.append((now, self.position.x, self.position.y))

    def position_at(self, when: float) -> WorldPoint:
        """Where this entity was at ``when``, for hit validation.

        Linearly interpolates between the two bracketing samples. Outside the
        retained window it clamps to the nearest end, which is safe because the
        caller has already refused rewinds beyond the compensation limit.
        """
        if not self.history:
            return self.position
        if when >= self.history[-1][0]:
            return self.position
        if when <= self.history[0][0]:
            return WorldPoint(self.history[0][1], self.history[0][2])

        previous = self.history[0]
        for sample in self.history:
            if sample[0] >= when:
                span = sample[0] - previous[0]
                if span <= 0.0:
                    return WorldPoint(sample[1], sample[2])
                t = (when - previous[0]) / span
                return WorldPoint(
                    previous[1] + (sample[1] - previous[1]) * t,
                    previous[2] + (sample[2] - previous[2]) * t,
                )
            previous = sample
        return self.position

    def apply_damage(self, amount: int) -> int:
        """Deal damage, returning how much actually landed."""
        if amount <= 0 or not self.is_alive:
            return 0
        applied = min(amount, self.health)
        self.health -= applied
        self.dirty |= DirtyField.HEALTH
        if self.health <= 0:
            self.dirty |= DirtyField.STATE
        return applied

    def apply_healing(self, amount: int) -> int:
        """Heal, returning how much was not wasted on full health."""
        if amount <= 0 or not self.is_alive:
            return 0
        applied = min(amount, self.max_health - self.health)
        if applied:
            self.health += applied
            self.dirty |= DirtyField.HEALTH
        return applied

    def spend_resource(self, amount: int) -> bool:
        if self.resource < amount:
            return False
        self.resource -= amount
        self.dirty |= DirtyField.RESOURCE
        return True

    def give(self, item: str, count: int) -> None:
        """Add to the inventory. Infinite by design (GDD 6.1), so no capacity."""
        if count <= 0:
            return
        self.inventory[item] = self.inventory.get(item, 0) + count

    def take(self, item: str, count: int) -> bool:
        held = self.inventory.get(item, 0)
        if held < count:
            return False
        remaining = held - count
        if remaining:
            self.inventory[item] = remaining
        else:
            self.inventory.pop(item, None)
        return True

    def enter_ai_state(self, state: AIState, now: float) -> None:
        if state is not self.ai_state:
            self.ai_state = state
            self.ai_state_entered_at = now
            self.dirty |= DirtyField.STATE


@dataclass(slots=True)
class PlayerSession:
    """Per-connection state, separate from the entity it drives.

    Kept apart so the simulation never has to know about sockets, and so a
    reconnect can re-attach to an existing entity.
    """

    session_id: str
    entity_id: EntityId
    character_name: str
    # Highest input sequence the server has processed, echoed back so the client
    # knows which of its predicted inputs are now confirmed (TDD 5.3).
    last_input_sequence: int = 0
    last_seen_at: float = 0.0
    acknowledged_topology: int = 0
    # Chunk keys the client currently holds, so spawns and tile deltas are only
    # sent for terrain it can actually render.
    loaded_chunks: set[str] = field(default_factory=set)
    known_entities: set[EntityId] = field(default_factory=set)
    chat_timestamps: deque[float] = field(default_factory=lambda: deque(maxlen=16))
    location: LocationRef | None = None
    ready: bool = False


class EntityIdAllocator:
    """Monotonic entity ids.

    Never reuses an id: a stale packet referring to a dead entity must resolve to
    nothing rather than to whatever now occupies that slot.
    """

    __slots__ = ("_next",)

    def __init__(self, start: EntityId = 1) -> None:
        self._next = start

    def allocate(self) -> EntityId:
        value = self._next
        self._next += 1
        return value

    @property
    def peek(self) -> EntityId:
        return self._next
