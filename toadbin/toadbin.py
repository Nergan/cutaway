import os
from pathlib import Path
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel

router = APIRouter()
BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=BASE_DIR)
BACKGROUNDS_DIR = BASE_DIR / 'static' / 'backgrounds'

# MongoDB connection
MONGO_URL = os.environ.get('MONGODB_URI', 'mongodb://localhost:27017')
client = AsyncIOMotorClient(MONGO_URL, tls=True, tlsAllowInvalidCertificates=True)
db = client.toadbin
codes_collection = db.codes


class SaveRequest(BaseModel):
    id: str
    code: str


@router.get('/', response_class=HTMLResponse, name='toad_root')
async def toadpage(request: Request):
    """Render the main page with an empty editor."""
    return templates.TemplateResponse(
        'toadbin.html',
        {
            'request': request,
            'code': '',
            'code_id': None,
        }
    )


@router.get('/{code_id}')
async def toadbin_codeview(request: Request, code_id: str):
    """Render a read-only view of an existing code snippet."""
    try:
        doc = await codes_collection.find_one({'code_id': code_id})
        if not doc:
            return RedirectResponse(url=request.url_for('toad_root'))
        return templates.TemplateResponse(
            'toadbin.html',
            {
                'request': request,
                'code': doc['content'],
                'code_id': code_id,
            }
        )
    except Exception as e:
        # Log the error appropriately in production
        print(f"Error in toadbin_codeview: {e}")
        return RedirectResponse(url=request.url_for('toad_root'))


@router.get('/api/backgrounds')
async def toad_backgrounds():
    """Return a list of available background video filenames."""
    if not BACKGROUNDS_DIR.exists():
        raise HTTPException(status_code=404, detail='Backgrounds directory not found')
    try:
        mp4_files = [f.name for f in BACKGROUNDS_DIR.iterdir() if f.is_file() and f.suffix.lower() == '.mp4']
        mp4_files.sort()
        return JSONResponse(content={'backgrounds': mp4_files})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get('/api/existing-ids')
async def toad_ids():
    """Return all existing code IDs (limited to 10000)."""
    try:
        cursor = codes_collection.find({}, {'code_id': 1})
        docs = await cursor.to_list(length=10000)  # Increased limit
        ids = [doc['code_id'] for doc in docs]
        return ids
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post('/api/save')
async def toad_save(request: SaveRequest):
    """Save a new code snippet or update an existing one."""
    try:
        await codes_collection.update_one(
            {'code_id': request.id},
            {'$set': {'code_id': request.id, 'content': request.code}},
            upsert=True
        )
        return {'status': 'success', 'id': request.id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get('/{path:path}', include_in_schema=False)
async def toad_fallback(request: Request, path: str):
    """Catch-all route: redirect to root for any non-API path."""
    if path.startswith('api/'):
        raise HTTPException(status_code=404, detail='API endpoint not found')
    return RedirectResponse(url=request.url_for('toad_root'))