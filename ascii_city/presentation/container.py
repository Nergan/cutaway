"""Composition root: chooses adapters and wires the application services.

World preparation runs as a background task so an isolated worker answers its
readiness probe immediately. Endpoints await :meth:`Container.ready`, and the
client shows its loading overlay until that resolves.
"""

from __future__ import annotations

import asyncio
import logging

from ..application.chat_service import ChatService
from ..application.room import CityRoom
from ..application.world_service import WorldService
from ..config import Settings, load_settings
from ..domain.ports import ChatArchivePort, ClockPort, TileRepositoryPort, WorldRegistryPort
from ..infrastructure.generator import DistrictGenerator
from ..infrastructure.repositories.memory import (
    InMemoryChatArchive,
    InMemoryTileRepository,
    InMemoryWorldRegistry,
    SystemClock,
)

logger = logging.getLogger(__name__)


class Container:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or load_settings()
        self.clock: ClockPort = SystemClock()
        self.storage_backend = "memory"
        self._tiles: TileRepositoryPort = InMemoryTileRepository()
        self._registry: WorldRegistryPort = InMemoryWorldRegistry()
        self._archive: ChatArchivePort = InMemoryChatArchive()
        self._world_service: WorldService | None = None
        self._room: CityRoom | None = None
        self._ready: asyncio.Task[None] | None = None
        self._error: str | None = None

    # --- lifecycle ---------------------------------------------------------

    async def startup(self) -> None:
        if self.settings.use_mongo:
            self._attach_mongo()
        self._world_service = WorldService(
            generator=DistrictGenerator(),
            tiles=self._tiles,
            registry=self._registry,
            world_id=self.settings.world_id,
            seed=self.settings.world_seed,
            version=self.settings.world_version,
            tiles_x=self.settings.tiles_x,
            tiles_y=self.settings.tiles_y,
            tile_cells=self.settings.tile_cells,
            cell_size=self.settings.cell_size,
        )
        self._ready = asyncio.create_task(self._prepare(), name="ascii-city-world")

    async def shutdown(self) -> None:
        if self._ready is not None and not self._ready.done():
            self._ready.cancel()
        if self._room is not None:
            await self._room.stop()
            self._room = None
        self._ready = None

    def _attach_mongo(self) -> None:
        """Fall back to in-process storage when the cluster is not reachable."""
        try:
            import shared_mongo

            from ..infrastructure.repositories.mongo import (
                DATABASE_NAME,
                MongoChatArchive,
                MongoTileRepository,
                MongoWorldRegistry,
            )

            database = shared_mongo.get_client()[DATABASE_NAME]
            self._tiles = MongoTileRepository(database)
            self._registry = MongoWorldRegistry(database)
            self._archive = MongoChatArchive(database)
            self.storage_backend = "mongodb"
        except Exception as exc:
            logger.warning("MongoDB adapters unavailable, using in-memory storage: %s", exc)

    async def _prepare(self) -> None:
        assert self._world_service is not None
        if isinstance(self._archive, object) and hasattr(self._archive, "ensure_indexes"):
            await self._archive.ensure_indexes()  # type: ignore[attr-defined]
        world = await self._world_service.load()
        self._room = CityRoom(
            room_id=self.settings.room_id,
            world=world,
            chat=ChatService(self.clock),
            archive=self._archive,
            clock=self.clock,
            max_clients=self.settings.max_clients,
        )
        await self._room.start()

    async def ready(self) -> None:
        """Block until the district is playable, re-raising any load failure."""
        if self._ready is None:
            raise RuntimeError("Container.startup() has not run.")
        try:
            await asyncio.shield(self._ready)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._error = f"{type(exc).__name__}: {exc}"
            raise

    # --- accessors ---------------------------------------------------------

    @property
    def is_ready(self) -> bool:
        return self._ready is not None and self._ready.done() and self._ready.exception() is None

    @property
    def error(self) -> str | None:
        if self._error:
            return self._error
        if self._ready is not None and self._ready.done():
            exception = self._ready.exception()
            if exception is not None:
                return f"{type(exception).__name__}: {exception}"
        return None

    @property
    def world_service(self) -> WorldService:
        if self._world_service is None:
            raise RuntimeError("Container.startup() has not run.")
        return self._world_service

    @property
    def room(self) -> CityRoom:
        if self._room is None:
            raise RuntimeError("The city room is not running yet.")
        return self._room


_container: Container | None = None


def get_container() -> Container:
    global _container
    if _container is None:
        _container = Container()
    return _container


def reset_container(container: Container | None = None) -> Container:
    """Replace the process-wide container. Tests use this to inject fakes."""
    global _container
    _container = container or Container()
    return _container
