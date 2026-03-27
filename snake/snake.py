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
async def get_mainpage_backgrounds():
    """Return a list of available background video filenames."""
    if not BACKGROUNDS_DIR.exists():
        raise HTTPException(status_code=404, detail='Backgrounds directory not found')
    try:
        mp4_files = [f.name for f in BACKGROUNDS_DIR.iterdir() if f.is_file() and f.suffix.lower() == '.mp4']
        mp4_files.sort()
        return JSONResponse(content={'backgrounds': mp4_files})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get('/{rest_of_path:path}', include_in_schema=False)
async def snake_fallback(request: Request):
    """Редирект на главную страницу игры."""
    return RedirectResponse(url=request.url_for('snake_root'))