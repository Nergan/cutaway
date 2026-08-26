"""Request guards for the hub's unauthenticated write endpoints.

The hub serves every plugin from a single uvicorn worker, so per-process
counters here are effectively global. Nothing survives a restart, which is
acceptable: the goal is to blunt storage spam and oversized payloads, not to
enforce durable quotas.
"""

import time
from collections import deque
from typing import Callable, Deque, Dict

from fastapi import HTTPException, Request


def body_size_limit(max_bytes: int) -> Callable:
    """Reject oversized bodies before FastAPI buffers and validates them.

    Pydantic's max_length runs after the whole body is already in memory, so
    the check has to happen while it is still just a header.
    """

    async def guard(request: Request) -> None:
        declared = request.headers.get("content-length")
        if declared is None:
            return
        try:
            length = int(declared)
        except ValueError:
            raise HTTPException(status_code=400, detail="Malformed Content-Length.")
        if length > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"Payload exceeds the {max_bytes // 1024} KiB limit.",
            )

    return guard


class RateLimiter:
    """Sliding-window limiter keyed by client address, usable as a dependency."""

    def __init__(self, limit: int, window_seconds: int):
        self.limit = limit
        self.window = window_seconds
        self._hits: Dict[str, Deque[float]] = {}
        self._last_gc = 0.0

    @staticmethod
    def _client_key(request: Request) -> str:
        # uvicorn runs with --forwarded-allow-ips, so client.host is the real peer.
        return request.client.host if request.client else "unknown"

    def _collect_garbage(self, now: float) -> None:
        """Keep idle clients from accumulating in memory forever."""
        if now - self._last_gc < self.window:
            return
        self._last_gc = now
        cutoff = now - self.window
        stale = [key for key, hits in self._hits.items() if not hits or hits[-1] < cutoff]
        for key in stale:
            del self._hits[key]

    async def __call__(self, request: Request) -> None:
        now = time.monotonic()
        self._collect_garbage(now)

        hits = self._hits.setdefault(self._client_key(request), deque())
        cutoff = now - self.window
        while hits and hits[0] < cutoff:
            hits.popleft()

        if len(hits) >= self.limit:
            retry_after = max(1, int(hits[0] + self.window - now))
            raise HTTPException(
                status_code=429,
                detail="Too many requests. Please slow down.",
                headers={"Retry-After": str(retry_after)},
            )

        hits.append(now)
