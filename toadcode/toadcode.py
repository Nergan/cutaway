import os
import hashlib
import json
import urllib.request
import asyncio
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, Request, HTTPException, Response
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel
from pymongo.errors import DuplicateKeyError

router = APIRouter()
BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=BASE_DIR)

MONGO_URL = os.environ.get('MONGODB_URI', 'mongodb://localhost:27017')
client = AsyncIOMotorClient(MONGO_URL, tls=True, tlsAllowInvalidCertificates=True)
db = client.toadcode
codes_collection = db.codes

class FileItem(BaseModel):
    path: str
    content: str
    is_dir: Optional[bool] = False

class SaveRequest(BaseModel):
    id: str
    files: List[FileItem]

@router.on_event("startup")
async def create_indexes():
    await codes_collection.create_index("hash", unique=True, sparse=True)
    await codes_collection.create_index("code_id", unique=True)

@router.get('/', response_class=HTMLResponse, name='toad_root')
async def toadpage(request: Request):
    return templates.TemplateResponse('toadcode.html', {'request': request, 'repo_data': '[]', 'code_id': None})

@router.get('/api/backgrounds')
async def toad_backgrounds():
    mp4_files = [
        "abypie.mp4", "black kirry.mp4", "cold rainy.mp4", "cozy rain.mp4",
        "fashion look.mp4", "jump into a puddle.mp4", "on lizzard.mp4",
        "salmons.mp4", "sigh.mp4", "snowy.mp4", "swimming.mp4",
        "there is no god beyond.mp4", "toad at home.mp4", "toad in a dark forest.mp4",
        "toad with guitar.mp4", "wisdom toad.mp4", "with mushroom.mp4", "bug day.mp4",
        "bug night.mp4", "pinus sylvestris.mp4"
    ]
    return JSONResponse(content={'backgrounds': mp4_files})

@router.get('/api/proxy-zip')
async def proxy_zip(url: str):
    """Securely proxies ZIP downloads for GitHub and HuggingFace to bypass client CORS."""
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 Toadcode/1.0'})
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, urllib.request.urlopen, req)
        zip_bytes = await loop.run_in_executor(None, response.read)
        return Response(content=zip_bytes, media_type="application/zip")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post('/api/save')
async def toad_save(request: SaveRequest):
    m = hashlib.sha256()
    for f in sorted(request.files, key=lambda x: x.path):
        m.update(f.path.encode('utf-8'))
        m.update(f.content.encode('utf-8'))
        m.update(str(f.is_dir).encode('utf-8'))
    content_hash = m.hexdigest()

    existing_doc = await codes_collection.find_one({"hash": content_hash})
    if existing_doc:
        return {'status': 'success', 'id': existing_doc['code_id']}

    try:
        await codes_collection.insert_one({
            'code_id': request.id, 
            'files': [f.dict() for f in request.files],
            'hash': content_hash
        })
        return {'status': 'success', 'id': request.id}
    except DuplicateKeyError:
        existing_doc = await codes_collection.find_one({"hash": content_hash})
        if existing_doc:
            return {'status': 'success', 'id': existing_doc['code_id']}
        raise HTTPException(status_code=500, detail="Database conflict error")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get('/{code_id:path}')
async def toadcode_codeview(request: Request, code_id: str):
    parts = code_id.strip("/").split("/")
    actual_code_id = parts[0]
    
    if actual_code_id == "api":
        raise HTTPException(status_code=404, detail="API endpoint not found")

    try:
        doc = await codes_collection.find_one({'code_id': actual_code_id})
        if not doc:
            return RedirectResponse(url=request.url_for('toad_root'))
        
        if 'content' in doc and 'files' not in doc:
            files_list = [{'path': 'snippet.txt', 'content': doc['content'], 'is_dir': False}]
        else:
            files_list = doc.get('files', [])
            
        files_json = json.dumps(files_list).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
        
        return templates.TemplateResponse(
            'toadcode.html',
            {
                'request': request,
                'repo_data': files_json,
                'code_id': actual_code_id,
            }
        )
    except Exception as e:
        print(f"Error in toadcode_codeview: {e}")
        return RedirectResponse(url=request.url_for('toad_root'))