const assert = require("assert");
const query = require("../dnd/scripts/druid_query.js");
const foundry = require("../dnd/scripts/foundry_actor.js");
const db = require("../dnd/static/db.json");

function sorts(text, key) {
  const result = query.classifyQuery(text);
  assert.ok(result.sort.includes(key), text + " -> " + JSON.stringify(result));
  return result;
}

const speed = sorts("скорос", "speed");
assert.deepStrictEqual(speed.filters, []);
assert.deepStrictEqual(sorts("скорость", "speed").filters, []);
assert.ok(sorts("скрыт", "st").sort.includes("st"));
const construct = query.classifyQuery("construct");
assert.deepStrictEqual(construct.sort, []);
assert.deepStrictEqual(construct.filters, ["construct"]);
assert.ok(query.classifyQuery("плавание").sort.includes("sp_s"));
const field = query.classifyQuery("поле");
assert.ok(!field.sort.includes("sp_f"), JSON.stringify(field));
assert.deepStrictEqual(query.classifyQuery("паук").sort, []);
assert.deepStrictEqual(query.classifyQuery("паук").filters, ["паук"]);
assert.ok(query.classifyQuery("con").sort.includes("con"));
assert.deepStrictEqual(query.classifyQuery("con").filters, []);

const eel = db.find(creature => creature.n_en === "Space Eel");
assert.ok(!query.categoriesFor(eel).includes("lvl4"));
assert.ok(query.categoriesFor(eel).includes("lvl8"));
const fish = db.find(creature => creature.n_en === "Fish");
assert.ok(query.categoriesFor(fish).includes("fam"));
const wolf = db.find(creature => creature.n_en === "Wolf");
assert.deepStrictEqual(query.categoriesFor(wolf), ["lvl2", "lvl4", "lvl8"]);
const owl = db.find(creature => creature.n_en === "Owl");
assert.deepStrictEqual(query.categoriesFor(owl).filter(cat => cat !== "fam"), ["lvl8"]);

for (const creature of db) {
  assert.equal(typeof creature.fam, "boolean");
  assert.ok(creature.src && creature.src_ru);
  assert.equal(creature.cat, undefined);
  const tiers = query.categoriesFor(creature);
  if ((creature.sp.f || 0) > 0) {
    assert.ok(!tiers.includes("lvl2") && !tiers.includes("lvl4"), creature.n_en);
  }
  if ((creature.sp.s || 0) > 0) assert.ok(!tiers.includes("lvl2"), creature.n_en);
}
const crocodile = db.find(creature => creature.n_en === "Crocodile");
assert.equal(crocodile.sp.s, 30);
const rat = db.find(creature => creature.n_en === "Giant rat");
assert.ok(!rat.tg_en.some(tag => /disease/i.test(tag)));
assert.ok(!rat.tg_ru.some(tag => tag.toLowerCase().includes("\u0437\u0430\u0440\u0430\u0436\u0435\u043d")));
const bats = db.find(creature => creature.n_en === "Swarm of bats");
assert.ok(bats.sn_en.some(sense => sense.includes("60")));
const octopus = db.find(creature => creature.n_en === "Giant octopus");
assert.equal(octopus.pr, 4);
const frog = db.find(creature => creature.n_en === "Frog");
assert.deepStrictEqual(frog.sn_en, []);

const legacy = foundry.normalizeDocument({
  name: "Old Wren",
  type: "character",
  img: "worlds/lost/portrait.webp",
  data: {
    abilities: {
      str: { value: 8, mod: -1, proficient: 0, save: -1 },
      dex: { value: 16, mod: 3, proficient: 1, save: 5 },
      con: { value: 14, mod: 2, proficient: 0, save: 2 },
      int: { value: 12, mod: 1, proficient: 0, save: 1 },
      wis: { value: 10, mod: 0, proficient: 1, save: 2 },
      cha: { value: 10, mod: 0, proficient: 0, save: 0 }
    },
    attributes: {
      ac: { value: 14 },
      hp: { value: 18, max: 22, temp: 3 },
      speed: { value: "30 ft" },
      init: { value: 3, bonus: 0, mod: 3 },
      prof: 2,
      death: { success: 1, failure: 2 },
      inspiration: true
    },
    skills: {
      ste: { value: 5, ability: "dex", mod: 3, prof: 1 },
      prc: { value: 2, ability: "wis", mod: 0, prof: 1 }
    },
    spells: { spell1: { value: 2, max: 3 }, pact: { value: 1, max: 1, level: 1 } },
    details: { biography: { value: "<p>Hello</p><img src=x onerror=alert(1)>" } },
    currency: { gp: 12 }
  },
  items: [
    { name: "Rogue", type: "class", data: { levels: 3, description: { value: "Sneak [[/r 1d20+5]]" } } },
    { name: "Elf", type: "race", data: { description: { value: "@race[elf]{Elf}" } } },
    { name: "Dagger", type: "weapon", data: { quantity: 2, equipped: true, damage: { parts: [["1d4+3", "piercing"]] } } },
    { name: "Mage Hand", type: "spell", data: { level: 0, description: { value: "A hand." } } },
    { name: "Healing Word", type: "spell", data: { level: 1, preparation: { prepared: true }, description: { value: "Heal." } } }
  ],
  effects: [{ name: "Concentrating", disabled: false, flags: { core: { statusId: "concentrating" } } }]
});
assert.equal(legacy.error, "");
const oldSheet = legacy.actors[0];
assert.equal(oldSheet.edition, "Foundry 0.8–9 · dnd5e 1.x");
assert.equal(oldSheet.img, "");
assert.equal(oldSheet.ac.value, 14);
assert.equal(oldSheet.hp.temp, 3);
assert.equal(oldSheet.speeds[0].value, 30);
assert.equal(oldSheet.initiative.total, 3);
assert.equal(oldSheet.death.failure, 2);
assert.equal(oldSheet.abilities[1].save, 5);
assert.ok(oldSheet.abilities[1].proficient);
assert.equal(oldSheet.skills.find(skill => skill.key === "ste").total, 5);
assert.equal(oldSheet.slots[0].remaining, 2);
assert.equal(oldSheet.slots[0].max, 3);
assert.equal(oldSheet.slots[1].pact, true);
assert.ok(oldSheet.conditions.includes("Concentrating"));
assert.ok(oldSheet.concentration.active);
assert.ok(!oldSheet.biography[0].text.includes("<"));
assert.ok(oldSheet.biography[0].text.includes("Hello"));
assert.ok(oldSheet.features.some(item => item.text.includes("[[/r 1d20+5]]")));
assert.ok(oldSheet.inventory[0].damage.includes("1d4+3"));
assert.equal(oldSheet.spells[0].level, 0);
assert.equal(oldSheet.spells[1].items[0].preparation, "prepared");

const modern = foundry.normalizeDocument({
  name: "New Wren",
  type: "character",
  _stats: { coreVersion: "13.351", systemVersion: "5.1.2", systemId: "dnd5e" },
  system: {
    abilities: {
      str: { value: 10 }, dex: { value: 14 }, con: { value: 12 },
      int: { value: 16, proficient: 1 }, wis: { value: 10 }, cha: { value: 8 }
    },
    attributes: {
      ac: { calc: "default" },
      hp: { value: 20, max: 20 },
      movement: { walk: 30, fly: 40, hover: true, units: "ft" },
      init: { bonus: 1 },
      prof: 3,
      death: { success: 0, failure: 0 },
      senses: { darkvision: 60, units: "ft" },
      concentration: { ability: "con", bonuses: { save: "1d4" } },
      spell: { dc: 14, attack: 6 }
    },
    skills: { arc: { proficient: 1, passive: 16 } },
    spells: { spell1: { value: 1, override: 4 }, spell3: { value: 0, max: 2 } }
  },
  items: [
    { name: "Wizard", type: "class", system: { levels: 5, spellcasting: { progression: "full" } } },
    { name: "Leather", type: "equipment", system: { equipped: true, armor: { value: 11, type: "light" } } },
    { name: "Shield", type: "equipment", system: { equipped: true, armor: { value: 2, type: "shield" } } },
    {
      name: "Fire Bolt",
      type: "spell",
      system: { level: 0, activities: { cast: { damage: { parts: [["1d10", "fire"]] } } }, description: { value: "Bolt." } }
    }
  ],
  effects: [{ disabled: false, statuses: ["prone", "concentrating"] }]
});
const sheet = modern.actors[0];
assert.equal(sheet.edition, "Foundry 13.351 · dnd5e 5.1.2");
assert.equal(sheet.ac.value, 15);
assert.equal(sheet.ac.formula, "light 11 + Dex 2 + shield 2");
assert.equal(sheet.speeds.find(speed => speed.key === "fly").hover, true);
assert.equal(sheet.initiative.total, 3);
assert.equal(sheet.senses[0], "Darkvision 60 ft");
assert.equal(sheet.skills.find(skill => skill.key === "arc").total, 6);
assert.equal(sheet.slots.find(slot => slot.level === 1).max, 4);
assert.equal(sheet.slots.find(slot => slot.level === 3).max, 2);
assert.deepStrictEqual(sheet.conditions, ["Prone", "Concentrating"]);
assert.equal(sheet.spell.dc, 14);
assert.equal(sheet.inventory.find(item => item.name === "Fire Bolt"), undefined);
assert.equal(sheet.spells[0].items[0].damage[0], "1d10");

const computed = foundry.normalizeDocument({
  name: "Slotless",
  type: "character",
  system: {
    abilities: { str: { value: 10 }, dex: { value: 10 }, con: { value: 10 }, int: { value: 10 }, wis: { value: 10 }, cha: { value: 10 } },
    attributes: { ac: { calc: "flat", flat: 18 } }
  },
  items: [
    { name: "Wizard", type: "class", system: { levels: 1, spellcasting: { progression: "full" } } },
    { name: "Fighter", type: "class", system: { levels: 3 } },
    { name: "Eldritch Knight", type: "subclass" }
  ]
});
assert.equal(computed.actors[0].ac.value, 18);
const levels = computed.actors[0].slots.map(slot => slot.level + ":" + slot.max).join(",");
assert.ok(levels.includes("1:4") || levels.includes("1:3") || levels.includes("1:2"), levels);

const many = foundry.normalizeDocument([
  { name: "One", type: "npc", system: { abilities: { str: { value: 10 } }, attributes: { hp: { value: 4, max: 4 } }, details: { cr: 0.25, type: "beast" } } },
  { name: "Two", type: "npc", data: { abilities: { str: { value: 12 } }, attributes: {} } }
]);
assert.equal(many.actors.length, 2);
assert.equal(many.actors[1].abilities[0].score, 12);

const refused = foundry.normalizeDocument({ name: "Not an actor", items: [] });
assert.equal(refused.actors.length, 0);

const rolled = foundry.rollFormula("2d6+1", () => 0);
assert.equal(rolled.total, 3);
const kept = foundry.rollFormula("4d6kh3", () => 0.99);
assert.equal(kept.total, 18);
assert.equal(foundry.rollFormula("alert(1)"), null);
const resolved = foundry.resolveFormula("1d20 + @abilities.str.mod + @prof", sheet.context);
assert.equal(resolved.includes("@"), false);

const plain = foundry.readable("<script>alert(1)</script>[[/r 1d8]]");
assert.ok(!plain.includes("<script>"));
assert.ok(!plain.includes("alert"));
assert.ok(plain.includes("[[/r 1d8]]"));
assert.equal(foundry.safeImg("javascript:alert(1)"), "");

console.log("dnd logic ok");
