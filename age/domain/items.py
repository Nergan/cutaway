"""Items, the slots they go into, and what wearing one is worth.

GDD 6.1 declared the inventory infinite, and that was right while the only things in
it were building materials: nobody agonises over a stack of soil. Equipment breaks
that assumption, because a slot is only a decision if filling it costs something. So
the pack is bounded here, and bounded small enough to be felt rather than
theoretically.

The catalogue is hand-authored. Twenty-five entries is squarely the range where a
table a person can read beats a generator nobody can predict, and the numbers are
placeholders. What is not a placeholder is the *shape*: every stat an item moves is a
stat the simulation already reads every tick, so a bonus is never decorative. A helm
raises the pool the health bar is drawn from, a blade raises the number
:func:`~age.application.combat.resolve_action` hands to ``apply_damage``, and boots
raise the metres per second the movement integrator uses.

Items are addressed by *key* on the server and by *id* on the wire. The keys are the
ones terrain harvesting and the build recipes already spoke, so a plank stays a plank
and no migration is owed to anything already stored; the ids are two bytes and travel
in the inventory snapshot rather than a name per stack. Neither may ever be reused: a
key is a persistence key and an id is a protocol constant.

Drops live here rather than on the archetypes in :mod:`age.domain.npc` for one
reason. ``NpcArchetype.loot`` is a guarantee — a wolf always has a hide — and adding
probabilities to it would either make every wolf drop a dagger or force a second,
differently-shaped field onto a frozen record that is otherwise pure combat tuning.
A table keyed by archetype keeps the two kinds of reward apart, and it keeps the
question "what can this creature give me" answerable in one place.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import IntEnum

from . import hashing

#: How many stacks a character may carry. Six columns of four in the client's grid,
#: which is the largest bag that still reads as a bag at a glance rather than as a
#: spreadsheet.
INVENTORY_SLOTS = 24


class EquipmentSlot(IntEnum):
    """Where an item is worn.

    ``NONE`` is not a slot but the absence of one: it is what a material or a
    consumable declares, so "can this be equipped" is one comparison rather than a
    second boolean that could disagree with the slot.
    """

    NONE = 0
    HEAD = 1
    CHEST = 2
    HANDS = 3
    LEGS = 4
    FEET = 5
    WEAPON = 6
    TRINKET = 7


#: The wearable slots, in the order the character sheet lays them out.
EQUIPMENT_SLOTS: tuple[EquipmentSlot, ...] = (
    EquipmentSlot.HEAD,
    EquipmentSlot.CHEST,
    EquipmentSlot.HANDS,
    EquipmentSlot.LEGS,
    EquipmentSlot.FEET,
    EquipmentSlot.WEAPON,
    EquipmentSlot.TRINKET,
)

SLOT_NAMES: dict[EquipmentSlot, str] = {
    EquipmentSlot.HEAD: "Head",
    EquipmentSlot.CHEST: "Chest",
    EquipmentSlot.HANDS: "Hands",
    EquipmentSlot.LEGS: "Legs",
    EquipmentSlot.FEET: "Feet",
    EquipmentSlot.WEAPON: "Weapon",
    EquipmentSlot.TRINKET: "Trinket",
}


class ItemKind(IntEnum):
    MATERIAL = 0
    CONSUMABLE = 1
    EQUIPMENT = 2


class Rarity(IntEnum):
    """Only ever used for tinting.

    Rarity carries no mechanical weight — the stats do that — but a wall of
    identically coloured squares is unreadable, and a colour is the cheapest way to
    say "this one is worth looking at".
    """

    COMMON = 0
    UNCOMMON = 1
    RARE = 2
    EPIC = 3


@dataclass(frozen=True, slots=True)
class Item:
    """One entry in the catalogue.

    The bonus fields are absolute rather than multiplicative. Multipliers compose
    badly across seven slots — two 20% weapons are not 40% — and a flat number is
    something a player can read off the sheet and add up themselves.
    """

    item_id: int
    key: str
    name: str
    kind: ItemKind
    slot: EquipmentSlot
    rarity: Rarity
    stack_limit: int
    description: str
    bonus_health: int = 0
    bonus_resource: int = 0
    bonus_damage: int = 0
    bonus_speed: float = 0.0
    restores_health: int = 0
    restores_resource: int = 0

    @property
    def is_equippable(self) -> bool:
        return self.slot is not EquipmentSlot.NONE

    @property
    def is_consumable(self) -> bool:
        return self.kind is ItemKind.CONSUMABLE


ITEMS: dict[str, Item] = {}


def _register(item: Item) -> Item:
    if item.key in ITEMS:
        raise ValueError(f"duplicate item key {item.key}")
    if any(existing.item_id == item.item_id for existing in ITEMS.values()):
        raise ValueError(f"duplicate item id {item.item_id}")
    ITEMS[item.key] = item
    return item


# --- materials --------------------------------------------------------------
#
# These keys are load bearing: they are what `tiles.HARVEST_RESULTS` yields, what
# `tiles.BUILD_RECIPES` consumes, and what the archetypes already drop. Renaming one
# silently breaks a build recipe, which is why a test pins the two tables together.

_MATERIAL = (ItemKind.MATERIAL, EquipmentSlot.NONE)

WOOD = _register(Item(1, "wood", "Wood", *_MATERIAL, Rarity.COMMON, 99,
                      "Cut timber. Two of it makes a wall."))
STONE = _register(Item(2, "stone", "Stone", *_MATERIAL, Rarity.COMMON, 99,
                       "Broken from rock and cliff. Heavier walls."))
SOIL = _register(Item(3, "soil", "Soil", *_MATERIAL, Rarity.COMMON, 99,
                      "Turned earth. Levels a tile back to bare ground."))
FIBRE = _register(Item(4, "fibre", "Fibre", *_MATERIAL, Rarity.COMMON, 99,
                       "Stripped from bushes and long grass. Twists into fence."))
HIDE = _register(Item(5, "hide", "Hide", *_MATERIAL, Rarity.COMMON, 99,
                      "Taken off something that objected."))
COIN = _register(Item(6, "coin", "Coin", *_MATERIAL, Rarity.COMMON, 99,
                      "Nobody in the hub sells anything yet. They will."))
PLANK = _register(Item(7, "plank", "Plank", *_MATERIAL, Rarity.COMMON, 99,
                       "Milled wood. Lays a wooden floor."))
FLAGSTONE = _register(Item(8, "flagstone", "Flagstone", *_MATERIAL, Rarity.COMMON, 99,
                           "Dressed stone. Lays a hard floor."))

# --- consumables ------------------------------------------------------------

_CONSUMABLE = (ItemKind.CONSUMABLE, EquipmentSlot.NONE)

FIELD_RATION = _register(Item(
    9, "field_ration", "Field Ration", *_CONSUMABLE, Rarity.COMMON, 10,
    "Bread, salt and resignation.",
    restores_health=35,
))
SPRING_WATER = _register(Item(
    10, "spring_water", "Spring Water", *_CONSUMABLE, Rarity.COMMON, 10,
    "Cold enough to clear the head.",
    restores_resource=45,
))

# --- equipment --------------------------------------------------------------
#
# Every slot has at least a common entry, so a character who has killed anything at
# all can fill the sheet, and the better pieces trade one stat against another rather
# than being strictly larger. A vest that slows you and sandals that thin your health
# are the whole reason a slot is a decision.

_EQUIP = ItemKind.EQUIPMENT

RUSTED_BLADE = _register(Item(
    11, "rusted_blade", "Rusted Blade", _EQUIP, EquipmentSlot.WEAPON, Rarity.COMMON, 1,
    "It was somebody's pride once.",
    bonus_damage=3,
))
WOLFSBANE_DAGGER = _register(Item(
    12, "wolfsbane_dagger", "Wolfsbane Dagger", _EQUIP, EquipmentSlot.WEAPON, Rarity.UNCOMMON, 1,
    "Thin, quick, and bitter along the edge.",
    bonus_damage=6, bonus_speed=0.2,
))
GOLEM_MAUL = _register(Item(
    13, "golem_maul", "Golem Maul", _EQUIP, EquipmentSlot.WEAPON, Rarity.RARE, 1,
    "A slab of the thing that carried it.",
    bonus_damage=13, bonus_speed=-0.25,
))
LEATHER_HOOD = _register(Item(
    14, "leather_hood", "Leather Hood", _EQUIP, EquipmentSlot.HEAD, Rarity.COMMON, 1,
    "Keeps the rain off, mostly.",
    bonus_health=6,
))
BANDIT_HELM = _register(Item(
    15, "bandit_helm", "Bandit Helm", _EQUIP, EquipmentSlot.HEAD, Rarity.UNCOMMON, 1,
    "Dented from the inside, which is not reassuring.",
    bonus_health=12, bonus_damage=1,
))
PADDED_JERKIN = _register(Item(
    16, "padded_jerkin", "Padded Jerkin", _EQUIP, EquipmentSlot.CHEST, Rarity.COMMON, 1,
    "Wool and patience.",
    bonus_health=14,
))
STONE_PLATED_VEST = _register(Item(
    17, "stone_plated_vest", "Stone-Plated Vest", _EQUIP, EquipmentSlot.CHEST, Rarity.RARE, 1,
    "You will survive a great deal. You will not outrun any of it.",
    bonus_health=32, bonus_speed=-0.35,
))
WORN_GLOVES = _register(Item(
    18, "worn_gloves", "Worn Gloves", _EQUIP, EquipmentSlot.HANDS, Rarity.COMMON, 1,
    "The grip is better than the leather.",
    bonus_damage=2,
))
ARCHERS_BRACERS = _register(Item(
    19, "archers_bracers", "Archer's Bracers", _EQUIP, EquipmentSlot.HANDS, Rarity.UNCOMMON, 1,
    "Cut for a draw you have not learned yet.",
    bonus_damage=4, bonus_resource=8,
))
HIDE_LEGGINGS = _register(Item(
    20, "hide_leggings", "Hide Leggings", _EQUIP, EquipmentSlot.LEGS, Rarity.COMMON, 1,
    "Still faintly of wolf.",
    bonus_health=10,
))
WARDED_GREAVES = _register(Item(
    21, "warded_greaves", "Warded Greaves", _EQUIP, EquipmentSlot.LEGS, Rarity.UNCOMMON, 1,
    "Someone chalked a ward inside each one.",
    bonus_health=16, bonus_resource=6,
))
TRAVELLERS_BOOTS = _register(Item(
    22, "travellers_boots", "Traveller's Boots", _EQUIP, EquipmentSlot.FEET, Rarity.COMMON, 1,
    "Walked the corridor both ways more than once.",
    bonus_speed=0.4,
))
SWIFT_SANDALS = _register(Item(
    23, "swift_sandals", "Swift Sandals", _EQUIP, EquipmentSlot.FEET, Rarity.UNCOMMON, 1,
    "Nothing between you and the road.",
    bonus_speed=0.9, bonus_health=-4,
))
EMBER_CHARM = _register(Item(
    24, "ember_charm", "Ember Charm", _EQUIP, EquipmentSlot.TRINKET, Rarity.UNCOMMON, 1,
    "Warm in the palm even at night.",
    bonus_resource=18,
))
WOLF_TOTEM = _register(Item(
    25, "wolf_totem", "Wolf Totem", _EQUIP, EquipmentSlot.TRINKET, Rarity.EPIC, 1,
    "The pack runs where you run.",
    bonus_health=10, bonus_damage=4, bonus_speed=0.35,
))


ITEMS_BY_ID: dict[int, Item] = {item.item_id: item for item in ITEMS.values()}


def get_item(key: str) -> Item | None:
    return ITEMS.get(key)


def item_by_id(item_id: int) -> Item | None:
    return ITEMS_BY_ID.get(item_id)


# --- what a loadout is worth ------------------------------------------------


@dataclass(frozen=True, slots=True)
class StatBonus:
    """The sum of everything worn. Zero when nothing is."""

    health: int = 0
    resource: int = 0
    damage: int = 0
    speed: float = 0.0


def total_bonus(item_keys: Iterable[str]) -> StatBonus:
    """Add up a loadout, skipping keys the catalogue no longer knows.

    Unknown keys are skipped rather than refused because they arrive from storage:
    an item retired between releases must not make its owner unable to log in.
    """
    health = resource = damage = 0
    speed = 0.0
    for key in item_keys:
        item = ITEMS.get(key)
        if item is None:
            continue
        health += item.bonus_health
        resource += item.bonus_resource
        damage += item.bonus_damage
        speed += item.bonus_speed
    return StatBonus(health=health, resource=resource, damage=damage, speed=speed)


# --- drops ------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Drop:
    """One line of a creature's drop table: what, how likely, how many."""

    item_key: str
    chance: float
    count: int = 1


#: Keyed by ``NpcArchetype.key``. Anything absent — townsfolk, guards — drops only
#: the guaranteed loot on the archetype itself, which for them is nothing.
DROP_TABLES: dict[str, tuple[Drop, ...]] = {
    "bandit": (
        Drop("rusted_blade", 0.18),
        Drop("bandit_helm", 0.10),
        Drop("worn_gloves", 0.14),
        Drop("field_ration", 0.25, 2),
    ),
    "wolf": (
        Drop("wolfsbane_dagger", 0.07),
        Drop("hide_leggings", 0.12),
        Drop("wolf_totem", 0.02),
    ),
    "golem": (
        Drop("golem_maul", 0.16),
        Drop("stone_plated_vest", 0.13),
        Drop("flagstone", 0.40, 3),
    ),
    "archer": (
        Drop("archers_bracers", 0.14),
        Drop("travellers_boots", 0.12),
        Drop("warded_greaves", 0.08),
    ),
    "slime": (
        Drop("spring_water", 0.22),
        Drop("padded_jerkin", 0.05),
    ),
}

#: Keeps one creature's rolls from correlating with another table's at the same seed.
_DROP_SALT = 0x10E7


def roll_drops(archetype_key: str, roll_seed: int) -> tuple[tuple[str, int], ...]:
    """The optional half of a kill's reward, as ``(item key, count)`` pairs.

    Deterministic in ``roll_seed`` rather than drawn from a random module. The
    simulation has no RNG port and does not want one: seeding from the victim's
    entity id gives every corpse its own independent roll, makes a replay of the
    same tick produce the same loot, and lets a test walk the seed space instead of
    reaching for a monkeypatch.
    """
    table = DROP_TABLES.get(archetype_key)
    if not table:
        return ()

    rolled: list[tuple[str, int]] = []
    for index, drop in enumerate(table):
        value = hashing.unit_float(hashing.combine(roll_seed, index, _DROP_SALT))
        if value < drop.chance:
            rolled.append((drop.item_key, drop.count))
    return tuple(rolled)
