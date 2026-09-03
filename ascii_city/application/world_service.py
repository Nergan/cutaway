"""Loads the live district and serves its tiles.

Order of preference: the tile cache, then regeneration from the registered
seed. Generation runs on a worker thread because it is CPU bound and the event
loop is also carrying the simulation.
"""

from __future__ import annotations

import asyncio
import gzip
import logging
from dataclasses import dataclass

from ..domain.errors import WorldDataError
from ..domain.ports import TileRepositoryPort, WorldGeneratorPort, WorldRegistryPort
from ..domain.world import World, WorldDescriptor, WorldTile
from ..infrastructure.rng import digest_bytes
from ..infrastructure.tile_codec import decode_tile, encode_tile

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class EncodedTile:
    """A tile prepared once and then served to every client unchanged."""

    raw: bytes
    gzipped: bytes
    etag: str

    @property
    def raw_size(self) -> int:
        return len(self.raw)


class WorldService:
    def __init__(
        self,
        *,
        generator: WorldGeneratorPort,
        tiles: TileRepositoryPort,
        registry: WorldRegistryPort,
        world_id: str,
        seed: int,
        version: int,
        tiles_x: int,
        tiles_y: int,
        tile_cells: int,
        cell_size: float,
    ) -> None:
        self._generator = generator
        self._tiles = tiles
        self._registry = registry
        self._requested = WorldDescriptor(
            id=world_id,
            version=version,
            seed=seed,
            tiles_x=tiles_x,
            tiles_y=tiles_y,
            tile_cells=tile_cells,
            cell_size=cell_size,
            source=generator.source,
        )
        self._world: World | None = None
        self._encoded: dict[tuple[int, int], EncodedTile] = {}
        self._lock = asyncio.Lock()

    @property
    def world(self) -> World:
        if self._world is None:
            raise WorldDataError("The world has not been loaded yet.")
        return self._world

    @property
    def loaded(self) -> bool:
        return self._world is not None

    async def load(self) -> World:
        async with self._lock:
            if self._world is not None:
                return self._world

            descriptor = await self._resolve_descriptor()
            tiles = await self._load_cached(descriptor)
            if tiles is None:
                tiles = await self._generate(descriptor)

            self._world = World.from_tiles(descriptor, tiles)
            logger.info(
                "World %s ready: %d tiles, %d buildings, %d spawn points, %d KiB encoded",
                descriptor.id,
                len(tiles),
                sum(len(tile.buildings) for tile in tiles),
                len(self._world.spawn_points),
                sum(item.raw_size for item in self._encoded.values()) // 1024,
            )
            return self._world

    def encoded_tile(self, tile_x: int, tile_y: int) -> EncodedTile | None:
        return self._encoded.get((tile_x, tile_y))

    async def _resolve_descriptor(self) -> WorldDescriptor:
        """Reuse the registered district unless its shape no longer matches config."""
        stored = await self._registry.get(self._requested.id)
        if stored is not None and _same_shape(stored, self._requested):
            return stored
        if stored is not None:
            logger.info(
                "World %s changed shape (v%d -> v%d); registering the new district.",
                self._requested.id,
                stored.version,
                self._requested.version,
            )
        await self._registry.put(self._requested)
        return self._requested

    async def _load_cached(self, descriptor: WorldDescriptor) -> list[WorldTile] | None:
        tiles: list[WorldTile] = []
        for tile_y in range(descriptor.tiles_y):
            for tile_x in range(descriptor.tiles_x):
                payload = await self._tiles.load(
                    descriptor.id, tile_x, tile_y, descriptor.version
                )
                if payload is None:
                    return None
                try:
                    tiles.append(decode_tile(payload))
                except WorldDataError as exc:
                    logger.warning("Cached tile %d,%d is unusable: %s", tile_x, tile_y, exc)
                    return None
                self._remember(tile_x, tile_y, payload)
        logger.info("World %s restored from the tile cache.", descriptor.id)
        return tiles

    async def _generate(self, descriptor: WorldDescriptor) -> list[WorldTile]:
        self._encoded.clear()
        tiles = list(await asyncio.to_thread(self._generator.generate_tiles, descriptor))
        for tile in tiles:
            payload = encode_tile(tile)
            self._remember(tile.tile_x, tile.tile_y, payload)
            await self._tiles.save(descriptor.id, tile.tile_x, tile.tile_y, descriptor.version, payload)
        return tiles

    def _remember(self, tile_x: int, tile_y: int, payload: bytes) -> None:
        self._encoded[(tile_x, tile_y)] = EncodedTile(
            raw=payload,
            # mtime is pinned so the same tile always produces the same bytes.
            gzipped=gzip.compress(payload, compresslevel=6, mtime=0),
            etag=f'W/"{digest_bytes(payload):08x}"',
        )


def _same_shape(left: WorldDescriptor, right: WorldDescriptor) -> bool:
    return (
        left.version == right.version
        and left.seed == right.seed
        and left.tiles_x == right.tiles_x
        and left.tiles_y == right.tiles_y
        and left.tile_cells == right.tile_cells
        and left.cell_size == right.cell_size
    )
