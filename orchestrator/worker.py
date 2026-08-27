"""ASGI factory used by isolated project worker processes."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .config import load_runtime_config
from .loader import LoadedProject, call_lifecycle, install_project


def create_app() -> FastAPI:
    project_id = os.getenv("CUTAWAY_WORKER_PROJECT", "").strip()
    if not project_id:
        raise RuntimeError("CUTAWAY_WORKER_PROJECT is required.")

    config = load_runtime_config()
    project = config.projects.get(project_id)
    if project is None:
        raise RuntimeError(f"Unknown worker project: {project_id}")
    if not project.run:
        raise RuntimeError(f"Project {project_id} is disabled for profile {config.profile}.")

    loaded: LoadedProject | None = None

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        assert loaded is not None
        await call_lifecycle(loaded.startup)
        try:
            yield
        finally:
            await call_lifecycle(loaded.shutdown)

    app = FastAPI(
        title=f"Cutaway worker: {project_id}",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )

    @app.get("/_orchestrator/health", include_in_schema=False)
    async def worker_health() -> dict[str, str]:
        return {"status": "ok", "project": project_id}

    loaded = install_project(app, project)
    return app
