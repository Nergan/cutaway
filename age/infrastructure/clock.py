"""Clock implementations for the :class:`~age.domain.ports.Clock` port."""

from __future__ import annotations

import time


class MonotonicClock:
    """Wall-independent time for the running server.

    ``perf_counter`` rather than ``time.time`` because the simulation must not be
    affected by an NTP correction or a daylight-saving change. It has no meaningful
    epoch, which is fine: every consumer works in differences.
    """

    __slots__ = ()

    def now(self) -> float:
        return time.perf_counter()


class ManualClock:
    """A clock that only moves when told to.

    Determinism tests need exact tick boundaries and the accordion tests need to
    jump fifteen minutes without waiting. Both are impossible against a real clock
    and trivial against this one.
    """

    __slots__ = ("_now",)

    def __init__(self, start: float = 0.0) -> None:
        self._now = start

    def now(self) -> float:
        return self._now

    def advance(self, seconds: float) -> float:
        """Step forward. Refuses to go backwards, as the port requires."""
        if seconds < 0.0:
            raise ValueError("a monotonic clock cannot go backwards")
        self._now += seconds
        return self._now

    def set(self, value: float) -> None:
        if value < self._now:
            raise ValueError("a monotonic clock cannot go backwards")
        self._now = value
