"""In-memory repositories: the default, not a test double.

Every persistence port has an implementation here. They are what the server runs on
when no MongoDB URI is configured, which means the demo starts with zero
infrastructure and a visitor sees a working world rather than a connection error.

They are also what the tests use, and the fact that those are the same code is the
point: the in-memory path is exercised constantly rather than rotting.
"""

from __future__ import annotations

import time
from copy import deepcopy


class MemoryTerrainOverlayRepository:
    """Terrain edits held in a dict."""

    __slots__ = ("_overlays",)

    def __init__(self) -> None:
        self._overlays: dict[str, dict[int, int]] = {}

    async def load(self, chunk_key: str) -> dict[int, int]:
        return dict(self._overlays.get(chunk_key, {}))

    async def save_batch(self, overlays: dict[str, dict[int, int]]) -> None:
        for chunk_key, changes in overlays.items():
            if changes:
                self._overlays[chunk_key] = dict(changes)
            else:
                # An empty overlay means the chunk was edited back to its generated
                # state; storing the empty dict would keep a useless document alive.
                self._overlays.pop(chunk_key, None)

    async def clear(self, chunk_key: str) -> None:
        self._overlays.pop(chunk_key, None)

    @property
    def size(self) -> int:
        return len(self._overlays)


class MemoryCharacterRepository:
    """Characters held in a dict, keyed by name."""

    __slots__ = ("_characters",)

    def __init__(self) -> None:
        self._characters: dict[str, dict[str, object]] = {}

    async def load(self, character_name: str) -> dict[str, object] | None:
        stored = self._characters.get(character_name)
        # Deep-copied on the way out so a caller mutating what it loaded cannot
        # change the stored document behind the repository's back. A real database
        # gives that guarantee for free; an in-memory one has to do it by hand.
        return deepcopy(stored) if stored is not None else None

    async def save(self, character_name: str, payload: dict[str, object]) -> None:
        self._characters[character_name] = deepcopy(payload)

    @property
    def size(self) -> int:
        return len(self._characters)


class MemoryTopologyRepository:
    """Accordion state held in a dict, keyed by edge id."""

    __slots__ = ("_edges",)

    def __init__(self) -> None:
        self._edges: dict[str, dict[str, object]] = {}

    async def load(self, edge_id: str) -> dict[str, object] | None:
        stored = self._edges.get(edge_id)
        return deepcopy(stored) if stored is not None else None

    async def save(self, edge_id: str, payload: dict[str, object]) -> None:
        self._edges[edge_id] = deepcopy(payload)


class MemoryCampRepository:
    """Camps with expiry, checked on read.

    Lazy expiry rather than a sweeper: a camp nobody looks at costs nothing, and a
    background task to delete it would cost a timer.
    """

    __slots__ = ("_camps",)

    def __init__(self) -> None:
        # camp_id -> (expires_at, chunk_key, payload)
        self._camps: dict[str, tuple[float, str, dict[str, object]]] = {}

    async def put(self, camp_id: str, payload: dict[str, object], ttl_seconds: int) -> None:
        chunk_key = str(payload.get("chunk_key", ""))
        self._camps[camp_id] = (
            time.time() + ttl_seconds,
            chunk_key,
            deepcopy(payload),
        )

    async def get(self, camp_id: str) -> dict[str, object] | None:
        entry = self._camps.get(camp_id)
        if entry is None:
            return None
        if entry[0] <= time.time():
            self._camps.pop(camp_id, None)
            return None
        return deepcopy(entry[2])

    async def delete(self, camp_id: str) -> None:
        self._camps.pop(camp_id, None)

    async def list_for_chunk(self, chunk_key: str) -> list[dict[str, object]]:
        now = time.time()
        alive: list[dict[str, object]] = []
        for camp_id, (expires_at, key, payload) in list(self._camps.items()):
            if expires_at <= now:
                self._camps.pop(camp_id, None)
                continue
            if key == chunk_key:
                alive.append(deepcopy(payload))
        return alive
