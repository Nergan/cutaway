from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter()


@router.get('/snake', response_class=FileResponse)
async def snakepage():
    return FileResponse('snake/snake.html')