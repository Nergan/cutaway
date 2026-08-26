import sys
import hashlib
import json
import logging
import urllib.request
import asyncio
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse
from fastapi import APIRouter, Depends, Request, HTTPException, Response
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError

router = APIRouter()
BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=BASE_DIR)

# В монолите корень уже в sys.path, при standalone-запуске из папки плагина — нет.
sys.path.append(str(BASE_DIR.parent))
from shared_mongo import get_client
from shared_limits import RateLimiter, body_size_limit

db = get_client().toadcode
codes_collection = db.codes

MAX_FILES = 2000
MAX_FILE_CHARS = 512 * 1024
MAX_SNIPPET_BYTES = 8 * 1024 * 1024
MAX_PROXY_BYTES = 64 * 1024 * 1024

# Writes are unauthenticated, so cap what one client can push into the cluster.
save_guards = [
    Depends(body_size_limit(MAX_SNIPPET_BYTES)),
    Depends(RateLimiter(limit=20, window_seconds=60)),
]

class FileItem(BaseModel):
    path: str = Field(..., max_length=1024)
    content: str = Field(..., max_length=MAX_FILE_CHARS)
    is_dir: Optional[bool] = False

class SaveRequest(BaseModel):
    id: str = Field(..., max_length=128)
    files: List[FileItem] = Field(..., max_length=MAX_FILES)

@router.on_event("startup")
async def create_indexes():
    await codes_collection.create_index("hash", unique=True, sparse=True)
    await codes_collection.create_index("code_id", unique=True)

@router.get('/', response_class=HTMLResponse, name='toad_root')
async def toadpage(request: Request):
    return templates.TemplateResponse(request, 'toadcode.html', {'repo_data': '[]', 'code_id': None})

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

PROXY_ALLOWED_HOSTS = (
    "github.com",
    "codeload.github.com",
    "githubusercontent.com",
    "huggingface.co",
    "hf.co",
)


def _is_allowed_proxy_target(raw_url: str) -> bool:
    """Without this the endpoint is an open proxy into the container's network."""
    parsed = urlparse(raw_url)
    if parsed.scheme not in ("http", "https"):
        return False
    host = (parsed.hostname or "").lower()
    return any(host == allowed or host.endswith("." + allowed) for allowed in PROXY_ALLOWED_HOSTS)


def _fetch_zip(url: str) -> bytes:
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 Toadcode/1.0'})
    with urllib.request.urlopen(req, timeout=30) as response:
        # urlopen follows redirects, so whoever answered may not be who we vetted.
        if not _is_allowed_proxy_target(response.geturl()):
            raise ValueError("Redirected outside the allowed hosts.")
        declared = response.headers.get("Content-Length")
        if declared and declared.isdigit() and int(declared) > MAX_PROXY_BYTES:
            raise ValueError("Archive exceeds the size limit.")
        payload = response.read(MAX_PROXY_BYTES + 1)
    if len(payload) > MAX_PROXY_BYTES:
        raise ValueError("Archive exceeds the size limit.")
    return payload


@router.get('/api/proxy-zip', dependencies=[Depends(RateLimiter(limit=30, window_seconds=60))])
async def proxy_zip(url: str):
    """Proxies ZIP downloads for GitHub and HuggingFace to bypass client CORS."""
    if not _is_allowed_proxy_target(url):
        raise HTTPException(status_code=400, detail="Only GitHub and HuggingFace URLs are allowed.")
    try:
        zip_bytes = await asyncio.to_thread(_fetch_zip, url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        raise HTTPException(status_code=502, detail="Upstream archive could not be fetched.")
    return Response(content=zip_bytes, media_type="application/zip")

@router.post('/api/save', dependencies=save_guards)
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
            'files': [f.model_dump() for f in request.files],
            'hash': content_hash
        })
        return {'status': 'success', 'id': request.id}
    except DuplicateKeyError:
        existing_doc = await codes_collection.find_one({"hash": content_hash})
        if existing_doc:
            return {'status': 'success', 'id': existing_doc['code_id']}
        raise HTTPException(status_code=500, detail="Database conflict error")
    except Exception:
        logging.exception("toadcode: failed to persist snippet")
        raise HTTPException(status_code=500, detail="Could not save the snippet.")

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
            request,
            'toadcode.html',
            {
                'repo_data': files_json,
                'code_id': actual_code_id,
            }
        )
    except Exception:
        logging.exception("toadcode: failed to render snippet view")
        return RedirectResponse(url=request.url_for('toad_root'))