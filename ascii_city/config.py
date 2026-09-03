"""Runtime settings.

Only names listed in ``env_allowlist`` of ``orchestrator.toml`` reach an
isolated worker, so every variable read here has to be declared there too.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from .domain.constants import CELL_SIZE_M, MAX_CLIENTS, MAX_TILES_PER_AXIS, TILE_CELLS

DEFAULT_SEED = 0x5A17C17E


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw, 0)
    except ValueError:
        return default


def _flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class Settings:
    world_id: str
    world_seed: int
    world_version: int
    tiles_x: int
    tiles_y: int
    tile_cells: int
    cell_size: float
    room_id: str
    max_clients: int
    use_mongo: bool
    base_path: str

    @property
    def world_width_m(self) -> float:
        return self.tiles_x * self.tile_cells * self.cell_size

    @property
    def world_height_m(self) -> float:
        return self.tiles_y * self.tile_cells * self.cell_size


def load_settings() -> Settings:
    world_id = os.getenv("ASCII_CITY_WORLD_ID", "demo").strip() or "demo"
    # Beyond MAX_TILES_PER_AXIS the wire cannot name a position, so a larger
    # district would strand players at the edge rather than fail loudly.
    tiles_x = max(1, min(MAX_TILES_PER_AXIS, _int("ASCII_CITY_TILES_X", 2)))
    tiles_y = max(1, min(MAX_TILES_PER_AXIS, _int("ASCII_CITY_TILES_Y", 2)))
    return Settings(
        world_id=world_id,
        world_seed=_int("ASCII_CITY_WORLD_SEED", DEFAULT_SEED) & 0xFFFFFFFF,
        world_version=max(1, _int("ASCII_CITY_WORLD_VERSION", 1)),
        tiles_x=tiles_x,
        tiles_y=tiles_y,
        tile_cells=TILE_CELLS,
        cell_size=CELL_SIZE_M,
        room_id=os.getenv("ASCII_CITY_ROOM_ID", f"city:{world_id}:main"),
        max_clients=max(2, min(200, _int("ASCII_CITY_MAX_CLIENTS", MAX_CLIENTS))),
        use_mongo=_flag("ASCII_CITY_USE_MONGO", True),
        base_path=os.getenv("ASCII_CITY_BASE_PATH", "/ascii-city").rstrip("/") or "/ascii-city",
    )
