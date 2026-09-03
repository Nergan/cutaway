"""Entrypoint discovered by the orchestrator.

Exports ``asgi_app`` plus the lifecycle hooks the hub loader looks for. Running
this file directly starts a standalone server on the same URL layout the hub
would publish, which is what the development script uses.
"""

from __future__ import annotations

import argparse
import logging

from .config import load_settings
from .presentation.app import create_app
from .presentation.container import get_container

logger = logging.getLogger(__name__)

asgi_app = create_app()


async def startup_clients() -> None:
    await get_container().startup()


async def shutdown_clients() -> None:
    await get_container().shutdown()


def _standalone():
    """Mount the project under its public prefix with its own lifecycle."""
    from contextlib import asynccontextmanager

    from fastapi import FastAPI
    from fastapi.responses import RedirectResponse

    settings = load_settings()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await startup_clients()
        try:
            yield
        finally:
            await shutdown_clients()

    root = FastAPI(title="ASCII City (standalone)", lifespan=lifespan)

    @root.get("/", include_in_schema=False)
    async def _redirect() -> RedirectResponse:
        return RedirectResponse(url=f"{settings.base_path}/")

    root.mount(settings.base_path, asgi_app, name="ascii_city")
    return root, settings


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the ASCII City server on its own.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8130)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    import uvicorn

    logging.basicConfig(level=logging.INFO)
    root, settings = _standalone()
    logger.info("ASCII City on http://%s:%d%s/", args.host, args.port, settings.base_path)
    uvicorn.run(root, host=args.host, port=args.port, loop="asyncio")


if __name__ == "__main__":
    main()
