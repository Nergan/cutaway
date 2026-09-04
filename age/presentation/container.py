"""Composition root: picks the adapters and wires the world together.

The only place in the project that knows both a port and its implementation. Startup
happens as a background task so an isolated worker answers its readiness probe
immediately, and endpoints await :meth:`Container.ready`.

Storage degrades on purpose. If MongoDB is unreachable the world runs on the
in-memory repositories and says so in the health payload, because a demo that shows
a broken page because a free-tier cluster is asleep demonstrates nothing.
"""

from __future__ import annotations

import asyncio
import logging

from ..application.accordion import WorldManager
from ..application.chat import ChatService
from ..application.events import EventQueue
from ..application.session import SessionService
from ..application.simulation import Simulation
from ..application.world import World, build_default_world
from ..config import Settings, load_settings
from ..domain.ports import (
    CharacterRepository,
    Clock,
    TerrainOverlayRepository,
    TopologyRepository,
)
from ..infrastructure.clock import MonotonicClock
from ..infrastructure.generator import WorldGenerator
from ..infrastructure.memory_repositories import (
    MemoryCharacterRepository,
    MemoryTerrainOverlayRepository,
    MemoryTopologyRepository,
)
from .room import Room

logger = logging.getLogger(__name__)

# How long a restore may spend on storage before the world opens without it. The
# shared cluster is a free tier that sleeps, and the alternative to a budget here is
# a world that never becomes ready because it is waiting on a connect timeout per
# read. Everything read at bootstrap is reconstructible, so giving up is safe.
STORAGE_READ_BUDGET_SECONDS = 5.0


class Container:
    """Owns every long-lived object in the process."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or load_settings()
        self.clock: Clock = MonotonicClock()
        self.storage_backend = "memory"
        self.events = EventQueue()

        self._overlays: TerrainOverlayRepository = MemoryTerrainOverlayRepository()
        self._characters: CharacterRepository = MemoryCharacterRepository()
        self._topology: TopologyRepository = MemoryTopologyRepository()

        self._world: World | None = None
        self._room: Room | None = None
        self._ready: asyncio.Task[None] | None = None
        self._error: str | None = None

    # --- lifecycle -----------------------------------------------------------

    async def startup(self) -> None:
        if self.settings.use_mongo:
            self._attach_mongo()
        self._ready = asyncio.create_task(self._prepare(), name="age-bootstrap")

    async def shutdown(self) -> None:
        if self._ready is not None and not self._ready.done():
            self._ready.cancel()
        if self._room is not None:
            await self._room.stop()
            self._room = None
        self._world = None
        self._ready = None

    def _attach_mongo(self) -> None:
        """Swap in the MongoDB adapters, or keep the in-memory ones."""
        try:
            import shared_mongo

            from ..infrastructure.mongo_repositories import (
                DATABASE_NAME,
                MongoCharacterRepository,
                MongoTerrainOverlayRepository,
                MongoTopologyRepository,
            )

            database = shared_mongo.get_client()[DATABASE_NAME]
            self._overlays = MongoTerrainOverlayRepository(database)
            self._characters = MongoCharacterRepository(database)
            self._topology = MongoTopologyRepository(database)
            self.storage_backend = "mongodb"
        except Exception as exc:
            logger.warning("MongoDB adapters unavailable, using in-memory storage: %s", exc)

    async def _prepare(self) -> None:
        """Build the world, restore what was persisted, and start ticking."""
        generator = WorldGenerator(world_seed=self.settings.world_seed)
        world = build_default_world(
            world_seed=self.settings.world_seed,
            clock=self.clock,
            generator=generator,
            segments=self.settings.corridor_segments,
        )
        self._world = world

        manager = WorldManager(
            world,
            self.events,
            topology_repository=self._topology,
            cooldown_seconds=self.settings.tier_cooldown_seconds,
        )

        # Restoring before bootstrap so the tier that comes back is the tier that
        # gets its chunks activated, rather than tier 0 followed by an expansion.
        stored = await self._restore_topology(world.edge.edge_id)
        if stored:
            manager.restore(stored, self.clock.now())

        manager.bootstrap(self.clock.now())

        simulation = Simulation(
            world=world,
            manager=manager,
            sessions=SessionService(world, self._characters),
            chat=ChatService(),
            events=self.events,
            overlays=self._overlays,
            allow_dev_controls=self.settings.allow_dev_controls,
        )

        try:
            async with asyncio.timeout(STORAGE_READ_BUDGET_SECONDS):
                await simulation.load_overlays()
        except TimeoutError:
            logger.warning("Terrain edits took too long to read, serving generated terrain.")
        except Exception as exc:
            logger.warning("Could not restore terrain edits: %s", exc)

        self._room = Room(simulation, max_clients=self.settings.max_clients)
        await self._room.start()

        logger.info(
            "Age world %s ready: seed %#x, %d segments, storage %s",
            self.settings.world_id,
            self.settings.world_seed,
            self.settings.corridor_segments,
            self.storage_backend,
        )

    async def _restore_topology(self, edge_id: str) -> dict[str, object] | None:
        """Read the stored accordion state, or give up and start fresh."""
        try:
            async with asyncio.timeout(STORAGE_READ_BUDGET_SECONDS):
                return await self._topology.load(edge_id)
        except TimeoutError:
            logger.warning("Stored topology took too long to read, starting at tier 0.")
        except Exception as exc:
            logger.warning("Could not read stored topology, starting fresh: %s", exc)
        return None

    async def ready(self) -> None:
        """Block until the world is playable, re-raising any startup failure."""
        if self._ready is None:
            raise RuntimeError("Container.startup() has not run.")
        try:
            await asyncio.shield(self._ready)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._error = f"{type(exc).__name__}: {exc}"
            raise

    # --- accessors -----------------------------------------------------------

    @property
    def is_ready(self) -> bool:
        return (
            self._ready is not None
            and self._ready.done()
            and self._ready.exception() is None
        )

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
    def room(self) -> Room:
        if self._room is None:
            raise RuntimeError("The world is not running yet.")
        return self._room

    @property
    def world(self) -> World:
        if self._world is None:
            raise RuntimeError("The world has not been built yet.")
        return self._world


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
