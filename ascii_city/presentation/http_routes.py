"""HTTP surface: world metadata, binary tiles, room status and the SPA shell."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse

from ..domain.constants import (
    CHAT_MAX_LENGTH,
    CHAT_PROXIMITY_RADIUS_M,
    CHAT_RATE_LIMIT,
    CHAT_RATE_WINDOW_S,
    EYE_HEIGHT_M,
    FULL_DETAIL_RADIUS_M,
    PLAYER_RADIUS_M,
    RUN_SPEED_MS,
    SIMPLIFIED_RADIUS_M,
    SIMULATION_HZ,
    SNAPSHOT_HZ,
    WALK_SPEED_MS,
)
from ..infrastructure.tile_codec import FORMAT_VERSION
from .container import Container, get_container

BASE_DIR = Path(__file__).resolve().parents[1]
STATIC_DIR = BASE_DIR / "static"

router = APIRouter()

_NOT_BUILT = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>ASCII CITY - client not built</title>
<style>
 body{background:#04070a;color:#7ef7c8;font:14px/1.6 ui-monospace,Menlo,Consolas,monospace;
      display:flex;align-items:center;justify-content:center;height:100vh;margin:0}
 div{max-width:52ch}
 code{color:#ffd479}
 h1{font-size:16px;letter-spacing:.3em}
</style></head>
<body><div>
<h1>ASCII CITY</h1>
<p>The web client has not been built yet. From the repository root run:</p>
<p><code>cd ascii_city &amp;&amp; npm install &amp;&amp; npm run build</code></p>
<p>The server itself is running; <code>GET api/world</code> already answers.</p>
</div></body></html>
"""


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def index() -> Response:
    document = STATIC_DIR / "index.html"
    if not document.is_file():
        return HTMLResponse(_NOT_BUILT, status_code=200)
    return HTMLResponse(document.read_text(encoding="utf-8"))


@router.get("/healthz", include_in_schema=False)
async def healthz() -> JSONResponse:
    container = get_container()
    return JSONResponse(
        {
            "status": "ok" if container.is_ready else "loading",
            "storage": container.storage_backend,
            "error": container.error,
        }
    )


@router.get("/api/world")
async def world_metadata() -> JSONResponse:
    """Everything the client needs before it starts pulling tiles."""
    container = get_container()
    await container.ready()
    descriptor = container.world_service.world.descriptor
    return JSONResponse(
        {
            "world": {
                "id": descriptor.id,
                "version": descriptor.version,
                "seed": descriptor.seed,
                "source": descriptor.source,
                "tilesX": descriptor.tiles_x,
                "tilesY": descriptor.tiles_y,
                "tileCells": descriptor.tile_cells,
                "cellSize": descriptor.cell_size,
                "widthM": descriptor.width_m,
                "heightM": descriptor.height_m,
                "tileFormat": FORMAT_VERSION,
            },
            "physics": {
                "playerRadius": PLAYER_RADIUS_M,
                "eyeHeight": EYE_HEIGHT_M,
                "walkSpeed": WALK_SPEED_MS,
                "runSpeed": RUN_SPEED_MS,
            },
            "network": {
                "simulationHz": SIMULATION_HZ,
                "snapshotHz": SNAPSHOT_HZ,
                "fullDetailRadius": FULL_DETAIL_RADIUS_M,
                "simplifiedRadius": SIMPLIFIED_RADIUS_M,
            },
            "chat": {
                "maxLength": CHAT_MAX_LENGTH,
                "rateLimit": CHAT_RATE_LIMIT,
                "rateWindowSeconds": CHAT_RATE_WINDOW_S,
                "proximityRadius": CHAT_PROXIMITY_RADIUS_M,
            },
        }
    )


@router.get("/api/world/tiles/{tile_x}/{tile_y}")
async def world_tile(tile_x: int, tile_y: int, request: Request) -> Response:
    """Serve one encoded tile, pre-compressed and immutable per world version."""
    container = get_container()
    await container.ready()
    encoded = container.world_service.encoded_tile(tile_x, tile_y)
    if encoded is None:
        return JSONResponse({"detail": "Unknown tile."}, status_code=404)

    if request.headers.get("if-none-match") == encoded.etag:
        return Response(status_code=304, headers={"etag": encoded.etag})

    headers = {
        "etag": encoded.etag,
        # A tile is immutable for its world version, so it can be held forever.
        "cache-control": "public, max-age=31536000, immutable",
        "x-tile-bytes": str(encoded.raw_size),
    }
    if "gzip" in request.headers.get("accept-encoding", ""):
        headers["content-encoding"] = "gzip"
        return Response(encoded.gzipped, media_type="application/octet-stream", headers=headers)
    return Response(encoded.raw, media_type="application/octet-stream", headers=headers)


@router.get("/api/room")
async def room_status() -> JSONResponse:
    container = get_container()
    if not container.is_ready:
        return JSONResponse(
            {"status": "loading", "error": container.error}, status_code=503
        )
    stats = dict(container.room.stats())
    stats.pop("nicknames", None)
    stats["status"] = "online"
    stats["storage"] = container.storage_backend
    return JSONResponse(stats)


def build_static_dir(container: Container | None = None) -> Path:
    """Exposed so the app factory and the tests agree on one location."""
    return STATIC_DIR
