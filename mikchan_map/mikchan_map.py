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

import base64
import zlib

from fastapi import APIRouter, Body, Query
from fastapi.responses import FileResponse, JSONResponse

from mikchan_map.biomes import biome_labels, filter_biomes, sample_grid
from mikchan_map.markers import check_suggestion, filter_markers

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

        client = get_client()
        rows = await client[DATABASE].catalog.find({}).to_list(length=16)
        indexes = await client[DATABASE].biome_index.find({}).to_list(length=16)
        spots = {str(item.get("_id") or ""): item.get("spots") or [] for item in indexes}
        public = []
        for row in rows:
            item = _public_dimension(row)
            extra = spots.get(item["id"])
            if extra is not None:
                item["biomes"] = _public_biomes(extra)
            public.append(item)
        return public

    async def _biome_document(self, dimension: str, x: int, z: int) -> tuple[int, int, dict] | None:
        from shared.mongo import get_client

        rx, rz = x // 512, z // 512
        doc = await get_client()[DATABASE].biome_regions.find_one({"_id": f"{dimension}:{rx}:{rz}"})
        if not doc:
            return None
        return rx, rz, doc

    async def biome_region(self, dimension: str, x: int, z: int) -> dict | None:
        found = await self._biome_document(dimension, x, z)
        if found is None:
            return None
        rx, rz, doc = found
        names, grid = _unpack_grid(doc)
        packed = doc.get("grid") or b""
        cells = base64.b64encode(packed).decode("ascii") if grid and any(grid) else ""
        return {"names": names, "cells": cells, "rx": rx, "rz": rz}

    async def biome_at(self, dimension: str, x: int, z: int) -> dict | None:
        found = await self._biome_document(dimension, x, z)
        if found is None:
            return None
        rx, rz, doc = found
        names, grid = _unpack_grid(doc)
        biome_id = sample_grid(names, grid, x, z, rx, rz)
        if not biome_id:
            return None
        english, russian = biome_labels(biome_id)
        return {"dimension": dimension, "id": biome_id, "en": english, "ru": russian, "x": x, "z": z}

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


def _public_biomes(value: object) -> list[dict]:
    if not isinstance(value, list):
        return []
    spots = []
    for item in value:
        if not isinstance(item, dict):
            continue
        biome_id = item.get("id")
        x, z = item.get("x"), item.get("z")
        if not isinstance(biome_id, str) or not biome_id.strip():
            continue
        if not all(isinstance(number, int) and not isinstance(number, bool) for number in (x, z)):
            continue
        spots.append({"id": biome_id.strip()[:80], "x": x, "z": z})
    return spots


def _limit(value: int) -> int:
    if value < 1:
        return 1
    if value > 2000:
        return 2000
    return value


def _unpack_grid(doc: dict) -> tuple[list[str], bytes]:
    names = [str(name) for name in doc.get("names") or []]
    raw = doc.get("grid") or b""
    if not raw:
        return names, b""
    return names, zlib.decompress(raw)


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
        "biomes": _public_biomes(row.get("biomes")),
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


def _query_dimension(value: str) -> str | None:
    cleaned = value.strip().lower()
    if not cleaned:
        return ""
    if not cleaned[0].isalpha() or any(character not in "abcdefghijklmnopqrstuvwxyz0123456789_-" for character in cleaned):
        return None
    return cleaned[:32]


@router.get("/api/markers")
async def map_markers(
    dimension: str = "",
    q: str = "",
    limit: int = Query(default=2000),
):
    chosen = _query_dimension(dimension)
    if chosen is None:
        return JSONResponse({"error": "dimension"}, status_code=400)
    try:
        dimensions = await get_store().read_catalog()
    except Exception as exc:
        logger.error("map markers failed: %s", type(exc).__name__)
        return JSONResponse({"error": "store"}, status_code=503)
    return {"markers": filter_markers(dimensions, dimension=chosen, query=q.strip()[:80], limit=_limit(limit))}


@router.get("/api/biomes")
async def map_biomes(
    dimension: str = "",
    q: str = "",
    limit: int = Query(default=2000),
):
    chosen = _query_dimension(dimension)
    if chosen is None:
        return JSONResponse({"error": "dimension"}, status_code=400)
    try:
        dimensions = await get_store().read_catalog()
    except Exception as exc:
        logger.error("map biomes failed: %s", type(exc).__name__)
        return JSONResponse({"error": "store"}, status_code=503)
    return {"biomes": filter_biomes(dimensions, dimension=chosen, query=q.strip()[:80], limit=_limit(limit))}


def _block_query(value: int) -> bool:
    return abs(value) <= 30_000_000


@router.get("/api/biomes/at")
async def map_biome_at(dimension: str, x: int, z: int):
    chosen = _query_dimension(dimension)
    if not chosen or not _block_query(x) or not _block_query(z):
        return JSONResponse({"error": "place"}, status_code=400)
    try:
        biome = await get_store().biome_at(chosen, x, z)
    except Exception as exc:
        logger.error("map biome failed: %s", type(exc).__name__)
        return JSONResponse({"error": "store"}, status_code=503)
    return {"biome": biome}


@router.get("/api/biomes/region")
async def map_biome_region(dimension: str, x: int, z: int):
    chosen = _query_dimension(dimension)
    if not chosen or not _block_query(x) or not _block_query(z):
        return JSONResponse({"error": "place"}, status_code=400)
    try:
        region = await get_store().biome_region(chosen, x, z)
    except Exception as exc:
        logger.error("map biome region failed: %s", type(exc).__name__)
        return JSONResponse({"error": "store"}, status_code=503)
    return region or {"names": [], "cells": "", "rx": x // 512, "rz": z // 512}


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
