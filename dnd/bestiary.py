"""Bestiary search shared with the druid helper page."""

from __future__ import annotations

import json
import re
from functools import cmp_to_key
from pathlib import Path

_DB = Path(__file__).parent / "static" / "db.json"
_CACHE: tuple[float, list[dict]] | None = None

TIERS = ("all", "fam", "lvl2", "lvl4", "lvl8")

_STAT_RULES = (
    ("st", ("скрытность", "скрыт", "stealth", "stealt")),
    ("pr", ("восприятие", "восприя", "perception", "percep")),
    ("dm", ("урон", "урона", "damage", "damag")),
    ("hp", ("хиты", "хитов", "хит", "хп", "hp")),
    ("ac", ("броня", "брони", "брон", "кд", "armor", "ac")),
    ("speed", ("скорость", "скорости", "скоростью", "speed", "speeds")),
    ("str", ("сила", "силы", "силе", "силу", "силой", "strength", "сил", "str")),
    ("dex", ("ловкость", "ловкости", "ловк", "лвк", "dexterity", "dex")),
    ("con", ("телосложение", "тело", "тел", "constitution", "con")),
)

_REFINE_RULES = (
    ("sp_w", ("ходьба", "ходьбы", "ходьбу", "ходьб", "walk")),
    ("sp_f", ("полет", "полета", "полету", "fly")),
    ("sp_s", ("плавание", "плавания", "плава", "swim")),
    ("sp_c", ("лазание", "лазания", "лазан", "climb")),
    ("sp_b", ("копание", "копания", "копан", "burrow")),
    ("sn_blind", ("слепое", "слепо", "blind")),
    ("sn_dark", ("темное", "темн", "dark")),
    ("sn_tremor", ("вибрация", "вибрации", "вибрац", "tremor")),
    ("sn_true", ("истинное", "истин", "true")),
    ("sn_any", ("чувства", "чувств", "зрение", "зрен", "senses", "sens", "vision", "sight")),
)

_SYNONYMS = {
    "ru": {
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
        "рой": ["рой", "рои", "стая"],
    },
    "en": {
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
        "swarm": ["flock", "school", "swarm"],
    },
}

_SENSE = {
    "blind": re.compile(r"(?:blind|слепо)[^\d]*(\d+)", re.IGNORECASE),
    "dark": re.compile(r"(?:dark|т[её]мн)[^\d]*(\d+)", re.IGNORECASE),
    "tremor": re.compile(r"(?:tremor|вибрац)[^\d]*(\d+)", re.IGNORECASE),
    "true": re.compile(r"(?:true|истин)[^\d]*(\d+)", re.IGNORECASE),
}
_TOKEN = re.compile(r"[.,;:!?()\[\]\"'«»]")


def load_beasts() -> list[dict]:
    global _CACHE
    stamp = _DB.stat().st_mtime
    if _CACHE and _CACHE[0] == stamp:
        return _CACHE[1]
    beasts = json.loads(_DB.read_text(encoding="utf-8"))
    _CACHE = (stamp, beasts)
    return beasts


def _matches_loose(word: str, form: str) -> bool:
    if not word or not form:
        return False
    if word == form:
        return True
    if len(form) >= 4 and word.startswith(form) and len(word) - len(form) <= 6:
        return True
    if len(word) >= 5 and form.startswith(word) and len(form) - len(word) <= 2:
        return True
    return False


def _match_rule(word: str, rules: tuple) -> str | None:
    for key, forms in rules:
        if any(_matches_loose(word, form) for form in forms):
            return key
    return None


def classify_query(query: str) -> dict:
    sort: list[str] = []
    filters: list[str] = []
    negative: list[str] = []
    seen: set[str] = set()
    text = str(query or "").replace("ё", "е").lower()
    for raw in text.split():
        minus = raw.startswith("-") and len(raw) > 1
        body = _TOKEN.sub("", raw[1:] if minus else raw)
        if not body:
            continue
        if minus:
            negative.append(body)
            continue
        stat = _match_rule(body, _STAT_RULES)
        if stat:
            if stat not in seen:
                seen.add(stat)
                sort.append(stat)
            continue
        filters.append(body)
        refine = _match_rule(body, _REFINE_RULES)
        if refine and refine not in seen:
            seen.add(refine)
            sort.append(refine)
    return {"sort": sort, "filters": filters, "negative": negative}


def cr_value(cr) -> float:
    if isinstance(cr, (int, float)) and not isinstance(cr, bool):
        return float(cr)
    text = str("" if cr is None else cr).strip()
    if not text:
        return float("nan")
    if "/" in text:
        num, den = text.split("/", 1)
        try:
            denominator = float(den)
            if not denominator:
                return float("nan")
            return float(num) / denominator
        except ValueError:
            return float("nan")
    try:
        return float(text)
    except ValueError:
        return float("nan")


def categories_for(creature: dict) -> list[str]:
    cats: list[str] = []
    if creature and creature.get("fam"):
        cats.append("fam")
    cr = cr_value(creature.get("cr") if creature else None)
    if cr != cr:
        return cats
    speed = (creature or {}).get("sp") or {}
    fly = float(speed.get("f") or 0) > 0
    swim = float(speed.get("s") or 0) > 0
    if cr <= 0.25 and not fly and not swim:
        cats.append("lvl2")
    if cr <= 0.5 and not fly:
        cats.append("lvl4")
    if cr <= 1:
        cats.append("lvl8")
    return cats


def _sense_distance(creature: dict, sense_type: str) -> int:
    pattern = _SENSE.get(sense_type)
    if not pattern:
        return -1
    senses = " ".join((creature.get("sn_ru") or []) + (creature.get("sn_en") or []))
    match = pattern.search(senses)
    return int(match.group(1)) if match else -1


def stat_value(creature: dict, key: str) -> float:
    speed = creature.get("sp") or {}
    if key == "speed":
        return max(speed.get("w") or 0, speed.get("f") or 0, speed.get("s") or 0, speed.get("c") or 0, speed.get("b") or 0)
    if key.startswith("sp_"):
        return speed.get(key.split("_", 1)[1]) or 0
    if key.startswith("sn_") and key != "sn_any":
        distance = _sense_distance(creature, key.split("_", 1)[1])
        return distance if distance > 0 else 0
    if key == "sn_any":
        return 1 if (creature.get("sn_ru") or creature.get("sn_en")) else 0
    value = creature.get(key)
    if isinstance(value, bool) or value is None:
        return 0
    if isinstance(value, (int, float)):
        return value
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _searchable(creature: dict, lang: str) -> str:
    name = creature.get("n_ru") if lang == "ru" else creature.get("n_en")
    size = creature.get("sz_ru") if lang == "ru" else creature.get("sz_en")
    tags = (creature.get("tg_ru") if lang == "ru" else creature.get("tg_en")) or []
    habitats = (creature.get("hb_ru") if lang == "ru" else creature.get("hb_en")) or []
    text = " ".join(
        str(part or "")
        for part in (
            name,
            creature.get("n_en"),
            size,
            creature.get("cr"),
            creature.get("src"),
            creature.get("src_ru"),
            " ".join(tags),
            " ".join(habitats),
            " ".join(creature.get("sn_ru") or []),
            " ".join(creature.get("sn_en") or []),
        )
    ).replace("ё", "е").lower()
    speed = creature.get("sp") or {}
    if speed.get("w"):
        text += " walk ходьба ходьбу"
    if speed.get("f"):
        text += " fly полет полёт flyby"
    if speed.get("s"):
        text += " swim плавание"
    if speed.get("c"):
        text += " climb лазание"
    if speed.get("b"):
        text += " burrow копание"
    if creature.get("sn_ru") or creature.get("sn_en"):
        text += " чувства senses зрение vision sight"
    for key, forms in _SYNONYMS.get(lang, _SYNONYMS["ru"]).items():
        if any(form in text for form in forms):
            text += " " + key + " " + " ".join(forms)
    return text


def _by_name(lang: str):
    def compare(left: dict, right: dict) -> int:
        a = left.get("n_ru") if lang == "ru" else left.get("n_en")
        b = right.get("n_ru") if lang == "ru" else right.get("n_en")
        a = "" if a is None else str(a)
        b = "" if b is None else str(b)
        if a < b:
            return -1
        if a > b:
            return 1
        return 0

    return compare


def search_beasts(creatures: list[dict], *, q: str = "", cat: str = "all", lang: str = "ru") -> dict:
    language = "en" if lang == "en" else "ru"
    tier = cat or "all"
    query = classify_query(q)
    found = []
    for creature in creatures or []:
        if tier != "all" and tier not in categories_for(creature):
            continue
        text = _searchable(creature, language)
        if any(word in text for word in query["negative"]):
            continue
        if any(word not in text for word in query["filters"]):
            continue
        found.append(creature)
    if query["sort"]:
        bounds: dict[str, tuple[float, float]] = {}
        scored: list[tuple[dict, dict[str, float]]] = []
        for creature in found:
            values = {key: stat_value(creature, key) for key in query["sort"]}
            scored.append((creature, values))
            for key, value in values.items():
                low, high = bounds.get(key, (float("inf"), float("-inf")))
                bounds[key] = (min(low, value), max(high, value))

        def total_of(values: dict[str, float]) -> float:
            total = 0.0
            for key in query["sort"]:
                low, high = bounds[key]
                span = high - low
                if span > 0:
                    total += (values[key] - low) / span
            return total

        def compare(left, right) -> int:
            gap = total_of(left[1]) - total_of(right[1])
            if abs(gap) > 0.0001:
                return -1 if gap > 0 else 1
            return _by_name(language)(left[0], right[0])

        found = [creature for creature, _values in sorted(scored, key=cmp_to_key(compare))]
    else:
        found = sorted(found, key=lambda creature: (creature.get("n_ru") if language == "ru" else creature.get("n_en")) or "")
    beasts = []
    for creature in found:
        record = {key: value for key, value in creature.items() if not str(key).startswith("_")}
        record["categories"] = categories_for(creature)
        beasts.append(record)
    return {
        "sort": query["sort"],
        "filters": query["filters"],
        "negative": query["negative"],
        "beasts": beasts,
    }
