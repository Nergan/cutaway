"""Фабрика FastAPI-приложения: Worker REST-прокси + админ-API + статическая админка."""

from __future__ import annotations

import mimetypes
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pymongo import AsyncMongoClient

from another_admin.adapters.async_mongo_store import AsyncMongoStore
from another_admin.api.admin_routes import router as admin_router
from another_admin.api.config import ApiConfig
from another_admin.api.internal_routes import router as internal_router
from another_admin.ports.control_plane_store import ControlPlaneStore

STATIC_DIR = Path(__file__).resolve().parent / "static"

# StaticFiles определяет Content-Type через mimetypes, а тот на Windows берёт
# типы из реестра, где .js часто прописан как text/plain. Браузер отказывается
# исполнять такой ответ как ES-модуль (строгая проверка MIME в HTML-спеке), и
# админка молча не запускается при локальном `uvicorn`. В Linux-образе на
# Hugging Face этого нет, поэтому проблема ловится только на машине разработчика.
# add_type перезаписывает соответствие в обе стороны и на Linux ничего не меняет.
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/javascript", ".mjs")


def create_app(
    *,
    store: ControlPlaneStore | None = None,
    cfg: ApiConfig | None = None,
) -> FastAPI:
    injected_store = store
    injected_cfg = cfg

    async def open_state(app: FastAPI) -> None:
        """Идемпотентно поднимает app.state. Вызывается из lifespan либо снаружи
        (монорепозиторий cutaway монтирует это приложение как sub-app, а Starlette
        не прокидывает lifespan в mount'ы — см. another/main.py)."""
        if getattr(app.state, "store", None) is not None:
            return

        if injected_store is not None:
            app.state.store = injected_store
            app.state.cfg = injected_cfg or ApiConfig(
                mongo_uri="memory",
                mongo_db_name="another",
                service_secret="test-secret",
                control_plane_url="https://cf-worker.another.example",
                edge_internal_url="",
                events_capped_bytes=1024,
            )
            return

        runtime_cfg = injected_cfg or ApiConfig.from_env()
        client: AsyncMongoClient = AsyncMongoClient(runtime_cfg.mongo_uri)
        mongo_store = AsyncMongoStore.from_client(
            client,
            runtime_cfg.mongo_db_name,
            events_capped_bytes=runtime_cfg.events_capped_bytes,
        )
        await mongo_store.ensure_schema()
        app.state.store = mongo_store
        app.state.cfg = runtime_cfg
        app.state.mongo_client = client

    async def close_state(app: FastAPI) -> None:
        client = getattr(app.state, "mongo_client", None)
        if client is not None:
            await client.close()
        app.state.mongo_client = None
        app.state.store = None

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await open_state(app)
        try:
            yield
        finally:
            await close_state(app)

    application = FastAPI(
        title="Another control plane",
        version="0.3.0",
        lifespan=lifespan,
    )
    application.state.store = None
    application.state.cfg = None
    application.state.mongo_client = None
    application.state.open_state = open_state
    application.state.close_state = close_state

    application.include_router(internal_router)
    application.include_router(admin_router)

    @application.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": "another-control-plane"}

    @application.get("/")
    async def root(request: Request) -> RedirectResponse:
        # root_path непустой, когда приложение смонтировано под префиксом (/another).
        return RedirectResponse(f"{request.scope.get('root_path', '')}/admin/")

    if STATIC_DIR.is_dir():
        application.mount("/admin", StaticFiles(directory=STATIC_DIR, html=True), name="admin-ui")

    return application


def create_prod_app() -> FastAPI:
    return create_app()
