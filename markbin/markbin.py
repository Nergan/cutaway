import os
import uuid
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Optional
from pathlib import Path

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel
from pymongo.errors import DuplicateKeyError

router = APIRouter()

BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=BASE_DIR)

MONGO_URL = os.environ.get('MONGODB_URI', 'mongodb://localhost:27017')
client = AsyncIOMotorClient(MONGO_URL, tls=True, tlsAllowInvalidCertificates=True)
db = client.markbins
codes_collection = db.docs

class DocRequest(BaseModel):
    content: str
    ttl_seconds: Optional[int] = None

@router.on_event("startup")
async def create_indexes():
    await codes_collection.create_index("hash", unique=True, sparse=True)
    await codes_collection.create_index("uuid", unique=True)
    # Native MongoDB TTL cleanup: automatically deletes documents when 'expires_at' is reached
    await codes_collection.create_index("expires_at", expireAfterSeconds=0)

@router.post('/api/save')
async def save_doc(doc: DocRequest):
    # Include TTL in the hash to allow identical content to have distinct expirations
    hash_input = doc.content + str(doc.ttl_seconds or 0)
    content_hash = hashlib.sha256(hash_input.encode('utf-8')).hexdigest()
    
    existing_doc = await codes_collection.find_one({"hash": content_hash})
    if existing_doc:
        return {"uuid": existing_doc["uuid"]}

    doc_id = uuid.uuid4().hex[:8]
    doc_payload = {
        "uuid": doc_id,
        "content": doc.content,
        "hash": content_hash
    }
    
    if doc.ttl_seconds and doc.ttl_seconds > 0:
        doc_payload["expires_at"] = datetime.now(timezone.utc) + timedelta(seconds=doc.ttl_seconds)

    try:
        await codes_collection.insert_one(doc_payload)
        return {"uuid": doc_id}
    except DuplicateKeyError:
        existing_doc = await codes_collection.find_one({"hash": content_hash})
        return {"uuid": existing_doc["uuid"]}

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
            
        return {"content": doc["content"], "expires_at": expires_at.isoformat()}
        
    return {"content": doc["content"]}

@router.get('/', response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("markbin.html", {
        "request": request,
        "uuid": "",
        "base_url": "/markbin"
    })

@router.get('/{doc_uuid}', response_class=HTMLResponse)
async def view_doc(request: Request, doc_uuid: str):
    return templates.TemplateResponse("markbin.html", {
        "request": request,
        "uuid": doc_uuid,
        "base_url": "/markbin"
    })