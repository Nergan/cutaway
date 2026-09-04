"""Ability resolution: validation, lag compensation, and effects.

Server-authoritative throughout (TDD 10.1). The client sends an intent; this
module decides whether it was possible, and only then does anything happen. Every
rejection returns a specific error code rather than silence, because a client that
cannot tell "on cooldown" from "out of range" cannot show the player why nothing
happened.

Validation order is deliberate: cheapest and most common failures first, so a
spamming client is rejected by an integer comparison rather than a raycast.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from ..domain.classes import Ability, AbilityFlag, AbilityKind, get_ability
from ..domain.constants import (
    ABILITY_MIN_INTERVAL_MS,
    LAG_COMPENSATION_WINDOW_MS,
)
from ..domain.coordinates import WorldPoint
from ..domain.entities import DirtyField, Entity, EntityId
from ..infrastructure import wire
from .world import World


@dataclass(slots=True)
class CombatOutcome:
    """The result of one ability activation."""

    ok: bool
    error: int = 0
    ability: Ability | None = None
    impact: WorldPoint | None = None
    hits: list[tuple[EntityId, int, int, bool]] = field(default_factory=list)
    dash_to: WorldPoint | None = None

    @property
    def total_damage(self) -> int:
        return sum(hit[1] for hit in self.hits)

    @property
    def total_healing(self) -> int:
        return sum(hit[2] for hit in self.hits)


def resolve_action(
    world: World,
    actor: Entity,
    ability_id: int,
    target_point: WorldPoint,
    target_entity_id: EntityId,
    now: float,
    client_time_offset: float = 0.0,
) -> CombatOutcome:
    """Validate and apply one ability use."""
    ability = get_ability(ability_id)
    if ability is None:
        return CombatOutcome(ok=False, error=wire.ERROR_INVALID)

    if not actor.is_alive:
        return CombatOutcome(ok=False, error=wire.ERROR_DEAD)

    # Does the actor's class actually have this ability? Without this check a
    # client can cast anything in the catalogue regardless of what it rolled.
    if actor.is_player and ability not in actor.character_class.abilities:
        return CombatOutcome(ok=False, error=wire.ERROR_INVALID)

    if (now - actor.last_ability_at) * 1000.0 < ABILITY_MIN_INTERVAL_MS:
        return CombatOutcome(ok=False, error=wire.ERROR_RATE_LIMITED)

    if actor.cooldowns.get(ability.ability_id, 0.0) > now:
        return CombatOutcome(ok=False, error=wire.ERROR_ON_COOLDOWN)

    # Hub zones forbid anything that could harm another player (GDD 11.1). Healing
    # and mobility are explicitly exempt so a hub is still a place you can play in.
    harmful = ability.damage > 0
    if harmful and not (ability.flags & AbilityFlag.SAFE_IN_HUB):
        if world.is_in_hub(actor.position):
            return CombatOutcome(ok=False, error=wire.ERROR_SAFE_ZONE)

    impact = _clamp_to_range(actor.position, target_point, ability.range_tiles)

    # Soft aim: a ranged ability with no explicit target snaps to the nearest
    # valid one, which is the "auto-target for ranged" rule from GDD 7.2.
    resolved_target: Entity | None = world.entities.get(target_entity_id)
    if resolved_target is None and (ability.flags & AbilityFlag.SOFT_AIM):
        friendly = bool(ability.flags & AbilityFlag.FRIENDLY)
        resolved_target = world.nearest_enemy(
            actor, ability.range_tiles, hostile_to_players=not friendly
        )
        if resolved_target is not None:
            impact = resolved_target.position

    if ability.flags & AbilityFlag.REQUIRES_TARGET and resolved_target is None:
        return CombatOutcome(ok=False, error=wire.ERROR_INVALID)

    if not world.has_line_of_sight(actor.position, impact):
        return CombatOutcome(ok=False, error=wire.ERROR_OUT_OF_RANGE)

    if not actor.spend_resource(ability.resource_cost):
        return CombatOutcome(ok=False, error=wire.ERROR_NO_RESOURCE)

    actor.cooldowns[ability.ability_id] = now + ability.cooldown_ms / 1000.0
    actor.last_ability_at = now
    actor.facing = math.atan2(impact.y - actor.position.y, impact.x - actor.position.x)
    actor.mark(DirtyField.FACING)

    outcome = CombatOutcome(ok=True, ability=ability, impact=impact)

    if ability.kind is AbilityKind.DASH:
        outcome.dash_to = impact

    # Rewind to where things were when the player pressed the button, bounded by
    # the compensation window (TDD 10.2). Beyond the bound the request is simply
    # too late and resolves against the present, which is the honest answer.
    rewind = _clamp(client_time_offset, 0.0, LAG_COMPENSATION_WINDOW_MS / 1000.0)
    validation_time = now - rewind

    friendly_only = bool(ability.flags & AbilityFlag.FRIENDLY)
    radius = ability.radius_tiles if ability.radius_tiles > 0.0 else 0.6

    for candidate in world.entities_near(impact, radius + 1.5):
        if candidate.entity_id == actor.entity_id or not candidate.is_alive:
            continue
        if friendly_only and not candidate.is_player:
            continue
        if ability.damage > 0 and not _is_hostile(actor, candidate):
            continue
        if ability.healing > 0 and ability.damage == 0 and not _is_friendly(actor, candidate):
            continue

        historical = candidate.position_at(validation_time)
        if historical.distance_to(impact) > radius + candidate.radius:
            continue

        damage = candidate.apply_damage(ability.damage) if ability.damage else 0
        healing = candidate.apply_healing(ability.healing) if ability.healing else 0
        if damage or healing:
            outcome.hits.append(
                (candidate.entity_id, damage, healing, not candidate.is_alive)
            )
            if damage and candidate.is_npc and candidate.ai_target is None:
                # Being hit is enough to make an NPC care, even from out of its
                # detection radius. Otherwise archers are free kills.
                candidate.ai_target = actor.entity_id

    return outcome


def _is_hostile(actor: Entity, other: Entity) -> bool:
    """Allegiance check.

    PvE always; PvP only outside a hub, which the caller has already verified for
    the actor. Two NPCs never fight each other in this slice.
    """
    if actor.is_player:
        return other.is_npc or other.is_player
    return other.is_player


def _is_friendly(actor: Entity, other: Entity) -> bool:
    return actor.is_player == other.is_player


def _clamp_to_range(origin: WorldPoint, target: WorldPoint, max_range: float) -> WorldPoint:
    """Pull an out-of-range aim point back onto the range circle.

    Clamping rather than rejecting: a player aiming slightly too far should hit
    the edge of their reach, not have the input swallowed.
    """
    if max_range <= 0.0:
        return origin
    dx = target.x - origin.x
    dy = target.y - origin.y
    distance = math.hypot(dx, dy)
    if distance <= max_range or distance == 0.0:
        return target
    scale = max_range / distance
    return WorldPoint(origin.x + dx * scale, origin.y + dy * scale)


def _clamp(value: float, low: float, high: float) -> float:
    if value < low:
        return low
    if value > high:
        return high
    return value


def regenerate(entity: Entity, delta_time: float, health_rate: float, resource_rate: float) -> None:
    """Tick health and resource regeneration.

    Regeneration is fractions of a point per tick, so the remainder carries on the
    entity. Only whole points are committed, which means a regenerating entity
    appears in a snapshot a few times a second rather than in every one.
    """
    if not entity.is_alive:
        entity.health_carry = 0.0
        entity.resource_carry = 0.0
        return

    if entity.resource < entity.max_resource:
        entity.resource_carry += resource_rate * delta_time
        whole = int(entity.resource_carry)
        if whole > 0:
            entity.resource_carry -= whole
            entity.resource = min(entity.max_resource, entity.resource + whole)
            entity.mark(DirtyField.RESOURCE)
    else:
        entity.resource_carry = 0.0

    if entity.health < entity.max_health:
        entity.health_carry += health_rate * delta_time
        whole = int(entity.health_carry)
        if whole > 0:
            entity.health_carry -= whole
            entity.health = min(entity.max_health, entity.health + whole)
            entity.mark(DirtyField.HEALTH)
    else:
        entity.health_carry = 0.0
