import os
import hashlib
from pathlib import Path
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel
from pymongo.errors import DuplicateKeyError

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


@router.on_event("startup")
async def create_indexes():
    # Ensure fast unique lookups. sparse=True prevents DuplicateKeyError 
    # for older database records that do not contain a 'hash' field.
    await codes_collection.create_index("hash", unique=True, sparse=True)
    await codes_collection.create_index("code_id", unique=True)


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
    """Return a list of available background video filenames from the CDN."""
    mp4_files =[
        "abypie.mp4", "black kirry.mp4", "cold rainy.mp4", "cozy rain.mp4",
        "fashion look.mp4", "jump into a puddle.mp4", "on lizzard.mp4",
        "salmons.mp4", "sigh.mp4", "snowy.mp4", "swimming.mp4",
        "there is no god beyond.mp4", "toad at home.mp4", "toad in a dark forest.mp4",
        "toad with guitar.mp4", "wisdom toad.mp4", "with mushroom.mp4", "bug day.mp4",
        "bug night.mp4"
    ]
    return JSONResponse(content={'backgrounds': mp4_files})


@router.post('/api/save')
async def toad_save(request: SaveRequest):
    """Save a new code snippet or update an existing one."""
    content_hash = hashlib.sha256(request.code.encode('utf-8')).hexdigest()

    # Deduplication check: see if this code was already uploaded
    existing_doc = await codes_collection.find_one({"hash": content_hash})
    if existing_doc:
        # Code already exists! Send back the original ID.
        return {'status': 'success', 'id': existing_doc['code_id']}

    try:
        # Insert the new code block along with its hash
        await codes_collection.insert_one({
            'code_id': request.id, 
            'content': request.code,
            'hash': content_hash
        })
        return {'status': 'success', 'id': request.id}
    except DuplicateKeyError:
        # In the exceedingly rare case of two simultaneous identical uploads
        existing_doc = await codes_collection.find_one({"hash": content_hash})
        if existing_doc:
            return {'status': 'success', 'id': existing_doc['code_id']}
        raise HTTPException(status_code=500, detail="Database conflict error")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get('/{path:path}', include_in_schema=False)
async def toad_fallback(request: Request, path: str):
    """Catch-all route: redirect to root for any non-API path."""
    if path.startswith('api/'):
        raise HTTPException(status_code=404, detail='API endpoint not found')
    return RedirectResponse(url=request.url_for('toad_root'))