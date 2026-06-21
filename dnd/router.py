from pathlib import Path
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()
BASE_DIR = Path(__file__).parent

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