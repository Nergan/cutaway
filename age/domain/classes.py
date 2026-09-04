"""The composite class system: 4 base classes combining into 14 total.

GDD 6.3 is specific about the shape of this, and the shape is the point: a
character does not pick one of fourteen classes. They start as one of **four**
base classes, and the hybrid is *earned* — at level-up the player chooses a
second half, and the pairing names what they became. Ten pairings exist (six
mixed plus four doubled), so four starting choices open into fourteen classes.

That ordering matters for the kit. The half chosen at creation is the character's
origin and contributes more than the half added later:

    one half only   basic attack + primary + secondary            = 3 abilities
    doubled half    the above + a pure signature                  = 4 abilities
    two halves      basic + origin's pair + the other's primary
                    + the pairing's signature                     = 5 abilities

All within the 3-5 GDD 7.2 budgets, growing rather than trading, and pures buy
depth (stronger numbers on fewer buttons) where hybrids buy breadth. Deriving the
kit from the halves rather than hand-writing fourteen of them means 22 ability
definitions cover all fourteen classes, and it is the shape the post-MVP
data-driven system wants anyway (abilities as modifiers, not hardcoded classes).

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

# Basic attacks. Free and always available: GDD 7.2 counts the basic attack among
# a class's 3-5 abilities, and a kit whose every button costs resource leaves a
# drained player with nothing to press.
STRIKE = _register(
    Ability(
        15, "strike", "Strike", AbilityKind.MELEE,
        range_tiles=1.5, radius_tiles=0.0, cooldown_ms=600, resource_cost=0,
        damage=9, flags=AbilityFlag.CAN_INTERRUPT,
    )
)
REBUKE = _register(
    Ability(
        16, "rebuke", "Rebuke", AbilityKind.RANGED,
        range_tiles=7.0, radius_tiles=0.0, cooldown_ms=750, resource_cost=0,
        damage=7, flags=AbilityFlag.SOFT_AIM, projectile_speed=15.0,
    )
)
ARCANE_DART = _register(
    Ability(
        17, "arcane_dart", "Arcane Dart", AbilityKind.RANGED,
        range_tiles=9.0, radius_tiles=0.0, cooldown_ms=650, resource_cost=0,
        damage=8, flags=AbilityFlag.SOFT_AIM, projectile_speed=19.0,
    )
)
SLASH = _register(
    Ability(
        18, "slash", "Slash", AbilityKind.MELEE,
        range_tiles=1.4, radius_tiles=0.0, cooldown_ms=480, resource_cost=0,
        damage=8, flags=AbilityFlag.CAN_INTERRUPT,
    )
)

# Second ability of each half. What a base class has beyond its opener, so playing
# one before the first level-up is a kit rather than a single button.
SHIELD_BASH = _register(
    Ability(
        19, "shield_bash", "Shield Bash", AbilityKind.MELEE,
        range_tiles=1.7, radius_tiles=0.0, cooldown_ms=5000, resource_cost=14,
        damage=14, flags=AbilityFlag.CAN_INTERRUPT, duration_ms=900,
    )
)
RADIANCE = _register(
    Ability(
        20, "radiance", "Radiance", AbilityKind.HEAL,
        range_tiles=0.0, radius_tiles=3.0, cooldown_ms=6500, resource_cost=26,
        healing=18, flags=AbilityFlag.FRIENDLY | AbilityFlag.SAFE_IN_HUB,
    )
)
FROST_SHARD = _register(
    Ability(
        21, "frost_shard", "Frost Shard", AbilityKind.RANGED,
        range_tiles=10.0, radius_tiles=1.4, cooldown_ms=4200, resource_cost=20,
        damage=22, flags=AbilityFlag.SOFT_AIM, projectile_speed=13.0,
    )
)
VITAL_STRIKE = _register(
    Ability(
        22, "vital_strike", "Vital Strike", AbilityKind.MELEE,
        range_tiles=1.6, radius_tiles=0.0, cooldown_ms=5500, resource_cost=18,
        damage=30, flags=AbilityFlag.CAN_INTERRUPT,
    )
)


BASIC_ATTACK: dict[BaseClass, Ability] = {
    BaseClass.WARRIOR: STRIKE,
    BaseClass.HEALER: REBUKE,
    BaseClass.MAGE: ARCANE_DART,
    BaseClass.ROGUE: SLASH,
}

BASE_ABILITY: dict[BaseClass, Ability] = {
    BaseClass.WARRIOR: CLEAVE,
    BaseClass.HEALER: MEND,
    BaseClass.MAGE: EMBER_BOLT,
    BaseClass.ROGUE: SHADOWSTEP,
}

SECOND_ABILITY: dict[BaseClass, Ability] = {
    BaseClass.WARRIOR: SHIELD_BASH,
    BaseClass.HEALER: RADIANCE,
    BaseClass.MAGE: FROST_SHARD,
    BaseClass.ROGUE: VITAL_STRIKE,
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
    """A playable class: an origin half, and the half added at level-up.

    ``chosen`` is ``None`` for the four base classes, which is what a character is
    before their first level-up. It is not a placeholder for "same as origin" —
    doubling a half is a deliberate choice that yields a different, stronger class.
    """

    class_id: int
    key: str
    name: str
    origin: BaseClass
    chosen: BaseClass | None
    role: Role
    fantasy: str
    health_multiplier: float
    resource_multiplier: float
    speed_multiplier: float

    @property
    def is_base(self) -> bool:
        """Still one half: eligible to compose at the next level-up."""
        return self.chosen is None

    @property
    def is_pure(self) -> bool:
        return self.chosen is not None and self.chosen is self.origin

    @property
    def halves(self) -> tuple[BaseClass, ...]:
        return (self.origin,) if self.chosen is None else (self.origin, self.chosen)

    @property
    def abilities(self) -> tuple[Ability, ...]:
        """The kit, derived from the halves. See the module docstring for the shape."""
        basic = BASIC_ATTACK[self.origin]
        opener = BASE_ABILITY[self.origin]
        follow = SECOND_ABILITY[self.origin]

        if self.chosen is None:
            return (basic, opener, follow)
        if self.chosen is self.origin:
            return (basic, opener, follow, PURE_ABILITY[self.origin])
        return (
            basic,
            opener,
            follow,
            BASE_ABILITY[self.chosen],
            HYBRID_ABILITY[_pair(self.origin, self.chosen)],
        )


def _pair(first: BaseClass, second: BaseClass) -> tuple[BaseClass, BaseClass]:
    """The order-independent key a pairing's signature is filed under."""
    return tuple(sorted((first, second)))  # type: ignore[return-value]


W, H, M, R = BaseClass.WARRIOR, BaseClass.HEALER, BaseClass.MAGE, BaseClass.ROGUE

CLASSES: tuple[CharacterClass, ...] = (
    # The four base classes. This is the whole of the character-creation menu: one
    # half, no second half yet, and the only classes a new character may be.
    CharacterClass(0, "warrior", "Warrior", W, None, Role.TANK,
                   "I stand watch over the hub; my sword is a shield for the weak.",
                   1.35, 0.85, 0.95),
    CharacterClass(1, "healer", "Healer", H, None, Role.HEALER,
                   "I hold the group together; my hands close wounds.",
                   0.90, 1.40, 1.00),
    CharacterClass(2, "mage", "Mage", M, None, Role.DPS,
                   "I command the elements, and reality obeys.",
                   0.80, 1.35, 0.95),
    CharacterClass(3, "rogue", "Rogue", R, None, Role.DPS,
                   "I move in shadow; my knife finds its mark before I am seen.",
                   0.90, 1.00, 1.15),
    # The six mixed hybrids. Reached by adding a different half at level-up.
    CharacterClass(4, "paladin", "Paladin", W, H, Role.TANK,
                   "I am light in the dark: a sword in one hand, healing in the other.",
                   1.30, 1.05, 0.95),
    CharacterClass(5, "spellblade", "Spellblade", W, M, Role.DPS,
                   "Steel is only the shape my magic takes.",
                   1.10, 1.15, 1.00),
    CharacterClass(6, "mercenary", "Mercenary", W, R, Role.DPS,
                   "I fight for coin, and I am worth every coin.",
                   1.15, 0.95, 1.10),
    CharacterClass(7, "shaman", "Shaman", H, M, Role.SUPPORT,
                   "I speak with the spirits of nature; they answer with storm and healing.",
                   0.95, 1.30, 1.00),
    CharacterClass(8, "pathfinder", "Pathfinder", H, R, Role.SUPPORT,
                   "I read the wilds, and the wilds keep my company alive.",
                   0.95, 1.10, 1.10),
    CharacterClass(9, "trickster", "Trickster", M, R, Role.DPS,
                   "Watch closely. You still will not see it coming.",
                   0.85, 1.20, 1.10),
    # The four pure specialisations, reached by doubling a half.
    CharacterClass(10, "warmaster", "Warmaster", W, W, Role.TANK,
                   "The line holds because I am the line.",
                   1.50, 0.85, 0.95),
    CharacterClass(11, "archcleric", "Archcleric", H, H, Role.HEALER,
                   "No one falls while I still stand.",
                   1.00, 1.55, 1.00),
    CharacterClass(12, "archmage", "Archmage", M, M, Role.DPS,
                   "I have read the world's grammar, and I write in it.",
                   0.80, 1.50, 0.95),
    CharacterClass(13, "shadowmaster", "Shadowmaster", R, R, Role.DPS,
                   "You have been dead for a moment already.",
                   0.90, 1.05, 1.25),
)

CLASSES_BY_ID: dict[int, CharacterClass] = {entry.class_id: entry for entry in CLASSES}
CLASSES_BY_KEY: dict[str, CharacterClass] = {entry.key: entry for entry in CLASSES}

#: The four a new character may choose between, in menu order.
BASE_CLASSES: tuple[CharacterClass, ...] = tuple(entry for entry in CLASSES if entry.is_base)

#: The base class each half starts life as.
BASE_BY_HALF: dict[BaseClass, int] = {entry.origin: entry.class_id for entry in BASE_CLASSES}

#: Which class an origin half becomes once a second half is chosen.
_COMPOSED: dict[tuple[BaseClass, BaseClass], CharacterClass] = {
    (entry.origin, entry.chosen): entry
    for entry in CLASSES
    if entry.chosen is not None
}
# A pairing of two different halves has one class, whichever order it was reached in:
# a Warrior who studies healing and a Healer who takes up the sword are both Paladins.
for _entry in CLASSES:
    if _entry.chosen is not None and _entry.chosen is not _entry.origin:
        _COMPOSED.setdefault((_entry.chosen, _entry.origin), _entry)


def base_class_of(class_id: int) -> CharacterClass:
    """The base class a character with this class id started as."""
    return CLASSES_BY_ID[BASE_BY_HALF[get_class(class_id).origin]]


def base_class_or_default(class_id: int) -> CharacterClass:
    """A base class from a client-supplied id, for character creation.

    An id naming a hybrid is not an error to refuse but a menu the client should not
    have shown; it collapses to the base class of that hybrid's origin half, which is
    the closest honest reading of the request.
    """
    requested = CLASSES_BY_ID.get(class_id)
    if requested is None:
        return BASE_CLASSES[0]
    return requested if requested.is_base else base_class_of(class_id)


def experience_for_level(level: int) -> int:
    """Experience needed to leave ``level`` for the next one."""
    return 40 + level * 60


def compose(class_id: int, chosen: BaseClass) -> CharacterClass | None:
    """The class a character becomes by adding ``chosen`` to their origin half.

    ``None`` when the character has already composed: the MVP has two halves and
    therefore exactly one composition, so a second attempt is a client error rather
    than a re-specialisation.
    """
    current = get_class(class_id)
    if not current.is_base:
        return None
    return _COMPOSED.get((current.origin, chosen))

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
