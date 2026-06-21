from pathlib import Path
from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, RedirectResponse

from formular.api.endpoints import router as api_router

router = APIRouter()
BASE_DIR = Path(__file__).parent

router.include_router(api_router, prefix="/api")

@router.get('/', response_class=FileResponse, name='formular_root')
async def formular_page():
    return FileResponse(BASE_DIR / 'index.html')

@router.get('/{rest_of_path:path}', include_in_schema=False)
async def formular_fallback(request: Request):
    return RedirectResponse(url=request.url_for('formular_root'))