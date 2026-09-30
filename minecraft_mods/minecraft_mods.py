"""Minecraft mod list. Mounted by the hub at /mods."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from minecraft_mods.catalog import get_catalog
from minecraft_mods.render import render_page

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def mods_home(request: Request) -> HTMLResponse:
    lang = _language(request)
    sort = request.query_params.get("sort") or "name"
    catalog = await asyncio.to_thread(get_catalog)
    return HTMLResponse(render_page(catalog, lang, sort))


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
