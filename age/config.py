"""Runtime settings.

Only names listed in ``env_allowlist`` of ``orchestrator.toml`` reach an isolated
worker, so every variable read here is declared there too.

Defaults are chosen so the project runs with no configuration at all: in-memory
storage, a fixed seed, and dev controls off. A visitor with no database sees a
working world, which is the point of a demo.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from .domain.constants import (
    CORRIDOR_SEGMENTS,
    MAX_CLIENTS,
    TIER_COOLDOWN_SECONDS,
)

# "AGE" in hex, padded. A fixed default rather than a random one so two people
# comparing notes about the demo are describing the same world.
DEFAULT_WORLD_SEED = 0x0A6E5EED


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw, 0)
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
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
    corridor_segments: int
    max_clients: int
    use_mongo: bool
    base_path: str
    tier_cooldown_seconds: float
    # Lets a client force a tier change from the UI. The accordion is the most
    # interesting thing in the project and its production cadence is fifteen
    # minutes, so a demo that cannot show it on demand cannot show it at all.
    allow_dev_controls: bool
    cdn_base: str

    @property
    def api_path(self) -> str:
        return f"{self.base_path}/api"


def load_settings() -> Settings:
    world_id = os.getenv("AGE_WORLD_ID", "demo").strip() or "demo"
    return Settings(
        world_id=world_id,
        world_seed=_int("AGE_WORLD_SEED", DEFAULT_WORLD_SEED) & 0xFFFFFFFFFFFFFFFF,
        # Below two segments the corridor has no middle and the accordion has
        # nothing to widen; above sixteen the demo world stops being walkable in a
        # sitting.
        corridor_segments=max(2, min(16, _int("AGE_CORRIDOR_SEGMENTS", CORRIDOR_SEGMENTS))),
        max_clients=max(2, min(200, _int("AGE_MAX_CLIENTS", MAX_CLIENTS))),
        use_mongo=_flag("AGE_USE_MONGO", True),
        base_path=os.getenv("AGE_BASE_PATH", "/age").rstrip("/") or "/age",
        tier_cooldown_seconds=max(
            5.0, _float("AGE_TIER_COOLDOWN_SECONDS", float(TIER_COOLDOWN_SECONDS))
        ),
        allow_dev_controls=_flag("AGE_ALLOW_DEV_CONTROLS", True),
        # The developer CDN the rest of the monorepo already uses. Game art is
        # public and cached by jsDelivr, so it needs none of Cloudinary's masking;
        # that adapter stays behind a port for user-generated content later.
        cdn_base=os.getenv(
            "AGE_CDN_BASE", "https://cdn.jsdelivr.net/gh/Nergan/cdn@main"
        ).rstrip("/"),
    )
