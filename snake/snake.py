from pathlib import Path
from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, RedirectResponse

router = APIRouter()
BASE_DIR = Path(__file__).parent


@router.get('/', response_class=FileResponse, name='snake_root')
async def snakepage():
    """Главная страница игры Snake."""
    return FileResponse(BASE_DIR / 'snake.html')


@router.get('/{rest_of_path:path}', include_in_schema=False)
async def snake_fallback(request: Request):
    """Редирект на главную страницу игры."""
    return RedirectResponse(url=request.url_for('snake_root'))