"""Joining, leaving, persisting, and respawning characters.

The lifecycle of a player, kept apart from the transport that carries it. A
WebSocket closing is not the same event as a character leaving the world, and
separating them is what makes a grace period or a reconnect a change here rather
than a change in the socket handler.

Character state is in the zero-loss tier of TDD 9.1, so it is written on join, on
leave, and on level-up rather than batched with terrain.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from ..domain.classes import base_class_or_default, get_class
from ..domain.constants import (
    ENTITY_PLAYER,
    MAX_NAME_LENGTH,
    RESPAWN_DELAY_SECONDS,
)
from ..domain.coordinates import LocationRef, SpaceType, WorldPoint
from ..domain.entities import Appearance, DirtyField, Entity, EntityId, PlayerSession
from ..domain.items import ITEMS
from ..domain.ports import CharacterRepository
from .movement import find_walkable_near
from .world import World

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class JoinResult:
    session: PlayerSession
    entity: Entity
    returning: bool


class SessionService:
    """Creates, restores, and retires player characters."""

    __slots__ = ("world", "characters")

    def __init__(self, world: World, characters: CharacterRepository | None = None) -> None:
        self.world = world
        self.characters = characters

    async def join(
        self,
        *,
        session_id: str,
        character_name: str,
        class_id: int,
        appearance: tuple[int, int, int, int, int],
    ) -> JoinResult:
        """Bring a character into the world, restoring saved state if any."""
        name = normalise_name(character_name) or f"Wanderer{session_id[:4]}"
        now = self.world.now

        stored = await self.characters.load(name) if self.characters else None
        returning = stored is not None

        # A new character may only be one of the four base classes (GDD 6.3): the
        # hybrids are earned at level-up, not picked from a menu. A returning one keeps
        # whatever they composed into, so the stored id is taken as it stands.
        character_class = (
            get_class(int(stored["class_id"]))
            if stored
            else base_class_or_default(class_id)
        )
        spawn = self._spawn_point(stored)

        entity = Entity(
            entity_id=self.world.allocate_entity_id(),
            kind=ENTITY_PLAYER,
            position=spawn,
            name=name,
            class_id=character_class.class_id,
            appearance=_appearance_from(stored, appearance),
            level=int(stored.get("level", 1)) if stored else 1,
            experience=int(stored.get("experience", 0)) if stored else 0,
        )
        _restore_carried(entity, stored)
        # After the loadout, never before: the pools depend on what is worn, and a
        # character topped up from the wrong maximum arrives either wounded or over
        # full.
        entity.refresh_stats()
        entity.health = entity.max_health
        entity.resource = entity.max_resource

        self.world.add_entity(entity)

        session = PlayerSession(
            session_id=session_id,
            entity_id=entity.entity_id,
            character_name=name,
            last_seen_at=now,
            acknowledged_topology=self.world.topology.topology_version,
        )
        self.world.sessions[session_id] = session

        logger.info(
            "%s joined as %s (%s), entity %d",
            session_id,
            name,
            character_class.key,
            entity.entity_id,
        )
        return JoinResult(session=session, entity=entity, returning=returning)

    async def leave(self, session_id: str) -> EntityId | None:
        """Persist and remove a character. Returns the freed entity id."""
        session = self.world.sessions.pop(session_id, None)
        if session is None:
            return None

        entity = self.world.entities.get(session.entity_id)
        if entity is not None:
            await self.persist(entity)
            self.world.remove_entity(entity.entity_id)

        logger.info("%s left (%s)", session_id, session.character_name)
        return session.entity_id

    async def persist(self, entity: Entity) -> None:
        """Write a character in its accordion-safe form.

        Stored as a :class:`~age.domain.coordinates.LocationRef`, never as plane
        coordinates: a tier change would otherwise silently move every saved
        character (Accordion Spec 3.1).
        """
        if self.characters is None:
            return

        location = self.world.locate(entity.position)
        await self.characters.save(
            entity.name,
            {
                "class_id": entity.class_id,
                "level": entity.level,
                "experience": entity.experience,
                "health": entity.health,
                "resource": entity.resource,
                # A list of documents rather than a mapping of key to count, because
                # slot order is what the client addresses and a mapping would lose it
                # along with the distinction between one stack and two.
                "inventory": [
                    {"key": stack.key, "count": stack.count} for stack in entity.inventory
                ],
                # BSON keys must be strings, so the slot travels as one.
                "equipment": {str(slot): key for slot, key in entity.equipment.items()},
                "appearance": list(entity.appearance.pack()),
                "location": _location_to_document(location),
            },
        )

    def respawn(self, entity: Entity, now: float) -> bool:
        """Return a dead player to their nearest hub once the delay has passed.

        Death costs time and position, not progress: no experience or inventory is
        taken, per GDD 8.4. The penalty is the walk back.
        """
        if entity.is_alive:
            return False
        if entity.dead_until == 0.0:
            entity.dead_until = now + RESPAWN_DELAY_SECONDS
            return False
        if now < entity.dead_until:
            return False

        hub = self.world.nearest_hub(entity.position)
        destination = find_walkable_near(self.world, self.world.spawn_point_for(hub))

        entity.health = entity.max_health
        entity.resource = entity.max_resource
        entity.health_carry = 0.0
        entity.resource_carry = 0.0
        entity.dead_until = 0.0
        entity.velocity = (0.0, 0.0)
        entity.move_to(destination.x, destination.y)
        entity.mark(DirtyField.ALL)
        self.world.reindex(entity)
        return True

    def _spawn_point(self, stored: dict[str, object] | None) -> WorldPoint:
        """Where a joining character appears.

        A returning character resumes where it saved, provided that spot still
        exists in the current topology; a contraction can retire the lane it left
        from, in which case it falls back to a hub. New characters always start on
        a hub plaza.
        """
        hub = self.world.hubs[min(self.world.hubs)]
        point = self.world.spawn_point_for(hub)

        document = stored.get("location") if stored else None
        if isinstance(document, dict):
            location = _location_from_document(document)
            if location is not None:
                try:
                    saved = self.world.resolve(location)
                except KeyError:
                    saved = None
                if saved is not None and self.world.contains(saved):
                    point = saved

        return find_walkable_near(self.world, point)


def normalise_name(raw: str) -> str:
    """Clean a client-supplied character name.

    Letters, digits, spaces and hyphens only. Names are displayed to other players
    and used as the storage key, so anything that could be confused with markup or
    with another player's name is stripped rather than escaped at each use site.
    """
    kept = [
        character
        for character in raw.strip()
        if character.isalnum() or character in " -'"
    ]
    return " ".join("".join(kept).split())[:MAX_NAME_LENGTH]


def _restore_carried(entity: Entity, stored: dict[str, object] | None) -> None:
    """Put back what a returning character was carrying and wearing.

    Everything is filtered through the catalogue rather than trusted. A stored
    document outlives the release that wrote it, so an item retired since then must
    be dropped quietly here instead of making its owner unable to log in.
    """
    if stored is None:
        return

    carried = stored.get("inventory")
    if isinstance(carried, list):
        for raw in carried:
            if isinstance(raw, dict) and str(raw.get("key", "")) in ITEMS:
                entity.give(str(raw["key"]), int(raw.get("count", 0)))
    elif isinstance(carried, dict):
        # The pre-equipment shape: a mapping of material to count. Read so a demo
        # database written before the pack was bounded still opens.
        for key, value in carried.items():
            if str(key) in ITEMS:
                entity.give(str(key), int(value))

    worn = stored.get("equipment")
    if isinstance(worn, dict):
        for key in worn.values():
            item = ITEMS.get(str(key))
            # The slot is re-derived from the catalogue rather than read back, so a
            # hand-edited document cannot wear a helm on its feet.
            if item is not None and item.is_equippable:
                entity.equipment[int(item.slot)] = item.key


def _appearance_from(
    stored: dict[str, object] | None, requested: tuple[int, int, int, int, int]
) -> Appearance:
    values = requested
    if stored and isinstance(stored.get("appearance"), list):
        raw = stored["appearance"]
        if len(raw) == 5:
            values = tuple(int(item) & 0xFF for item in raw)  # type: ignore[assignment]
    return Appearance(*values)


def _location_to_document(location: LocationRef) -> dict[str, object]:
    document: dict[str, object] = {
        "space": int(location.space_type),
        "tile_x": round(location.tile_x, 3),
        "tile_y": round(location.tile_y, 3),
    }
    if location.space_type is SpaceType.HUB:
        document["hub_id"] = location.hub_id
    else:
        document["edge_id"] = location.edge_id
        document["segment_index"] = location.segment_index
        document["lane_offset"] = location.lane_offset
    return document


def _location_from_document(document: dict[str, object]) -> LocationRef | None:
    try:
        space = SpaceType(int(document["space"]))
        tile_x = float(document["tile_x"])
        tile_y = float(document["tile_y"])
        if space is SpaceType.HUB:
            return LocationRef.in_hub(int(document["hub_id"]), tile_x, tile_y)
        return LocationRef.in_edge(
            str(document["edge_id"]),
            int(document["segment_index"]),
            int(document["lane_offset"]),
            tile_x,
            tile_y,
        )
    except (KeyError, TypeError, ValueError):
        # A malformed stored location is not worth refusing the login over; the
        # caller falls back to a hub spawn.
        return None
