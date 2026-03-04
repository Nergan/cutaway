import os
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from motor.motor_asyncio import AsyncIOMotorClient
from pathlib import Path

router = APIRouter()
templates = Jinja2Templates(directory='toadbin')
toad_background_dir = Path('toadbin/static/backgrounds')

# MongoDB для toadbin
MONGO_URL = os.environ.get('MONGODB_URI', 'mongodb://localhost:27017')
client = AsyncIOMotorClient(MONGO_URL, tls=True, tlsAllowInvalidCertificates=True)
db = client.toadbin
codes_collection = db.codes


@router.get('/toadbin', response_class=HTMLResponse)
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


@router.get('/toadbin/{code_id}')
async def toadbin_codeview(request: Request, code_id: str):
    doc = await codes_collection.find_one({'code_id': code_id})
    if not doc:
        raise HTTPException(status_code=404, detail='Code not found')
    return templates.TemplateResponse(
        'toadbin.html',
        {
            'request': request,
            'code': doc['content'],
            'code_id': code_id
        }
    )


@router.get('/api/backgrounds')
async def toad_backgrounds():
    try:
        if not toad_background_dir.exists():
            raise HTTPException(status_code=404, detail='Backgrounds directory not found')
        gif_files = []
        for file in toad_background_dir.iterdir():
            if file.is_file() and file.suffix.lower() == '.mp4':
                gif_files.append(file.name)
        gif_files.sort()
        return JSONResponse(content={'backgrounds': gif_files})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get('/api/existing-ids')
async def toad_ids():
    cursor = codes_collection.find({}, {'code_id': 1})
    docs = await cursor.to_list(length=1000)
    ids = [int(doc['code_id']) for doc in docs if doc.get('code_id', '').isdigit()]
    return ids


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