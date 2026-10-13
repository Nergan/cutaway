"""Minecraft mod list. Mounted by the hub at /mods."""

from __future__ import annotations

import asyncio
import re

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from minecraft_mods.catalog import get_catalog, published_zip
from minecraft_mods.render import render_page
from minecraft_mods.search import mod_document, select_mods

router = APIRouter()
_REPO_NAME = re.compile(r"[A-Za-z0-9._-]{1,120}")
_VERSION = re.compile(r"[A-Za-z0-9._+-]{0,40}")


@router.get("/api")
async def api_index() -> dict:
    return {
        "mods": "/mods/api/mods",
        "query": ["q", "loader", "minecraft", "license"],
    }


@router.get("/api/mods")
async def list_mods(
    q: str = "",
    loader: str = "",
    minecraft: str = "",
    license: str = "",
) -> dict:
    if max(len(q), len(loader), len(minecraft), len(license)) > 200:
        raise HTTPException(status_code=400, detail="Filter is too long.")
    catalog = await asyncio.to_thread(get_catalog)
    mods = select_mods(
        catalog.mods,
        q=q,
        loader=loader,
        minecraft=minecraft,
        license_name=license,
    )
    return {
        "q": q,
        "loader": loader,
        "minecraft": minecraft,
        "license": license,
        "count": len(mods),
        "partial": catalog.partial,
        "error": catalog.error,
        "mods": [mod_document(mod) for mod in mods],
    }


@router.get("/")
async def mods_home(request: Request) -> Response:
    download = request.query_params.get("download", "")
    if download:
        return await _archive(
            download,
            request.query_params.get("loader", ""),
            request.query_params.get("minecraft", ""),
        )
    lang = _language(request)
    sort = request.query_params.get("sort") or "name"
    catalog = await asyncio.to_thread(get_catalog)
    return HTMLResponse(render_page(catalog, lang, sort))


async def _archive(repo: str, loader: str, minecraft: str) -> Response:
    if not _REPO_NAME.fullmatch(repo) or not _VERSION.fullmatch(minecraft or ""):
        raise HTTPException(status_code=404)
    catalog = await asyncio.to_thread(get_catalog)
    mod = next((item for item in catalog.mods if item.repo == repo), None)
    if mod is None:
        raise HTTPException(status_code=404)
    url = published_zip(mod, loader or None, minecraft or None)
    if not url:
        raise HTTPException(status_code=404)
    return RedirectResponse(url, status_code=302)


def _language(request: Request) -> str:
    requested = (request.query_params.get("lang") or "").lower()
    if requested in {"ru", "en"}:
        return requested
    header = request.headers.get("accept-language", "")
    for part in header.split(","):
        tag = part.split(";", 1)[0].strip().lower()
        if tag.startswith("ru"):
            return "ru"
        if tag.startswith("en"):
            return "en"
    return "en"
