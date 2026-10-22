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


def six(en, ru, pt, zh, ja, ko):
    return {"en": en, "ru": ru, "pt": pt, "zh": zh, "ja": ja, "ko": ko}


TOOLS = {
    "coding", "programming", "vibe coding", "python", "javascript", "typescript",
    "c++", "rust", "go", "sql", "docker", "kubernetes", "git", "blender", "maya",
    "3ds max", "zbrush", "premiere pro", "davinci resolve", "after effects",
    "final cut pro", "java", "kotlin", "swift", "c#", "php", "ruby", "html/css",
    "linux", "bash/shell", "aws", "google cloud", "azure", "nginx", "postgresql",
    "mongodb", "redis", "prometheus", "grafana", "cinema 4d", "houdini",
    "solidworks", "autocad", "sony vegas", "avid media composer", "capcut",
    "premiere rush", "scala", "haskell", "clojure", "elixir", "erlang", "dart",
    "zig", "objective-c", "perl", "r language", "cobol", "fortran", "lisp",
    "terraform", "ansible", "jenkins", "ci/cd", "apache kafka", "rabbitmq",
    "elasticsearch", "kibana", "logstash", "docker compose", "helm", "cloudflare",
    "graphql", "grpc", "sketchup", "revit", "rhino 3d", "modo", "lightwave",
    "fusion 360", "tinkercad", "hitfilm", "lightworks", "shotcut", "imovie",
    "kdenlive", "camtasia", "3d modeling", "it ai dev", "art ai dev", "media ai dev",
    "ui/ux design", "qa testing", "product management", "drawing",
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


CUSTOM = {
    "online": six("talks online", "общается онлайн", "fala online", "線上聊", "ネットで話す", "온라인으로 대화"),
    "serious relationship": six("wants a real relationship", "хочет серьёзные отношения", "quer um relacionamento sério", "想認真交往", "真剣な付き合いがいい", "진지한 연애를 원함"),
    "casual relationship": six("something easy, no heavy promises", "легко, без обязательств", "leve, sem compromisso", "輕鬆就好", "軽くていい", "가볍게"),
    "sex-only relationship": six("just sex", "только секс", "só sexo", "只是性", "セックスだけ", "섹스만"),
    "one-off chat": six("one chat and that's it", "один раз поболтать", "uma conversa só", "聊一次就好", "一回だけ話す", "한 번만 대화"),
    "dirty talk / horny": six("horny talk", "пошлый разговор", "papo safado", "色色的聊天", "えっちな話", "야한 대화"),
    "casual chat": six("just chatting", "просто поболтать", "só bater papo", "隨便聊聊", "ただ雑談", "그냥 수다"),
    "networking": six("for work contacts", "для работы и связей", "para contatos de trabalho", "找工作人脈", "仕事の人脈", "일 인맥"),
    "guy": six("a guy", "парень", "um cara", "男生", "男", "남자"),
    "girl": six("a girl", "девушка", "uma mina", "女生", "女", "여자"),
    "straight": six("into the other gender", "гетеро", "hétero", "異性戀", "異性好き", "이성애"),
    "gay": six("a guy into guys", "гей", "gay", "男同", "ゲイ", "게이"),
    "lesbian": six("a girl into girls", "лесбиянка", "lésbica", "女同", "レズ", "레즈비언"),
    "bi": six("into more than one gender", "би", "bi", "雙性戀", "バイ", "양성애"),
    "asexual": six("little or no sexual attraction", "секс почти не тянет", "quase sem atração sexual", "沒什麼性慾", "性的な惹かれが薄い", "성적 끌림이 거의 없음"),
    "submissive": six("likes to submit", "любит подчиняться", "gosta de se submeter", "喜歡服從", "従うのが好き", "복종하는 게 좋음"),
    "dominant": six("likes to dominate", "любит доминировать", "gosta de dominar", "喜歡主導", "支配するのが好き", "지배하는 게 좋음"),
    "soft": six("gentle, nothing rough", "мягко, без жёсткости", "suave, sem dureza", "溫柔不粗暴", "優しくて激しくない", "부드럽고 거칠지 않음"),
    "facesitting": six("sitting on a face", "сидеть на лице", "sentar no rosto", "坐臉上", "顔の上に座る", "얼굴 위에 앉기"),
    "foot fetish": six("into feet", "нравятся ноги", "curte pés", "喜歡腳", "足が好き", "발을 좋아함"),
    "chubby": six("into bigger soft bodies", "нравятся пышные", "curte corpos maiores", "喜歡肉肉的", "ぽっちゃりが好き", "통통한 몸을 좋아함"),
    "vore": six("swallowing fantasy", "фантазия про глотание", "fantasia de engolir", "吞食幻想", "飲み込む空想", "삼키는 상상"),
    "trampling": six("stepping on someone", "топтание", "pisar em alguém", "踩人", "踏みつけ", "밟기"),
    "mommy fetish": six("into mommies", "нравятся мамочки", "curte mamães", "喜歡媽媽型", "ママが好き", "마미를 좋아함"),
    "daddy fetish": six("into daddies", "нравятся папочки", "curte papais", "喜歡爸爸型", "パパが好き", "대디를 좋아함"),
    "spitting": six("spit and saliva", "слюна и плевки", "saliva e cuspe", "唾液", "唾", "침"),
    "scaly": six("scales and reptiles", "чешуя и рептилии", "escamas", "鱗片", "鱗", "비늘"),
    "white skin": six("light skin", "светлая кожа", "pele clara", "淺膚色", "明るい肌", "밝은 피부"),
    "black skin": six("dark skin", "тёмная кожа", "pele escura", "深膚色", "暗い肌", "어두운 피부"),
    "dark skin": six("brown skin", "смуглая кожа", "pele morena", "棕色皮膚", "褐色の肌", "갈색 피부"),
    "asian": six("asian look", "азиатская внешность", "aparência asiática", "亞洲外表", "アジア系の見た目", "아시아 외모"),
    "latin": six("latin look", "латинская внешность", "aparência latina", "拉丁外表", "ラテン系の見た目", "라틴 외모"),
    "belly inflation": six("a swelling belly", "раздутый живот", "barriga inchando", "肚子脹起來", "お腹が膨らむ", "배가 부풂"),
    "bondage": six("tying someone up", "связывание", "amarrar", "捆綁", "縛る", "묶기"),
    "sadomasochism": six("pain, if both want it", "боль, если оба хотят", "dor, se os dois querem", "雙方想要的痛", "合意の痛み", "서로 원하는 고통"),
    "latex/leather": six("latex, leather, rubber", "латекс, кожа, резина", "látex, couro, borracha", "乳膠皮革橡膠", "ラテックスや革", "라텍스, 가죽, 고무"),
    "roleplay (fetish)": six("playing a character in bed", "ролевая в постели", "interpretar alguém na cama", "床上角色扮演", "ベッドで役を演じる", "침대에서 역할극"),
    "tomboy": six("a boyish girl", "девушка-пацанка", "mina com jeito de moleque", "男孩子氣的女生", "ボーイッシュな女", "보이시한 여자"),
    "introvert": six("an introvert", "интроверт", "introvertido", "內向", "内向", "내향"),
    "extrovert": six("an extrovert", "экстраверт", "extrovertido", "外向", "外向", "외향"),
    "cute": six("cute", "милый", "fofo", "可愛", "かわいい", "귀여움"),
    "shy": six("shy", "стесняется", "tímido", "害羞", "人見知り", "수줍음"),
    "funny": six("funny", "смешной", "engraçado", "好笑", "面白い", "웃김"),
    "kind": six("kind", "добрый", "gentil", "善良", "優しい", "다정함"),
    "smart": six("smart", "умный", "inteligente", "聰明", "賢い", "똑똑함"),
    "athletic": six("sporty", "спортивный", "esportivo", "愛運動", "スポーツ体型", "운동하는 체형"),
    "slim": six("slim", "стройный", "magro", "瘦", "細身", "슬림"),
    "tall": six("tall", "высокий", "alto", "高", "背が高い", "키가 큼"),
    "short": six("short", "невысокий", "baixo", "矮", "背が低い", "키가 작음"),
    "blonde": six("blonde", "блондин", "loiro", "金髮", "金髪", "금발"),
    "brunette": six("dark hair", "брюнет", "cabelo escuro", "深色頭髮", "暗い髪", "어두운 머리"),
    "redhead": six("red hair", "рыжий", "ruivo", "紅髮", "赤い髪", "붉은 머리"),
    "tattoos": six("has tattoos", "есть тату", "tem tatuagem", "有刺青", "タトゥーがある", "타투 있음"),
    "piercings": six("has piercings", "есть пирсинг", "tem piercing", "有穿環", "ピアスがある", "피어싱 있음"),
    "glasses": six("wears glasses", "носит очки", "usa óculos", "戴眼鏡", "眼鏡", "안경"),
    "curvy": six("curvy", "пышные формы", "curvas", "有曲線", "グラマー", "글래머"),
    "switch": six("can lead or follow", "может и вести, и подчиняться", "pode mandar ou obedecer", "可攻可受", "攻めても受けてもいい", "주도도 복종도 가능"),
    "brat": six("teases and acts up", "дразнит и вредничает", "provoca e implica", "搗蛋", "からかって反抗する", "장난치고 반항"),
    "petplay": six("pet and owner play", "игра в питомца", "brincar de bichinho", "寵物扮演", "ペット遊び", "펫플레이"),
    "praise": six("likes being praised", "нравится когда хвалят", "gosta de elogio", "喜歡被誇", "褒められるのが好き", "칭찬이 좋음"),
    "degradation": six("likes being put down", "нравится когда унижают", "gosta de humilhação", "喜歡被貶", "貶されるのが好き", "모욕이 좋음"),
    "cats": six("likes cats", "любит кошек", "gosta de gatos", "喜歡貓", "猫が好き", "고양이를 좋아함"),
    "dogs": six("likes dogs", "любит собак", "gosta de cães", "喜歡狗", "犬が好き", "개를 좋아함"),
    "cat person": six("a cat person", "кошатник", "pessoa de gatos", "貓派", "猫派", "고양이파"),
    "has a dog": six("has a dog", "есть собака", "tem um cão", "有狗", "犬を飼っている", "개가 있음"),
    "reading": six("likes reading", "любит читать", "gosta de ler", "喜歡讀書", "読書が好き", "독서"),
    "travelling": six("likes travel", "любит путешествовать", "gosta de viajar", "喜歡旅行", "旅行が好き", "여행"),
    "cooking": six("likes cooking", "любит готовить", "gosta de cozinhar", "喜歡做菜", "料理が好き", "요리"),
    "photography": six("likes taking photos", "любит фотографировать", "gosta de fotografar", "喜歡拍照", "写真が好き", "사진"),
    "hiking": six("likes hiking", "любит походы", "gosta de trilha", "喜歡健行", "ハイキングが好き", "하이킹"),
    "coffee": six("into coffee", "любит кофе", "gosta de café", "喜歡咖啡", "コーヒーが好き", "커피"),
    "cycling": six("likes cycling", "любит велик", "gosta de pedalar", "喜歡騎車", "自転車が好き", "자전거"),
    "swimming": six("likes swimming", "любит плавать", "gosta de nadar", "喜歡游泳", "泳ぐのが好き", "수영"),
    "yoga": six("does yoga", "занимается йогой", "faz yoga", "做瑜伽", "ヨガ", "요가"),
    "healthy lifestyle": six("looks after sleep, food and moving", "следит за сном, едой и движением", "cuida de sono, comida e movimento", "在意睡眠飲食和運動", "睡眠と食事と運動", "잠, 밥, 운동"),
    "sports": six("into sports", "любит спорт", "gosta de esporte", "喜歡運動", "スポーツ", "스포츠"),
    "computer games": six("plays games", "играет в игры", "joga", "玩遊戲", "ゲームをする", "게임"),
    "anime": six("watches anime", "смотрит аниме", "assiste anime", "看動畫", "アニメを見る", "애니"),
    "cinema": six("watches films", "смотрит кино", "assiste filmes", "看電影", "映画を見る", "영화"),
    "cosplay": six("dresses as characters", "одевается персонажами", "se veste de personagem", "扮角色", "コスプレ", "코스프레"),
    "job": six("about work", "про работу", "sobre trabalho", "關於工作", "仕事の話", "일 이야기"),
    "employer": six("hiring", "нанимает", "está contratando", "在招人", "人を雇う", "사람을 뽑음"),
    "candidate": six("looking for a job", "ищет работу", "procura emprego", "在找工作", "仕事を探している", "일자리를 찾음"),
    "hr": six("does hiring", "занимается наймом", "cuida de contratação", "負責招人", "採用担当", "채용 담당"),
    "startapp": six("building a young company", "делает стартап", "faz uma empresa nova", "在做新公司", "新しい会社を作っている", "새 회사를 만듦"),
    "unpaid": six("no pay", "без оплаты", "sem pagamento", "沒有報酬", "報酬なし", "보수 없음"),
    "free": six("free", "бесплатно", "de graça", "免費", "無料", "무료"),
    "ai": six("into machine learning", "занимается ии", "mexe com ia", "做人工智慧", "機械学習", "인공지능"),
    "mbti": six("uses the personality letters", "пользуется типами личности", "usa as letras de personalidade", "用人格字母", "性格タイプ", "성격 유형"),
    "k-pop": six("listens to k-pop", "слушает кейпоп", "ouve k-pop", "聽韓流", "k-popを聴く", "케이팝"),
    "metal music": six("listens to metal", "слушает метал", "ouve metal", "聽金屬樂", "メタルを聴く", "메탈"),
    "lo-fi / chill": six("listens to calm music", "слушает спокойную музыку", "ouve música calma", "聽輕音樂", "落ち着いた音楽", "잔잔한 음악"),
    "cyberpunk / techwear": six("futuristic tech look", "футуристичный технический вид", "visual futurista", "未來機能風", "近未来の見た目", "미래적 기능 스타일"),
    "smoker (cigarettes)": six("smokes", "курит", "fuma", "抽菸", "たばこを吸う", "담배 핌"),
    "non-smoker (cigarettes)": six("does not smoke", "не курит", "não fuma", "不抽菸", "たばこは吸わない", "담배 안 핌"),
    "vaper": six("vapes", "парит", "usa vape", "用電子煙", "ベイプ", "전자담배"),
    "non-vaper": six("does not vape", "не парит", "não usa vape", "不用電子煙", "ベイプは吸わない", "전자담배 안 핌"),
    "drinks alcohol": six("drinks", "пьёт", "bebe", "喝酒", "酒を飲む", "술을 마심"),
    "doesn't drink alcohol": six("does not drink", "не пьёт", "não bebe", "不喝酒", "酒は飲まない", "술을 안 마심"),
    "femboy": six("a feminine guy", "женственный парень", "cara feminino", "女性化的男生", "女の子っぽい男", "여성스러운 남자"),
    "goth look": six("goth look", "готический вид", "visual gótico", "哥德風", "ゴス", "고스 룩"),
    "tabletop rpgs": six("plays tabletop rpgs", "играет в настольные ролевые", "joga rpg de mesa", "玩桌遊角色扮演", "trpg", "테이블 알피지"),
    "board games": six("plays board games", "играет в настолки", "joga jogos de tabuleiro", "玩桌遊", "ボドゲ", "보드게임"),
}


TEMPLATES = {
    "place": six("place {x}", "место {x}", "lugar {x}", "地點 {x}", "場所 {x}", "장소 {x}"),
    "age": six("age {x}", "возраст {x}", "idade {x}", "年齡 {x}", "年齢 {x}", "나이 {x}"),
    "fetish": six("{x}", "{x}", "{x}", "{x}", "{x}", "{x}"),
    "speaks": six("speaks {x}", "говорит на {x}", "fala {x}", "會說{x}", "{x}が話せる", "{x}를 한다"),
    "learning": six("learning {x}", "учит {x}", "aprende {x}", "在學{x}", "{x}を勉強中", "{x}를 배우는 중"),
    "uses": six("uses {x}", "пользуется {x}", "usa {x}", "用{x}", "{x}を使う", "{x}를 쓴다"),
    "interest": six("into {x}", "нравится {x}", "gosta de {x}", "喜歡{x}", "{x}が好き", "{x}를 좋아함"),
}


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


def kind_of(name, aliases):
    lower = {item.lower() for item in aliases}
    if "location" in lower:
        return "place"
    if "age" in lower or name.endswith(" years old"):
        return "age"
    if "fetish" in lower:
        return "fetish"
    if "(native/fluent)" in name:
        return "speaks"
    if name.startswith("learning "):
        return "learning"
    if name in TOOLS:
        return "uses"
    return "interest"


def label_for(kind, name, i18n, lang):
    label = i18n.get(lang) or i18n.get("en") or name
    if kind == "speaks":
        return name.split(" (", 1)[0]
    if kind == "learning":
        return name[len("learning "):]
    return label


def plain(text):
    text = " ".join(str(text).split()).lower()
    return text.strip(" .。．!！?？,，、:：")


def describe(name, aliases, i18n):
    if name in CUSTOM:
        raw = CUSTOM[name]
    else:
        kind = kind_of(name, aliases)
        template = TEMPLATES[kind]
        raw = {lang: template[lang].format(x=label_for(kind, name, i18n, lang)) for lang in LANGS}
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
        if len(words) == 1 and words[0] in pieces:
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
