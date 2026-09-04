"""The ports of the hexagon.

Everything the simulation needs from the outside world is a ``Protocol`` here.
The application layer imports these and nothing else, which is what makes the
in-memory and MongoDB repositories interchangeable, the clock injectable, and the
whole simulation testable without a socket or a database.

The seam that matters most for the roadmap is :class:`ChunkGenerator`. Replacing
the Python generator with a compiled one means implementing this protocol; no
caller changes.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .coordinates import ChunkAddress, LocationRef
from .entities import EntityId


@runtime_checkable
class Clock(Protocol):
    """Monotonic time source.

    Injected rather than called directly so tests can step time by exact ticks
    and assert on accordion timings without sleeping.
    """

    def now(self) -> float:
        """Seconds since an arbitrary origin. Must never go backwards."""


@runtime_checkable
class ChunkGenerator(Protocol):
    """Deterministic terrain generation.

    The same address and world seed must always produce byte-identical tiles,
    across processes and across the Python/TypeScript boundary. The client
    generates its own copy from the seed, so terrain costs no bandwidth; that only
    works if determinism holds exactly.
    """

    def generate(self, address: ChunkAddress) -> bytearray:
        """Tiles for a chunk: ``CHUNK_TILE_COUNT`` bytes, row-major."""

    def biome_of(self, address: ChunkAddress) -> int:
        """The dominant biome of a chunk, for spawns and weather."""


@runtime_checkable
class TerrainOverlayRepository(Protocol):
    """Player edits layered on top of generated terrain.

    Batched, not immediate: TDD 9.1 accepts up to thirty seconds of terrain loss,
    because a re-dug tile is cheap to lose and writing every tile change through
    to storage is not.
    """

    async def load(self, chunk_key: str) -> dict[int, int]:
        """Overlay for a chunk as ``{tile_index: tile_id}``."""

    async def save_batch(self, overlays: dict[str, dict[int, int]]) -> None:
        """Flush accumulated edits for several chunks at once."""

    async def clear(self, chunk_key: str) -> None:
        """Drop a chunk's overlay, returning it to pure generated terrain."""


@runtime_checkable
class CharacterRepository(Protocol):
    """Durable character state. Written immediately; loss must be zero."""

    async def load(self, character_name: str) -> dict[str, object] | None: ...

    async def save(self, character_name: str, payload: dict[str, object]) -> None: ...


@runtime_checkable
class TopologyRepository(Protocol):
    """Durable accordion state.

    Written inside the same commit as the tier change so a crash can never leave
    the world claiming a tier whose chunks were never persisted.
    """

    async def load(self, edge_id: str) -> dict[str, object] | None: ...

    async def save(self, edge_id: str, payload: dict[str, object]) -> None: ...


@runtime_checkable
class CampRepository(Protocol):
    """Temporary corridor camps.

    Not durable by design (GDD 9.5): a camp has a TTL and is compensated when it
    expires or is destroyed, so it lives in a store that can forget it.
    """

    async def put(self, camp_id: str, payload: dict[str, object], ttl_seconds: int) -> None: ...

    async def get(self, camp_id: str) -> dict[str, object] | None: ...

    async def delete(self, camp_id: str) -> None: ...

    async def list_for_chunk(self, chunk_key: str) -> list[dict[str, object]]: ...


@runtime_checkable
class EventSink(Protocol):
    """Where the simulation posts things clients should hear about.

    The simulation never touches a socket. It posts events; the presentation
    layer decides who is close enough to receive them.
    """

    def entity_spawned(self, entity_id: EntityId) -> None: ...

    def entity_despawned(self, entity_id: EntityId, reason: int) -> None: ...

    def combat_resolved(
        self,
        attacker_id: EntityId,
        target_id: EntityId,
        ability_id: int,
        damage: int,
        healing: int,
        killed: bool,
    ) -> None: ...

    def tiles_changed(self, chunk_key: str, changes: dict[int, int]) -> None: ...

    def topology_changed(self, version: int) -> None: ...

    def system_message(self, text: str, location: LocationRef | None = None) -> None: ...
