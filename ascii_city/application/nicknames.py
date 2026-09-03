"""Server-issued nicknames.

Clients never choose their own name. The server picks one, guarantees it is
unique inside the room, and only then tells the client what it is called.
"""

from __future__ import annotations

import re
import secrets

from ..domain.constants import PLAYER_COLOR_COUNT
from ..infrastructure.wordlists import ADJECTIVES, NOUNS

MIN_LENGTH = 6
MAX_LENGTH = 24
SAFE_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9-]{4,22}[A-Za-z0-9]$")


class NicknameFactory:
    """Draws unique ``AdjectiveNoun-1234`` names for one room."""

    def __init__(self) -> None:
        self._taken: set[str] = set()

    @property
    def taken(self) -> frozenset[str]:
        return frozenset(self._taken)

    def issue(self) -> str:
        for _ in range(64):
            candidate = self._compose()
            if candidate not in self._taken:
                self._taken.add(candidate)
                return candidate
        # Astronomically unlikely with 64 * 64 * 9000 combinations, but a room
        # must never fail to admit a player because of a name collision.
        base = self._compose()
        suffix = 1
        while f"{base}{suffix}" in self._taken or not is_safe_nickname(f"{base}{suffix}"):
            suffix += 1
        candidate = f"{base}{suffix}"
        self._taken.add(candidate)
        return candidate

    def claim(self, nickname: str) -> bool:
        """Reserve a player-chosen nickname if it passes policy and is free."""
        cleaned = nickname.strip()
        if not is_safe_nickname(cleaned) or cleaned in self._taken:
            return False
        self._taken.add(cleaned)
        return True

    def release(self, nickname: str) -> None:
        self._taken.discard(nickname)

    def rename(self, old: str, new: str) -> bool:
        """Atomically swap a nickname when the new one is valid and unused."""
        cleaned = new.strip()
        if not is_safe_nickname(cleaned) or cleaned in self._taken:
            return False
        self._taken.discard(old)
        self._taken.add(cleaned)
        return True

    @staticmethod
    def _compose() -> str:
        adjective = secrets.choice(ADJECTIVES)
        noun = secrets.choice(NOUNS)
        number = secrets.randbelow(9000) + 1000
        return f"{adjective}{noun}-{number}"


def is_safe_nickname(value: str) -> bool:
    """Length and character policy for anything rendered into a glyph cell."""
    return MIN_LENGTH <= len(value) <= MAX_LENGTH and bool(SAFE_PATTERN.match(value))


def pick_color(player_id: int) -> int:
    """Spread colours across the palette so neighbours rarely match."""
    return (player_id * 5) % PLAYER_COLOR_COUNT


class ColorAllocator:
    """Hand out palette indices so two online players rarely share a colour."""

    def __init__(self) -> None:
        self._used: set[int] = set()

    def issue(self, player_id: int) -> int:
        for offset in range(PLAYER_COLOR_COUNT):
            candidate = (player_id + offset) % PLAYER_COLOR_COUNT
            if candidate not in self._used:
                self._used.add(candidate)
                return candidate
        return pick_color(player_id)

    def release(self, color: int) -> None:
        self._used.discard(color)
