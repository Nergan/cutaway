// Read a Foundry VTT actor export from any dnd5e generation.
// Foundry 0.8–9 keep the system payload on `data`. Foundry 10 and later
// (including 13 and 14) keep it on `system`. dnd5e 4 and 5 add activities
// and a few renamed fields; the reader accepts both shapes.
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.FoundryActor = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  const ABILITIES = [
    ["str", "STR"], ["dex", "DEX"], ["con", "CON"],
    ["int", "INT"], ["wis", "WIS"], ["cha", "CHA"]
  ];
  const SKILLS = [
    ["acr", "Acrobatics", "dex"], ["ani", "Animal Handling", "wis"], ["arc", "Arcana", "int"],
    ["ath", "Athletics", "str"], ["dec", "Deception", "cha"], ["his", "History", "int"],
    ["ins", "Insight", "wis"], ["itm", "Intimidation", "cha"], ["inv", "Investigation", "int"],
    ["med", "Medicine", "wis"], ["nat", "Nature", "int"], ["prc", "Perception", "wis"],
    ["prf", "Performance", "cha"], ["per", "Persuasion", "cha"], ["rel", "Religion", "int"],
    ["slt", "Sleight of Hand", "dex"], ["ste", "Stealth", "dex"], ["sur", "Survival", "wis"]
  ];
  const FULL_CASTERS = ["bard", "cleric", "druid", "sorcerer", "wizard", "mage"];
  const HALF_CASTERS = ["paladin", "ranger"];
  const FULL_SLOTS = [
    [],
    [2], [3], [4, 2], [4, 3], [4, 3, 2], [4, 3, 3], [4, 3, 3, 1], [4, 3, 3, 2], [4, 3, 3, 3, 1],
    [4, 3, 3, 3, 2], [4, 3, 3, 3, 2, 1], [4, 3, 3, 3, 2, 1], [4, 3, 3, 3, 2, 1, 1], [4, 3, 3, 3, 2, 1, 1],
    [4, 3, 3, 3, 2, 1, 1, 1], [4, 3, 3, 3, 2, 1, 1, 1], [4, 3, 3, 3, 2, 1, 1, 1, 1],
    [4, 3, 3, 3, 3, 1, 1, 1, 1], [4, 3, 3, 3, 3, 2, 1, 1, 1], [4, 3, 3, 3, 3, 2, 2, 1, 1]
  ];
  const GEAR_TYPES = new Set([
    "weapon", "equipment", "armor", "consumable", "loot", "container", "tool", "backpack", "gear"
  ]);
  const STATUS_LABELS = {
    concentrating: "Concentrating",
    prone: "Prone",
    restrained: "Restrained",
    grappled: "Grappled",
    stunned: "Stunned",
    incapacitated: "Incapacitated",
    paralyzed: "Paralyzed",
    petrified: "Petrified",
    unconscious: "Unconscious",
    poisoned: "Poisoned",
    frightened: "Frightened",
    charmed: "Charmed",
    blinded: "Blinded",
    deafened: "Deafened",
    exhaustion: "Exhaustion",
    invisible: "Invisible",
    dodging: "Dodging",
    burning: "Burning",
    diseased: "Diseased",
    cursed: "Cursed",
    bleeding: "Bleeding",
    flying: "Flying",
    hovering: "Hovering",
    hiding: "Hiding",
    silenced: "Silenced",
    transformed: "Transformed",
    dead: "Dead"
  };

  function numberOrNull(value) {
    if (typeof value === "number" && Number.isFinite(value)) return value;
    if (typeof value === "string" && value.trim() && Number.isFinite(Number(value))) return Number(value);
    return null;
  }

  function abilityMod(score) {
    const n = numberOrNull(score);
    if (n == null) return 0;
    return Math.floor((n - 10) / 2);
  }

  function fmtMod(n) {
    const value = Math.trunc(Number(n) || 0);
    return value >= 0 ? "+" + value : String(value);
  }

  function decodeEntities(text) {
    return String(text)
      .replace(/&#(\d+);/g, (_, n) => String.fromCodePoint(Number(n)))
      .replace(/&#x([0-9a-f]+);/gi, (_, n) => String.fromCodePoint(parseInt(n, 16)))
      .replace(/&nbsp;/gi, " ")
      .replace(/&amp;/gi, "&")
      .replace(/&lt;/gi, "<")
      .replace(/&gt;/gi, ">")
      .replace(/&quot;/gi, "\"")
      .replace(/&#39;|&apos;/gi, "'");
  }

  function readable(value) {
    if (value == null) return "";
    if (typeof value !== "string") {
      if (typeof value === "object" && typeof value.value === "string") return readable(value.value);
      return "";
    }
    let text = value
      .replace(/<script[\s\S]*?<\/script>/gi, "")
      .replace(/<style[\s\S]*?<\/style>/gi, "")
      .replace(/<br\s*\/?>/gi, "\n")
      .replace(/<\/(p|div|li|h\d|tr|blockquote)>/gi, "\n")
      .replace(/<li[^>]*>/gi, "• ")
      .replace(/<[^>]+>/g, "");
    text = decodeEntities(text);
    text = text.replace(/(?:@|&)[A-Za-z0-9_.]+\[([^\]]*)\](?:\{([^}]*)\})?/g, (_, id, label) => label || id || "");
    return text.replace(/[ \t]+\n/g, "\n").replace(/\n{3,}/g, "\n\n").trim();
  }

  function systemOf(doc) {
    if (!doc || typeof doc !== "object") return {};
    if (doc.system && typeof doc.system === "object") return doc.system;
    const data = doc.data;
    if (!data || typeof data !== "object") return {};
    if (data.abilities || data.attributes || data.skills || data.spells) return data;
    if (data.data && typeof data.data === "object") return data.data;
    return {};
  }

  function systemOfItem(item) {
    if (!item || typeof item !== "object") return {};
    if (item.system && typeof item.system === "object") return item.system;
    const data = item.data;
    if (!data || typeof data !== "object") return {};
    if (
      data.description || data.quantity != null || data.level != null || data.armor ||
      data.damage || data.preparation || data.activities || data.spellcasting
    ) return data;
    if (data.data && typeof data.data === "object") return data.data;
    return data;
  }

  function itemsOf(doc) {
    const lists = [];
    if (Array.isArray(doc.items)) lists.push(doc.items);
    if (Array.isArray(doc.data?.items)) lists.push(doc.data.items);
    if (Array.isArray(doc.system?.items)) lists.push(doc.system.items);
    return lists.flat().filter(item => item && typeof item === "object");
  }

  function isActorLike(doc) {
    if (!doc || typeof doc !== "object" || Array.isArray(doc)) return false;
    const kind = String(doc.type || "");
    if (["character", "npc", "vehicle", "group"].includes(kind) && (doc.system || doc.data || doc.name)) return true;
    const system = systemOf(doc);
    return !!(system.abilities || system.attributes);
  }

  function collectActors(root) {
    if (Array.isArray(root)) return root.filter(isActorLike);
    if (isActorLike(root)) return [root];
    if (!root || typeof root !== "object") return [];
    const found = [];
    for (const key of ["actor", "actors", "data"]) {
      const value = root[key];
      if (Array.isArray(value)) found.push(...value.filter(isActorLike));
      else if (isActorLike(value)) found.push(value);
    }
    return found;
  }

  function editionOf(doc, items) {
    const stats = doc._stats || {};
    const activities = items.some(item => {
      const system = systemOfItem(item);
      return system.activities && typeof system.activities === "object";
    });
    const parts = [];
    if (stats.coreVersion) parts.push("Foundry " + stats.coreVersion);
    else if (doc.system) parts.push("Foundry 10+");
    else if (doc.data) parts.push("Foundry 0.8–9");
    if (stats.systemVersion) parts.push("dnd5e " + stats.systemVersion);
    else if (activities) parts.push("dnd5e 4+");
    else if (doc.system) parts.push("dnd5e 2/3");
    else if (doc.data) parts.push("dnd5e 1.x");
    return parts.join(" · ");
  }

  function safeImg(src) {
    if (typeof src !== "string") return "";
    const text = src.trim();
    if (/^https?:\/\//i.test(text)) return text;
    if (/^data:image\/(?:png|jpeg|jpg|gif|webp);base64,/i.test(text)) return text;
    return "";
  }

  function formulaText(ac) {
    if (!ac || typeof ac !== "object") return "";
    if (typeof ac.formula === "string" && ac.formula.trim()) return ac.formula.trim();
    if (Array.isArray(ac.formulas) && ac.formulas.length) {
      return ac.formulas.map(part => (typeof part === "string" ? part : part?.formula || "")).filter(Boolean).join(" + ");
    }
    return "";
  }

  function defenseLabel(base, dex, shield, bonus, cover, flat) {
    const parts = [base];
    if (dex) parts.push("Dex " + dex);
    if (shield) parts.push("shield " + shield);
    if (flat) parts.push("flat " + flat);
    if (bonus) parts.push("bonus " + bonus);
    if (cover) parts.push("cover " + cover);
    return parts.join(" + ");
  }

  function equippedDefense(items) {
    const armors = [];
    let shield = 0;
    for (const item of items) {
      const system = systemOfItem(item);
      if (!system.equipped) continue;
      const armor = system.armor || {};
      const armorType = String(armor.type || "");
      const ac = numberOrNull(armor.value);
      if (armorType === "shield" || item.type === "shield") {
        shield += ac == null ? 2 : ac;
      } else if (ac != null && ["light", "medium", "heavy"].includes(armorType)) {
        armors.push({ type: armorType, ac, dex: numberOrNull(armor.dex) });
      }
    }
    return { armor: armors[0] || null, shield };
  }

  function dexContribution(armor, dex) {
    if (!armor || armor.type === "heavy") return 0;
    let cap = armor.dex;
    if (cap == null && armor.type === "medium") cap = 2;
    if (cap == null) return dex;
    return Math.min(dex, cap);
  }

  function armorClass(system, items) {
    const raw = system.attributes?.ac;
    if (typeof raw === "number") return { value: raw, formula: String(raw) };
    const ac = raw && typeof raw === "object" ? raw : {};
    const stored = numberOrNull(ac.value);
    const formula = formulaText(ac);
    if (stored != null) return { value: stored, formula: formula || String(stored) };

    const abilities = system.abilities || {};
    const dex = abilityMod(abilities.dex?.value);
    const con = abilityMod(abilities.con?.value);
    const wis = abilityMod(abilities.wis?.value);
    const flat = numberOrNull(ac.flat) || 0;
    const bonus = numberOrNull(ac.bonus) || 0;
    const cover = numberOrNull(ac.cover) || 0;
    const calc = typeof ac.calc === "string" ? ac.calc : "";
    const defense = equippedDefense(items);
    let base = null;
    let how = formula;

    if (calc === "flat") {
      base = flat;
      how = how || "flat " + flat;
    } else if (calc === "natural") {
      base = 10 + dex + flat;
      how = how || "10 + Dex + natural";
    } else if (calc === "mage" || calc === "mageArmor") {
      base = 13 + dex;
      how = how || "13 + Dex";
    } else if (calc === "draconic") {
      base = 13 + dex;
      how = how || "13 + Dex";
    } else if (calc === "unarmoredBarb" || calc === "unarmoredBarbarian") {
      base = 10 + dex + con;
      how = how || "10 + Dex + Con";
    } else if (calc === "unarmoredMonk") {
      base = 10 + dex + wis;
      how = how || "10 + Dex + Wis";
    } else if (calc === "custom" && formula) {
      return { value: null, formula };
    } else if (defense.armor) {
      const dexPart = dexContribution(defense.armor, dex);
      base = defense.armor.ac + dexPart + defense.shield + bonus + cover;
      how = how || defenseLabel(defense.armor.type + " " + defense.armor.ac, dexPart, defense.shield, bonus, cover, 0);
    } else {
      base = 10 + dex + defense.shield + flat + bonus + cover;
      how = how || defenseLabel("10", dex, defense.shield, bonus, cover, flat);
    }
    return { value: base, formula: how };
  }

  function speedsOf(system) {
    const attr = system.attributes || {};
    const move = attr.movement;
    const out = [];
    if (typeof move === "number") {
      out.push({ key: "walk", value: move, units: "ft" });
      return out;
    }
    if (move && typeof move === "object") {
      const units = move.units || "ft";
      for (const key of ["walk", "fly", "swim", "climb", "burrow"]) {
        const value = numberOrNull(move[key]);
        if (value) out.push({ key, value, units, hover: key === "fly" && !!move.hover });
      }
    }
    if (!out.length && attr.speed != null) {
      const raw = typeof attr.speed === "object" ? attr.speed.value : attr.speed;
      const value = numberOrNull(String(raw).match(/\d+/)?.[0]);
      if (value) out.push({ key: "walk", value, units: "ft" });
    }
    return out;
  }

  function sensesOf(system) {
    const senses = system.attributes?.senses || {};
    const ranges = senses.ranges && typeof senses.ranges === "object" ? senses.ranges : senses;
    const labels = [
      ["darkvision", "Darkvision"],
      ["blindsight", "Blindsight"],
      ["tremorsense", "Tremorsense"],
      ["truesight", "Truesight"]
    ];
    const units = senses.units || "ft";
    const out = [];
    for (const [key, label] of labels) {
      const value = numberOrNull(ranges[key]);
      if (value) out.push(label + " " + value + " " + units);
    }
    const special = readable(senses.special);
    if (special) out.push(special);
    return out;
  }

  function profMultiplier(entry) {
    if (!entry || typeof entry !== "object") return 0;
    if (typeof entry.proficient === "number") return entry.proficient;
    if (typeof entry.prof === "number") return entry.prof;
    if (entry.prof && typeof entry.prof.multiplier === "number") return entry.prof.multiplier;
    if (entry.value === true) return 1;
    return 0;
  }

  function numericBonus(value) {
    if (typeof value === "number") return value;
    if (typeof value === "string" && value.trim() && Number.isFinite(Number(value))) return Number(value);
    return 0;
  }

  function abilitiesOf(system, prof) {
    const source = system.abilities || {};
    return ABILITIES.map(([key, label]) => {
      const entry = source[key] || {};
      const score = numberOrNull(entry.value);
      const mod = numberOrNull(entry.mod);
      const shownMod = mod == null ? abilityMod(score == null ? 10 : score) : mod;
      const multiplier = profMultiplier(entry);
      const saveBonus = numericBonus(entry.bonuses?.save ?? entry.saveBonus);
      let save = null;
      if (entry.save && typeof entry.save === "object" && numberOrNull(entry.save.value) != null) {
        save = entry.save.value;
      } else if (numberOrNull(entry.save) != null && typeof entry.save !== "object") {
        save = Number(entry.save);
      } else {
        save = shownMod + Math.floor(prof * multiplier) + saveBonus;
      }
      return {
        key,
        label,
        score: score == null ? 10 : score,
        mod: shownMod,
        save,
        proficient: multiplier > 0
      };
    });
  }

  function skillsOf(system, abilities, prof) {
    const source = system.skills || {};
    const byKey = Object.fromEntries(abilities.map(ability => [ability.key, ability]));
    return SKILLS.map(([key, label, ability]) => {
      const entry = source[key] || {};
      const abilityModValue = byKey[ability] ? byKey[ability].mod : 0;
      const multiplier = profMultiplier(entry);
      const bonus = numericBonus(entry.bonuses?.check ?? entry.bonus ?? entry.roll?.bonus);
      let total = null;
      if (numberOrNull(entry.passive) != null) total = entry.passive - 10;
      else if (numberOrNull(entry.total) != null) total = entry.total;
      else if (numberOrNull(entry.value) != null && (multiplier || bonus || entry.prof != null || entry.proficient != null)) {
        total = entry.value;
      } else {
        total = abilityModValue + Math.floor(prof * multiplier) + bonus;
      }
      return {
        key,
        label,
        ability,
        total,
        passive: numberOrNull(entry.passive) != null ? entry.passive : 10 + total,
        proficient: multiplier >= 1,
        expertise: multiplier >= 2
      };
    });
  }

  function initiativeOf(system, abilities) {
    const init = system.attributes?.init || {};
    const dex = abilities.find(ability => ability.key === "dex");
    const dexMod = dex ? dex.mod : 0;
    const bonus = numericBonus(init.bonus);
    let total = numberOrNull(init.total);
    if (total == null) total = numberOrNull(init.value);
    if (total == null) total = dexMod + bonus;
    return { total, formula: "1d20" + fmtMod(total) };
  }

  function classProgression(item, subclassNames) {
    const system = systemOfItem(item);
    const progression = system.spellcasting?.progression || system.spellcasting;
    if (typeof progression === "string" && progression) return progression.toLowerCase();
    const name = String(item.name || "").toLowerCase();
    if (FULL_CASTERS.includes(name)) return "full";
    if (HALF_CASTERS.includes(name)) return "half";
    if (name === "warlock") return "pact";
    if (name === "artificer") return "artificer";
    if (name === "fighter" && subclassNames.some(sub => sub.includes("eldritch knight"))) return "third";
    if (name === "rogue" && subclassNames.some(sub => sub.includes("arcane trickster"))) return "third";
    return "";
  }

  function casterLevel(items) {
    let full = 0;
    let half = 0;
    let third = 0;
    let artificer = 0;
    let pact = 0;
    const subclasses = items
      .filter(item => item.type === "subclass")
      .map(item => String(item.name || "").toLowerCase());
    for (const item of items) {
      if (item.type !== "class") continue;
      const system = systemOfItem(item);
      const level = numberOrNull(system.levels) || 1;
      const progression = classProgression(item, subclasses);
      if (progression === "full") full += level;
      else if (progression === "half") half += level;
      else if (progression === "third") third += level;
      else if (progression === "artificer") artificer += level;
      else if (progression === "pact") pact = Math.max(pact, level);
    }
    const levels = full + Math.floor(half / 2) + Math.floor(third / 3) + Math.ceil(artificer / 2);
    return { levels: Math.min(20, levels), pact };
  }

  function pactSlots(level) {
    if (!level) return null;
    let slots = 1;
    let slotLevel = 1;
    if (level >= 2) slots = 2;
    if (level >= 11) slots = 3;
    if (level >= 17) slots = 4;
    if (level >= 3) slotLevel = 2;
    if (level >= 5) slotLevel = 3;
    if (level >= 7) slotLevel = 4;
    if (level >= 9) slotLevel = 5;
    return { remaining: null, max: slots, level: slotLevel, pact: true };
  }

  function slotsFromClasses(items) {
    const caster = casterLevel(items);
    const table = FULL_SLOTS[caster.levels] || [];
    const rows = [];
    table.forEach((max, index) => {
      if (max) rows.push({ level: index + 1, remaining: null, max, pact: false });
    });
    const pact = pactSlots(caster.pact);
    if (pact) rows.push(pact);
    return rows;
  }

  function spellSlots(system, items) {
    const spells = system.spells || {};
    const rows = [];
    for (let level = 1; level <= 9; level += 1) {
      const slot = spells["spell" + level];
      if (!slot || typeof slot !== "object") continue;
      const maxField = numberOrNull(slot.max);
      const override = numberOrNull(slot.override);
      const max = maxField != null ? maxField : override;
      let remaining = numberOrNull(slot.value);
      const spent = numberOrNull(slot.spent);
      if (spent != null && max != null) remaining = Math.max(0, max - spent);
      if ((max == null || max === 0) && (remaining == null || remaining === 0)) continue;
      rows.push({ level, remaining, max, pact: false });
    }
    const pact = spells.pact;
    if (pact && typeof pact === "object") {
      const max = numberOrNull(pact.max) != null ? pact.max : numberOrNull(pact.override);
      let remaining = numberOrNull(pact.value);
      const spent = numberOrNull(pact.spent);
      if (spent != null && max != null) remaining = Math.max(0, max - spent);
      if (max || remaining) {
        rows.push({
          level: numberOrNull(pact.level) || 1,
          remaining,
          max,
          pact: true
        });
      }
    }
    if (rows.length) return rows;
    return slotsFromClasses(items);
  }

  function effectRecords(doc) {
    const lists = [];
    if (Array.isArray(doc.effects)) lists.push(doc.effects);
    if (Array.isArray(doc.data?.effects)) lists.push(doc.data.effects);
    if (Array.isArray(doc.system?.effects)) lists.push(doc.system.effects);
    return lists.flat().filter(effect => effect && typeof effect === "object" && !effect.disabled);
  }

  function conditionsOf(doc) {
    const names = [];
    const seen = new Set();
    function add(label) {
      const text = String(label || "").trim();
      if (!text) return;
      const key = text.toLowerCase();
      if (seen.has(key)) return;
      seen.add(key);
      names.push(text);
    }
    for (const effect of effectRecords(doc)) {
      const statuses = []
        .concat(effect.statuses || [])
        .concat(effect.flags?.core?.statusId || []);
      if (Array.isArray(effect.statuses)) {
        for (const status of effect.statuses) add(STATUS_LABELS[status] || status);
      } else if (effect.statuses && typeof effect.statuses === "object") {
        for (const status of Object.keys(effect.statuses)) add(STATUS_LABELS[status] || status);
      }
      const statusId = effect.flags?.core?.statusId;
      if (typeof statusId === "string") add(STATUS_LABELS[statusId] || statusId);
      if (!statuses.length && !statusId) add(effect.name || effect.label);
    }
    return names;
  }

  function concentrating(doc, system) {
    const active = conditionsOf(doc).some(name => name.toLowerCase() === "concentrating");
    const config = system.attributes?.concentration || {};
    const bonus = readable(config.bonuses?.save || config.bonus || "");
    const ability = typeof config.ability === "string" ? config.ability.toUpperCase() : "";
    return { active, bonus, ability };
  }

  function deathSaves(system) {
    const death = system.attributes?.death || {};
    return {
      success: numberOrNull(death.success) || 0,
      failure: numberOrNull(death.failure) || 0
    };
  }

  function itemSource(system) {
    const source = system.source;
    if (!source) return "";
    if (typeof source === "string") return source;
    return source.custom || source.book || "";
  }

  function damageFormulas(system) {
    const found = [];
    const parts = system.damage?.parts;
    if (Array.isArray(parts)) {
      for (const part of parts) {
        if (Array.isArray(part) && part[0]) found.push(String(part[0]));
        else if (part && part.formula) found.push(String(part.formula));
      }
    }
    const base = system.damage?.base?.formula || system.damage?.formula;
    if (base) found.push(String(base));
    const activities = system.activities;
    if (activities && typeof activities === "object") {
      for (const activity of Object.values(activities)) {
        const activityParts = activity?.damage?.parts || activity?.damage?.includeBase;
        if (Array.isArray(activity?.damage?.parts)) {
          for (const part of activity.damage.parts) {
            if (Array.isArray(part) && part[0]) found.push(String(part[0]));
            else if (typeof part === "string") found.push(part);
            else if (part?.formula) found.push(String(part.formula));
          }
        }
        if (activity?.damage?.formula) found.push(String(activity.damage.formula));
        if (typeof activityParts === "string") found.push(activityParts);
      }
    }
    return [...new Set(found.map(formula => formula.trim()).filter(Boolean))];
  }

  function concentrationFlag(system) {
    if (system.components?.concentration) return true;
    const props = system.properties;
    if (Array.isArray(props)) return props.includes("concentration");
    if (props && typeof props === "object") return !!props.concentration;
    return false;
  }

  function preparation(system) {
    const prep = system.preparation || {};
    const mode = prep.mode || system.method || "";
    if (mode === "always" || mode === "atwill" || mode === "innate" || mode === "pact") return mode;
    if (prep.prepared === true || system.prepared === true) return "prepared";
    return "";
  }

  function blankItem(item) {
    const system = systemOfItem(item);
    const description = readable(system.description?.value || system.description);
    const quantity = numberOrNull(system.quantity);
    const attuned = system.attunement === true || system.attunement === 2 || system.attuned === true;
    return {
      name: item.name || "Unnamed",
      type: item.type || "",
      text: description,
      quantity: quantity != null && quantity !== 1 ? quantity : null,
      equipped: !!system.equipped,
      attuned,
      source: itemSource(system),
      damage: damageFormulas(system),
      level: numberOrNull(system.level),
      preparation: preparation(system),
      concentration: concentrationFlag(system)
    };
  }

  function spellGroups(items) {
    const groups = new Map();
    for (const item of items) {
      if (item.type !== "spell") continue;
      const blank = blankItem(item);
      const level = blank.level == null ? 0 : blank.level;
      if (!groups.has(level)) groups.set(level, []);
      groups.get(level).push(blank);
    }
    return [...groups.keys()].sort((a, b) => a - b).map(level => ({
      level,
      items: groups.get(level)
    }));
  }

  function splitItems(items) {
    const features = [];
    const inventory = [];
    for (const item of items) {
      if (item.type === "spell") continue;
      const blank = blankItem(item);
      if (GEAR_TYPES.has(item.type)) inventory.push(blank);
      else features.push(blank);
    }
    return { features, inventory };
  }

  function subtitleOf(doc, system, items) {
    if (doc.type === "npc") {
      const cr = system.details?.cr;
      const crText = cr == null || typeof cr === "object" ? (cr?.value ?? cr?.cr ?? "") : cr;
      const kind = readable(system.details?.type?.value || system.details?.type?.custom || system.details?.type || "NPC");
      return [kind, crText !== "" ? "CR " + crText : ""].filter(Boolean).join(" · ");
    }
    const classes = items.filter(item => item.type === "class").map(item => {
      const level = numberOrNull(systemOfItem(item).levels) || 1;
      return item.name + " " + level;
    });
    const species = items.find(item => item.type === "race" || item.type === "species");
    const background = items.find(item => item.type === "background");
    return [
      classes.join(", ") || "Unknown class",
      species?.name || "Unknown ancestry",
      background?.name || "Unknown background"
    ].join(" · ");
  }

  function biographyOf(system) {
    const details = system.details || {};
    const alignment = details.alignment;
    let alignmentText = "";
    if (typeof alignment === "string") alignmentText = alignment;
    else if (alignment && typeof alignment === "object") alignmentText = alignment.custom || alignment.value || "";
    const fields = [
      ["Alignment", alignmentText],
      ["Biography", details.biography?.value || details.biography],
      ["Appearance", details.appearance],
      ["Personality", details.trait],
      ["Ideal", details.ideal],
      ["Bond", details.bond],
      ["Flaw", details.flaw]
    ];
    return fields
      .map(([label, value]) => ({ label, text: readable(value) }))
      .filter(field => field.text);
  }

  function currenciesOf(system) {
    const currency = system.currency || {};
    return ["pp", "gp", "ep", "sp", "cp"]
      .map(key => ({ key, value: numberOrNull(currency[key]) || 0 }))
      .filter(coin => coin.value);
  }

  function characterLevel(items, system) {
    const classes = items.filter(item => item.type === "class");
    if (classes.length) {
      return classes.reduce((sum, item) => sum + (numberOrNull(systemOfItem(item).levels) || 1), 0);
    }
    return numberOrNull(system.details?.level) || 0;
  }

  function proficiencyOf(system, level) {
    const stored = numberOrNull(system.attributes?.prof);
    if (stored != null) return stored;
    if (!level) return 2;
    return Math.floor((level - 1) / 4) + 2;
  }

  function rollContext(abilities, prof, ac) {
    const context = { prof, ac: ac?.value };
    for (const ability of abilities) {
      context[ability.key] = { mod: ability.mod, value: ability.score, save: ability.save };
    }
    return context;
  }

  function normalizeOne(doc) {
    const system = systemOf(doc);
    const items = itemsOf(doc);
    const level = characterLevel(items, system);
    const prof = proficiencyOf(system, level);
    const abilities = abilitiesOf(system, prof);
    const ac = armorClass(system, items);
    const groups = spellGroups(items);
    const split = splitItems(items);
    const hp = system.attributes?.hp || {};
    return {
      name: doc.name || "Unnamed",
      type: doc.type || "character",
      img: safeImg(doc.img || doc.prototypeToken?.texture?.src || doc.token?.img || ""),
      edition: editionOf(doc, items),
      subtitle: subtitleOf(doc, system, items),
      level,
      proficiency: prof,
      inspiration: !!system.attributes?.inspiration,
      exhaustion: numberOrNull(system.attributes?.exhaustion) || 0,
      ac,
      hp: {
        value: numberOrNull(hp.value),
        max: numberOrNull(hp.max),
        temp: numberOrNull(hp.temp) || 0
      },
      speeds: speedsOf(system),
      initiative: initiativeOf(system, abilities),
      death: deathSaves(system),
      concentration: concentrating(doc, system),
      conditions: conditionsOf(doc),
      abilities,
      skills: skillsOf(system, abilities, prof),
      senses: sensesOf(system),
      slots: spellSlots(system, items),
      features: split.features,
      spells: groups,
      inventory: split.inventory,
      biography: biographyOf(system),
      currencies: currenciesOf(system),
      spell: {
        dc: numberOrNull(system.attributes?.spell?.dc ?? system.attributes?.spelldc),
        attack: numberOrNull(system.attributes?.spell?.attack ?? system.attributes?.spellcasting)
      },
      context: rollContext(abilities, prof, ac)
    };
  }

  function normalizeDocument(root) {
    const actors = collectActors(root).map(normalizeOne);
    if (!actors.length) {
      return { actors: [], error: "This JSON is not a Foundry actor export." };
    }
    return { actors, error: "" };
  }

  function resolveFormula(formula, context) {
    const ctx = context || {};
    return String(formula || "").replace(/@([A-Za-z0-9_.]+)/g, (match, path) => {
      if (path === "prof" || path === "attributes.prof" || path === "prof.flat") {
        return ctx.prof == null ? match : String(ctx.prof);
      }
      if (path === "attributes.ac.value" || path === "attributes.ac.flat") {
        return ctx.ac == null ? match : String(ctx.ac);
      }
      const ability = path.match(/^abilities\.([a-z]{3})\.(mod|value|save)$/);
      if (ability && ctx[ability[1]] && ctx[ability[1]][ability[2]] != null) {
        return String(ctx[ability[1]][ability[2]]);
      }
      const skill = path.match(/^skills\.([a-z]{3})\.(mod|total|value)$/);
      if (skill) return match;
      return match;
    });
  }

  function rollFormula(formula, rng) {
    const random = rng || Math.random;
    const cleaned = String(formula || "").toLowerCase().replace(/\s+/g, "");
    if (!cleaned || /[^0-9dklh+-]/.test(cleaned)) return null;
    const terms = cleaned.match(/[+-]?[^+-]+/g);
    if (!terms) return null;
    let total = 0;
    const parts = [];
    for (const term of terms) {
      const sign = term.startsWith("-") ? -1 : 1;
      const body = term.replace(/^[+-]/, "");
      if (/^\d+$/.test(body)) {
        total += sign * Number(body);
        parts.push((sign < 0 ? "-" : "+") + body);
        continue;
      }
      const dice = body.match(/^(\d*)d(\d+)(?:k([hl])(\d+))?$/);
      if (!dice) return null;
      const count = dice[1] ? Number(dice[1]) : 1;
      const sides = Number(dice[2]);
      if (!sides || count < 1 || count > 40 || sides > 1000) return null;
      const rolls = [];
      for (let i = 0; i < count; i += 1) rolls.push(1 + Math.floor(random() * sides));
      let kept = rolls.slice();
      if (dice[3]) {
        const keep = Math.min(Number(dice[4]) || 1, rolls.length);
        const ordered = rolls.slice().sort((a, b) => a - b);
        kept = dice[3] === "h" ? ordered.slice(-keep) : ordered.slice(0, keep);
      }
      const subtotal = kept.reduce((sum, roll) => sum + roll, 0);
      total += sign * subtotal;
      parts.push((sign < 0 ? "-" : "+") + kept.join("/"));
    }
    return { total, detail: parts.join(" ").replace(/^\+/, "") };
  }

  return {
    normalizeDocument,
    resolveFormula,
    rollFormula,
    readable,
    safeImg,
    crSlots: slotsFromClasses
  };
});
