"""FastAPI sub-application factory.

The project exports an ASGI app rather than a bare router so that it owns its
own static mount and middleware regardless of whether the orchestrator embeds
it in the hub process or proxies it to an isolated worker.
"""

from __future__ import annotations

import mimetypes

from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles

from . import http_routes, ws_routes

# StaticFiles asks `mimetypes` for the Content-Type, and on Windows that reads
# the registry, where installed software often leaves `.js` mapped to
# text/plain. The HTML specification makes the MIME check for ES modules
# strict, so the browser refuses to execute the bundle and the page stays
# black with no console error worth the name. Linux never hits this, which is
# exactly why it only ever breaks on a developer's machine.
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/javascript", ".mjs")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("application/json", ".json")


def create_app() -> FastAPI:
    app = FastAPI(
        title="ASCII City",
        description="Multiplayer ASCII city rendered from an authoritative world grid.",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    # Tiles arrive pre-compressed with an explicit Content-Encoding, which this
    # middleware leaves alone; it only picks up the JSON and the SPA shell.
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.include_router(ws_routes.router)
    app.include_router(http_routes.router)

    static_dir = http_routes.STATIC_DIR
    if static_dir.is_dir():
        app.mount("/static", StaticFiles(directory=static_dir), name="ascii_city_static")
    return app
