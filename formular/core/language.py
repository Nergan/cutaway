"""Определение языка текста по коротким устойчивым словам и буквам.

Это маленькая локальная модель, она входит в сам formular: файл весит килобайты,
скачивать его отдельно незачем. Ответ всегда помечен как AI.
"""

from __future__ import annotations

import re

_CUES: dict[str, tuple[str, ...]] = {
    "en": (" the ", " and ", " of ", " to ", " is ", " that ", " for "),
    "de": (" und ", " die ", " der ", " nicht ", " ein ", " das ", " ist "),
    "fr": (" les ", " des ", " une ", " est ", " que ", " pas ", " dans "),
    "es": (" los ", " las ", " una ", " que ", " del ", " por ", " con "),
    "ru": (" и ", " в ", " не ", " что ", " это ", " на ", " как "),
    "uk": (" і ", " не ", " що ", " це ", " на ", " як ", " та "),
}
_CYRILLIC = re.compile(r"[а-яёіїєґ]", re.IGNORECASE)
_UKRAINIAN = set("іїєґІЇЄҐ")
_RUSSIAN = set("ыэъёЫЭЪЁ")


def detect_language(text: str) -> dict[str, object]:
    sample = " " + re.sub(r"\s+", " ", text.strip().lower()) + " "
    if len(sample.strip()) < 12:
        return _result("unknown", 0.0)
    scores = {code: sum(sample.count(cue) for cue in cues) for code, cues in _CUES.items()}
    letters = _CYRILLIC.findall(sample)
    if letters:
        ukrainian = sum(char in _UKRAINIAN for char in sample)
        russian = sum(char in _RUSSIAN for char in sample)
        scores["uk"] += ukrainian * 2
        scores["ru"] += russian * 2
        if ukrainian == 0 and russian == 0:
            scores["ru"] += 1
    best = max(scores, key=scores.get)
    top = scores[best]
    if top <= 0:
        return _result("unknown", 0.0)
    second = max(value for code, value in scores.items() if code != best)
    if top == second:
        return _result("unknown", 0.0)
    confidence = round(top / (top + second + 1), 2)
    return _result(best, confidence)


def _result(language: str, confidence: float) -> dict[str, object]:
    return {
        "ai": True,
        "operation": "text.language",
        "language": language,
        "confidence": confidence,
        "model": {
            "id": "formular-language-cues",
            "license": "MPL-2.0",
            "provider": "formular",
            "downloaded": False,
        },
    }
