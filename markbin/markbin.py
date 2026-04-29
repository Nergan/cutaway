import os
import uuid
from pathlib import Path

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel

router = APIRouter()

BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=BASE_DIR)

MONGO_URL = os.environ.get('MONGODB_URI', 'mongodb://localhost:27017')
client = AsyncIOMotorClient(MONGO_URL, tls=True, tlsAllowInvalidCertificates=True)
db = client.markbins
codes_collection = db.docs

class DocRequest(BaseModel):
    content: str

@router.post('/api/save')
async def save_doc(doc: DocRequest):
    doc_id = uuid.uuid4().hex[:8]
    await codes_collection.insert_one({"uuid": doc_id, "content": doc.content})
    return {"uuid": doc_id}

@router.get('/api/docs/{doc_uuid}')
async def get_doc(doc_uuid: str):
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