"""Плагин cutaway для проекта another (VPN control plane).

Точка входа, которую находит автодискавери из корневого main.py. Отдаёт
`asgi_app` — полноценное FastAPI-приложение из another_admin, монтируемое как
sub-app под /another. Sub-app держит собственный state, поэтому /internal/v1,
/admin/v1 и статическая админка работают ровно так же, как при standalone-деплое
(control-plane-admin/Dockerfile.api).

Каталог пакета называется control-plane-admin (дефис), импортировать его как
Python-модуль нельзя, поэтому он добавляется в sys.path, а пакет another_admin
внутри импортируется по своему обычному абсолютному имени.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parent
PACKAGE_ROOT = PLUGIN_DIR / "control-plane-admin"
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

logger = logging.getLogger(__name__)

# cutaway держит строку подключения в MONGODB_URI, another читает MONGO_URI.
# Переиспользуем один и тот же секрет HF Space вместо дубликата.
_shared_mongo_uri = os.environ.get("MONGODB_URI")
if _shared_mongo_uri and not os.environ.get("MONGO_URI"):
    os.environ["MONGO_URI"] = _shared_mongo_uri
os.environ.setdefault("MONGO_DB_NAME", "another")

# Ban-invalidate и QR ходят на воркер. Если на Space задан только
# ANOTHER_CONTROL_PLANE_URL — копируем его в EDGE_INTERNAL_URL. Loopback
# (wrangler dev) с HF недоступен, его не подставляем.
_public_edge = (
    os.environ.get("EDGE_INTERNAL_URL")
    or os.environ.get("ANOTHER_CONTROL_PLANE_URL")
    or ""
).rstrip("/")
if _public_edge and "127.0.0.1" not in _public_edge and "localhost" not in _public_edge.lower():
    os.environ.setdefault("EDGE_INTERNAL_URL", _public_edge)
    os.environ.setdefault("ANOTHER_CONTROL_PLANE_URL", _public_edge)

from fastapi.responses import JSONResponse  # noqa: E402

from another_admin.api.app import create_app  # noqa: E402

_app = create_app()


def _needs_store(path: str) -> bool:
    """Статика админки и healthcheck обходятся без Mongo — пусть открываются
    даже когда control plane не сконфигурирован, чтобы было видно причину."""
    if path in ("", "/", "/index.html") or path.startswith("/health"):
        return False
    if path.startswith("/portal"):
        return False
    if path.startswith("/admin") and not path.startswith("/admin/v1"):
        return False
    return True


class _LazyState:
    """Starlette не прокидывает lifespan в смонтированные приложения, поэтому
    состояние поднимается либо через startup_clients, либо лениво на первом
    запросе. Пока Mongo или секреты недоступны — честный 503, а не 500, и
    следующий запрос попробует снова."""

    def __init__(self, app) -> None:
        self._app = app
        self._lock = asyncio.Lock()

    @staticmethod
    def _local_path(scope) -> str:
        # Starlette >= 0.33 оставляет scope["path"] полным и передаёт префикс в
        # root_path; более старые версии обрезают path сами. Работает в обоих.
        path = scope.get("path", "")
        root_path = scope.get("root_path", "")
        if root_path and path.startswith(root_path):
            return path[len(root_path) :]
        return path

    async def __call__(self, scope, receive, send) -> None:
        if (
            scope["type"] == "http"
            and getattr(self._app.state, "store", None) is None
            and _needs_store(self._local_path(scope))
        ):
            async with self._lock:
                if getattr(self._app.state, "store", None) is None:
                    try:
                        await self._app.state.open_state(self._app)
                    except Exception as exc:
                        logger.error("another: control plane недоступен: %s", exc)
                        response = JSONResponse(
                            status_code=503,
                            content={"detail": f"another control plane unavailable: {exc}"},
                        )
                        await response(scope, receive, send)
                        return
        await self._app(scope, receive, send)


asgi_app = _LazyState(_app)


async def startup_clients() -> None:
    await _app.state.open_state(_app)


async def shutdown_clients() -> None:
    await _app.state.close_state(_app)
