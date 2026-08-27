"""Конфигурация origin API (HF/Render)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from another_admin.adapters.async_mongo_store import DEFAULT_EVENTS_CAPPED_BYTES


class MissingConfigError(RuntimeError):
    pass


def _require(key: str) -> str:
    value = os.environ.get(key)
    if not value:
        raise MissingConfigError(
            f"переменная окружения {key} не задана — см. .env.example"
        )
    return value


def _default_core_src() -> str:
    return str(Path(__file__).resolve().parents[3] / "core")


def _default_build_dir() -> str:
    return str(Path(__file__).resolve().parents[2] / "var" / "builds")


@dataclass(frozen=True)
class ApiConfig:
    mongo_uri: str
    mongo_db_name: str
    service_secret: str
    control_plane_url: str
    edge_internal_url: str
    events_capped_bytes: int
    nodes_json: str = "[]"
    core_src: str = ""
    build_dir: str = ""
    build_enabled: bool = False
    github_repo: str = ""
    github_dispatch_token: str = ""
    github_dispatch_event: str = "another-installer"
    public_redeem_per_hour: int = 20

    @staticmethod
    def from_env() -> ApiConfig:
        return ApiConfig(
            mongo_uri=_require("MONGO_URI"),
            mongo_db_name=os.environ.get("MONGO_DB_NAME", "another"),
            service_secret=_require("ANOTHER_SERVICE_SECRET"),
            control_plane_url=os.environ.get(
                "ANOTHER_CONTROL_PLANE_URL", "http://127.0.0.1:8787"
            ),
            edge_internal_url=os.environ.get("EDGE_INTERNAL_URL", "").rstrip("/"),
            events_capped_bytes=int(
                os.environ.get("EVENTS_CAPPED_SIZE_BYTES", str(DEFAULT_EVENTS_CAPPED_BYTES))
            ),
            nodes_json=os.environ.get("ANOTHER_NODES_JSON", "[]"),
            core_src=os.environ.get("ANOTHER_CORE_DIR") or _default_core_src(),
            build_dir=os.environ.get("ANOTHER_BUILD_DIR") or _default_build_dir(),
            build_enabled=os.environ.get("ANOTHER_BUILD_ENABLED", "") == "1",
            github_repo=os.environ.get("GITHUB_REPO", ""),
            github_dispatch_token=os.environ.get("GITHUB_DISPATCH_TOKEN", ""),
            github_dispatch_event=os.environ.get("ANOTHER_INSTALLER_EVENT", "another-installer"),
            public_redeem_per_hour=int(os.environ.get("ANOTHER_PUBLIC_REDEEM_PER_HOUR", "20")),
        )
