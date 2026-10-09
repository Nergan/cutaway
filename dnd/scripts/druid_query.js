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

  return { classifyQuery, categoriesFor, crValue, matchesLoose };
});
