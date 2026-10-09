// Query words and wild-shape tiers for the druid bestiary.
// A sort word matches a known form when it is that form, a short ending on it,
// or one or two letters short of it. Short aliases such as "кд" match only whole.
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.DruidQuery = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  const STAT_RULES = [
    { key: "st", forms: ["скрытность", "скрыт", "stealth", "stealt"] },
    { key: "pr", forms: ["восприятие", "восприя", "perception", "percep"] },
    { key: "dm", forms: ["урон", "урона", "damage", "damag"] },
    { key: "hp", forms: ["хиты", "хитов", "хит", "хп", "hp"] },
    { key: "ac", forms: ["броня", "брони", "брон", "кд", "armor", "ac"] },
    { key: "speed", forms: ["скорость", "скорости", "скоростью", "speed", "speeds"] },
    { key: "str", forms: ["сила", "силы", "силе", "силу", "силой", "strength", "сил", "str"] },
    { key: "dex", forms: ["ловкость", "ловкости", "ловк", "лвк", "dexterity", "dex"] },
    { key: "con", forms: ["телосложение", "тело", "тел", "constitution", "con"] }
  ];

  const REFINE_RULES = [
    { key: "sp_w", forms: ["ходьба", "ходьбы", "ходьбу", "ходьб", "walk"] },
    { key: "sp_f", forms: ["полет", "полета", "полету", "fly"] },
    { key: "sp_s", forms: ["плавание", "плавания", "плава", "swim"] },
    { key: "sp_c", forms: ["лазание", "лазания", "лазан", "climb"] },
    { key: "sp_b", forms: ["копание", "копания", "копан", "burrow"] },
    { key: "sn_blind", forms: ["слепое", "слепо", "blind"] },
    { key: "sn_dark", forms: ["темное", "темн", "dark"] },
    { key: "sn_tremor", forms: ["вибрация", "вибрации", "вибрац", "tremor"] },
    { key: "sn_true", forms: ["истинное", "истин", "true"] },
    { key: "sn_any", forms: ["чувства", "чувств", "зрение", "зрен", "senses", "sens", "vision", "sight"] }
  ];

  function matchesLoose(word, form) {
    if (!word || !form) return false;
    if (word === form) return true;
    if (form.length >= 4 && word.startsWith(form) && word.length - form.length <= 6) return true;
    if (word.length >= 5 && form.startsWith(word) && form.length - word.length <= 2) return true;
    return false;
  }

  function matchRule(word, rules) {
    for (const rule of rules) {
      if (rule.forms.some(form => matchesLoose(word, form))) return rule.key;
    }
    return null;
  }

  function tokenize(query) {
    return String(query || "")
      .replace(/ё/g, "е")
      .toLowerCase()
      .split(/\s+/)
      .map(word => {
        const negative = word.startsWith("-") && word.length > 1;
        const body = (negative ? word.slice(1) : word).replace(/[.,;:!?()[\]"'«»]/g, "");
        if (!body) return "";
        return negative ? "-" + body : body;
      })
      .filter(Boolean);
  }

  function classifyQuery(query) {
    const sort = [];
    const filters = [];
    const negative = [];
    const seen = new Set();
    for (const word of tokenize(query)) {
      if (word.startsWith("-")) {
        negative.push(word.slice(1));
        continue;
      }
      const stat = matchRule(word, STAT_RULES);
      if (stat) {
        if (!seen.has(stat)) {
          seen.add(stat);
          sort.push(stat);
        }
        continue;
      }
      filters.push(word);
      const refine = matchRule(word, REFINE_RULES);
      if (refine && !seen.has(refine)) {
        seen.add(refine);
        sort.push(refine);
      }
    }
    return { sort, filters, negative };
  }

  function crValue(cr) {
    if (typeof cr === "number" && Number.isFinite(cr)) return cr;
    const text = String(cr == null ? "" : cr).trim();
    if (!text) return NaN;
    if (text.includes("/")) {
      const parts = text.split("/");
      const num = Number(parts[0]);
      const den = Number(parts[1]);
      if (!den) return NaN;
      return num / den;
    }
    return Number(text);
  }

  // 2014 wild shape: CR 1/4 and no swim or fly at level 2,
  // CR 1/2 and no fly at level 4, CR 1 at level 8.
  // Familiar is a separate flag; a flying familiar is not a level 2 shape.
  function categoriesFor(creature) {
    const cats = [];
    if (creature && creature.fam) cats.push("fam");
    const cr = crValue(creature && creature.cr);
    if (!Number.isFinite(cr)) return cats;
    const speed = (creature && creature.sp) || {};
    const fly = Number(speed.f) > 0;
    const swim = Number(speed.s) > 0;
    if (cr <= 0.25 && !fly && !swim) cats.push("lvl2");
    if (cr <= 0.5 && !fly) cats.push("lvl4");
    if (cr <= 1) cats.push("lvl8");
    return cats;
  }

  const SYNONYMS = {
    ru: {
      "кошка": ["кот", "котик", "кошка", "кошачий", "кошачья", "львица", "тигрица"],
      "собака": ["пес", "пёс", "собака", "собачка", "щенок"],
      "лошадь": ["конь", "лошадь", "скакун", "жеребец", "кобыла", "пони"],
      "вьючное": ["грузоподъемность", "груз", "нести", "вьючное", "вьючный", "вьючные"],
      "ездовое": ["маунт", "верхом", "седло", "кататься", "ездовой", "ездовое", "верховое", "верховая"],
      "яд": ["яд", "отрава", "токсин", "отравлен", "ядом", "отравление"],
      "сбить": ["сбить", "ног", "упасть", "опрокинуть", "таран", "сбивает"],
      "захват": ["захват", "схватить", "удержать", "опутать", "опутан", "схвачен"],
      "паутина": ["паутина", "паутину", "паутине", "паучь", "web"],
      "язык": ["язык", "говорит", "понимает", "речь"],
      "сопротивление": ["иммунитет", "сопротивление", "невосприимчивость", "устойчивость", "резист"],
      "особенный": ["особенный", "уникальный", "специфичный", "магия", "магический"],
      "рой": ["рой", "рои", "стая"]
    },
    en: {
      "cat": ["cat", "kitty", "feline", "tomcat"],
      "dog": ["dog", "hound", "canine", "pup"],
      "horse": ["horse", "steed", "stallion", "mare", "pony"],
      "pack": ["carrying capacity", "carry", "burden", "pack"],
      "mount": ["riding", "saddle", "ride", "mount", "steed"],
      "poison": ["toxin", "poisoned", "venom", "poison"],
      "prone": ["knock", "fall", "ram", "prone"],
      "grapple": ["grab", "hold", "restrain", "grapple"],
      "web": ["web", "spider web", "webs"],
      "language": ["speak", "understand", "speech", "language"],
      "immunity": ["resistance", "immune", "resist", "immunity"],
      "special": ["unique", "specific", "magic", "magical", "special"],
      "swarm": ["flock", "school", "swarm"]
    }
  };

  const SENSE_DISTANCE = {
    blind: /(?:blind|слепо)[^\d]*(\d+)/i,
    dark: /(?:dark|т[её]мн)[^\d]*(\d+)/i,
    tremor: /(?:tremor|вибрац)[^\d]*(\d+)/i,
    true: /(?:true|истин)[^\d]*(\d+)/i
  };

  function normalizeText(value) {
    return String(value || "").replace(/ё/g, "е").toLowerCase();
  }

  function senseDistance(creature, senseType) {
    const pattern = SENSE_DISTANCE[senseType];
    if (!pattern) return -1;
    const senses = (creature.sn_ru || []).concat(creature.sn_en || []).join(" ");
    const match = senses.match(pattern);
    return match ? parseInt(match[1], 10) : -1;
  }

  function statValue(creature, key) {
    const speed = creature.sp || {};
    if (key === "speed") return Math.max(speed.w || 0, speed.f || 0, speed.s || 0, speed.c || 0, speed.b || 0);
    if (key.startsWith("sp_")) return speed[key.split("_")[1]] || 0;
    if (key.startsWith("sn_") && key !== "sn_any") {
      const distance = senseDistance(creature, key.split("_")[1]);
      return distance > 0 ? distance : 0;
    }
    if (key === "sn_any") return (creature.sn_ru || []).length || (creature.sn_en || []).length ? 1 : 0;
    const value = creature[key];
    return typeof value === "number" ? value : (parseInt(value, 10) || 0);
  }

  function searchableText(creature, lang) {
    const name = lang === "ru" ? creature.n_ru : creature.n_en;
    const size = lang === "ru" ? creature.sz_ru : creature.sz_en;
    const tags = (lang === "ru" ? creature.tg_ru : creature.tg_en) || [];
    const habitats = (lang === "ru" ? creature.hb_ru : creature.hb_en) || [];
    let text = normalizeText([
      name, creature.n_en, size, creature.cr, creature.src, creature.src_ru,
      tags.join(" "), habitats.join(" "),
      (creature.sn_ru || []).join(" "), (creature.sn_en || []).join(" ")
    ].join(" "));
    const speed = creature.sp || {};
    if (speed.w) text += " walk ходьба ходьбу";
    if (speed.f) text += " fly полет полёт flyby";
    if (speed.s) text += " swim плавание";
    if (speed.c) text += " climb лазание";
    if (speed.b) text += " burrow копание";
    if ((creature.sn_ru && creature.sn_ru.length) || (creature.sn_en && creature.sn_en.length)) {
      text += " чувства senses зрение vision sight";
    }
    const synonyms = SYNONYMS[lang] || SYNONYMS.ru;
    for (const [key, forms] of Object.entries(synonyms)) {
      if (forms.some(form => text.includes(form))) text += " " + key + " " + forms.join(" ");
    }
    return text;
  }

  function byName(lang) {
    return (left, right) => {
      const a = lang === "ru" ? left.n_ru : left.n_en;
      const b = lang === "ru" ? right.n_ru : right.n_en;
      if (a < b) return -1;
      if (a > b) return 1;
      return 0;
    };
  }

  // Same answers as the bestiary page: category, words, exclusions, then sort.
  function searchCreatures(creatures, options) {
    const settings = options || {};
    const lang = settings.lang === "en" ? "en" : "ru";
    const cat = settings.cat || settings.tier || "all";
    const query = classifyQuery(settings.q || settings.query || "");
    let found = (creatures || []).filter(creature => {
      if (cat !== "all" && !categoriesFor(creature).includes(cat)) return false;
      const text = searchableText(creature, lang);
      if (query.negative.some(word => text.includes(word))) return false;
      return query.filters.every(word => text.includes(word));
    });
    if (query.sort.length) {
      const bounds = {};
      for (const key of query.sort) {
        let min = Infinity;
        let max = -Infinity;
        for (const creature of found) {
          const value = statValue(creature, key);
          if (value < min) min = value;
          if (value > max) max = value;
          creature._sortVals = creature._sortVals || {};
          creature._sortVals[key] = value;
        }
        bounds[key] = { min, max };
      }
      found.sort((left, right) => {
        let scoreLeft = 0;
        let scoreRight = 0;
        for (const key of query.sort) {
          const span = bounds[key].max - bounds[key].min;
          if (span > 0) {
            scoreLeft += (left._sortVals[key] - bounds[key].min) / span;
            scoreRight += (right._sortVals[key] - bounds[key].min) / span;
          }
        }
        if (Math.abs(scoreLeft - scoreRight) > 0.0001) return scoreRight - scoreLeft;
        return byName(lang)(left, right);
      });
    } else {
      found.sort(byName(lang));
    }
    return {
      sort: query.sort,
      filters: query.filters,
      negative: query.negative,
      beasts: found
    };
  }

  return { classifyQuery, categoriesFor, crValue, matchesLoose, searchCreatures, statValue };
});
