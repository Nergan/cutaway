import re

_TRAILING_SPACE = re.compile(r"[ \t]+\n")
_EXTRA_BLANK_LINES = re.compile(r"\n(?:[ \t]*\n){2,}")
_LEADING_BLANK_LINES = re.compile(r"^(?:[ \t]*\n)+")
_TRAILING_BLANK_LINES = re.compile(r"(?:\n[ \t]*)+$")


def normalize_bio(text: str, max_length: int) -> str:
    """Keep single blank lines and drop the rest, then cap the length."""
    value = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    value = _TRAILING_SPACE.sub("\n", value)
    value = _EXTRA_BLANK_LINES.sub("\n\n", value)
    value = _LEADING_BLANK_LINES.sub("", value)
    value = _TRAILING_BLANK_LINES.sub("", value)
    if len(value) > max_length:
        value = _TRAILING_BLANK_LINES.sub("", value[:max_length])
    return value
