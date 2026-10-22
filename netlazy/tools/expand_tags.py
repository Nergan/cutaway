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
    "gentle femdom": ["girl", "dominant", "soft"],
    "soft femdom": ["girl", "dominant", "soft"],
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
    "online": six("Prefers contact at a distance, over the network.", "Предпочитает общение на расстоянии, по сети.", "Prefere contato à distância, pela rede.", "偏好透過網路遠距聯絡。", "ネット越しの距離を置いたやり取りを好む。", "네트워크로 거리를 두고 연락하는 쪽."),
    "serious relationship": six("Looking for a steady, long-term relationship.", "Ищет устойчивые, долгие отношения.", "Procura uma relação estável e longa.", "在找穩定、長期的關係。", "長く安定した関係を探している。", "안정적이고 긴 관계를 찾는다."),
    "casual relationship": six("Open to an easy relationship without a heavy commitment.", "Открыт к лёгким отношениям без жёстких обязательств.", "Aberto a uma relação leve, sem compromisso pesado.", "可以接受輕鬆、沒有沉重承諾的關係。", "重い約束のない軽い関係でもよい。", "무거운 약속 없는 가벼운 관계도 괜찮다."),
    "sex-only relationship": six("Looking for a sexual connection without a romance.", "Ищет сексуальную связь без романа.", "Procura uma ligação sexual sem romance.", "在找沒有戀愛的性關係。", "恋愛なしの性的な関係を探している。", "연애 없는 성적 관계를 찾는다."),
    "one-off chat": six("Up for a single conversation, not an ongoing thread.", "Готов к одному разговору, не к долгой переписке.", "Serve uma conversa só, sem fio contínuo.", "只想聊一次，不打算長期聊下去。", "一度きりの会話でよく、続きは求めない。", "한 번의 대화면 되고, 이어가지는 않는다."),
    "dirty talk / horny": six("In the mood for explicit, sexual conversation.", "Настроен на откровенный, сексуальный разговор.", "No clima de uma conversa explícita e sexual.", "想要露骨的性對話。", "露骨で性的な会話の気分。", "노골적인 성적 대화를 원하는 기분."),
    "casual chat": six("Wants an ordinary, low-stakes conversation.", "Хочет обычный, ни к чему не обязывающий разговор.", "Quer uma conversa comum, sem pressão.", "想要普通、沒有壓力的聊天。", "気軽で普通の会話がしたい。", "부담 없는 평범한 대화를 원한다."),
    "networking": six("Here for work contacts and professional ties.", "Здесь ради рабочих контактов и деловых связей.", "Aqui por contatos de trabalho e laços profissionais.", "來這裡是為了工作人脈。", "仕事の連絡先と職業上のつながりが目的。", "일과 직업적인 인맥이 목적."),
    "guy": six("A man or a guy.", "Мужчина или парень.", "Um homem.", "男性。", "男性。", "남성."),
    "girl": six("A woman or a girl.", "Девушка или женщина.", "Uma mulher.", "女性。", "女性。", "여성."),
    "straight": six("Attracted to a different gender.", "Влечение к другому полу.", "Atração por outro gênero.", "被不同性別吸引。", "別の性別に惹かれる。", "다른 성별에 끌린다."),
    "gay": six("A man attracted to men.", "Мужчина, которого влекут мужчины.", "Um homem atraído por homens.", "被男性吸引的男性。", "男性に惹かれる男性。", "남성에게 끌리는 남성."),
    "lesbian": six("A woman attracted to women.", "Женщина, которую влекут женщины.", "Uma mulher atraída por mulheres.", "被女性吸引的女性。", "女性に惹かれる女性。", "여성에게 끌리는 여성."),
    "bi": six("Attracted to more than one gender.", "Влечение больше чем к одному полу.", "Atração por mais de um gênero.", "會被不只一種性別吸引。", "複数の性別に惹かれる。", "둘 이상의 성별에 끌린다."),
    "asexual": six("Little or no sexual attraction.", "Слабое или отсутствующее сексуальное влечение.", "Pouca ou nenhuma atração sexual.", "性吸引很少或沒有。", "性的な惹かれが薄い、またはない。", "성적 끌림이 거의 없거나 없다."),
    "submissive": six("Likes to yield the lead in an intimate dynamic. It appears in search and stays out of the tag cloud.", "Нравится отдавать инициативу в интимной динамике. Находится поиском и не входит в облако тегов.", "Gosta de ceder a iniciativa numa dinâmica íntima. Aparece na busca e fica fora da nuvem de tags.", "在親密關係裡喜歡把主導交給對方。搜尋才會出現，不進標籤雲。", "親密な関係では主導を渡すのが好き。検索に出るが、タグの雲には出ない。", "친밀한 관계에서 주도권을 넘기는 쪽. 검색에만 나오고 태그 구름에는 없다."),
    "dominant": six("Likes to take the lead in an intimate dynamic. It appears in search and stays out of the tag cloud.", "Нравится вести в интимной динамике. Находится поиском и не входит в облако тегов.", "Gosta de conduzir a dinâmica íntima. Aparece na busca e fica fora da nuvem de tags.", "在親密關係裡喜歡主導。搜尋才會出現，不進標籤雲。", "親密な関係では主導するのが好き。検索に出るが、タグの雲には出ない。", "친밀한 관계에서 주도하는 쪽. 검색에만 나오고 태그 구름에는 없다."),
    "soft": six("A gentle, low-intensity intimate style. It appears in search and stays out of the tag cloud.", "Мягкий, спокойный интимный стиль. Находится поиском и не входит в облако тегов.", "Um estilo íntimo gentil e leve. Aparece na busca e fica fora da nuvem de tags.", "溫和、強度低的親密風格。搜尋才會出現，不進標籤雲。", "穏やかで弱い親密なスタイル。検索に出るが、タグの雲には出ない。", "부드럽고 강도가 낮은 친밀한 스타일. 검색에만 나오고 태그 구름에는 없다."),
    "facesitting": six("Sitting on a partner's face. It appears in search and stays out of the tag cloud.", "Сидеть на лице партнёра. Находится поиском и не входит в облако тегов.", "Sentar no rosto de um parceiro. Aparece na busca e fica fora da nuvem de tags.", "坐在對方臉上。搜尋才會出現，不進標籤雲。", "相手の顔の上に座る。検索に出るが、タグの雲には出ない。", "상대 얼굴 위에 앉는 것. 검색에만 나오고 태그 구름에는 없다."),
    "foot fetish": six("Attraction to feet. It appears in search and stays out of the tag cloud.", "Влечение к ступням. Находится поиском и не входит в облако тегов.", "Atração por pés. Aparece na busca e fica fora da nuvem de tags.", "對腳的吸引。搜尋才會出現，不進標籤雲。", "足への惹かれ。検索に出るが、タグの雲には出ない。", "발에 대한 끌림. 검색에만 나오고 태그 구름에는 없다."),
    "chubby": six("A soft, larger body. It appears in search and stays out of the tag cloud.", "Мягкое, крупное тело. Находится поиском и не входит в облако тегов.", "Um corpo macio e maior. Aparece na busca e fica fora da nuvem de tags.", "柔軟、偏大的體型。搜尋才會出現，不進標籤雲。", "やわらかく大きめの体。検索に出るが、タグの雲には出ない。", "부드럽고 큰 체형. 검색에만 나오고 태그 구름에는 없다."),
    "vore": six("A fantasy of swallowing or being swallowed. It appears in search and stays out of the tag cloud.", "Фантазия о том, чтобы проглотить или быть проглоченным. Находится поиском и не входит в облако тегов.", "Uma fantasia de engolir ou ser engolido. Aparece na busca e fica fora da nuvem de tags.", "吞下或被吞下的想像。搜尋才會出現，不進標籤雲。", "飲み込む、または飲み込まれる想像。検索に出るが、タグの雲には出ない。", "삼키거나 삼켜지는 상상. 검색에만 나오고 태그 구름에는 없다."),
    "trampling": six("Being stepped on, or stepping on someone. It appears in search and stays out of the tag cloud.", "Наступать или когда наступают. Находится поиском и не входит в облако тегов.", "Pisar ou ser pisado. Aparece na busca e fica fora da nuvem de tags.", "踩人或被踩。搜尋才會出現，不進標籤雲。", "踏む、または踏まれる。検索に出るが、タグの雲には出ない。", "밟거나 밟히는 것. 검색에만 나오고 태그 구름에는 없다."),
    "mommy fetish": six("Attraction to an older, maternal figure. It appears in search and stays out of the tag cloud.", "Влечение к старшей, материнской фигуре. Находится поиском и не входит в облако тегов.", "Atração por uma figura mais velha e materna. Aparece na busca e fica fora da nuvem de tags.", "對年長、母性形象的吸引。搜尋才會出現，不進標籤雲。", "年上で母性的な人への惹かれ。検索に出るが、タグの雲には出ない。", "더 나이 들고 모성적인 사람에 대한 끌림. 검색에만 나오고 태그 구름에는 없다."),
    "daddy fetish": six("Attraction to an older, paternal figure. It appears in search and stays out of the tag cloud.", "Влечение к старшей, отцовской фигуре. Находится поиском и не входит в облако тегов.", "Atração por uma figura mais velha e paterna. Aparece na busca e fica fora da nuvem de tags.", "對年長、父性形象的吸引。搜尋才會出現，不進標籤雲。", "年上で父性的な人への惹かれ。検索に出るが、タグの雲には出ない。", "더 나이 들고 부성적인 사람에 대한 끌림. 검색에만 나오고 태그 구름에는 없다."),
    "spitting": six("Spit and saliva in an intimate setting. It appears in search and stays out of the tag cloud.", "Слюна в интимной обстановке. Находится поиском и не входит в облако тегов.", "Saliva num contexto íntimo. Aparece na busca e fica fora da nuvem de tags.", "親密情境裡的唾液。搜尋才會出現，不進標籤雲。", "親密な場面での唾液。検索に出るが、タグの雲には出ない。", "친밀한 상황에서의 침. 검색에만 나오고 태그 구름에는 없다."),
    "scaly": six("A scaled, reptilian fantasy look. It appears in search and stays out of the tag cloud.", "Чешуйчатый, рептильный образ. Находится поиском и не входит в облако тегов.", "Um visual de fantasia com escamas. Aparece na busca e fica fora da nuvem de tags.", "帶鱗片的爬蟲想像外形。搜尋才會出現，不進標籤雲。", "鱗のある爬虫類ふうの姿。検索に出るが、タグの雲には出ない。", "비늘이 있는 파충류풍 모습. 검색에만 나오고 태그 구름에는 없다."),
    "white skin": six("A light skin tone the person wants. It appears in search and stays out of the tag cloud.", "Светлая кожа, которую человек ищет. Находится поиском и не входит в облако тегов.", "Um tom de pele claro que a pessoa procura. Aparece na busca e fica fora da nuvem de tags.", "對方想要的淺膚色。搜尋才會出現，不進標籤雲。", "その人が求める明るい肌。検索に出るが、タグの雲には出ない。", "그 사람이 원하는 밝은 피부. 검색에만 나오고 태그 구름에는 없다."),
    "black skin": six("A dark skin tone the person wants. It appears in search and stays out of the tag cloud.", "Тёмная кожа, которую человек ищет. Находится поиском и не входит в облако тегов.", "Um tom de pele escuro que a pessoa procura. Aparece na busca e fica fora da nuvem de tags.", "對方想要的深膚色。搜尋才會出現，不進標籤雲。", "その人が求める暗い肌。検索に出るが、タグの雲には出ない。", "그 사람이 원하는 어두운 피부. 검색에만 나오고 태그 구름에는 없다."),
    "dark skin": six("A brown or deep skin tone the person wants. It appears in search and stays out of the tag cloud.", "Смуглая или глубокая кожа, которую человек ищет. Находится поиском и не входит в облако тегов.", "Um tom de pele marrom ou profundo que a pessoa procura. Aparece na busca e fica fora da nuvem de tags.", "對方想要的棕褐或深色皮膚。搜尋才會出現，不進標籤雲。", "その人が求める褐色や濃い肌。検索に出るが、タグの雲には出ない。", "그 사람이 원하는 갈색이나 진한 피부. 검색에만 나오고 태그 구름에는 없다."),
    "asian": six("An East or Southeast Asian look the person wants. It appears in search and stays out of the tag cloud.", "Восточно- или юго-восточноазиатская внешность, которую человек ищет. Находится поиском и не входит в облако тегов.", "Uma aparência do leste ou sudeste asiático que a pessoa procura. Aparece na busca e fica fora da nuvem de tags.", "對方想要的東亞或東南亞外表。搜尋才會出現，不進標籤雲。", "その人が求める東アジアまたは東南アジアの見た目。検索に出るが、タグの雲には出ない。", "그 사람이 원하는 동아시아 또는 동남아시아의 외모. 검색에만 나오고 태그 구름에는 없다."),
    "latin": six("A Latin American look the person wants. It appears in search and stays out of the tag cloud.", "Латиноамериканская внешность, которую человек ищет. Находится поиском и не входит в облако тегов.", "Uma aparência latino-americana que a pessoa procura. Aparece na busca e fica fora da nuvem de tags.", "對方想要的拉丁美洲外表。搜尋才會出現，不進標籤雲。", "その人が求めるラテンアメリカの見た目。検索に出るが、タグの雲には出ない。", "그 사람이 원하는 라틴아메리카의 외모. 검색에만 나오고 태그 구름에는 없다."),
    "belly inflation": six("A fantasy of a swelling belly. It appears in search and stays out of the tag cloud.", "Фантазия о раздувающемся животе. Находится поиском и не входит в облако тегов.", "Uma fantasia de barriga que incha. Aparece na busca e fica fora da nuvem de tags.", "腹部脹起的想像。搜尋才會出現，不進標籤雲。", "お腹が膨らむ想像。検索に出るが、タグの雲には出ない。", "배가 부푸는 상상. 검색에만 나오고 태그 구름에는 없다."),
    "bondage": six("Restraint with rope, cuffs, or similar. It appears in search and stays out of the tag cloud.", "Ограничение верёвками, наручниками и похожим. Находится поиском и не входит в облако тегов.", "Contenção com corda, algemas ou algo parecido. Aparece na busca e fica fora da nuvem de tags.", "用繩子、手銬或類似物拘束。搜尋才會出現，不進標籤雲。", "縄、手錠などで拘束する。検索に出るが、タグの雲には出ない。", "밧줄, 수갑 등으로 묶는 것. 검색에만 나오고 태그 구름에는 없다."),
    "sadomasochism": six("Pain given or received by agreement. It appears in search and stays out of the tag cloud.", "Боль по согласию, с той или другой стороны. Находится поиском и не входит в облако тегов.", "Dor dada ou recebida de comum acordo. Aparece na busca e fica fora da nuvem de tags.", "雙方同意下的施加或承受疼痛。搜尋才會出現，不進標籤雲。", "合意の上で与える、または受ける痛み。検索に出るが、タグの雲には出ない。", "합의 아래 주거나 받는 고통. 검색에만 나오고 태그 구름에는 없다."),
    "latex/leather": six("Latex, leather, or rubber clothing. It appears in search and stays out of the tag cloud.", "Одежда из латекса, кожи или резины. Находится поиском и не входит в облако тегов.", "Roupa de látex, couro ou borracha. Aparece na busca e fica fora da nuvem de tags.", "乳膠、皮革或橡膠衣物。搜尋才會出現，不進標籤雲。", "ラテックス、革、ゴムの服。検索に出るが、タグの雲には出ない。", "라텍스, 가죽, 고무 옷. 검색에만 나오고 태그 구름에는 없다."),
    "roleplay (fetish)": six("An intimate scene played as characters. It appears in search and stays out of the tag cloud.", "Интимная сцена в образах персонажей. Находится поиском и не входит в облако тегов.", "Uma cena íntima vivida como personagens. Aparece na busca e fica fora da nuvem de tags.", "以角色進行的親密情景。搜尋才會出現，不進標籤雲。", "役になって演じる親密な場面。検索に出るが、タグの雲には出ない。", "배역으로 하는 친밀한 장면. 검색에만 나오고 태그 구름에는 없다."),
    "tomboy": six("A girl with a boyish manner or look.", "Девушка с мальчишеской манерой или видом.", "Uma mulher com jeito ou visual de rapaz.", "帶點男孩子氣的女生。", "少年っぽい様子の女性。", "소년 같은 느낌의 여성."),
    "introvert": six("Draws energy from quiet and solitude.", "Восстанавливается в тишине и одиночестве.", "Recupera energia no silêncio e na solidão.", "從安靜和獨處恢復精力。", "静けさと一人の時間で回復する。", "고요함과 혼자 있는 시간에서 힘을 얻는다."),
    "extrovert": six("Draws energy from people and activity.", "Восстанавливается среди людей и движения.", "Recupera energia com gente e movimento.", "從人群和活動恢復精力。", "人と動きの中で回復する。", "사람과 활동 속에서 힘을 얻는다."),
    "cute": six("A cute, pretty, or adorable vibe.", "Милый, няшный или кавайный образ.", "Um ar fofo, bonito ou adorável.", "可愛、漂亮或惹人憐愛的感覺。", "かわいい、きれい、愛らしい雰囲気。", "귀엽거나 사랑스러운 느낌."),
    "shy": six("Slow to open up, easily bashful.", "Не сразу раскрывается, легко смущается.", "Demora a se abrir e se acanha fácil.", "不容易放開，容易害羞。", "すぐには打ち解けず、照れやすい。", "쉽게 마음을 열지 않고 잘 수줍어한다."),
    "funny": six("A humorous, playful manner.", "Юморная, игривая манера.", "Um jeito bem-humorado e brincalhão.", "幽默、愛玩的樣子。", "ユーモアがあって茶目っ気のある様子。", "유머 있고 장난기 있는 태도."),
    "kind": six("A warm, considerate manner.", "Тёплая, внимательная манера.", "Um jeito caloroso e atencioso.", "溫暖、體貼的樣子。", "あたたかく気遣いのある様子。", "따뜻하고 살가운 태도."),
    "smart": six("A sharp, thoughtful mind.", "Острый, вдумчивый ум.", "Uma mente afiada e atenta.", "敏銳、會想事情的頭腦。", "鋭く考え深い頭。", "예리하고 생각이 깊은 머리."),
    "athletic": six("A fit, sporty build or habit.", "Спортивное телосложение или привычка.", "Um corpo ou hábito esportivo.", "健美的體態或運動習慣。", "引き締まった体つき、または運動の習慣。", "탄탄한 체형이나 운동 습관."),
    "slim": six("A slim build.", "Стройное телосложение.", "Um corpo magro.", "纖細的體型。", "細身。", "슬림한 체형."),
    "tall": six("Tall stature.", "Высокий рост.", "Estatura alta.", "個子高。", "身長が高い。", "키가 크다."),
    "short": six("Short stature.", "Невысокий рост.", "Estatura baixa.", "個子不高。", "身長が低い。", "키가 작다."),
    "blonde": six("Blonde hair.", "Светлые волосы.", "Cabelo loiro.", "金髮。", "金髪。", "금발."),
    "brunette": six("Dark hair.", "Тёмные волосы.", "Cabelo escuro.", "深色頭髮。", "暗い髪。", "어두운 머리."),
    "redhead": six("Red hair.", "Рыжие волосы.", "Cabelo ruivo.", "紅髮。", "赤い髪。", "붉은 머리."),
    "tattoos": six("Has tattoos.", "Есть татуировки.", "Tem tatuagens.", "有刺青。", "タトゥーがある。", "타투가 있다."),
    "piercings": six("Has piercings.", "Есть пирсинг.", "Tem piercings.", "有穿刺。", "ピアスがある。", "피어싱이 있다."),
    "glasses": six("Wears glasses.", "Носит очки.", "Usa óculos.", "戴眼鏡。", "眼鏡をかけている。", "안경을 쓴다."),
    "curvy": six("A curvy figure.", "Пышная фигура.", "Uma silhueta curvilínea.", "有曲線的身材。", "曲線のある体型。", "곡선이 있는 체형."),
    "switch": six("Can take either role in an intimate dynamic. It appears in search and stays out of the tag cloud.", "Может быть и ведущим, и ведомым. Находится поиском и не входит в облако тегов.", "Pode ficar dos dois lados numa dinâmica íntima. Aparece na busca e fica fora da nuvem de tags.", "在親密關係裡兩種角色都可以。搜尋才會出現，不進標籤雲。", "親密な関係でどちら側にもなれる。検索に出るが、タグの雲には出ない。", "친밀한 관계에서 양쪽 역할을 다 할 수 있다. 검색에만 나오고 태그 구름에는 없다."),
    "brat": six("Playfully resists and teases the person who leads. It appears in search and stays out of the tag cloud.", "Игриво сопротивляется и дразнит ведущего. Находится поиском и не входит в облако тегов.", "Resiste e provoca, de brincadeira, quem conduz. Aparece na busca e fica fora da nuvem de tags.", "會鬧著反抗、逗主導的人。搜尋才會出現，不進標籤雲。", "主導する人にいたずらで抗い、からかう。検索に出るが、タグの雲には出ない。", "주도하는 사람을 장난으로 거스르고 놀린다. 검색에만 나오고 태그 구름에는 없다."),
    "petplay": six("An intimate game of pet and keeper. It appears in search and stays out of the tag cloud.", "Интимная игра в питомца и хозяина. Находится поиском и не входит в облако тегов.", "Um jogo íntimo de animal de estimação e dono. Aparece na busca e fica fora da nuvem de tags.", "寵物與飼主的親密扮演。搜尋才會出現，不進標籤雲。", "ペットと飼い主の親密な遊び。検索に出るが、タグの雲には出ない。", "펫과 주인의 친밀한 놀이. 검색에만 나오고 태그 구름에는 없다."),
    "praise": six("Likes to be praised in an intimate setting. It appears in search and stays out of the tag cloud.", "Нравится, когда хвалят в интимной обстановке. Находится поиском и не входит в облако тегов.", "Gosta de ser elogiado num contexto íntimo. Aparece na busca e fica fora da nuvem de tags.", "在親密情境裡喜歡被誇獎。搜尋才會出現，不進標籤雲。", "親密な場面で褒められるのが好き。検索に出るが、タグの雲には出ない。", "친밀한 상황에서 칭찬받는 것을 좋아한다. 검색에만 나오고 태그 구름에는 없다."),
    "degradation": six("Likes humiliation in an intimate setting. It appears in search and stays out of the tag cloud.", "Нравится унижение в интимной обстановке. Находится поиском и не входит в облако тегов.", "Gosta de humilhação num contexto íntimo. Aparece na busca e fica fora da nuvem de tags.", "在親密情境裡喜歡被貶低。搜尋才會出現，不進標籤雲。", "親密な場面での辱めが好き。検索に出るが、タグの雲には出ない。", "친밀한 상황에서의 모욕을 좋아한다. 검색에만 나오고 태그 구름에는 없다."),
    "cats": six("Likes cats.", "Любит кошек.", "Gosta de gatos.", "喜歡貓。", "猫が好き。", "고양이를 좋아한다."),
    "dogs": six("Likes dogs.", "Любит собак.", "Gosta de cães.", "喜歡狗。", "犬が好き。", "개를 좋아한다."),
    "cat person": six("Feels like a cat person.", "Считает себя кошатником.", "Se vê como uma pessoa de gatos.", "覺得自己是貓派。", "自分は猫派だと思っている。", "자신을 고양이파로 여긴다."),
    "has a dog": six("Lives with a dog.", "Живёт с собакой.", "Vive com um cão.", "和狗一起生活。", "犬と暮らしている。", "개와 함께 산다."),
    "reading": six("Likes to read.", "Любит читать.", "Gosta de ler.", "喜歡閱讀。", "読書が好き。", "독서를 좋아한다."),
    "travelling": six("Likes to travel.", "Любит путешествовать.", "Gosta de viajar.", "喜歡旅行。", "旅が好き。", "여행을 좋아한다."),
    "cooking": six("Likes to cook.", "Любит готовить.", "Gosta de cozinhar.", "喜歡做菜。", "料理が好き。", "요리를 좋아한다."),
    "photography": six("Likes taking photos.", "Любит фотографировать.", "Gosta de fotografar.", "喜歡拍照。", "写真を撮るのが好き。", "사진 찍는 것을 좋아한다."),
    "hiking": six("Likes walking trails and hills.", "Любит тропы и походы.", "Gosta de trilhas e caminhadas.", "喜歡步道和健行。", "道や山歩きが好き。", "길과 산행을 좋아한다."),
    "coffee": six("Cares about coffee.", "Неравнодушен к кофе.", "Se importa com café.", "在意咖啡。", "コーヒーにこだわる。", "커피에 관심이 많다."),
    "cycling": six("Likes riding a bike.", "Любит кататься на велосипеде.", "Gosta de pedalar.", "喜歡騎車。", "自転車に乗るのが好き。", "자전거 타는 것을 좋아한다."),
    "swimming": six("Likes to swim.", "Любит плавать.", "Gosta de nadar.", "喜歡游泳。", "泳ぐのが好き。", "수영을 좋아한다."),
    "yoga": six("Practices yoga.", "Занимается йогой.", "Pratica yoga.", "做瑜伽。", "ヨガをする。", "요가를 한다."),
    "healthy lifestyle": six("Looks after sleep, food, and movement.", "Следит за сном, едой и движением.", "Cuida do sono, da comida e do movimento.", "在意睡眠、飲食和活動。", "睡眠、食事、運動を大事にする。", "잠, 식사, 움직임을 챙긴다."),
    "sports": six("Follows or plays sports.", "Следит за спортом или занимается им.", "Acompanha ou pratica esporte.", "看運動或自己運動。", "スポーツを見るか、自分でする。", "스포츠를 보거나 직접 한다."),
    "computer games": six("Plays computer games.", "Играет в компьютерные игры.", "Joga jogos de computador.", "玩電腦遊戲。", "コンピュータゲームをする。", "컴퓨터 게임을 한다."),
    "anime": six("Watches anime.", "Смотрит аниме.", "Assiste anime.", "看動畫。", "アニメを見る。", "애니메이션을 본다."),
    "cinema": six("Watches films.", "Смотрит кино.", "Assiste filmes.", "看電影。", "映画を見る。", "영화를 본다."),
    "cosplay": six("Dresses as characters.", "Одевается персонажами.", "Se veste de personagens.", "扮成角色。", "キャラクターの格好をする。", "캐릭터로 분장한다."),
    "job": six("About work and employment.", "Про работу и занятость.", "Sobre trabalho e emprego.", "關於工作和就業。", "仕事と雇用について。", "일과 고용에 관한 것."),
    "employer": six("Hiring people.", "Нанимает людей.", "Está contratando.", "在招人。", "人を雇っている。", "사람을 뽑는다."),
    "candidate": six("Looking to be hired.", "Хочет, чтобы его наняли.", "Quer ser contratado.", "想被錄用。", "雇われたい。", "채용되고 싶다."),
    "hr": six("Works with hiring and people at a company.", "Занимается наймом и людьми в компании.", "Trabalha com contratação e pessoas numa empresa.", "在公司裡處理招募和人事。", "会社で採用と人を扱う。", "회사에서 채용과 사람을 다룬다."),
    "startapp": six("Building or joining an early company.", "Делает или входит в раннюю компанию.", "Constrói ou entra numa empresa no começo.", "在做或加入剛起步的公司。", "初期の会社を作っているか、加わっている。", "초기 회사를 만들거나 합류한다."),
    "unpaid": six("The work or offer does not pay.", "Работа или предложение без оплаты.", "O trabalho ou a oferta não paga.", "這份工作或提議不付錢。", "その仕事や提案には報酬がない。", "그 일이나 제안에는 보수가 없다."),
    "free": six("Available at no charge.", "Доступно без оплаты.", "Disponível sem cobrança.", "免費。", "無料で使える。", "무료로 쓸 수 있다."),
    "ai": six("Works with or cares about machine learning.", "Работает с машинным обучением или интересуется им.", "Trabalha com aprendizado de máquina ou se interessa por isso.", "做機器學習，或關心它。", "機械学習に関わるか、関心がある。", "기계학습을 다루거나 관심이 있다."),
    "mbti": six("Uses the sixteen-type personality letters.", "Пользуется шестнадцатью буквенными типами личности.", "Usa as dezesseis letras de tipo de personalidade.", "使用十六種人格字母。", "16の性格タイプの文字を使う。", "열여섯 성격 유형 문자를 쓴다."),
    "k-pop": six("Listens to Korean pop.", "Слушает корейскую поп-музыку.", "Ouve pop coreano.", "聽韓國流行樂。", "韓国のポップを聴く。", "한국 팝을 듣는다."),
    "metal music": six("Listens to metal.", "Слушает метал.", "Ouve metal.", "聽金屬樂。", "メタルを聴く。", "메탈을 듣는다."),
    "lo-fi / chill": six("Listens to calm, low-fidelity music.", "Слушает спокойную, приглушённую музыку.", "Ouve música calma e de baixa fidelidade.", "聽平靜、低保真的音樂。", "落ち着いた粗い音の音楽を聴く。", "차분하고 거친 음질의 음악을 듣는다."),
    "cyberpunk / techwear": six("Likes a futuristic, technical look.", "Нравится футуристичный, технический вид.", "Gosta de um visual futurista e técnico.", "喜歡未來感、機能性的外表。", "未来的で機能的な見た目が好き。", "미래적이고 기능적인 모습을 좋아한다."),
    "smoker (cigarettes)": six("Smokes cigarettes.", "Курит сигареты.", "Fuma cigarros.", "抽菸。", "紙巻きたばこを吸う。", "담배를 피운다."),
    "non-smoker (cigarettes)": six("Does not smoke cigarettes.", "Не курит сигареты.", "Não fuma cigarros.", "不抽菸。", "紙巻きたばこは吸わない。", "담배를 피우지 않는다."),
    "vaper": six("Vapes.", "Парит.", "Usa vape.", "用電子煙。", "ベイプを吸う。", "전자담배를 핀다."),
    "non-vaper": six("Does not vape.", "Не парит.", "Não usa vape.", "不用電子煙。", "ベイプは吸わない。", "전자담배를 피우지 않는다."),
    "drinks alcohol": six("Drinks alcohol.", "Пьёт алкоголь.", "Bebe álcool.", "喝酒。", "酒を飲む。", "술을 마신다."),
    "doesn't drink alcohol": six("Does not drink alcohol.", "Не пьёт алкоголь.", "Não bebe álcool.", "不喝酒。", "酒は飲まない。", "술을 마시지 않는다."),
    "femboy": six("A feminine-presenting guy. It appears in search and stays out of the tag cloud.", "Парень с женственной подачей. Находится поиском и не входит в облако тегов.", "Um rapaz de apresentação feminina. Aparece na busca e fica fora da nuvem de tags.", "呈現女性氣質的男生。搜尋才會出現，不進標籤雲。", "女性的な見せ方の男性。検索に出るが、タグの雲には出ない。", "여성스럽게 보이는 남성. 검색에만 나오고 태그 구름에는 없다."),
    "goth look": six("A gothic look. It appears in search and stays out of the tag cloud.", "Готический вид. Находится поиском и не входит в облако тегов.", "Um visual gótico. Aparece na busca e fica fora da nuvem de tags.", "哥德外表。搜尋才會出現，不進標籤雲。", "ゴシックな見た目。検索に出るが、タグの雲には出ない。", "고딕풍 외모. 검색에만 나오고 태그 구름에는 없다."),
    "tabletop rpgs": six("Plays tabletop role-playing games.", "Играет в настольные ролевые игры.", "Joga RPGs de mesa.", "玩桌上角色扮演。", "テーブルトークRPGをする。", "테이블 롤플레잉을 한다."),
    "board games": six("Plays board games.", "Играет в настольные игры.", "Joga jogos de tabuleiro.", "玩桌上遊戲。", "ボードゲームをする。", "보드게임을 한다."),
}


TEMPLATES = {
    "place": six(
        "{x}. A place. It appears in search and stays out of the tag cloud.",
        "{x}. Место. Находится поиском и не входит в облако тегов.",
        "{x}. Um lugar. Aparece na busca e fica fora da nuvem de tags.",
        "{x}。地點。搜尋才會出現，不進標籤雲。",
        "{x}。場所。検索に出るが、タグの雲には出ない。",
        "{x}. 장소. 검색에만 나오고 태그 구름에는 없다.",
    ),
    "age": six(
        "{x}. An age. It appears in search and stays out of the tag cloud.",
        "{x}. Возраст. Находится поиском и не входит в облако тегов.",
        "{x}. Uma idade. Aparece na busca e fica fora da nuvem de tags.",
        "{x}。年齡。搜尋才會出現，不進標籤雲。",
        "{x}。年齢。検索に出るが、タグの雲には出ない。",
        "{x}. 나이. 검색에만 나오고 태그 구름에는 없다.",
    ),
    "fetish": six(
        "{x}. A sexual preference. It appears in search and stays out of the tag cloud.",
        "{x}. Сексуальное предпочтение. Находится поиском и не входит в облако тегов.",
        "{x}. Uma preferência sexual. Aparece na busca e fica fora da nuvem de tags.",
        "{x}。性偏好。搜尋才會出現，不進標籤雲。",
        "{x}。性的な好み。検索に出るが、タグの雲には出ない。",
        "{x}. 성적 선호. 검색에만 나오고 태그 구름에는 없다.",
    ),
    "speaks": six(
        "Speaks {x} fluently.",
        "Свободно говорит: {x}.",
        "Fala {x} com fluência.",
        "能流利使用{x}。",
        "{x}を流暢に話せる。",
        "{x}를 유창하게 한다.",
    ),
    "learning": six(
        "Is learning {x}.",
        "Изучает: {x}.",
        "Está aprendendo {x}.",
        "正在學{x}。",
        "{x}を学んでいる。",
        "{x}를 배우는 중이다.",
    ),
    "uses": six(
        "Uses {x}.",
        "Пользуется: {x}.",
        "Usa {x}.",
        "使用{x}。",
        "{x}を使う。",
        "{x}를 쓴다.",
    ),
    "interest": six(
        "An interest: {x}.",
        "Интерес: {x}.",
        "Um interesse: {x}.",
        "興趣：{x}。",
        "興味：{x}。",
        "관심사: {x}.",
    ),
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


def describe(name, aliases, i18n):
    if name in CUSTOM:
        return dict(CUSTOM[name])
    kind = kind_of(name, aliases)
    template = TEMPLATES[kind]
    return {lang: template[lang].format(x=label_for(kind, name, i18n, lang)) for lang in LANGS}


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
