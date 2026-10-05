"""Minecraft mod list. Mounted by the hub at /mods."""

from __future__ import annotations

import asyncio
import re

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, Response

from minecraft_mods.catalog import CatalogError, build_jar_archive, get_catalog
from minecraft_mods.render import render_page

router = APIRouter()
_REPO_NAME = re.compile(r"[A-Za-z0-9._-]{1,120}")


@router.get("/", response_class=HTMLResponse)
async def mods_home(request: Request) -> HTMLResponse:
    lang = _language(request)
    sort = request.query_params.get("sort") or "name"
    catalog = await asyncio.to_thread(get_catalog)
    return HTMLResponse(render_page(catalog, lang, sort))


@router.get("/{repo}/jars.zip")
async def download_jars(repo: str, loader: str = "") -> Response:
    if not _REPO_NAME.fullmatch(repo):
        raise HTTPException(status_code=404)
    catalog = await asyncio.to_thread(get_catalog)
    mod = next((item for item in catalog.mods if item.repo == repo), None)
    if mod is None or not (mod.mod_jars or mod.dependency_jars):
        raise HTTPException(status_code=404)
    try:
        payload, filename = await asyncio.to_thread(build_jar_archive, mod, loader or None)
    except CatalogError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
    return Response(
        content=payload,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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
