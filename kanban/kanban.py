from pathlib import Path
from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter()

BASE_DIR = Path(__file__).parent

@router.get('/', response_class=FileResponse)
async def kanban_home():
    # Return the standalone HTML file
    return FileResponse(BASE_DIR / 'kanban.html')