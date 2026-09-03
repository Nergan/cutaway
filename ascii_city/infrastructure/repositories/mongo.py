"""MongoDB adapters backed by the shared cluster.

Every method degrades to a cache miss instead of raising. A district can always
be regenerated from its seed, and chat history is a convenience rather than a
requirement, so a database outage must never take the room down.
"""

from __future__ import annotations

import logging
from typing import Any, Sequence

from bson.binary import Binary
from pymongo.errors import PyMongoError

from ...domain.chat import ChatMessage, ChatScope
from ...domain.ports import ChatArchivePort, TileRepositoryPort, WorldRegistryPort
from ...domain.world import WorldDescriptor

logger = logging.getLogger(__name__)

DATABASE_NAME = "ascii_city"
TILE_COLLECTION = "tiles"
WORLD_COLLECTION = "worlds"
CHAT_COLLECTION = "chat_log"


class MongoTileRepository(TileRepositoryPort):
    """Caches encoded tiles so a worker restart does not regenerate the district.

    A 128 x 128 tile is roughly 55 KB, three orders of magnitude below the
    16 MB document ceiling, so the payload lives inline as BSON binary rather
    than in GridFS.
    """

    def __init__(self, database: Any) -> None:
        self._collection = database[TILE_COLLECTION]

    @staticmethod
    def _key(world_id: str, tile_x: int, tile_y: int, version: int) -> str:
        return f"{world_id}:{tile_x}:{tile_y}:v{version}"

    async def load(self, world_id: str, tile_x: int, tile_y: int, version: int) -> bytes | None:
        try:
            document = await self._collection.find_one(
                {"_id": self._key(world_id, tile_x, tile_y, version)}
            )
        except PyMongoError as exc:
            logger.warning("Tile cache read failed, regenerating instead: %s", exc)
            return None
        if not document:
            return None
        payload = document.get("payload")
        return bytes(payload) if payload is not None else None

    async def save(
        self, world_id: str, tile_x: int, tile_y: int, version: int, payload: bytes
    ) -> None:
        try:
            await self._collection.update_one(
                {"_id": self._key(world_id, tile_x, tile_y, version)},
                {
                    "$set": {
                        "worldId": world_id,
                        "tileX": tile_x,
                        "tileY": tile_y,
                        "version": version,
                        "bytes": len(payload),
                        "payload": Binary(payload),
                    }
                },
                upsert=True,
            )
        except PyMongoError as exc:
            logger.warning("Tile cache write failed, continuing without it: %s", exc)


class MongoWorldRegistry(WorldRegistryPort):
    """Keeps the live district stable across restarts by pinning its seed."""

    def __init__(self, database: Any) -> None:
        self._collection = database[WORLD_COLLECTION]

    async def get(self, world_id: str) -> WorldDescriptor | None:
        try:
            document = await self._collection.find_one({"_id": world_id})
        except PyMongoError as exc:
            logger.warning("World registry read failed: %s", exc)
            return None
        if not document:
            return None
        try:
            return WorldDescriptor(
                id=world_id,
                version=int(document["version"]),
                seed=int(document["seed"]),
                tiles_x=int(document["tilesX"]),
                tiles_y=int(document["tilesY"]),
                tile_cells=int(document["tileCells"]),
                cell_size=float(document["cellSize"]),
                source=str(document.get("source", "procedural")),
            )
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("World registry document for %s is unusable: %s", world_id, exc)
            return None

    async def put(self, descriptor: WorldDescriptor) -> None:
        try:
            await self._collection.update_one(
                {"_id": descriptor.id},
                {
                    "$set": {
                        "version": descriptor.version,
                        "seed": descriptor.seed,
                        "tilesX": descriptor.tiles_x,
                        "tilesY": descriptor.tiles_y,
                        "tileCells": descriptor.tile_cells,
                        "cellSize": descriptor.cell_size,
                        "source": descriptor.source,
                    }
                },
                upsert=True,
            )
        except PyMongoError as exc:
            logger.warning("World registry write failed: %s", exc)


class MongoChatArchive(ChatArchivePort):
    """Stores the tail of the conversation so a joining player has context."""

    def __init__(self, database: Any, retention_seconds: int = 86_400) -> None:
        self._collection = database[CHAT_COLLECTION]
        self._retention_seconds = retention_seconds
        self._indexed = False

    async def ensure_indexes(self) -> None:
        if self._indexed:
            return
        try:
            await self._collection.create_index(
                "createdAt", expireAfterSeconds=self._retention_seconds
            )
            await self._collection.create_index([("roomId", 1), ("createdAt", -1)])
            self._indexed = True
        except PyMongoError as exc:
            logger.warning("Chat archive indexes unavailable: %s", exc)

    async def append(self, room_id: str, message: ChatMessage) -> None:
        try:
            await self._collection.insert_one(
                {
                    "roomId": room_id,
                    "messageId": message.id,
                    "senderId": message.sender_id,
                    "nickname": message.nickname,
                    "text": message.text,
                    "scope": message.scope.value,
                    "createdAt": message.created_at,
                }
            )
        except PyMongoError as exc:
            logger.warning("Chat archive write failed: %s", exc)

    async def recent(self, room_id: str, limit: int) -> Sequence[ChatMessage]:
        try:
            cursor = (
                self._collection.find({"roomId": room_id, "scope": ChatScope.GLOBAL.value})
                .sort("createdAt", -1)
                .limit(limit)
            )
            documents = await cursor.to_list(length=limit)
        except PyMongoError as exc:
            logger.warning("Chat archive read failed: %s", exc)
            return ()
        messages = []
        for document in reversed(documents):
            try:
                messages.append(
                    ChatMessage(
                        id=int(document["messageId"]),
                        sender_id=int(document["senderId"]),
                        nickname=str(document["nickname"]),
                        text=str(document["text"]),
                        scope=ChatScope(document["scope"]),
                        created_at=float(document["createdAt"]),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        return tuple(messages)
