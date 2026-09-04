"""The event queue between the simulation and the transport.

Implements :class:`~age.domain.ports.EventSink`. The simulation posts facts here
and never learns who received them; the presentation layer drains the queue after
each tick and works out the audience.

The indirection buys two things. Systems stay synchronous and testable, because
posting an event is a list append rather than an await. And the fan-out policy,
which is really a networking concern, stays out of the combat code.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..domain.coordinates import LocationRef
from ..domain.entities import EntityId


@dataclass(frozen=True, slots=True)
class CombatEvent:
    attacker_id: EntityId
    target_id: EntityId
    ability_id: int
    damage: int
    healing: int
    killed: bool


@dataclass(frozen=True, slots=True)
class TileEvent:
    chunk_key: str
    changes: dict[int, int]


@dataclass(frozen=True, slots=True)
class SystemMessageEvent:
    text: str
    location: LocationRef | None = None


@dataclass(slots=True)
class EventQueue:
    """Accumulates one tick's worth of events."""

    spawned: list[EntityId] = field(default_factory=list)
    despawned: list[tuple[EntityId, int]] = field(default_factory=list)
    combat: list[CombatEvent] = field(default_factory=list)
    tiles: list[TileEvent] = field(default_factory=list)
    topology_versions: list[int] = field(default_factory=list)
    messages: list[SystemMessageEvent] = field(default_factory=list)

    # --- EventSink -----------------------------------------------------------

    def entity_spawned(self, entity_id: EntityId) -> None:
        self.spawned.append(entity_id)

    def entity_despawned(self, entity_id: EntityId, reason: int) -> None:
        self.despawned.append((entity_id, reason))

    def combat_resolved(
        self,
        attacker_id: EntityId,
        target_id: EntityId,
        ability_id: int,
        damage: int,
        healing: int,
        killed: bool,
    ) -> None:
        self.combat.append(
            CombatEvent(attacker_id, target_id, ability_id, damage, healing, killed)
        )

    def tiles_changed(self, chunk_key: str, changes: dict[int, int]) -> None:
        self.tiles.append(TileEvent(chunk_key, dict(changes)))

    def topology_changed(self, version: int) -> None:
        # Several systems can notice the same change in one tick; the transport
        # only needs to know that it happened, and the newest version wins.
        if version not in self.topology_versions:
            self.topology_versions.append(version)

    def system_message(self, text: str, location: LocationRef | None = None) -> None:
        self.messages.append(SystemMessageEvent(text, location))

    # --- draining ------------------------------------------------------------

    @property
    def is_empty(self) -> bool:
        return not (
            self.spawned
            or self.despawned
            or self.combat
            or self.tiles
            or self.topology_versions
            or self.messages
        )

    def drain(self) -> "EventQueue":
        """Hand over everything accumulated and reset.

        Returns a new queue holding the events rather than clearing in place, so a
        caller iterating the result cannot be surprised by the next tick appending
        to the list underneath it.
        """
        taken = EventQueue(
            spawned=self.spawned,
            despawned=self.despawned,
            combat=self.combat,
            tiles=self.tiles,
            topology_versions=self.topology_versions,
            messages=self.messages,
        )
        self.spawned = []
        self.despawned = []
        self.combat = []
        self.tiles = []
        self.topology_versions = []
        self.messages = []
        return taken
