"""Chat messages and the sanitiser that runs before anything is broadcast."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import Enum

from .constants import CHAT_MAX_LENGTH
from .errors import ChatRejected


class ChatScope(str, Enum):
    GLOBAL = "global"
    PROXIMITY = "proximity"
    SYSTEM = "system"

    @classmethod
    def from_wire(cls, value: int) -> "ChatScope":
        try:
            return _SCOPE_BY_WIRE[value]
        except KeyError as exc:
            raise ChatRejected("Unknown chat scope.") from exc

    @property
    def wire(self) -> int:
        return _WIRE_BY_SCOPE[self]


_SCOPE_BY_WIRE = {0: ChatScope.GLOBAL, 1: ChatScope.PROXIMITY, 2: ChatScope.SYSTEM}
_WIRE_BY_SCOPE = {scope: value for value, scope in _SCOPE_BY_WIRE.items()}


# C0/C1 controls, zero-width joiners and bidirectional overrides. These are the
# characters that let a message impersonate another speaker or hide content in a
# monospace viewport, so they never reach another player.
_FORBIDDEN = re.compile(
    "[\u0000-\u0008\u000a-\u001f\u007f-\u009f\u200b-\u200f\u2028-\u202e\u2060-\u2064\ufeff]"
)
_WHITESPACE_RUN = re.compile(r"[ \t]{2,}")


def sanitise_chat_text(raw: str) -> str:
    """Return display-safe text or raise :class:`ChatRejected`.

    Angle brackets survive on purpose: they are ordinary characters in an ASCII
    world and the clients render chat into text nodes and glyph cells, never
    into markup. ``docs/protocol.md`` records that contract.
    """
    if not isinstance(raw, str):
        raise ChatRejected("Chat payload must be text.")
    text = unicodedata.normalize("NFC", raw)
    text = _FORBIDDEN.sub("", text)
    text = _WHITESPACE_RUN.sub(" ", text).strip()
    if not text:
        raise ChatRejected("Empty message.")
    if len(text) > CHAT_MAX_LENGTH:
        raise ChatRejected(f"Message exceeds {CHAT_MAX_LENGTH} characters.")
    return text


@dataclass(frozen=True, slots=True)
class ChatMessage:
    id: int
    sender_id: int
    nickname: str
    text: str
    scope: ChatScope
    created_at: float

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "senderId": self.sender_id,
            "nickname": self.nickname,
            "text": self.text,
            "scope": self.scope.value,
            "createdAt": self.created_at,
        }
