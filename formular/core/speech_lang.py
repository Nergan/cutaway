"""Split text into pieces that can be spoken by one language voice.

Detection uses the writing system and a few function words. It does not
download a language model. Pieces keep their original characters so they can
be concatenated back into the input.
"""

from __future__ import annotations

import re

# Words that rarely belong to the other languages we can speak.
_CLUES = {
    "de": frozenset(
        {
            "und", "der", "die", "das", "nicht", "ist", "ein", "eine", "mit",
            "auf", "für", "von", "den", "dem", "auch", "sich", "dass", "oder",
        }
    ),
    "fr": frozenset(
        {
            "les", "des", "une", "est", "pas", "dans", "pour", "avec", "nous",
            "vous", "elle", "cette", "aux", "sont", "dans",
        }
    ),
    "es": frozenset(
        {
            "los", "las", "del", "una", "por", "para", "está", "están", "pero",
            "hay", "como", "sus", "más",
        }
    ),
    "nl": frozenset(
        {
            "het", "een", "van", "niet", "zijn", "voor", "aan", "ook", "wij",
            "zij", "geen", "naar",
        }
    ),
    "sv": frozenset(
        {
            "och", "att", "det", "som", "för", "inte", "ett", "jag", "på",
            "är", "har",
        }
    ),
    "en": frozenset(
        {
            "the", "and", "of", "to", "is", "that", "for", "with", "on",
            "this", "are", "was", "you", "have", "not",
        }
    ),
}

_UK_WORDS = frozenset(
    {"що", "це", "він", "вона", "але", "або", "від", "вже", "ще", "мене", "тебе", "було", "буде", "також"}
)
_RU_WORDS = frozenset(
    {"что", "это", "как", "он", "она", "или", "от", "уже", "ещё", "меня", "тебя", "было", "будет", "привет"}
)
_WORD = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ]+")
_CYR_WORD = re.compile(r"[А-Яа-яЁёІіЇїЄєҐґ]+")
_LETTER = re.compile(r"[^\W\d_]", re.UNICODE)


def segment_languages(text: str) -> list[tuple[str, str]]:
    pieces: list[tuple[str, str]] = []
    for chunk, script in _script_runs(text):
        for sentence in _sentences(chunk):
            pieces.append((_language(sentence, script), sentence))
    return _merge(_absorb_tiny(pieces))


def _script(char: str) -> str:
    code = ord(char)
    if 0x0400 <= code <= 0x04FF:
        return "cyrl"
    if 0x0370 <= code <= 0x03FF:
        return "grek"
    if 0x0590 <= code <= 0x05FF:
        return "hebr"
    if 0x0600 <= code <= 0x06FF or 0x0750 <= code <= 0x077F:
        return "arab"
    if 0x0900 <= code <= 0x097F:
        return "deva"
    if 0x3040 <= code <= 0x30FF:
        return "cjk"
    if 0x4E00 <= code <= 0x9FFF:
        return "cjk"
    if 0xAC00 <= code <= 0xD7AF or 0x1100 <= code <= 0x11FF:
        return "hang"
    if char.isascii() and char.isalpha():
        return "latn"
    return ""


def _script_runs(text: str) -> list[tuple[str, str]]:
    runs: list[tuple[str, str]] = []
    buffer: list[str] = []
    current = ""
    for char in text:
        script = _script(char)
        if script and current and script != current:
            runs.append(("".join(buffer), current))
            buffer = [char]
            current = script
            continue
        if script:
            current = script
        buffer.append(char)
    if buffer:
        runs.append(("".join(buffer), current or "latn"))
    return runs


def _sentences(chunk: str) -> list[str]:
    if not chunk.strip():
        return []
    parts = re.split(r"((?<=[.!?…])\s+|\n+)", chunk)
    sentences: list[str] = []
    for part in parts:
        if not part:
            continue
        if sentences and part.isspace():
            sentences[-1] += part
            continue
        sentences.append(part)
    return sentences or [chunk]


def _language(sentence: str, script: str) -> str:
    if script == "cyrl":
        return _cyrillic_language(sentence)
    if script == "grek":
        return "el"
    if script == "hebr":
        return "he"
    if script == "arab":
        return "ar"
    if script == "deva":
        return "hi"
    if script == "hang":
        return "ko"
    if script == "cjk":
        return "ja" if re.search(r"[\u3040-\u30ff]", sentence) else "zh"
    if script == "latn":
        return _latin_language(sentence)
    return "en"


def _latin_language(sentence: str) -> str:
    words = [word.lower() for word in _WORD.findall(sentence)]
    scores = {
        lang: sum(1 for word in words if word in clues)
        for lang, clues in _CLUES.items()
    }
    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return "en"
    tied = [lang for lang, score in scores.items() if score == scores[best]]
    if len(tied) > 1:
        return "en" if "en" in tied else tied[0]
    return best


def _cyrillic_language(sentence: str) -> str:
    lowered = sentence.lower()
    uk_letters = sum(lowered.count(char) for char in "іїєґ")
    ru_letters = sum(lowered.count(char) for char in "ыэъё")
    if uk_letters > ru_letters:
        return "uk"
    if ru_letters > uk_letters:
        return "ru"
    words = {word.lower() for word in _CYR_WORD.findall(sentence)}
    uk_score = len(words & _UK_WORDS)
    ru_score = len(words & _RU_WORDS)
    if uk_score > ru_score:
        return "uk"
    return "ru"


def _absorb_tiny(pieces: list[tuple[str, str]]) -> list[tuple[str, str]]:
    merged: list[tuple[str, str]] = []
    pending = ""
    for lang, chunk in pieces:
        if len(_LETTER.findall(chunk)) < 3:
            if merged:
                previous_lang, previous = merged[-1]
                merged[-1] = (previous_lang, previous + chunk)
            else:
                pending += chunk
            continue
        merged.append((lang, pending + chunk))
        pending = ""
    if pending:
        if merged:
            lang, chunk = merged[-1]
            merged[-1] = (lang, chunk + pending)
        else:
            merged.append(("en", pending))
    return merged


def _merge(pieces: list[tuple[str, str]]) -> list[tuple[str, str]]:
    merged: list[tuple[str, str]] = []
    for lang, chunk in pieces:
        if merged and merged[-1][0] == lang:
            previous_lang, previous = merged[-1]
            merged[-1] = (previous_lang, previous + chunk)
            continue
        merged.append((lang, chunk))
    return merged
