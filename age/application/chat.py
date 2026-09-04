"""Chat: routing, rate limiting, and history.

GDD 1.2 puts social interaction first, so chat is a core system rather than a
utility. There are three channels and each has a different audience: local is
proximity-based, global reaches everyone, and system is server-authored.

Rate limiting is per session and sliding-window rather than a fixed cooldown, so a
player can send a burst in conversation but cannot sustain a flood.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from ..domain.constants import (
    CHANNEL_GLOBAL,
    CHANNEL_LOCAL,
    CHANNEL_SYSTEM,
    CHAT_HISTORY_SIZE,
    CHAT_MAX_LENGTH,
    CHAT_PROXIMITY_RADIUS_TILES,
    CHAT_RATE_LIMIT,
    CHAT_RATE_WINDOW_S,
)
from ..domain.entities import Entity, EntityId, PlayerSession
from .world import World


@dataclass(frozen=True, slots=True)
class ChatMessage:
    sender_id: EntityId
    sender_name: str
    channel: int
    text: str
    at: float


@dataclass(frozen=True, slots=True)
class ChatDecision:
    """Whether a message is allowed, and who should receive it."""

    accepted: bool
    message: ChatMessage | None = None
    recipients: tuple[EntityId, ...] = ()
    reason: str = ""


class ChatService:
    """Validates and routes chat, and keeps a short scrollback."""

    __slots__ = ("_history",)

    def __init__(self) -> None:
        self._history: deque[ChatMessage] = deque(maxlen=CHAT_HISTORY_SIZE)

    @property
    def history(self) -> list[ChatMessage]:
        return list(self._history)

    def submit(
        self,
        world: World,
        session: PlayerSession,
        speaker: Entity,
        channel: int,
        text: str,
        now: float,
    ) -> ChatDecision:
        """Validate a player message and work out its audience."""
        cleaned = sanitise(text)
        if not cleaned:
            return ChatDecision(accepted=False, reason="empty")

        if channel not in (CHANNEL_LOCAL, CHANNEL_GLOBAL):
            return ChatDecision(accepted=False, reason="bad_channel")

        if not self._allow(session, now):
            return ChatDecision(accepted=False, reason="rate_limited")

        message = ChatMessage(
            sender_id=speaker.entity_id,
            sender_name=speaker.name,
            channel=channel,
            text=cleaned,
            at=now,
        )
        self._history.append(message)

        if channel == CHANNEL_GLOBAL:
            recipients = tuple(entity.entity_id for entity in world.players)
        else:
            recipients = tuple(
                entity.entity_id
                for entity in world.entities_near(speaker.position, CHAT_PROXIMITY_RADIUS_TILES)
                if entity.is_player
            )

        return ChatDecision(accepted=True, message=message, recipients=recipients)

    def system(self, text: str, now: float) -> ChatMessage:
        """Record a server-authored line. Never rate limited."""
        message = ChatMessage(
            sender_id=0, sender_name="", channel=CHANNEL_SYSTEM, text=text, at=now
        )
        self._history.append(message)
        return message

    def _allow(self, session: PlayerSession, now: float) -> bool:
        """Sliding window: at most ``CHAT_RATE_LIMIT`` in the last window."""
        stamps = session.chat_timestamps
        cutoff = now - CHAT_RATE_WINDOW_S
        while stamps and stamps[0] < cutoff:
            stamps.popleft()
        if len(stamps) >= CHAT_RATE_LIMIT:
            return False
        stamps.append(now)
        return True


def sanitise(text: str) -> str:
    """Strip control characters, collapse whitespace, and clip to the limit.

    Control characters are removed rather than escaped because they have no
    legitimate use in chat and every renderer handles them differently. Newlines
    become spaces so one message cannot occupy the whole chat pane.
    """
    filtered = "".join(
        " " if character in "\r\n\t" else character
        for character in text
        if character.isprintable() or character in "\r\n\t"
    )
    return " ".join(filtered.split())[:CHAT_MAX_LENGTH]
