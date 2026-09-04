"""FastAPI sub-application factory.

Exports an ASGI app rather than a bare router so the project owns its own static
mount and middleware whether the orchestrator embeds it in the hub process or proxies
it to an isolated worker.
"""

from __future__ import annotations

import mimetypes

from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles

from . import http_routes, ws_routes

# StaticFiles asks `mimetypes` for the Content-Type, and on Windows that reads the
# registry, where installed software often leaves `.js` mapped to text/plain. The
# HTML specification makes the MIME check for ES modules strict, so the browser
# refuses to execute the bundle and the page stays black with no useful console
# error. Linux never hits this, which is exactly why it only breaks locally.
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/javascript", ".mjs")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("application/json", ".json")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Age",
        description=(
            "A browser MMO vertical slice: an accordion world that widens with its "
            "population, procedurally generated pixel art, and an authoritative "
            "simulation behind a binary protocol."
        ),
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    # PNG pages arrive already compressed and the middleware leaves them alone; it
    # picks up the JSON payloads and the SPA shell, which are the only text here.
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.include_router(ws_routes.router)
    app.include_router(http_routes.router)

    static_dir = http_routes.STATIC_DIR
    if static_dir.is_dir():
        app.mount("/static", StaticFiles(directory=static_dir), name="age_static")
    return app
