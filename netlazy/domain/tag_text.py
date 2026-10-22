import re

_LABEL_WORD = re.compile(r"[^\W_]+", re.UNICODE)


def label_hits(label: object, term: str) -> bool:
    """A typed token hits a label when the label or one of its words starts with it.

    A compound people type is stored as an alias on each elementary tag.
    "fem" still finds the alias "femdom". A whole word inside a phrase matches
    too, but a token does not fire only because it sits inside a longer word.
    """
    text = str(label or "").lower()
    needle = str(term or "").lower()
    if not text or not needle:
        return False
    if text.startswith(needle):
        return True
    return any(word == needle for word in _LABEL_WORD.findall(text))
