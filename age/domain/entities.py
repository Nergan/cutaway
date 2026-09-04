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

from .classes import CharacterClass, experience_for_level, get_class
from .constants import (
    BASE_MAX_HEALTH,
    BASE_MAX_RESOURCE,
    COMPOSE_LEVEL,
    ENTITY_NPC,
    ENTITY_PLAYER,
    HEALTH_PER_LEVEL,
    POSITION_HISTORY_SECONDS,
    RESOURCE_PER_LEVEL,
    SIMULATION_HZ,
    WALK_SPEED_TILES_S,
)
from .coordinates import LocationRef, WorldPoint
from .items import INVENTORY_SLOTS, ITEMS, total_bonus
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
class ItemStack:
    """One occupied inventory slot.

    Mutable, unlike almost everything else in the domain, because the alternative is
    rebuilding the list on every point of a harvest. The list *position* is the
    handle the client sends back, so nothing may reorder it silently.
    """

    key: str
    count: int


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

    # What the worn loadout is worth, folded into two numbers by
    # :meth:`refresh_stats` so combat and movement read a field rather than walking
    # the equipment map every tick. The pools are folded into ``max_health`` and
    # ``max_resource`` for the same reason.
    bonus_damage: int = 0
    bonus_speed: float = 0.0

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

    # A list rather than a mapping of key to count, because the pack is bounded and a
    # bound is over *slots*: two half stacks of wood are two slots even though they
    # are one kind of thing, and that is the cost the player is being asked to weigh.
    inventory: list[ItemStack] = field(default_factory=list)
    # Slot value from :class:`~age.domain.items.EquipmentSlot` to item key. Integer
    # keys rather than the enum so the whole map serialises without a converter.
    equipment: dict[int, str] = field(default_factory=dict)

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

    @property
    def can_compose(self) -> bool:
        """Whether this character is owed the level-up class choice (GDD 6.3).

        Derived rather than stored, so an unclaimed choice survives a reconnect and
        cannot be spent twice: the moment the second half lands the class stops being
        a base class and this goes false on its own.
        """
        return (
            self.is_player
            and self.level >= COMPOSE_LEVEL
            and get_class(self.class_id).is_base
        )

    @property
    def experience_to_next_level(self) -> int:
        return experience_for_level(self.level)

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

    # --- carrying things ----------------------------------------------------

    def count_of(self, item: str) -> int:
        return sum(stack.count for stack in self.inventory if stack.key == item)

    def give(self, item: str, count: int) -> int:
        """Store up to ``count`` of an item, returning how much actually fitted.

        A bounded pack has to be able to refuse, and a caller that cannot tell how
        much was refused would silently void the remainder of a drop. Existing
        stacks are topped up before a new slot is opened, so a full pack still
        accepts wood as long as it is already carrying some.
        """
        if count <= 0:
            return 0

        catalogued = ITEMS.get(item)
        # An uncatalogued key can only come from stale storage. Treating it as
        # unstackable keeps it visible and removable rather than merging it into
        # something it is not.
        limit = catalogued.stack_limit if catalogued is not None else 1

        remaining = count
        for stack in self.inventory:
            if remaining <= 0:
                break
            if stack.key != item or stack.count >= limit:
                continue
            moved = min(limit - stack.count, remaining)
            stack.count += moved
            remaining -= moved

        while remaining > 0 and len(self.inventory) < INVENTORY_SLOTS:
            moved = min(limit, remaining)
            self.inventory.append(ItemStack(item, moved))
            remaining -= moved

        return count - remaining

    def take(self, item: str, count: int) -> bool:
        """Remove ``count`` of an item, all or nothing."""
        if count <= 0:
            return True
        if self.count_of(item) < count:
            return False

        remaining = count
        for stack in list(self.inventory):
            if remaining <= 0:
                break
            if stack.key != item:
                continue
            moved = min(stack.count, remaining)
            stack.count -= moved
            remaining -= moved
            if stack.count <= 0:
                self.inventory.remove(stack)
        return True

    def discard(self, index: int, count: int) -> bool:
        """Throw away part of a stack. Dropped items are gone, not put on the ground."""
        if index < 0 or index >= len(self.inventory) or count <= 0:
            return False
        stack = self.inventory[index]
        stack.count -= min(count, stack.count)
        if stack.count <= 0:
            del self.inventory[index]
        return True

    # --- wearing things -----------------------------------------------------

    def refresh_stats(self) -> None:
        """Recompute the pools and combat bonuses from class, level, and equipment.

        One formula, called from everywhere the inputs change, because the three
        places that used to derive these independently disagreed: joining ignored
        level entirely, levelling added a flat six, and composing overwrote the
        total from the class multiplier and threw the level bonus away.

        Only players have a class to derive from; an NPC's pool is its archetype's
        and nothing here may touch it.
        """
        if not self.is_player:
            return

        bonus = total_bonus(self.equipment.values())
        character_class = self.character_class
        growth = self.level - 1

        self.max_health = max(
            1,
            int(BASE_MAX_HEALTH * character_class.health_multiplier)
            + HEALTH_PER_LEVEL * growth
            + bonus.health,
        )
        self.max_resource = max(
            0,
            int(BASE_MAX_RESOURCE * character_class.resource_multiplier)
            + RESOURCE_PER_LEVEL * growth
            + bonus.resource,
        )
        self.bonus_damage = bonus.damage
        self.bonus_speed = bonus.speed

        self.health = min(self.health, self.max_health)
        self.resource = min(self.resource, self.max_resource)
        # Vitals travel as a fraction of the maximum, so a pool that grew changes
        # what the client should draw even though the absolute value did not move.
        self.mark(DirtyField.HEALTH | DirtyField.RESOURCE)

    def equip(self, index: int) -> bool:
        """Wear the item in inventory slot ``index``, swapping out what it replaces.

        The incoming item leaves the pack before the outgoing one enters it, so
        swapping with a full pack works: the slot the new piece vacated is the slot
        the old piece lands in.
        """
        if index < 0 or index >= len(self.inventory):
            return False

        stack = self.inventory[index]
        item = ITEMS.get(stack.key)
        if item is None or not item.is_equippable:
            return False

        slot = int(item.slot)
        replaced = self.equipment.get(slot)

        stack.count -= 1
        if stack.count <= 0:
            del self.inventory[index]
        self.equipment[slot] = item.key

        if replaced is not None:
            self.give(replaced, 1)

        self.refresh_stats()
        return True

    def unequip(self, slot: int) -> bool:
        """Take off what is in ``slot``, provided there is somewhere to put it."""
        key = self.equipment.get(slot)
        if key is None:
            return False
        if self.give(key, 1) < 1:
            return False
        del self.equipment[slot]
        self.refresh_stats()
        return True

    def consume(self, index: int) -> bool:
        """Use up a consumable. Refuses when it would be wasted."""
        if index < 0 or index >= len(self.inventory) or not self.is_alive:
            return False

        stack = self.inventory[index]
        item = ITEMS.get(stack.key)
        if item is None or not item.is_consumable:
            return False

        healed = self.apply_healing(item.restores_health)
        restored = min(item.restores_resource, self.max_resource - self.resource)
        if restored > 0:
            self.resource += restored
            self.mark(DirtyField.RESOURCE)

        # Eating at full health should cost nothing. Without this the one button a
        # player presses in a panic is also the one that wastes the ration.
        if healed <= 0 and restored <= 0:
            return False

        stack.count -= 1
        if stack.count <= 0:
            del self.inventory[index]
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
