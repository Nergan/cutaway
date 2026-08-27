"""Ingress quotas shared by HTTP and WebSocket project proxies."""

from __future__ import annotations

import asyncio
import time
from collections import deque
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import AsyncIterator

from .config import ProjectConfig


@dataclass(frozen=True)
class PolicyViolation(Exception):
    status_code: int
    detail: str
    retry_after: int | None = None

    def __str__(self) -> str:
        return self.detail


class ProjectGovernor:
    def __init__(self, project: ProjectConfig):
        self.project = project
        self._request_slots = asyncio.Semaphore(max(1, project.limits.max_concurrency))
        self._request_hits: dict[str, deque[float]] = {}
        self._traffic: deque[tuple[float, int]] = deque()
        self._traffic_total = 0
        self._active_websockets = 0
        self._last_gc = 0.0

    def _collect(self, now: float) -> None:
        request_cutoff = now - self.project.limits.request_window_seconds
        if now - self._last_gc >= self.project.limits.request_window_seconds:
            stale = [
                key
                for key, hits in self._request_hits.items()
                if not hits or hits[-1] < request_cutoff
            ]
            for key in stale:
                del self._request_hits[key]
            self._last_gc = now

        traffic_cutoff = now - 60
        while self._traffic and self._traffic[0][0] < traffic_cutoff:
            _, amount = self._traffic.popleft()
            self._traffic_total -= amount

    def admit_request(self, client_key: str, content_length: str | None) -> None:
        limits = self.project.limits
        if content_length is not None:
            try:
                declared = int(content_length)
            except ValueError as exc:
                raise PolicyViolation(400, "Malformed Content-Length.") from exc
            if declared < 0:
                raise PolicyViolation(400, "Malformed Content-Length.")
            if limits.request_bytes and declared > limits.request_bytes:
                raise PolicyViolation(413, "Project request body limit exceeded.")

        now = time.monotonic()
        self._collect(now)
        if limits.request_rate <= 0:
            return
        hits = self._request_hits.setdefault(client_key, deque())
        cutoff = now - limits.request_window_seconds
        while hits and hits[0] < cutoff:
            hits.popleft()
        if len(hits) >= limits.request_rate:
            retry_after = max(1, int(hits[0] + limits.request_window_seconds - now))
            raise PolicyViolation(429, "Project request rate limit exceeded.", retry_after)
        hits.append(now)

    def record_traffic(self, amount: int) -> None:
        if amount <= 0:
            return
        now = time.monotonic()
        self._collect(now)
        limit = self.project.limits.traffic_bytes_per_minute
        if limit and self._traffic_total + amount > limit:
            raise PolicyViolation(429, "Project traffic budget exceeded.", 60)
        self._traffic.append((now, amount))
        self._traffic_total += amount

    @asynccontextmanager
    async def request_slot(self) -> AsyncIterator[None]:
        try:
            await asyncio.wait_for(
                self._request_slots.acquire(),
                timeout=self.project.limits.queue_timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            raise PolicyViolation(503, "Project concurrency limit reached.", 1) from exc
        try:
            yield
        finally:
            self._request_slots.release()

    @asynccontextmanager
    async def websocket_slot(self) -> AsyncIterator[None]:
        maximum = self.project.limits.max_websockets
        if maximum <= 0:
            raise PolicyViolation(403, "WebSockets are disabled for this project.")
        if self._active_websockets >= maximum:
            raise PolicyViolation(503, "Project WebSocket limit reached.", 5)
        self._active_websockets += 1
        try:
            yield
        finally:
            self._active_websockets -= 1
