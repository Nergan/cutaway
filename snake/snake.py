from pathlib import Path
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates


router = APIRouter()
BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=BASE_DIR)
BACKGROUNDS_DIR = BASE_DIR / 'static' / 'backgrounds'


@router.get('/', response_class=FileResponse, name='snake_root')
async def snakepage():
    """Главная страница игры Snake."""
    return FileResponse(BASE_DIR / 'snake.html')


@router.get('/api/snake-backgrounds')
async def get_snake_backgrounds():
    """Return a list of background video filenames for Snake from the CDN."""
    mp4_files = [
        "Autumn.mp4",
        "hardtimes.mp4",
        "lamp.mp4",
        "Minecraft.mp4",
        "warmlight.mp4"
    ]
    return JSONResponse(content={'backgrounds': mp4_files})


@router.get('/{rest_of_path:path}', include_in_schema=False)
async def snake_fallback(request: Request):
    """Редирект на главную страницу игры."""
    return RedirectResponse(url=request.url_for('snake_root'))