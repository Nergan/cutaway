from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

from dnd.bestiary import TIERS, load_beasts, search_beasts

router = APIRouter()
BASE_DIR = Path(__file__).parent


@router.get("/api")
async def api_index():
    return {
        "beasts": "/dnd/api/beasts",
        "query": ["q", "cat", "lang"],
        "cats": list(TIERS),
        "langs": ["ru", "en"],
    }


@router.get("/api/beasts")
async def beasts(
    q: str = "",
    cat: str = "all",
    lang: str = "ru",
):
    if len(q) > 200:
        raise HTTPException(status_code=400, detail="Query is too long.")
    if cat not in TIERS:
        raise HTTPException(status_code=400, detail="Unknown category.")
    if lang not in {"ru", "en"}:
        raise HTTPException(status_code=400, detail="Unknown language.")
    result = search_beasts(load_beasts(), q=q, cat=cat, lang=lang)
    return {
        "q": q,
        "cat": cat,
        "lang": lang,
        "sort": result["sort"],
        "filters": result["filters"],
        "negative": result["negative"],
        "count": len(result["beasts"]),
        "beasts": result["beasts"],
    }


@router.get("/", response_class=HTMLResponse)
async def dnd_menu():
    with open(BASE_DIR / "templates" / "menu.html", "r", encoding="utf-8") as f:
        return f.read()

@router.get("/foundry-blank-viewer", response_class=HTMLResponse)
async def foundry_viewer():
    with open(BASE_DIR / "templates" / "foundry_blank_viewer.html", "r", encoding="utf-8") as f:
        return f.read()

@router.get("/druid-helper", response_class=HTMLResponse)
async def druid_helper():
    with open(BASE_DIR / "templates" / "druid_helper.html", "r", encoding="utf-8") as f:
        return f.read()