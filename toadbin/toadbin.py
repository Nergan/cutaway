import os
from pathlib import Path
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from motor.motor_asyncio import AsyncIOMotorClient

router = APIRouter()
BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=BASE_DIR)
toad_background_dir = BASE_DIR / 'static/backgrounds'

MONGO_URL = os.environ.get('MONGODB_URI', 'mongodb://localhost:27017')
client = AsyncIOMotorClient(MONGO_URL, tls=True, tlsAllowInvalidCertificates=True)
db = client.toadbin
codes_collection = db.codes


@router.get('/', response_class=HTMLResponse, name='toad_root')
async def toadpage(request: Request):
    return templates.TemplateResponse(
        'toadbin.html',
        {
            'request': request,
            'code': '',
            'code_id': None,
            'is_readonly': False
        }
    )


@router.get('/{code_id}')
async def toadbin_codeview(request: Request, code_id: str):
    try:
        doc = await codes_collection.find_one({'code_id': code_id})
        if not doc:
            return RedirectResponse(url=request.url_for('toad_root'))
        return templates.TemplateResponse(
            'toadbin.html',
            {
                'request': request,
                'code': doc['content'],
                'code_id': code_id
            }
        )
    except Exception as e:
        # Логируем ошибку (можно заменить на нормальное логирование)
        print(f"Error in toadbin_codeview: {e}")
        return RedirectResponse(url=request.url_for('toad_root'))


@router.get('/api/backgrounds')
async def toad_backgrounds():
    try:
        if not toad_background_dir.exists():
            raise HTTPException(status_code=404, detail='Backgrounds directory not found')
        mp4_files = []
        for file in toad_background_dir.iterdir():
            if file.is_file() and file.suffix.lower() == '.mp4':
                mp4_files.append(file.name)
        mp4_files.sort()
        return JSONResponse(content={'backgrounds': mp4_files})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get('/api/existing-ids')
async def toad_ids():
    try:
        cursor = codes_collection.find({}, {'code_id': 1})
        docs = await cursor.to_list(length=1000)
        ids = [doc['code_id'] for doc in docs]
        return ids
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post('/api/save')
async def toad_save(request: dict):
    try:
        code_id = request.get('id')
        code_content = request.get('code')
        await codes_collection.update_one(
            {'code_id': str(code_id)},
            {'$set': {'code_id': str(code_id), 'content': code_content}},
            upsert=True
        )
        return {'status': 'success', 'id': code_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get('/{path:path}', include_in_schema=False)
async def toad_fallback(request: Request, path: str):
    if path.startswith('api/'):
        raise HTTPException(status_code=404, detail='API endpoint not found')
    return RedirectResponse(url=request.url_for('toad_root'))