"""Load one declared project without scanning or importing its neighbours."""

from __future__ import annotations

import importlib
import inspect
import logging
import sys
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .config import ProjectConfig


logger = logging.getLogger(__name__)
LifecycleCallback = Callable[[], Awaitable[None] | None]


@dataclass(frozen=True)
class LoadedProject:
    project: ProjectConfig
    module_name: str
    startup: LifecycleCallback | None
    shutdown: LifecycleCallback | None


async def call_lifecycle(callback: LifecycleCallback | None) -> None:
    if callback is None:
        return
    result = callback()
    if inspect.isawaitable(result):
        await result


def _mount_static(app: FastAPI, project: ProjectConfig) -> None:
    # Keep the legacy underscore URL for yellow_mirror assets. All other project
    # ids already match their public prefix.
    static_base = f"/{project.project_id}"
    for child in ("static", "scripts"):
        directory = project.directory / child
        if directory.is_dir():
            path = f"{static_base}/{child}"
            app.mount(
                path,
                StaticFiles(directory=directory),
                name=f"{project.project_id}_{child}",
            )


def install_project(app: FastAPI, project: ProjectConfig) -> LoadedProject:
    """Import and mount exactly the project declared by ``project``."""
    module = importlib.import_module(project.entrypoint)
    router = getattr(module, "router", None)
    asgi_app: Any = getattr(module, "asgi_app", None)
    if router is None and asgi_app is None:
        raise RuntimeError(
            f"{project.entrypoint} must export either 'router' or 'asgi_app'."
        )

    if router is not None:
        _mount_static(app, project)
        app.include_router(
            router,
            prefix=project.prefix,
            tags=[project.project_id.replace("_", " ").title()],
        )
    else:
        app.mount(project.prefix, asgi_app, name=project.project_id)

    logger.info("Mounted project %s from %s", project.project_id, project.entrypoint)
    return LoadedProject(
        project=project,
        module_name=module.__name__,
        startup=_lifecycle(module, "startup_clients"),
        shutdown=_lifecycle(module, "shutdown_clients"),
    )


def _lifecycle(module: Any, name: str) -> LifecycleCallback | None:
    callback = getattr(module, name, None)
    if callback is not None:
        return callback
    package = getattr(module, "__package__", "") or module.__name__
    root_name = package.split(".", 1)[0]
    imported = sys.modules.get(root_name)
    if imported is None or imported is module:
        return None
    return getattr(imported, name, None)
