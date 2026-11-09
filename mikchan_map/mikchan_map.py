"""World map of MikChan no Sekai at /mikchan-map.

The page is public. Catalog, biomes, suggestions and tiles are not: the
browser gets tiles only through this process, after a key from the access
list checks out. This process does not upload, and it does not open the
mikchan database.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import secrets
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import base64
import zlib

from fastapi import APIRouter, Body, Depends, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response

from mikchan_map.biomes import biome_labels, filter_biomes, sample_grid
from mikchan_map.gate import (
    SEED_KEYS,
    active_secret,
    clear_gate_cache,
    client_host,
    gate_open,
    issue_cookie,
    normalize_key,
    note_failure,
    require_gate,
    too_many_attempts,
)
from mikchan_map.markers import check_suggestion, filter_markers
from shared.network import safe_urlopen

logger = logging.getLogger(__name__)

router = APIRouter()
BASE_DIR = Path(__file__).parent
DATABASE = "mikchan_map"
_CLOUD = re.compile(r"^[a-z0-9]+$")
_PREFIX = re.compile(r"^mikchan-map(?:-[a-z0-9]{8,32})?$")
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

    async def access_keys(self) -> list[str]:
        from shared.mongo import get_client

        collection = get_client()[DATABASE].access
        await collection.update_one(
            {"_id": "gate"},
            {"$setOnInsert": {"keys": list(SEED_KEYS)}},
            upsert=True,
        )
        clear_gate_cache()
        doc = await collection.find_one({"_id": "gate"}, {"keys": 1})
        raw = doc.get("keys") if doc else []
        return [item for item in raw if isinstance(item, str)]

    async def gate_seal(self) -> bytes:
        from shared.mongo import get_client

        collection = get_client()[DATABASE].access
        doc = await collection.find_one({"_id": "gate"}, {"seal": 1})
        seal = doc.get("seal") if doc else ""
        if not isinstance(seal, str) or len(seal) < 32:
            seal = secrets.token_hex(32)
            await collection.update_one({"_id": "gate"}, {"$set": {"seal": seal}}, upsert=True)
        return seal.encode()

    async def tile_prefix(self) -> str:
        from shared.mongo import get_client

        doc = await get_client()[DATABASE].access.find_one({"_id": "gate"}, {"prefix": 1})
        prefix = doc.get("prefix") if doc else ""
        if isinstance(prefix, str) and _PREFIX.fullmatch(prefix):
            return prefix
        return "mikchan-map"

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


@router.get("/api/session")
async def map_session(request: Request):
    try:
        secret = await active_secret()
    except Exception as exc:
        logger.error("map gate failed: %s", type(exc).__name__)
        return JSONResponse({"ok": False}, status_code=503)
    if not secret:
        return JSONResponse({"ok": False}, status_code=503)
    if not await gate_open(request):
        return JSONResponse({"ok": False}, status_code=401)
    return {"ok": True}


@router.post("/api/access")
async def map_access(request: Request, body: dict = Body()):
    try:
        secret = await active_secret()
    except Exception as exc:
        logger.error("map gate failed: %s", type(exc).__name__)
        return JSONResponse({"error": "gate"}, status_code=503)
    if not secret:
        return JSONResponse({"error": "gate"}, status_code=503)
    host = client_host(request)
    if too_many_attempts(host):
        return JSONResponse({"error": "slow"}, status_code=429)
    raw = body.get("key") if isinstance(body, dict) else None
    key = normalize_key(raw) if isinstance(raw, str) else ""
    if not key or len(key) > 80 or any(ord(char) < 32 for char in key):
        note_failure(host)
        return JSONResponse({"error": "key"}, status_code=401)
    try:
        from mikchan_map.gate import current_keys

        clear_gate_cache()
        keys = await current_keys()
    except Exception as exc:
        logger.error("map gate failed: %s", type(exc).__name__)
        return JSONResponse({"error": "store"}, status_code=503)
    if key not in keys:
        note_failure(host)
        return JSONResponse({"error": "key"}, status_code=401)
    response = JSONResponse({"ok": True})
    response.set_cookie(
        "mikchan_map",
        issue_cookie(key, secret=secret),
        max_age=30 * 24 * 3600,
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
        path="/mikchan-map",
    )
    return response


@router.get("/api/map", dependencies=[Depends(require_gate)])
async def map_catalog():
    try:
        dimensions = await get_store().read_catalog()
    except Exception as exc:
        logger.error("map catalog failed: %s", type(exc).__name__)
        return JSONResponse({"error": "store"}, status_code=503)
    order = {"overworld": 0, "nether": 1, "end": 2}
    dimensions.sort(key=lambda item: (order.get(item["id"], 9), item["id"]))
    return {"dimensions": dimensions}


def _query_dimension(value: str) -> str | None:
    cleaned = value.strip().lower()
    if not cleaned:
        return ""
    if not cleaned[0].isalpha() or any(character not in "abcdefghijklmnopqrstuvwxyz0123456789_-" for character in cleaned):
        return None
    return cleaned[:32]


@router.get("/api/markers", dependencies=[Depends(require_gate)])
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


@router.get("/api/biomes", dependencies=[Depends(require_gate)])
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


@router.get("/api/biomes/at", dependencies=[Depends(require_gate)])
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


@router.get("/api/biomes/region", dependencies=[Depends(require_gate)])
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


@router.post("/api/suggestions", dependencies=[Depends(require_gate)])
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


def _fetch_tile(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "mikchan-map"})
    return safe_urlopen(
        request,
        timeout=12,
        allowed_hosts=("res.cloudinary.com",),
        max_bytes=2_000_000,
    )


@router.get("/api/tiles/{dimension}/{level}/{x}/{z}", dependencies=[Depends(require_gate)])
async def map_tile(dimension: str, level: int, x: int, z: int):
    if dimension not in {"overworld", "nether", "end"} or level not in range(4):
        return JSONResponse({"error": "tile"}, status_code=400)
    if abs(x) > 20_000 or abs(z) > 20_000:
        return JSONResponse({"error": "tile"}, status_code=400)
    cloud = cloud_name()
    try:
        prefix = await get_store().tile_prefix()
    except Exception as exc:
        logger.error("map tile prefix failed: %s", type(exc).__name__)
        return JSONResponse({"error": "store"}, status_code=503)
    if not cloud or not _PREFIX.fullmatch(prefix):
        return JSONResponse({"error": "store"}, status_code=503)
    url = f"https://res.cloudinary.com/{cloud}/image/upload/{prefix}/{dimension}/{level}/{x}_{z}.webp"
    try:
        body = await asyncio.to_thread(_fetch_tile, url)
    except Exception as exc:
        logger.error("map tile failed: %s", type(exc).__name__)
        return JSONResponse({"error": "tile"}, status_code=404)
    return Response(content=body, media_type="image/webp", headers={"Cache-Control": "private, max-age=86400"})
