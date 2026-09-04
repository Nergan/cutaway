"""The composite class system: 4 base classes combining into 14 total.

GDD 6.3 defines four base classes that pair into ten hybrids, including the four
doubled pures. Rather than writing 14 independent kits, a class is derived from
its two halves: each base contributes an ability, and the pair contributes one
signature ability. That is 4 + 4 + 6 = 14 kits from 4 + 4 + 6 = 14 ability
definitions instead of the 42-70 the TDD budgets for hand-writing, and it is the
shape the post-MVP data-driven system wants anyway (abilities as modifiers rather
than hardcoded classes).

Balance numbers here are placeholders. The point of this module is the structure.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum, IntFlag


class BaseClass(IntEnum):
    """The four halves every class is built from."""

    WARRIOR = 0
    HEALER = 1
    MAGE = 2
    ROGUE = 3


class Role(IntEnum):
    TANK = 0
    HEALER = 1
    DPS = 2
    SUPPORT = 3


class AbilityKind(IntEnum):
    MELEE = 0
    RANGED = 1
    AREA = 2
    HEAL = 3
    BUFF = 4
    DASH = 5


class AbilityFlag(IntFlag):
    NONE = 0
    REQUIRES_TARGET = 1 << 0
    CAN_INTERRUPT = 1 << 1
    # Auto-target picks the nearest valid enemy when the client does not aim.
    SOFT_AIM = 1 << 2
    # Friendly-only; refuses to resolve against an enemy.
    FRIENDLY = 1 << 3
    # Ignores the hub-zone PvP ban because it cannot harm anyone.
    SAFE_IN_HUB = 1 << 4


@dataclass(frozen=True, slots=True)
class Ability:
    """One activatable ability.

    ``radius_tiles`` is the effect footprint at the impact point: zero for a
    single-target hit, positive for a cone or blast. ``range_tiles`` is how far
    the impact point may be from the caster.
    """

    ability_id: int
    key: str
    name: str
    kind: AbilityKind
    range_tiles: float
    radius_tiles: float
    cooldown_ms: int
    resource_cost: int
    damage: int = 0
    healing: int = 0
    flags: AbilityFlag = AbilityFlag.NONE
    projectile_speed: float = 0.0
    duration_ms: int = 0

    @property
    def is_projectile(self) -> bool:
        return self.projectile_speed > 0.0


# --- ability catalogue ------------------------------------------------------
#
# Ids are stable and must never be reused: they travel on the wire and are
# recorded in cooldown maps. Grouped by which half of a class contributes them.

ABILITIES: dict[str, Ability] = {}


def _register(ability: Ability) -> Ability:
    if ability.key in ABILITIES:
        raise ValueError(f"duplicate ability key {ability.key}")
    if any(existing.ability_id == ability.ability_id for existing in ABILITIES.values()):
        raise ValueError(f"duplicate ability id {ability.ability_id}")
    ABILITIES[ability.key] = ability
    return ability


# Base-class abilities. Every class holds the ones from both of its halves, so a
# Paladin swings and mends without either being written twice.
CLEAVE = _register(
    Ability(
        1, "cleave", "Cleave", AbilityKind.MELEE,
        range_tiles=1.6, radius_tiles=1.1, cooldown_ms=900, resource_cost=8,
        damage=18, flags=AbilityFlag.CAN_INTERRUPT,
    )
)
MEND = _register(
    Ability(
        2, "mend", "Mend", AbilityKind.HEAL,
        range_tiles=8.0, radius_tiles=0.0, cooldown_ms=1400, resource_cost=18,
        healing=26, flags=AbilityFlag.FRIENDLY | AbilityFlag.SOFT_AIM | AbilityFlag.SAFE_IN_HUB,
    )
)
EMBER_BOLT = _register(
    Ability(
        3, "ember_bolt", "Ember Bolt", AbilityKind.RANGED,
        range_tiles=11.0, radius_tiles=0.6, cooldown_ms=800, resource_cost=12,
        damage=16, flags=AbilityFlag.SOFT_AIM, projectile_speed=17.0,
    )
)
SHADOWSTEP = _register(
    Ability(
        4, "shadowstep", "Shadowstep", AbilityKind.DASH,
        range_tiles=6.0, radius_tiles=0.0, cooldown_ms=4000, resource_cost=16,
        flags=AbilityFlag.SAFE_IN_HUB, duration_ms=180,
    )
)

# Pure abilities: the reward for doubling down on one half.
BULWARK = _register(
    Ability(
        5, "bulwark", "Bulwark", AbilityKind.BUFF,
        range_tiles=0.0, radius_tiles=3.0, cooldown_ms=12000, resource_cost=30,
        flags=AbilityFlag.FRIENDLY | AbilityFlag.SAFE_IN_HUB, duration_ms=6000,
    )
)
BENEDICTION = _register(
    Ability(
        6, "benediction", "Benediction", AbilityKind.HEAL,
        range_tiles=7.0, radius_tiles=4.0, cooldown_ms=9000, resource_cost=42,
        healing=34, flags=AbilityFlag.FRIENDLY | AbilityFlag.SAFE_IN_HUB,
    )
)
CATACLYSM = _register(
    Ability(
        7, "cataclysm", "Cataclysm", AbilityKind.AREA,
        range_tiles=9.0, radius_tiles=3.4, cooldown_ms=10000, resource_cost=46,
        damage=44,
    )
)
THOUSAND_CUTS = _register(
    Ability(
        8, "thousand_cuts", "Thousand Cuts", AbilityKind.MELEE,
        range_tiles=1.8, radius_tiles=0.9, cooldown_ms=6000, resource_cost=34,
        damage=52, flags=AbilityFlag.CAN_INTERRUPT,
    )
)

# Hybrid signatures: one per unordered pair of distinct halves.
CONSECRATE = _register(
    Ability(
        9, "consecrate", "Consecrate", AbilityKind.AREA,
        range_tiles=0.0, radius_tiles=3.2, cooldown_ms=8000, resource_cost=34,
        damage=20, healing=18, flags=AbilityFlag.SAFE_IN_HUB, duration_ms=4000,
    )
)
RUNEBLADE = _register(
    Ability(
        10, "runeblade", "Runeblade", AbilityKind.MELEE,
        range_tiles=2.4, radius_tiles=1.6, cooldown_ms=5000, resource_cost=28,
        damage=38, flags=AbilityFlag.CAN_INTERRUPT,
    )
)
GRAPPLE = _register(
    Ability(
        11, "grapple", "Grapple", AbilityKind.DASH,
        range_tiles=7.5, radius_tiles=1.0, cooldown_ms=7000, resource_cost=24,
        damage=22, flags=AbilityFlag.CAN_INTERRUPT, duration_ms=220,
    )
)
SPIRIT_SURGE = _register(
    Ability(
        12, "spirit_surge", "Spirit Surge", AbilityKind.AREA,
        range_tiles=8.0, radius_tiles=2.6, cooldown_ms=7000, resource_cost=32,
        damage=18, healing=22, flags=AbilityFlag.SAFE_IN_HUB,
    )
)
HUNTERS_MARK = _register(
    Ability(
        13, "hunters_mark", "Hunter's Mark", AbilityKind.RANGED,
        range_tiles=12.0, radius_tiles=0.7, cooldown_ms=3200, resource_cost=20,
        damage=28, flags=AbilityFlag.SOFT_AIM, projectile_speed=22.0, duration_ms=5000,
    )
)
MIRROR_TRICK = _register(
    Ability(
        14, "mirror_trick", "Mirror Trick", AbilityKind.BUFF,
        range_tiles=0.0, radius_tiles=2.0, cooldown_ms=9000, resource_cost=30,
        damage=14, flags=AbilityFlag.SAFE_IN_HUB, duration_ms=5000,
    )
)


BASE_ABILITY: dict[BaseClass, Ability] = {
    BaseClass.WARRIOR: CLEAVE,
    BaseClass.HEALER: MEND,
    BaseClass.MAGE: EMBER_BOLT,
    BaseClass.ROGUE: SHADOWSTEP,
}

PURE_ABILITY: dict[BaseClass, Ability] = {
    BaseClass.WARRIOR: BULWARK,
    BaseClass.HEALER: BENEDICTION,
    BaseClass.MAGE: CATACLYSM,
    BaseClass.ROGUE: THOUSAND_CUTS,
}

# Keyed by the sorted pair so lookup is order-independent.
HYBRID_ABILITY: dict[tuple[BaseClass, BaseClass], Ability] = {
    (BaseClass.WARRIOR, BaseClass.HEALER): CONSECRATE,
    (BaseClass.WARRIOR, BaseClass.MAGE): RUNEBLADE,
    (BaseClass.WARRIOR, BaseClass.ROGUE): GRAPPLE,
    (BaseClass.HEALER, BaseClass.MAGE): SPIRIT_SURGE,
    (BaseClass.HEALER, BaseClass.ROGUE): HUNTERS_MARK,
    (BaseClass.MAGE, BaseClass.ROGUE): MIRROR_TRICK,
}


@dataclass(frozen=True, slots=True)
class CharacterClass:
    """A playable class, derived from its two halves."""

    class_id: int
    key: str
    name: str
    halves: tuple[BaseClass, BaseClass]
    role: Role
    fantasy: str
    health_multiplier: float
    resource_multiplier: float
    speed_multiplier: float

    @property
    def is_pure(self) -> bool:
        return self.halves[0] is self.halves[1]

    @property
    def abilities(self) -> tuple[Ability, ...]:
        """The kit: one ability per half, plus the signature for the pairing.

        A pure class holds its base ability once rather than twice, and takes the
        pure signature instead of a hybrid one.
        """
        first, second = self.halves
        if self.is_pure:
            return (BASE_ABILITY[first], PURE_ABILITY[first])
        return (
            BASE_ABILITY[first],
            BASE_ABILITY[second],
            HYBRID_ABILITY[tuple(sorted(self.halves))],  # type: ignore[index]
        )


def _pair(first: BaseClass, second: BaseClass) -> tuple[BaseClass, BaseClass]:
    return tuple(sorted((first, second)))  # type: ignore[return-value]


W, H, M, R = BaseClass.WARRIOR, BaseClass.HEALER, BaseClass.MAGE, BaseClass.ROGUE

CLASSES: tuple[CharacterClass, ...] = (
    # The four base classes, played single-half until the first level-up.
    CharacterClass(0, "warrior", "Warrior", _pair(W, W), Role.TANK,
                   "I stand watch over the hub; my sword is a shield for the weak.",
                   1.35, 0.85, 0.95),
    CharacterClass(1, "healer", "Healer", _pair(H, H), Role.HEALER,
                   "I hold the group together; my hands close wounds.",
                   0.90, 1.40, 1.00),
    CharacterClass(2, "mage", "Mage", _pair(M, M), Role.DPS,
                   "I command the elements, and reality obeys.",
                   0.80, 1.35, 0.95),
    CharacterClass(3, "rogue", "Rogue", _pair(R, R), Role.DPS,
                   "I move in shadow; my knife finds its mark before I am seen.",
                   0.90, 1.00, 1.15),
    # The six mixed hybrids.
    CharacterClass(4, "paladin", "Paladin", _pair(W, H), Role.TANK,
                   "I am light in the dark: a sword in one hand, healing in the other.",
                   1.30, 1.05, 0.95),
    CharacterClass(5, "spellblade", "Spellblade", _pair(W, M), Role.DPS,
                   "Steel is only the shape my magic takes.",
                   1.10, 1.15, 1.00),
    CharacterClass(6, "mercenary", "Mercenary", _pair(W, R), Role.DPS,
                   "I fight for coin, and I am worth every coin.",
                   1.15, 0.95, 1.10),
    CharacterClass(7, "shaman", "Shaman", _pair(H, M), Role.SUPPORT,
                   "I speak with the spirits of nature; they answer with storm and healing.",
                   0.95, 1.30, 1.00),
    CharacterClass(8, "pathfinder", "Pathfinder", _pair(H, R), Role.SUPPORT,
                   "I read the wilds, and the wilds keep my company alive.",
                   0.95, 1.10, 1.10),
    CharacterClass(9, "trickster", "Trickster", _pair(M, R), Role.DPS,
                   "Watch closely. You still will not see it coming.",
                   0.85, 1.20, 1.10),
    # The four pure specialisations, reached by doubling a half.
    CharacterClass(10, "warmaster", "Warmaster", _pair(W, W), Role.TANK,
                   "The line holds because I am the line.",
                   1.50, 0.85, 0.95),
    CharacterClass(11, "archcleric", "Archcleric", _pair(H, H), Role.HEALER,
                   "No one falls while I still stand.",
                   1.00, 1.55, 1.00),
    CharacterClass(12, "archmage", "Archmage", _pair(M, M), Role.DPS,
                   "I have read the world's grammar, and I write in it.",
                   0.80, 1.50, 0.95),
    CharacterClass(13, "shadowmaster", "Shadowmaster", _pair(R, R), Role.DPS,
                   "You have been dead for a moment already.",
                   0.90, 1.05, 1.25),
)

CLASSES_BY_ID: dict[int, CharacterClass] = {entry.class_id: entry for entry in CLASSES}
CLASSES_BY_KEY: dict[str, CharacterClass] = {entry.key: entry for entry in CLASSES}

ABILITIES_BY_ID: dict[int, Ability] = {
    ability.ability_id: ability for ability in ABILITIES.values()
}


def get_class(class_id: int) -> CharacterClass:
    """Look up a class, falling back to Warrior for an unknown id.

    A bad class id arrives from an untrusted client or a stale database row, and
    neither is worth dropping a session over.
    """
    return CLASSES_BY_ID.get(class_id, CLASSES_BY_ID[0])


def get_ability(ability_id: int) -> Ability | None:
    return ABILITIES_BY_ID.get(ability_id)
