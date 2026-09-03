"""In-process adapters. These are the fallback whenever MongoDB is unavailable.

The whole application has to boot without a database: the orchestrator reports
Mongo as ``degraded`` from time to time and local development often runs
without a cluster at all.
"""

from __future__ import annotations

import time
from collections import deque
from typing import Sequence

from ...domain.chat import ChatMessage
from ...domain.ports import ChatArchivePort, ClockPort, TileRepositoryPort, WorldRegistryPort
from ...domain.world import WorldDescriptor


class SystemClock(ClockPort):
    def monotonic(self) -> float:
        return time.monotonic()

    def wall(self) -> float:
        return time.time()


class ManualClock(ClockPort):
    """Test double. Advancing time is explicit, so tests never sleep."""

    def __init__(self, start: float = 1_000.0) -> None:
        self._monotonic = start
        self._wall = 1_700_000_000.0

    def advance(self, seconds: float) -> None:
        self._monotonic += seconds
        self._wall += seconds

    def monotonic(self) -> float:
        return self._monotonic

    def wall(self) -> float:
        return self._wall


class InMemoryTileRepository(TileRepositoryPort):
    def __init__(self) -> None:
        self._tiles: dict[tuple[str, int, int, int], bytes] = {}

    async def load(self, world_id: str, tile_x: int, tile_y: int, version: int) -> bytes | None:
        return self._tiles.get((world_id, tile_x, tile_y, version))

    async def save(
        self, world_id: str, tile_x: int, tile_y: int, version: int, payload: bytes
    ) -> None:
        self._tiles[(world_id, tile_x, tile_y, version)] = payload


class InMemoryWorldRegistry(WorldRegistryPort):
    def __init__(self) -> None:
        self._worlds: dict[str, WorldDescriptor] = {}

    async def get(self, world_id: str) -> WorldDescriptor | None:
        return self._worlds.get(world_id)

    async def put(self, descriptor: WorldDescriptor) -> None:
        self._worlds[descriptor.id] = descriptor


class InMemoryChatArchive(ChatArchivePort):
    def __init__(self, capacity: int = 200) -> None:
        self._rooms: dict[str, deque[ChatMessage]] = {}
        self._capacity = capacity

    async def append(self, room_id: str, message: ChatMessage) -> None:
        room = self._rooms.setdefault(room_id, deque(maxlen=self._capacity))
        room.append(message)

    async def recent(self, room_id: str, limit: int) -> Sequence[ChatMessage]:
        room = self._rooms.get(room_id)
        if not room:
            return ()
        return tuple(room)[-limit:]
