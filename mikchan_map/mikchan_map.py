"""World map of MikChan no Sekai at /mikchan-map.

Tiles are public images. This process only reads the catalog and stores
suggestions. It does not upload, and it does not open the mikchan database.
"""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body
from fastapi.responses import FileResponse, JSONResponse

from mikchan_map.markers import check_suggestion

logger = logging.getLogger(__name__)

router = APIRouter()
BASE_DIR = Path(__file__).parent
DATABASE = "mikchan_map"
_CLOUD = re.compile(r"^[a-z0-9]+$")
_store: Any = None


def cloud_name() -> str:
    name = os.getenv("CLOUDINARY_CLOUD_NAME", "").strip()
    if not name:
        url = os.getenv("CLOUDINARY_URL", "")
        if "@" in url:
            name = url.rsplit("@", 1)[-1].split("/")[0].strip()
    return name if _CLOUD.fullmatch(name) else ""


class MongoStore:
    async def read_catalog(self) -> list[dict]:
        from shared.mongo import get_client

        rows = await get_client()[DATABASE].catalog.find({}).to_list(length=16)
        return [_public_dimension(row) for row in rows]

    async def add_suggestion(self, suggestion: dict) -> None:
        from shared.mongo import get_client

        await get_client()[DATABASE].suggestions.insert_one(
            {**suggestion, "at": datetime.now(timezone.utc)}
        )


def get_store() -> MongoStore:
    return _store if _store is not None else MongoStore()


def _ints(value: object) -> list[list[int]]:
    if not isinstance(value, list):
        return []
    tiles = []
    for item in value:
        if (
            isinstance(item, list)
            and len(item) == 2
            and isinstance(item[0], int)
            and isinstance(item[1], int)
            and not isinstance(item[0], bool)
            and not isinstance(item[1], bool)
        ):
            tiles.append([item[0], item[1]])
    return tiles


def _public_dimension(row: dict) -> dict:
    levels = []
    for level in row.get("levels") or []:
        if not isinstance(level, dict):
            continue
        index, blocks = level.get("level"), level.get("blocks")
        if not isinstance(index, int) or not isinstance(blocks, int):
            continue
        levels.append({"level": index, "blocks": blocks, "tiles": _ints(level.get("tiles"))})
    bounds = row.get("bounds") if isinstance(row.get("bounds"), dict) else {}
    clean_bounds = {}
    for key in ("minX", "maxX", "minZ", "maxZ"):
        value = bounds.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            clean_bounds[key] = value
    markers = []
    for marker in row.get("waypoints") or []:
        if not isinstance(marker, dict):
            continue
        if not all(isinstance(marker.get(key), int) and not isinstance(marker.get(key), bool) for key in ("x", "y", "z")):
            continue
        markers.append(
            {
                "name": str(marker.get("name") or "?")[:80],
                "initials": str(marker.get("initials") or "?")[:16],
                "x": marker["x"],
                "y": marker["y"],
                "z": marker["z"],
                "color": str(marker.get("color") or "#FFFFFF")[:7],
            }
        )
    return {
        "id": str(row.get("_id") or ""),
        "bounds": clean_bounds,
        "levels": levels,
        "waypoints": markers,
    }


@router.get("/", response_class=FileResponse)
async def map_page():
    return FileResponse(BASE_DIR / "map.html")


@router.get("/api/map")
async def map_catalog():
    try:
        dimensions = await get_store().read_catalog()
    except Exception as exc:
        logger.error("map catalog failed: %s", type(exc).__name__)
        return JSONResponse({"error": "store"}, status_code=503)
    order = {"overworld": 0, "nether": 1, "end": 2}
    dimensions.sort(key=lambda item: (order.get(item["id"], 9), item["id"]))
    return {"cloud": cloud_name(), "dimensions": dimensions}


@router.post("/api/suggestions")
async def add_suggestion(body: dict = Body()):
    suggestion = check_suggestion(body)
    if isinstance(suggestion, str):
        return JSONResponse({"error": suggestion}, status_code=400)
    try:
        await get_store().add_suggestion(suggestion)
    except Exception as exc:
        logger.error("map suggestion failed: %s", type(exc).__name__)
        return JSONResponse({"error": "store"}, status_code=503)
    return JSONResponse({"ok": True}, status_code=201)
