import sys
import uuid
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Optional
from pathlib import Path

from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import HTMLResponse
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

db = get_client().markbins
codes_collection = db.docs

MAX_DOC_CHARS = 512 * 1024
MAX_TTL_SECONDS = 365 * 24 * 3600

# Writes are unauthenticated, so cap what one client can push into the cluster.
save_guards = [
    Depends(body_size_limit(2 * MAX_DOC_CHARS)),
    Depends(RateLimiter(limit=20, window_seconds=60)),
]

class DocRequest(BaseModel):
    content: str = Field(..., max_length=MAX_DOC_CHARS)
    ttl_seconds: Optional[int] = Field(None, ge=0, le=MAX_TTL_SECONDS)

@router.on_event("startup")
async def create_indexes():
    await codes_collection.create_index("hash", unique=True, sparse=True)
    await codes_collection.create_index("uuid", unique=True)
    # Native MongoDB TTL cleanup: automatically deletes documents when 'expires_at' is reached
    await codes_collection.create_index("expires_at", expireAfterSeconds=0)

def _document_href(doc_id: str) -> str:
    return f"/markbin/api/docs/{doc_id}"


def _stored_reply(doc_id: str, expires_at=None) -> dict:
    reply = {"id": doc_id, "href": _document_href(doc_id)}
    if expires_at is not None:
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        reply["expires_at"] = expires_at.isoformat()
    return reply


async def _save(doc: DocRequest) -> dict:
    # Include TTL in the hash to allow identical content to have distinct expirations
    hash_input = doc.content + str(doc.ttl_seconds or 0)
    content_hash = hashlib.sha256(hash_input.encode('utf-8')).hexdigest()

    existing_doc = await codes_collection.find_one({"hash": content_hash})
    if existing_doc:
        return _stored_reply(existing_doc["uuid"], existing_doc.get("expires_at"))

    doc_id = uuid.uuid4().hex[:8]
    doc_payload = {
        "uuid": doc_id,
        "content": doc.content,
        "hash": content_hash
    }
    expires_at = None
    if doc.ttl_seconds and doc.ttl_seconds > 0:
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=doc.ttl_seconds)
        doc_payload["expires_at"] = expires_at

    try:
        await codes_collection.insert_one(doc_payload)
    except DuplicateKeyError:
        # Lost a race against a concurrent identical save, so reuse its document.
        existing_doc = await codes_collection.find_one({"hash": content_hash})
        if not existing_doc:
            raise HTTPException(status_code=409, detail="Concurrent write conflict, please retry.")
        return _stored_reply(existing_doc["uuid"], existing_doc.get("expires_at"))
    return _stored_reply(doc_id, expires_at)


@router.get('/api')
async def api_index():
    return {
        "create": {"method": "POST", "path": "/markbin/api/docs"},
        "read": {"method": "GET", "path": "/markbin/api/docs/{id}"},
        "page_save": {"method": "POST", "path": "/markbin/api/save"},
    }


@router.get('/api/docs')
async def docs_index():
    return {
        "create": {"method": "POST", "path": "/markbin/api/docs"},
        "read": {"method": "GET", "path": "/markbin/api/docs/{id}"},
    }


@router.post('/api/docs', status_code=201, dependencies=save_guards)
async def create_doc(doc: DocRequest):
    return await _save(doc)


@router.post('/api/save', dependencies=save_guards)
async def save_doc(doc: DocRequest):
    saved = await _save(doc)
    return {"uuid": saved["id"]}

@router.get('/api/docs/{doc_uuid}')
async def get_doc(doc_uuid: str):
    doc = await codes_collection.find_one({"uuid": doc_uuid})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
        
    expires_at = doc.get("expires_at")
    if expires_at:
        # Enforce UTC timezone awareness for accurate frontend client parsing
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
            
        if datetime.now(timezone.utc) >= expires_at:
            raise HTTPException(status_code=404, detail="Document expired")
            
        return {"id": doc["uuid"], "content": doc["content"], "expires_at": expires_at.isoformat()}

    return {"id": doc["uuid"], "content": doc["content"]}

@router.get('/', response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(request, "markbin.html", {
        "uuid": "",
        "base_url": "/markbin"
    })

@router.get('/{doc_uuid}', response_class=HTMLResponse)
async def view_doc(request: Request, doc_uuid: str):
    return templates.TemplateResponse(request, "markbin.html", {
        "uuid": doc_uuid,
        "base_url": "/markbin"
    })