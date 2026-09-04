"""One client's socket, with an outbound queue and a writer task.

The room encodes packets synchronously inside the tick and drops them here; a task
per connection drains the queue onto the socket. That is what stops one slow reader
from stalling the world: back-pressure lands in that client's queue rather than in
the loop's frame budget.

A queue that fills is a client that is not keeping up. It is marked broken and the
room drops it on the next snapshot round, which is the honest outcome: continuing to
buffer for a client that cannot read would trade the whole room's memory for one
player's connection.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Protocol

from ..domain.entities import EntityId

logger = logging.getLogger(__name__)

# Roughly two seconds of snapshots plus room for a burst of spawns. Beyond this the
# client is not going to catch up and the buffered frames are already stale.
MAX_QUEUED_FRAMES = 96


class Transport(Protocol):
    """What a connection needs from a socket. Keeps the room testable."""

    async def send_bytes(self, payload: bytes) -> None: ...

    async def close(self, code: int, reason: str) -> None: ...


class Connection:
    """A queued, non-blocking writer for one client."""

    __slots__ = (
        "session_id",
        "transport",
        "entity_id",
        "known_entity_ids",
        "failure",
        "_queue",
        "_writer",
        "_closed",
    )

    def __init__(self, session_id: str, transport: Transport) -> None:
        self.session_id = session_id
        self.transport = transport
        self.entity_id: EntityId | None = None
        # A view of the session's known set, so the room can decide whether a
        # despawn is worth sending without reaching into the simulation.
        self.known_entity_ids: set[EntityId] = set()
        self.failure: str | None = None
        self._queue: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=MAX_QUEUED_FRAMES)
        self._writer: asyncio.Task[None] | None = None
        self._closed = False

    def start(self) -> None:
        if self._writer is None:
            self._writer = asyncio.create_task(
                self._drain(), name=f"age-writer-{self.session_id}"
            )

    @property
    def is_broken(self) -> bool:
        return self.failure is not None

    def enqueue(self, frame: bytes) -> None:
        """Queue a frame. Never blocks, never raises."""
        if self._closed or self.failure is not None:
            return
        try:
            self._queue.put_nowait(frame)
        except asyncio.QueueFull:
            self.failure = "The client stopped reading."

    async def _drain(self) -> None:
        """Write queued frames until closed.

        Coalesces whatever is already queued into one batch of awaits, so a burst of
        spawns costs one wakeup rather than one per packet.
        """
        try:
            while True:
                frame = await self._queue.get()
                if frame is None:
                    return
                await self.transport.send_bytes(frame)

                while not self._queue.empty():
                    following = self._queue.get_nowait()
                    if following is None:
                        return
                    await self.transport.send_bytes(following)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.failure = f"{type(exc).__name__}: {exc}"

    async def close(self, code: int = 1000, reason: str = "") -> None:
        if self._closed:
            return
        self._closed = True

        # Sentinel first so the writer finishes what it has rather than being
        # cancelled mid-frame, which would send a truncated packet.
        try:
            self._queue.put_nowait(None)
        except asyncio.QueueFull:
            pass

        if self._writer is not None:
            try:
                await asyncio.wait_for(self._writer, timeout=1.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._writer.cancel()
            except Exception:
                logger.debug("Writer for %s ended badly.", self.session_id, exc_info=True)
            self._writer = None

        try:
            await self.transport.close(code, reason[:120])
        except Exception:
            logger.debug("Could not close the socket for %s.", self.session_id, exc_info=True)
