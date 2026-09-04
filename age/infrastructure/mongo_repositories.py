"""MongoDB adapters, on the monorepo's shared Atlas cluster.

One database per project, per the cluster convention, so ``age`` shares the free
M0 tier with the other plugins without sharing collections.

Every method degrades rather than raising, but *how* it degrades differs by
collection, and the difference is the whole point:

Terrain overlays and camps are reconstructible or expendable. A failed read means
generated terrain, a failed write means up to one flush interval of lost digging,
and TDD 9.1 accepts both.

Characters and topology are not. A silent character read failure would present a
returning player with a blank character and then overwrite the real one, so those
reads re-raise as :class:`PersistenceUnavailable` and the caller refuses the login
instead. Losing a session is recoverable; losing a character is not.
"""

from __future__ import annotations

import logging
from typing import Any

from pymongo.errors import PyMongoError

logger = logging.getLogger(__name__)

DATABASE_NAME = "age"
OVERLAY_COLLECTION = "terrain_overlays"
CHARACTER_COLLECTION = "characters"
TOPOLOGY_COLLECTION = "topology"
CAMP_COLLECTION = "camps"


class PersistenceUnavailable(RuntimeError):
    """Raised when a zero-loss read could not be completed."""


class MongoTerrainOverlayRepository:
    """Player tile edits, one document per chunk.

    Tile indices become string keys because BSON has no integer-keyed maps. A chunk
    is 1024 tiles and a heavily worked one might have a few dozen edits, so the
    document stays small; a chunk edited beyond recognition would still be under a
    kilobyte.
    """

    __slots__ = ("_collection",)

    def __init__(self, database: Any) -> None:
        self._collection = database[OVERLAY_COLLECTION]

    async def load(self, chunk_key: str) -> dict[int, int]:
        try:
            document = await self._collection.find_one({"_id": chunk_key})
        except PyMongoError as exc:
            logger.warning("Overlay read for %s failed, using generated terrain: %s", chunk_key, exc)
            return {}
        if not document:
            return {}
        return _decode_overlay(document.get("tiles"))

    async def save_batch(self, overlays: dict[str, dict[int, int]]) -> None:
        if not overlays:
            return

        from pymongo import DeleteOne, UpdateOne

        operations: list[Any] = []
        for chunk_key, changes in overlays.items():
            if changes:
                operations.append(
                    UpdateOne(
                        {"_id": chunk_key},
                        {"$set": {"tiles": {str(index): tile for index, tile in changes.items()}}},
                        upsert=True,
                    )
                )
            else:
                # Edited back to generated terrain: delete the document rather than
                # storing an empty map, so a chunk restored to nature stops costing
                # a read.
                operations.append(DeleteOne({"_id": chunk_key}))

        try:
            await self._collection.bulk_write(operations, ordered=False)
        except PyMongoError as exc:
            logger.warning("Overlay flush of %d chunks failed: %s", len(operations), exc)

    async def clear(self, chunk_key: str) -> None:
        try:
            await self._collection.delete_one({"_id": chunk_key})
        except PyMongoError as exc:
            logger.warning("Overlay clear for %s failed: %s", chunk_key, exc)


class MongoCharacterRepository:
    """Durable character state, keyed by name.

    Reads raise on failure. A character is the one thing in this world a player
    would be genuinely upset to lose, and a read that quietly returns ``None``
    would be followed by a write that destroys it.
    """

    __slots__ = ("_collection",)

    def __init__(self, database: Any) -> None:
        self._collection = database[CHARACTER_COLLECTION]

    async def load(self, character_name: str) -> dict[str, object] | None:
        try:
            document = await self._collection.find_one({"_id": character_name})
        except PyMongoError as exc:
            raise PersistenceUnavailable(
                f"could not read character {character_name!r}"
            ) from exc
        if not document:
            return None
        document.pop("_id", None)
        return document

    async def save(self, character_name: str, payload: dict[str, object]) -> None:
        try:
            await self._collection.update_one(
                {"_id": character_name}, {"$set": payload}, upsert=True
            )
        except PyMongoError as exc:
            logger.error("Character write for %s failed: %s", character_name, exc)


class MongoTopologyRepository:
    """Accordion state, one document per edge."""

    __slots__ = ("_collection",)

    def __init__(self, database: Any) -> None:
        self._collection = database[TOPOLOGY_COLLECTION]

    async def load(self, edge_id: str) -> dict[str, object] | None:
        try:
            document = await self._collection.find_one({"_id": edge_id})
        except PyMongoError as exc:
            raise PersistenceUnavailable(f"could not read topology for {edge_id!r}") from exc
        if not document:
            return None
        document.pop("_id", None)
        return document

    async def save(self, edge_id: str, payload: dict[str, object]) -> None:
        try:
            await self._collection.update_one(
                {"_id": edge_id}, {"$set": payload}, upsert=True
            )
        except PyMongoError as exc:
            logger.error("Topology write for %s failed: %s", edge_id, exc)


class MongoCampRepository:
    """Corridor camps, expired by the database rather than by the server.

    A TTL index means an abandoned camp disappears without the simulation holding a
    timer for it, which matters because a camp can outlive the process that made it
    (GDD 9.5).
    """

    __slots__ = ("_collection", "_indexed")

    def __init__(self, database: Any) -> None:
        self._collection = database[CAMP_COLLECTION]
        self._indexed = False

    async def ensure_indexes(self) -> None:
        if self._indexed:
            return
        try:
            await self._collection.create_index("expiresAt", expireAfterSeconds=0)
            await self._collection.create_index("chunkKey")
            self._indexed = True
        except PyMongoError as exc:
            logger.warning("Camp indexes unavailable, camps will not expire: %s", exc)

    async def put(self, camp_id: str, payload: dict[str, object], ttl_seconds: int) -> None:
        from datetime import datetime, timedelta, timezone

        try:
            await self._collection.update_one(
                {"_id": camp_id},
                {
                    "$set": {
                        "chunkKey": str(payload.get("chunk_key", "")),
                        "payload": payload,
                        # A real datetime, not an epoch float: the TTL monitor only
                        # understands BSON dates.
                        "expiresAt": datetime.now(timezone.utc)
                        + timedelta(seconds=ttl_seconds),
                    }
                },
                upsert=True,
            )
        except PyMongoError as exc:
            logger.warning("Camp write for %s failed: %s", camp_id, exc)

    async def get(self, camp_id: str) -> dict[str, object] | None:
        try:
            document = await self._collection.find_one({"_id": camp_id})
        except PyMongoError as exc:
            logger.warning("Camp read for %s failed: %s", camp_id, exc)
            return None
        if not document:
            return None
        payload = document.get("payload")
        return payload if isinstance(payload, dict) else None

    async def delete(self, camp_id: str) -> None:
        try:
            await self._collection.delete_one({"_id": camp_id})
        except PyMongoError as exc:
            logger.warning("Camp delete for %s failed: %s", camp_id, exc)

    async def list_for_chunk(self, chunk_key: str) -> list[dict[str, object]]:
        try:
            cursor = self._collection.find({"chunkKey": chunk_key}).limit(64)
            documents = await cursor.to_list(length=64)
        except PyMongoError as exc:
            logger.warning("Camp listing for %s failed: %s", chunk_key, exc)
            return []
        return [
            document["payload"]
            for document in documents
            if isinstance(document.get("payload"), dict)
        ]


def _decode_overlay(raw: object) -> dict[int, int]:
    """Turn a stored ``{"index": tile}`` map back into integer keys.

    Skips anything unparseable rather than failing the whole chunk: one corrupt
    key should cost one tile, not a player's entire settlement.
    """
    if not isinstance(raw, dict):
        return {}
    overlay: dict[int, int] = {}
    for key, value in raw.items():
        try:
            overlay[int(key)] = int(value)
        except (TypeError, ValueError):
            continue
    return overlay
