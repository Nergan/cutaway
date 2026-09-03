"""Domain-level failures. Transport layers translate these into codes."""

from __future__ import annotations


class AsciiCityError(Exception):
    """Base class for every failure this project raises deliberately."""


class WorldDataError(AsciiCityError):
    """A tile, building or grid violates the world format."""


class ProtocolError(AsciiCityError):
    """A client frame is malformed, truncated or unknown."""


class RoomFullError(AsciiCityError):
    """The room already holds its maximum number of players."""


class ChatRejected(AsciiCityError):
    """A chat message failed validation or rate limiting."""

    def __init__(self, reason: str, *, retry_after: float | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.retry_after = retry_after
