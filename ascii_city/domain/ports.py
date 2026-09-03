"""Ports the application layer depends on. Adapters live in ``infrastructure``."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Sequence

from .chat import ChatMessage
from .world import WorldDescriptor, WorldTile


class WorldGeneratorPort(ABC):
    """Produces tiles for a district. Procedural today, OSM-derived later.

    A whole district is produced at once because road networks have to stay
    continuous across tile seams. A streaming producer would implement the same
    port and return a lazy sequence.
    """

    @property
    @abstractmethod
    def source(self) -> str:
        """Identifier stored with every tile, e.g. ``procedural`` or ``osm``."""

    @abstractmethod
    def generate_tiles(self, descriptor: WorldDescriptor) -> Sequence[WorldTile]:
        ...


class TileRepositoryPort(ABC):
    """Persists encoded tiles so a district survives a worker restart."""

    @abstractmethod
    async def load(self, world_id: str, tile_x: int, tile_y: int, version: int) -> bytes | None:
        ...

    @abstractmethod
    async def save(
        self, world_id: str, tile_x: int, tile_y: int, version: int, payload: bytes
    ) -> None:
        ...


class WorldRegistryPort(ABC):
    """Remembers which seed produced the live district."""

    @abstractmethod
    async def get(self, world_id: str) -> WorldDescriptor | None:
        ...

    @abstractmethod
    async def put(self, descriptor: WorldDescriptor) -> None:
        ...


class ChatArchivePort(ABC):
    """Stores recent chat so a joining player sees the tail of the conversation."""

    @abstractmethod
    async def append(self, room_id: str, message: ChatMessage) -> None:
        ...

    @abstractmethod
    async def recent(self, room_id: str, limit: int) -> Sequence[ChatMessage]:
        ...


class ClockPort(ABC):
    """Injected so tests can advance time without sleeping."""

    @abstractmethod
    def monotonic(self) -> float:
        ...

    @abstractmethod
    def wall(self) -> float:
        ...
