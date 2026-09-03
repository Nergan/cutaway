import os
from pathlib import Path

# Windows CI/dev accounts sometimes cannot write to %TEMP%/pytest-of-*.
# Keep pytest scratch files inside the already-ignored workspace tree.
_TMP = Path(__file__).resolve().parents[1] / ".pytest-tmp"
_TMP.mkdir(exist_ok=True)
os.environ["TMP"] = str(_TMP)
os.environ["TEMP"] = str(_TMP)
os.environ["TMPDIR"] = str(_TMP)


# --- ascii_city ------------------------------------------------------------
# A one-tile district keeps every test under a tenth of a second while still
# exercising the real generator, codec and collision grid.

import pytest  # noqa: E402


@pytest.fixture
def small_descriptor():
    from ascii_city.domain.constants import CELL_SIZE_M, TILE_CELLS
    from ascii_city.domain.world import WorldDescriptor

    return WorldDescriptor(
        id="test",
        version=1,
        seed=0x1234ABCD,
        tiles_x=1,
        tiles_y=1,
        tile_cells=TILE_CELLS,
        cell_size=CELL_SIZE_M,
        source="procedural",
    )


@pytest.fixture
def small_world(small_descriptor):
    from ascii_city.domain.world import World
    from ascii_city.infrastructure.generator import DistrictGenerator

    tiles = DistrictGenerator().generate_tiles(small_descriptor)
    return World.from_tiles(small_descriptor, list(tiles))


@pytest.fixture
def manual_clock():
    from ascii_city.infrastructure.repositories.memory import ManualClock

    return ManualClock()


class RecordingConnection:
    """Captures every frame the room sends, so tests can assert on the wire."""

    def __init__(self) -> None:
        self.sent: list[bytes] = []
        self.closed: tuple[int, str] | None = None

    async def send(self, payload: bytes) -> None:
        self.sent.append(payload)

    async def close(self, code: int, reason: str) -> None:
        self.closed = (code, reason)

    def frames(self, kind: int) -> list[bytes]:
        return [frame for frame in self.sent if frame and frame[0] == kind]


@pytest.fixture
def connection_factory():
    return RecordingConnection
