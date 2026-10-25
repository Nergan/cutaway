"""Expand elementary tag aliases and hover descriptions.

Classified search keeps one controlled vocabulary. A phrase a person types,
such as femdom or princess, is an alternative label on each elementary tag it
is made of. The query is a union of those labels. Nothing is inferred later.

Age, place, and sexual-preference tags carry the sentinel aliases age,
location, and fetish. Those stay out of the tag cloud and still answer search.

Run from the repo: python netlazy/tools/expand_tags.py
The script is idempotent.
"""

import re
from pathlib import Path

import yaml

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tag_blurbs import blurb

_LABEL_WORD = re.compile(r"[^\W_]+", re.UNICODE)

PATH = Path(__file__).resolve().parents[1] / "tags.yaml"
LANGS = ("en", "ru", "pt", "zh", "ja", "ko")
STOP = {
    "a", "an", "the", "of", "and", "or", "for", "to", "in", "on", "at", "by",
    "de", "da", "do", "em", "na", "no", "um", "uma", "os", "as",
    "и", "в", "на", "с", "по", "от", "за", "не", "но", "или",
}
SENTINELS = {"age", "location", "fetish"}

# A phrase fans out onto every elementary tag it is made of.
RINGS = {
    "femdom": ["girl", "dominant"],
    "femdomme": ["girl", "dominant"],
    "female domination": ["girl", "dominant"],
    "female dominant": ["girl", "dominant"],
    "domme": ["girl", "dominant"],
    "mistress": ["girl", "dominant"],
    "goddess": ["girl", "dominant"],
    "findom": ["girl", "dominant"],
    "фемдом": ["girl", "dominant"],
    "госпожа": ["girl", "dominant"],
    "домина": ["girl", "dominant"],
    "maledom": ["guy", "dominant"],
    "male domination": ["guy", "dominant"],
    "master": ["guy", "dominant"],
    "господин": ["guy", "dominant"],
    "gentle femdom": ["girl", "dominant"],
    "soft femdom": ["girl", "dominant"],
    "soft dom": ["dominant", "soft"],
    "princess": ["girl", "cute"],
    "princesa": ["girl", "cute"],
    "принцесса": ["girl", "cute"],
    "公主": ["girl", "cute"],
    "プリンセス": ["girl", "cute"],
    "공주님": ["girl", "cute"],
    "kitten": ["cats", "cute"],
    "kitty": ["cats", "cute"],
    "kittens": ["cats", "cute"],
    "котёнок": ["cats", "cute"],
    "котенок": ["cats", "cute"],
    "котик": ["cats", "cute"],
    "angel": ["cute"],
    "ангел": ["cute"],
    "ангелочек": ["cute"],
    "good girl": ["girl", "submissive"],
    "good boy": ["guy", "submissive"],
    "babygirl": ["girl", "submissive", "cute"],
    "baby girl": ["girl", "submissive", "cute"],
    "daddy dom": ["guy", "dominant", "daddy fetish"],
    "mommy dom": ["girl", "dominant", "mommy fetish"],
    "mommy domme": ["girl", "dominant", "mommy fetish"],
    "brat tamer": ["dominant", "brat"],
    "kitten play": ["petplay", "cats"],
    "puppy play": ["petplay", "dogs"],
    "puppy": ["dogs", "cute"],
    "pup": ["dogs", "cute"],
    "щенок": ["dogs", "cute"],
    "catgirl": ["girl", "cats", "cute"],
    "cat girl": ["girl", "cats", "cute"],
    "neko": ["cats", "cute"],
    "неко": ["cats", "cute"],
    "dog person": ["has a dog", "dogs"],
    "собачник": ["has a dog", "dogs"],
    "twink": ["guy", "slim"],
    "твинк": ["guy", "slim"],
    "bear": ["guy", "chubby"],
    "медведь": ["guy", "chubby"],
    "milf": ["mommy fetish"],
    "cougar": ["mommy fetish"],
    "милфа": ["mommy fetish"],
    "dilf": ["daddy fetish"],
    "дилф": ["daddy fetish"],
    "feet": ["foot fetish"],
    "toes": ["foot fetish"],
    "foot": ["foot fetish"],
    "ноги": ["foot fetish"],
    "ступни": ["foot fetish"],
    "facesit": ["facesitting"],
    "bbw": ["chubby"],
    "plus size": ["chubby"],
    "thicc": ["chubby", "curvy"],
    "пышка": ["chubby"],
    "vanilla": ["soft"],
    "gentle": ["soft"],
    "нежный": ["soft"],
    "fwb": ["sex-only relationship"],
    "hookup": ["sex-only relationship"],
    "one night stand": ["sex-only relationship"],
    "ons": ["sex-only relationship"],
    "friends with benefits": ["sex-only relationship"],
    "секс на одну ночь": ["sex-only relationship"],
    "ltr": ["serious relationship"],
    "long term": ["serious relationship"],
    "long-term": ["serious relationship"],
    "marriage": ["serious relationship"],
    "wife": ["serious relationship", "girl"],
    "husband": ["serious relationship", "guy"],
    "жена": ["serious relationship", "girl"],
    "муж": ["serious relationship", "guy"],
    "just chatting": ["casual chat"],
    "small talk": ["casual chat"],
    "болтовня": ["casual chat"],
    "sexting": ["dirty talk / horny"],
    "horny": ["dirty talk / horny"],
    "nsfw": ["dirty talk / horny"],
    "virt": ["dirty talk / horny"],
    "вирт": ["dirty talk / horny"],
    "секстинг": ["dirty talk / horny"],
    "gym": ["athletic", "healthy lifestyle"],
    "fitness": ["athletic", "healthy lifestyle"],
    "качалка": ["athletic", "healthy lifestyle"],
    "фитнес": ["athletic"],
    "bookworm": ["reading"],
    "книжный": ["reading"],
    "traveler": ["travelling"],
    "traveller": ["travelling"],
    "travel": ["travelling"],
    "путешествия": ["travelling"],
    "gamer": ["computer games"],
    "геймер": ["computer games"],
    "weeb": ["anime"],
    "otaku": ["anime"],
    "отаку": ["anime"],
    "kpop": ["k-pop"],
    "k pop": ["k-pop"],
    "k-pop stan": ["k-pop"],
    "кейпоп": ["k-pop"],
    "metalhead": ["metal music"],
    "металлист": ["metal music"],
    "lofi": ["lo-fi / chill"],
    "lo fi": ["lo-fi / chill"],
    "лоуфай": ["lo-fi / chill"],
    "techwear": ["cyberpunk / techwear"],
    "теквир": ["cyberpunk / techwear"],
    "coder": ["coding", "programming"],
    "developer": ["coding", "programming"],
    "программист": ["coding", "programming"],
    "кодер": ["coding"],
    "programmer": ["programming"],
    "pythonista": ["python"],
    "питонист": ["python"],
    "lol": ["league of legends"],
    "league": ["league of legends"],
    "лига легенд": ["league of legends"],
    "dota": ["dota 2"],
    "дота": ["dota 2"],
    "cs2": ["counter-strike 2"],
    "csgo": ["counter-strike 2"],
    "counter strike": ["counter-strike 2"],
    "контра": ["counter-strike 2"],
    "genshin": ["genshin impact"],
    "геншин": ["genshin impact"],
    "zzz": ["zenless zone zero"],
    "hsr": ["honkai: star rail"],
    "star rail": ["honkai: star rail"],
    "хонкай": ["honkai: star rail"],
    "wuwa": ["wuthering waves"],
    "вува": ["wuthering waves"],
    "aot": ["attack on titan"],
    "snk": ["attack on titan"],
    "атака титанов": ["attack on titan"],
    "jjk": ["jujutsu kaisen"],
    "магическая битва": ["jujutsu kaisen"],
    "kimetsu": ["demon slayer"],
    "клинок": ["demon slayer"],
    "evangelion": ["neon genesis evangelion"],
    "eva": ["neon genesis evangelion"],
    "евангелион": ["neon genesis evangelion"],
    "jojo": ["jojo's bizarre adventure"],
    "джоджо": ["jojo's bizarre adventure"],
    "frieren": ["sousou no frieren"],
    "фрирен": ["sousou no frieren"],
    "csm": ["chainsaw man"],
    "человек-бензопила": ["chainsaw man"],
    "bsd": ["bungou stray dogs"],
    "бродячие псы": ["bungou stray dogs"],
    "steins gate": ["steins;gate"],
    "врата штейна": ["steins;gate"],
    "kimi no na wa": ["your name"],
    "твоё имя": ["your name"],
    "твое имя": ["your name"],
    "hazbin": ["hazbin hotel"],
    "хазбин": ["hazbin hotel"],
    "elden": ["elden ring"],
    "элден": ["elden ring"],
    "dnd": ["tabletop rpgs"],
    "d&d": ["tabletop rpgs"],
    "ttrpg": ["tabletop rpgs"],
    "настолки": ["tabletop rpgs", "board games"],
    "boardgame": ["board games"],
    "настольные игры": ["board games"],
    "movies": ["cinema"],
    "films": ["cinema"],
    "кино": ["cinema"],
    "фильмы": ["cinema"],
    "soccer": ["sports"],
    "basketball": ["sports"],
    "футбол": ["sports"],
    "photographer": ["photography"],
    "фотограф": ["photography"],
    "hiker": ["hiking"],
    "походник": ["hiking"],
    "yogi": ["yoga"],
    "йог": ["yoga"],
    "cyclist": ["cycling"],
    "велосипедист": ["cycling"],
    "swimmer": ["swimming"],
    "пловец": ["swimming"],
    "barista": ["coffee"],
    "coffee lover": ["coffee"],
    "кофеман": ["coffee"],
    "hiring": ["employer", "hr"],
    "recruiter": ["employer", "hr"],
    "рекрутер": ["hr"],
    "нанимаю": ["employer"],
    "job seeker": ["candidate", "job"],
    "ищу работу": ["candidate", "job"],
    "соискатель": ["candidate"],
    "founder": ["startapp"],
    "startup": ["startapp"],
    "фаундер": ["startapp"],
    "стартапер": ["startapp"],
    "internship": ["unpaid", "job"],
    "стажировка": ["unpaid", "job"],
    "shibari": ["bondage"],
    "rope": ["bondage"],
    "шибари": ["bondage"],
    "верёвки": ["bondage"],
    "веревки": ["bondage"],
    "sadist": ["sadomasochism", "dominant"],
    "садист": ["sadomasochism", "dominant"],
    "masochist": ["sadomasochism", "submissive"],
    "мазохист": ["sadomasochism", "submissive"],
    "bdsm": ["bondage", "sadomasochism", "dominant", "submissive"],
    "бдсм": ["bondage", "sadomasochism", "dominant", "submissive"],
    "latex": ["latex/leather"],
    "leather": ["latex/leather"],
    "rubber": ["latex/leather"],
    "латекс": ["latex/leather"],
    "кожа": ["latex/leather"],
    "roleplay": ["roleplay (fetish)", "cosplay"],
    "ролевая": ["roleplay (fetish)", "cosplay"],
    "cosplayer": ["cosplay"],
    "косплеер": ["cosplay"],
    "tomboyish": ["tomboy", "girl"],
    "пацанка": ["tomboy", "girl"],
    "sapphic": ["lesbian", "girl"],
    "wlw": ["lesbian", "girl"],
    "mlm": ["gay", "guy"],
    "bisexual": ["bi"],
    "бисексуал": ["bi"],
    "hetero": ["straight"],
    "гетеро": ["straight"],
    "натурал": ["straight"],
    "top": ["dominant"],
    "bottom": ["submissive"],
    "verse": ["switch"],
    "верс": ["switch"],
    "blond": ["blonde"],
    "blonde hair": ["blonde"],
    "блонд": ["blonde"],
    "блондинка": ["blonde"],
    "redhead": ["redhead"],
    "ginger": ["redhead"],
    "рыжая": ["redhead"],
    "рыжий": ["redhead"],
    "brunette hair": ["brunette"],
    "брюнетка": ["brunette"],
    "tattoo": ["tattoos"],
    "inked": ["tattoos"],
    "татуировки": ["tattoos"],
    "татуировка": ["tattoos"],
    "piercing": ["piercings"],
    "пирсинг": ["piercings"],
    "glasses": ["glasses"],
    "очкарик": ["glasses"],
    "в очках": ["glasses"],
    "tall": ["tall"],
    "высокий рост": ["tall"],
    "short king": ["short", "guy"],
    "short girl": ["short", "girl"],
    "невысокая": ["short", "girl"],
    "невысокий": ["short"],
    "skinny": ["slim"],
    "худой": ["slim"],
    "худенькая": ["slim"],
    "muscular": ["athletic"],
    "накачанный": ["athletic"],
    "introverted": ["introvert", "shy"],
    "интроверт": ["introvert", "shy"],
    "застенчивый": ["shy"],
    "стеснительный": ["shy"],
    "extroverted": ["extrovert"],
    "экстраверт": ["extrovert"],
    "sweet": ["kind", "cute"],
    "добрый": ["kind"],
    "добрая": ["kind"],
    "nerd": ["smart"],
    "ботан": ["smart"],
    "умный": ["smart"],
    "умная": ["smart"],
    "adorable": ["cute"],
    "няшка": ["cute"],
    "кавай": ["cute"],
    "kawaii": ["cute"],
    "pretty": ["cute"],
    "красивая": ["cute", "girl"],
    "красивый": ["cute"],
    "smoker": ["smoker (cigarettes)"],
    "курю": ["smoker (cigarettes)"],
    "курящий": ["smoker (cigarettes)"],
    "non-smoker": ["non-smoker (cigarettes)"],
    "не курю": ["non-smoker (cigarettes)"],
    "vape": ["vaper"],
    "вейп": ["vaper"],
    "sober": ["doesn't drink alcohol"],
    "teetotal": ["doesn't drink alcohol"],
    "трезвенник": ["doesn't drink alcohol"],
    "не пью": ["doesn't drink alcohol"],
    "drinker": ["drinks alcohol"],
    "alcohol": ["drinks alcohol"],
    "пью": ["drinks alcohol"],
    "ldr": ["online"],
    "long distance": ["online"],
    "на расстоянии": ["online"],
    "remote": ["online"],
    "curves": ["curvy"],
    "фигура": ["curvy"],
    "пышная": ["curvy"],
    "funny": ["funny"],
    "смешной": ["funny"],
    "смешная": ["funny"],
    "юмор": ["funny"],
    "humor": ["funny"],
    "humour": ["funny"],
    "praise kink": ["praise"],
    "похвала": ["praise"],
    "degradation kink": ["degradation"],
    "унижение": ["degradation"],
    "humiliation": ["degradation"],
    "pet play": ["petplay"],
    "петплей": ["petplay"],
    "брэт": ["brat"],
    "bratty": ["brat"],
    "свитч": ["switch"],
    "call of the night": ["call of rhe night"],
    "yofukashi": ["call of rhe night"],
}

PLACE_ALIASES = {
    "united kingdom": ["uk", "britain", "england", "great britain", "британия", "англия"],
    "united states": ["usa", "us", "america", "сша", "америка", "штаты"],
    "south korea": ["korea", "корея", "южная корея"],
    "united arab emirates": ["uae", "оаэ", "эмираты"],
    "netherlands": ["holland", "голландия", "нидерланды"],
    "czech republic": ["czechia", "чехия"],
    "ho chi minh city": ["saigon", "сайгон"],
    "saint petersburg": ["spb", "питер", "петербург", "спб"],
    "new york": ["nyc", "нью-йорк"],
    "los angeles": ["la", "лос-анджелес"],
    "san francisco": ["sf", "сан-франциско"],
    "rio de janeiro": ["rio", "рио"],
    "são paulo": ["sao paulo", "сан-паулу"],
    "mexico city": ["cdmx"],
    "hong kong": ["hk"],
}

MBTI = [
    "intj", "intp", "entj", "entp", "infj", "infp", "enfj", "enfp",
    "istj", "isfj", "estj", "esfj", "istp", "isfp", "estp", "esfp",
]

def tag(en, ru, pt, zh, ja, ko, aliases):
    return {
        "en": en,
        "ru": ru,
        "pt": pt,
        "zh": zh,
        "ja": ja,
        "ko": ko,
        "aliases": aliases,
    }


NEW_TAGS = [
    tag("cute", "милый", "fofo", "可愛", "かわいい", "귀여움", ["cute", "adorable", "pretty", "kawaii", "милый", "милая", "няшный", "кавай", "fofo", "fofa"]),
    tag("shy", "застенчивый", "tímido", "害羞", "人見知り", "수줍음", ["shy", "застенчивый", "стеснительный", "tímido", "tímida"]),
    tag("funny", "смешной", "engraçado", "幽默", "面白い", "유머", ["funny", "смешной", "смешная", "юмор", "engraçado", "humor"]),
    tag("kind", "добрый", "gentil", "善良", "優しい", "다정", ["kind", "добрый", "добрая", "gentil", "nice"]),
    tag("smart", "умный", "inteligente", "聰明", "賢い", "똑똑", ["smart", "умный", "умная", "inteligente", "clever"]),
    tag("athletic", "спортивный", "atlético", "健美", "アスリート", "운동체형", ["athletic", "спортивный", "спортивная", "atlético", "fit"]),
    tag("slim", "стройный", "magro", "纖細", "スリム", "슬림", ["slim", "стройный", "стройная", "magro", "slender"]),
    tag("tall", "высокий", "alto", "高個", "高身長", "큰키", ["tall", "высокий", "высокая", "alto", "alta"]),
    tag("short", "невысокий", "baixo", "嬌小", "低身長", "작은키", ["short", "невысокий", "невысокая", "baixo", "baixa"]),
    tag("blonde", "блондин", "loiro", "金髮", "金髪", "금발", ["blonde", "blond", "блондин", "блондинка", "loiro", "loira"]),
    tag("brunette", "брюнет", "moreno", "深髮", "黒髪", "흑발", ["brunette", "брюнет", "брюнетка", "moreno", "morena"]),
    tag("redhead", "рыжий", "ruivo", "紅髮", "赤毛", "적발", ["redhead", "ginger", "рыжий", "рыжая", "ruivo", "ruiva"]),
    tag("tattoos", "тату", "tatuagens", "刺青", "タトゥー", "타투", ["tattoos", "tattoo", "тату", "татуировки", "tatuagens", "inked"]),
    tag("piercings", "пирсинг", "piercings", "穿刺", "ピアス", "피어싱", ["piercings", "piercing", "пирсинг"]),
    tag("glasses", "очки", "óculos", "眼鏡", "眼鏡", "안경", ["glasses", "очки", "óculos"]),
    tag("curvy", "пышные формы", "curvilíneo", "曲線", "グラマー", "글래머", ["curvy", "пышные формы", "curvilíneo", "curves"]),
    tag("switch", "свитч", "switch", "切換", "スイッチ", "스위치", ["switch", "свитч", "verse", "fetish"]),
    tag("brat", "брэт", "brat", "調皮受", "ブラット", "브랫", ["brat", "брэт", "bratty", "fetish"]),
    tag("petplay", "петплей", "petplay", "寵物扮演", "ペットプレイ", "펫플레이", ["petplay", "петплей", "pet play", "fetish"]),
    tag("praise", "похвала", "elogio", "誇獎", "褒め", "칭찬", ["praise", "похвала", "praise kink", "fetish"]),
    tag("degradation", "унижение", "degradação", "貶低", "貶め", "모욕", ["degradation", "унижение", "humiliation", "fetish"]),
]


class Quoted(str):
    pass


class Flow(list):
    pass


def quoted_rep(dumper, data):
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style='"')


def flow_rep(dumper, data):
    return dumper.represent_sequence("tag:yaml.org,2002:seq", data, flow_style=True)


yaml.add_representer(Quoted, quoted_rep)
yaml.add_representer(Flow, flow_rep)


def en_of(entry):
    name = entry.get("name")
    if isinstance(name, dict):
        return str(name.get("en") or "")
    return str(name or "")


def i18n_of(entry):
    name = entry.get("name")
    if not isinstance(name, dict):
        return {"en": str(name or "")}
    return {lang: str(name.get(lang) or "") for lang in LANGS}


def aliases_of(entry):
    name = entry.get("name")
    raw = name.get("aliases") if isinstance(name, dict) else entry.get("aliases")
    if not isinstance(raw, list):
        return []
    return [str(item) for item in raw if str(item).strip()]



def plain(text):
    text = " ".join(str(text).split()).lower()
    return text.strip(" .。．!！?？,，、:：")



def describe(name, aliases, i18n):
    raw = blurb(name, i18n, aliases)
    return {lang: plain(text) for lang, text in raw.items()}


def age_aliases(name):
    if not name.endswith(" years old"):
        return []
    number = name.split()[0]
    if not number.isdigit():
        return []
    n = int(number)
    extra = [f"{n}yo", f"{n} y.o.", f"{n} y/o", f"{number} лет"]
    if n in (18, 19):
        extra += ["teen", "teenager", "подросток"]
    if 20 <= n <= 29:
        extra += ["twenties", "двадцатые"]
    if 20 <= n <= 23:
        extra += ["early twenties"]
    if 24 <= n <= 26:
        extra += ["mid twenties"]
    if 27 <= n <= 29:
        extra += ["late twenties"]
    if 30 <= n <= 39:
        extra += ["thirties", "тридцатые"]
    if 40 <= n <= 49:
        extra += ["forties", "сороковые"]
    if n == 50:
        extra += ["fifties", "пятьдесят"]
    if n >= 35:
        extra += ["milf", "cougar", "dilf", "mature"]
    return extra


def language_aliases(name, i18n):
    if "(native/fluent)" in name:
        lang = name.split(" (", 1)[0]
        extra = [lang, f"fluent {lang}", f"native {lang}", f"speaks {lang}"]
        ru = i18n.get("ru")
        if ru:
            extra += [f"носитель {ru}", f"говорю {ru}"]
        return extra
    if name.startswith("learning "):
        lang = name[len("learning "):]
        extra = [f"learning {lang}", f"studying {lang}", f"{lang} learner"]
        ru = i18n.get("ru")
        if ru:
            extra.append(f"учу {ru}")
        return extra
    return []


def usable(text, allow_sentinel=False):
    cleaned = " ".join(str(text).split())
    if len(cleaned) < 2:
        return ""
    if cleaned.lower() in STOP:
        return ""
    if cleaned.lower() in SENTINELS and not allow_sentinel:
        return ""
    return cleaned


def prune_name_fragments(name, aliases):
    """Drop a one-word alias that only repeats a word of a longer name.

    Otherwise that fragment becomes its own label, and a shorter prefix of it
    (angel inside angeles) answers for the place.
    """
    name_words = _LABEL_WORD.findall(name.lower())
    if len(name_words) < 2:
        return aliases
    pieces = set(name_words)
    kept = []
    for alias in aliases:
        words = _LABEL_WORD.findall(alias.lower())
        if len(words) == 1 and words[0] in pieces and words[0] not in SENTINELS:
            continue
        kept.append(alias)
    return kept


def dedupe(items):
    seen = set()
    out = []
    for item in items:
        text = str(item).strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out


def set_name_fields(entry, aliases, desc):
    name = entry["name"]
    if not isinstance(name, dict):
        entry["name"] = {"en": str(name), "desc": desc, "aliases": aliases}
        return
    name.pop("aliases", None)
    name.pop("desc", None)
    name["desc"] = desc
    name["aliases"] = aliases


def new_entry(spec):
    name = {lang: spec[lang] for lang in LANGS}
    entry = {"name": name}
    set_name_fields(entry, list(spec["aliases"]), {})
    return entry


def quote(obj):
    if isinstance(obj, dict):
        return {key: quote(value) for key, value in obj.items()}
    if isinstance(obj, list):
        if obj and all(not isinstance(item, (dict, list)) for item in obj):
            return Flow([quote(item) for item in obj])
        return [quote(item) for item in obj]
    if isinstance(obj, str):
        return Quoted(obj)
    return obj


def main():
    document = yaml.safe_load(PATH.read_text(encoding="utf-8"))
    tags = document["tags"]
    known = {en_of(entry) for entry in tags}
    for spec in NEW_TAGS:
        if spec["en"] not in known:
            tags.append(new_entry(spec))
            known.add(spec["en"])

    by_name = {}
    for entry in tags:
        by_name.setdefault(en_of(entry), []).append(entry)

    missing = sorted({target for targets in RINGS.values() for target in targets if target not in by_name})
    if missing:
        raise SystemExit("missing elementary tags: " + ", ".join(missing))

    additions = {name: [] for name in by_name}
    for phrase, targets in RINGS.items():
        for target in targets:
            additions[target].append(phrase)
    for name, phrases in PLACE_ALIASES.items():
        if name in additions:
            additions[name].extend(phrases)
    if "mbti" in additions:
        additions["mbti"].extend(MBTI)

    for entry in tags:
        name = en_of(entry)
        i18n = i18n_of(entry)
        current = aliases_of(entry)
        extra = []
        extra.extend(additions.get(name, []))
        extra.extend(age_aliases(name))
        extra.extend(language_aliases(name, i18n))
        for lang in LANGS:
            if i18n.get(lang):
                extra.append(i18n[lang])
        allow = "fetish" in {item.lower() for item in current} or "fetish" in {item.lower() for item in extra}
        cleaned = []
        for item in extra:
            text = usable(item, allow_sentinel=allow and str(item).lower() == "fetish")
            if text:
                cleaned.append(text)
        aliases = prune_name_fragments(name, dedupe(current + cleaned))
        if name == "soft":
            aliases = [item for item in aliases if item.lower() not in {"gentle femdom", "soft femdom"}]
        desc = describe(name, aliases, i18n)
        set_name_fields(entry, aliases, desc)

    dumped = yaml.dump(
        quote(document),
        allow_unicode=True,
        sort_keys=False,
        width=10**6,
        default_flow_style=False,
    )
    if not dumped.endswith("\n"):
        dumped += "\n"
    PATH.write_text(dumped, encoding="utf-8", newline="\n")
    print(f"tags={len(tags)} path={PATH}")


if __name__ == "__main__":
    main()
