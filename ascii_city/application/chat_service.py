"""Chat validation, rate limiting and message construction."""

from __future__ import annotations

from collections import deque
from itertools import count

from ..domain.chat import ChatMessage, ChatScope, sanitise_chat_text
from ..domain.constants import CHAT_RATE_LIMIT, CHAT_RATE_WINDOW_S
from ..domain.errors import ChatRejected
from ..domain.player import PlayerState
from ..domain.ports import ClockPort


class ChatService:
    """Owns everything that must happen before a message reaches other players."""

    def __init__(self, clock: ClockPort) -> None:
        self._clock = clock
        self._history: dict[int, deque[float]] = {}
        self._ids = count(1)

    def forget(self, player_id: int) -> None:
        self._history.pop(player_id, None)

    def compose(self, sender: PlayerState, scope: ChatScope, raw_text: str) -> ChatMessage:
        """Validate, rate limit and build a broadcastable message.

        Raises :class:`ChatRejected` with a reason the caller can show the user.
        """
        if scope is ChatScope.SYSTEM:
            raise ChatRejected("Players cannot send system messages.")
        text = sanitise_chat_text(raw_text)
        self._charge(sender.id)
        return ChatMessage(
            id=next(self._ids),
            sender_id=sender.id,
            nickname=sender.nickname,
            text=text,
            scope=scope,
            created_at=self._clock.wall(),
        )

    def system(self, text: str) -> ChatMessage:
        return ChatMessage(
            id=next(self._ids),
            sender_id=0,
            nickname="system",
            text=sanitise_chat_text(text),
            scope=ChatScope.SYSTEM,
            created_at=self._clock.wall(),
        )

    def _charge(self, player_id: int) -> None:
        now = self._clock.monotonic()
        window = self._history.setdefault(player_id, deque())
        cutoff = now - CHAT_RATE_WINDOW_S
        while window and window[0] < cutoff:
            window.popleft()
        if len(window) >= CHAT_RATE_LIMIT:
            retry_after = window[0] + CHAT_RATE_WINDOW_S - now
            raise ChatRejected(
                f"Slow down: {CHAT_RATE_LIMIT} messages per {int(CHAT_RATE_WINDOW_S)} seconds.",
                retry_after=max(0.0, retry_after),
            )
        window.append(now)
