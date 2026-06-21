import os
import uuid
import hashlib
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

@router.on_event("startup")
async def create_indexes():
    # Ensure we have fast, unique lookups for both UUIDs and content hashes.
    # We use sparse=True so that old legacy documents without a 'hash' field 
    # don't trigger a DuplicateKeyError upon startup.
    await codes_collection.create_index("hash", unique=True, sparse=True)
    await codes_collection.create_index("uuid", unique=True)

@router.post('/api/save')
async def save_doc(doc: DocRequest):
    # 1. Calculate a fast, secure SHA-256 hash of the incoming content
    content_hash = hashlib.sha256(doc.content.encode('utf-8')).hexdigest()
    
    # 2. Check if this exact content already exists using the lightning-fast index
    existing_doc = await codes_collection.find_one({"hash": content_hash})
    if existing_doc:
        # Deduplication success! Return the existing URL.
        return {"uuid": existing_doc["uuid"]}

    # 3. If it doesn't exist, generate a new short UUID
    doc_id = uuid.uuid4().hex[:8]
    
    try:
        # 4. Insert the new document alongside its hash
        await codes_collection.insert_one({
            "uuid": doc_id,
            "content": doc.content,
            "hash": content_hash
        })
        return {"uuid": doc_id}
    except DuplicateKeyError:
        # Race condition handling: In the extremely rare event that two users 
        # submit the exact same text at the exact same millisecond.
        existing_doc = await codes_collection.find_one({"hash": content_hash})
        return {"uuid": existing_doc["uuid"]}

@router.get('/api/docs/{doc_uuid}')
async def get_doc(doc_uuid: str):
    # Thanks to the index created on startup, fetching by UUID is now also faster!
    doc = await codes_collection.find_one({"uuid": doc_uuid})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"content": doc["content"]}

@router.get('/', response_class=HTMLResponse)
async def home(request: Request):
    # Hardcoded base_url ensures absolute predictability for static/script paths
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