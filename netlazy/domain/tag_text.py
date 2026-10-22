def label_hits(label: object, term: str) -> bool:
    """A typed token hits a label when that label starts with the token.

    femdom is its own alias on girl and on dominant, so the token finds both.
    A longer phrase such as soft femdom does not answer for femdom: the label
    has to begin with what was typed. fem still finds femdom.
    """
    text = str(label or "").lower()
    needle = str(term or "").lower()
    if not text or not needle:
        return False
    return text.startswith(needle)
