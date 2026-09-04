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

from ..domain.classes import get_class
from ..domain.constants import (
    BASE_MAX_HEALTH,
    BASE_MAX_RESOURCE,
    ENTITY_PLAYER,
    MAX_NAME_LENGTH,
    RESPAWN_DELAY_SECONDS,
)
from ..domain.coordinates import LocationRef, SpaceType, WorldPoint
from ..domain.entities import Appearance, DirtyField, Entity, EntityId, PlayerSession
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

        character_class = get_class(int(stored["class_id"]) if stored else class_id)
        max_health = int(BASE_MAX_HEALTH * character_class.health_multiplier)
        max_resource = int(BASE_MAX_RESOURCE * character_class.resource_multiplier)

        spawn = self._spawn_point(stored)

        entity = Entity(
            entity_id=self.world.allocate_entity_id(),
            kind=ENTITY_PLAYER,
            position=spawn,
            name=name,
            class_id=character_class.class_id,
            health=max_health,
            max_health=max_health,
            resource=max_resource,
            max_resource=max_resource,
            appearance=_appearance_from(stored, appearance),
            level=int(stored.get("level", 1)) if stored else 1,
            experience=int(stored.get("experience", 0)) if stored else 0,
        )
        if stored and isinstance(stored.get("inventory"), dict):
            entity.inventory = {
                str(key): int(value) for key, value in stored["inventory"].items()
            }

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
                "inventory": dict(entity.inventory),
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
