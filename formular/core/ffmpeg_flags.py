"""Белый список пользовательских флагов ffmpeg.

Чёрный список пропускал фильтры, которые читают файлы по относительному пути.
Здесь разрешены только флаги и фильтры без доступа к файловой системе.
"""

from __future__ import annotations

import re
import shlex

from formular.core.errors import FormularError

_ALLOWED_FLAGS = frozenset(
    {
        "-ss",
        "-to",
        "-t",
        "-vn",
        "-an",
        "-sn",
        "-b:v",
        "-b:a",
        "-crf",
        "-preset",
        "-cpu-used",
        "-deadline",
        "-row-mt",
        "-threads",
        "-ar",
        "-ac",
        "-q:a",
        "-q:v",
        "-vf",
        "-af",
        "-r",
        "-s",
    }
)
_BARE_FLAGS = frozenset({"-vn", "-an", "-sn"})
_ALLOWED_FILTERS = frozenset(
    {
        "scale",
        "crop",
        "hue",
        "negate",
        "colorchannelmixer",
        "format",
        "atempo",
        "aecho",
        "bass",
        "volume",
        "fps",
        "setsar",
    }
)
_PRESETS = frozenset(
    {"ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow"}
)
_TIME = re.compile(r"\d{1,6}(\.\d{1,3})?")
_SIZE = re.compile(r"\d{1,5}x\d{1,5}")
_BITRATE = re.compile(r"\d{1,7}[kKmM]?")
_FILTER_ARG = re.compile(r"[A-Za-z0-9_.:%=+-]*")
_FILE_FILTER = re.compile(
    r"filename|textfile|fontfile|subtitles|movie|amovie|signature",
    re.IGNORECASE,
)


def _reject(message: str) -> None:
    raise FormularError(message, 422)


def _check_value(flag: str, value: str) -> None:
    if _FILE_FILTER.search(value) or any(token in value for token in ("/", "\\", "..")):
        _reject("This ffmpeg option is not allowed.")
    if flag in {"-ss", "-to", "-t"} and not _TIME.fullmatch(value):
        _reject("Time values must be seconds.")
    elif flag == "-s" and not _SIZE.fullmatch(value):
        _reject("Size must look like 1280x720.")
    elif flag == "-threads":
        if value not in {"1", "2"}:
            _reject("Threads must be 1 or 2.")
    elif flag == "-preset" and value not in _PRESETS:
        _reject("Unknown video preset.")
    elif flag == "-deadline" and value not in {"realtime", "good"}:
        _reject("Unknown deadline.")
    elif flag == "-row-mt" and value not in {"0", "1"}:
        _reject("row-mt must be 0 or 1.")
    elif flag == "-crf":
        if not value.isdigit() or not 0 <= int(value) <= 63:
            _reject("crf is out of range.")
    elif flag in {"-b:v", "-b:a"} and not _BITRATE.fullmatch(value):
        _reject("Bitrate must be a number, optionally with k or m.")
    elif flag in {"-r", "-ar", "-q:a", "-q:v", "-cpu-used", "-ac"}:
        if not re.fullmatch(r"\d{1,6}", value):
            _reject("Numeric ffmpeg option is invalid.")
        if flag == "-ac" and value not in {"1", "2"}:
            _reject("Audio channels must be 1 or 2.")
        if flag == "-cpu-used" and int(value) > 8:
            _reject("cpu-used is out of range.")
    elif flag in {"-vf", "-af"}:
        _check_filtergraph(value)


def _check_filtergraph(value: str) -> None:
    if _FILE_FILTER.search(value):
        _reject("File-reading filters are not allowed.")
    for part in value.split(","):
        piece = part.strip()
        if not piece:
            _reject("Empty filter.")
        name = piece.split("=", 1)[0].split(":", 1)[0]
        if name not in _ALLOWED_FILTERS:
            _reject("This filter is not allowed.")
        argument = piece[len(name) :]
        if argument and not _FILTER_ARG.fullmatch(argument):
            _reject("Filter arguments contain unsupported characters.")


def custom_ffmpeg_args(text: str | None) -> list[str]:
    """Разобрать пользовательскую строку флагов. Пустая строка — пустой список."""
    raw = (text or "").strip()
    if not raw:
        return []
    if any(char in raw for char in "/\\&|;$`<>"):
        _reject("This ffmpeg option is not allowed.")
    try:
        tokens = shlex.split(raw)
    except ValueError as exc:
        raise FormularError("ffmpeg flags could not be parsed.", 422) from exc

    parsed: list[str] = []
    index = 0
    while index < len(tokens):
        flag = tokens[index]
        if flag not in _ALLOWED_FLAGS:
            _reject("This ffmpeg option is not allowed.")
        parsed.append(flag)
        if flag in _BARE_FLAGS:
            index += 1
            continue
        if index + 1 >= len(tokens):
            _reject("ffmpeg option is missing a value.")
        value = tokens[index + 1]
        if value.startswith("-"):
            _reject("ffmpeg option is missing a value.")
        _check_value(flag, value)
        parsed.append(value)
        index += 2
    return parsed
