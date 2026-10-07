import sys
import copy
import hashlib
import json
import logging
import os
import re
import secrets
import urllib.request
import uuid
import asyncio
from pathlib import Path
from typing import List, Optional
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
from shared_limits import RateLimiter, body_size_limit
from shared_network import NetworkPolicyError, safe_urlopen, validate_outbound_url

_CODE_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


class MemoryCollection:
    """Process-local stand-in used when MongoDB is not available for a local run."""

    def __init__(self):
        self._docs = []

    async def create_index(self, *args, **kwargs):
        return None

    async def find_one(self, query):
        for doc in self._docs:
            if all(doc.get(key) == value for key, value in query.items()):
                return copy.deepcopy(doc)
        return None

    async def insert_one(self, doc):
        if any(item.get("hash") == doc.get("hash") for item in self._docs):
            raise DuplicateKeyError("duplicate hash")
        if any(item.get("code_id") == doc.get("code_id") for item in self._docs):
            raise DuplicateKeyError("duplicate code_id")
        self._docs.append(copy.deepcopy(doc))

    async def update_one(self, query, update):
        for doc in self._docs:
            if all(doc.get(key) == value for key, value in query.items()):
                doc.update(copy.deepcopy(update.get("$set", {})))
                return

    async def delete_one(self, query):
        self._docs = [
            doc for doc in self._docs
            if not all(doc.get(key) == value for key, value in query.items())
        ]


def _open_collection():
    if os.environ.get("TOADCODE_STORE") == "memory":
        logging.warning("toadcode workspace store is in-memory for this process")
        return MemoryCollection()
    from shared_mongo import get_client
    return get_client().toadcode.codes


codes_collection = _open_collection()

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


class RepoWrite(BaseModel):
    files: List[FileItem] = Field(default_factory=list, max_length=MAX_FILES)


class FileWrite(BaseModel):
    content: str = Field("", max_length=MAX_FILE_CHARS)
    is_dir: bool = False


def _content_hash(files: list) -> str:
    digest = hashlib.sha256()
    for item in sorted(files, key=lambda entry: entry["path"]):
        digest.update(item["path"].encode("utf-8"))
        digest.update(item["content"].encode("utf-8"))
        digest.update(str(bool(item["is_dir"])).encode("utf-8"))
    return digest.hexdigest()


def _repo_hash(code_id: str, files: list) -> str:
    digest = hashlib.sha256()
    digest.update(b"repo\0")
    digest.update(code_id.encode("utf-8"))
    digest.update(b"\0")
    digest.update(_content_hash(files).encode("ascii"))
    return digest.hexdigest()


def _canonical_path(raw: str, is_dir: bool) -> str:
    text = (raw or "").replace("\\", "/").strip()
    wants_dir = is_dir or text.endswith("/")
    parts = [part for part in text.split("/") if part != ""]
    if (
        not parts
        or any(part in {".", ".."} or "\x00" in part for part in parts)
        or sum(len(part) for part in parts) + len(parts) - 1 > 1024
    ):
        raise HTTPException(status_code=400, detail="Invalid path.")
    cleaned = "/".join(parts)
    return cleaned + "/" if wants_dir else cleaned


def _measure(files: list) -> None:
    total = 0
    seen = set()
    for item in files:
        if item["path"] in seen:
            raise HTTPException(status_code=400, detail=f"Duplicate path '{item['path']}'.")
        seen.add(item["path"])
        total += len(item["content"].encode("utf-8"))
        if total > MAX_SNIPPET_BYTES:
            raise HTTPException(status_code=413, detail="Workspace exceeds the size limit.")
    if len(files) > MAX_FILES:
        raise HTTPException(status_code=400, detail="Too many files.")


def _normalize_files(files: list) -> list:
    cleaned = []
    for item in files:
        path = _canonical_path(item.path, bool(item.is_dir))
        content = "" if path.endswith("/") else item.content
        if path.endswith("/") and item.content:
            raise HTTPException(status_code=400, detail=f"Directory '{path}' cannot contain text.")
        cleaned.append({"path": path, "content": content, "is_dir": path.endswith("/")})
    _measure(cleaned)
    cleaned.sort(key=lambda entry: entry["path"])
    return cleaned


def _files_of(doc: dict) -> list:
    if "files" not in doc and "content" in doc:
        raw = [{"path": "snippet.txt", "content": doc.get("content") or "", "is_dir": False}]
    else:
        raw = doc.get("files") or []
    return [
        {
            "path": item.get("path") or "",
            "content": item.get("content") or "",
            "is_dir": bool(item.get("is_dir")),
        }
        for item in raw
    ]


def _view(doc: dict) -> dict:
    return {
        "id": doc["code_id"],
        "editable": bool(doc.get("token_hash")),
        "files": _files_of(doc),
    }


def _check_code_id(code_id: str) -> str:
    if not _CODE_ID.fullmatch(code_id or ""):
        raise HTTPException(status_code=404, detail="Workspace not found.")
    return code_id


async def _load(code_id: str) -> dict:
    doc = await codes_collection.find_one({"code_id": _check_code_id(code_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Workspace not found.")
    return doc


def _presented_token(request: Request) -> str:
    header = request.headers.get("authorization", "")
    if header[:7].lower() == "bearer ":
        token = header[7:].strip()
    else:
        token = (request.headers.get("x-toadcode-token") or "").strip()
    if len(token) > 256:
        return ""
    return token


def _authorize(doc: dict, request: Request) -> None:
    expected = doc.get("token_hash")
    if not expected:
        raise HTTPException(status_code=403, detail="This workspace is read-only.")
    token = _presented_token(request)
    actual = hashlib.sha256(token.encode("utf-8")).hexdigest() if token else ""
    if not token or not secrets.compare_digest(expected, actual):
        raise HTTPException(status_code=401, detail="Missing or invalid workspace token.")


def _find_entry(files: list, raw: str) -> Optional[dict]:
    file_path = _canonical_path(raw, False)
    dir_path = _canonical_path(raw, True)
    by_path = {item["path"]: item for item in files}
    if raw.replace("\\", "/").endswith("/") and dir_path in by_path:
        return by_path[dir_path]
    if file_path in by_path:
        return by_path[file_path]
    if dir_path in by_path:
        return by_path[dir_path]
    return None


def _drop_path(files: list, raw: str) -> Optional[list]:
    file_path = _canonical_path(raw, False)
    dir_path = _canonical_path(raw, True)
    paths = {item["path"] for item in files}
    has_file = file_path in paths
    has_dir = dir_path in paths or any(path.startswith(dir_path) for path in paths)
    directory_request = raw.replace("\\", "/").endswith("/")
    if has_dir and (directory_request or not has_file):
        return [
            item for item in files
            if item["path"] != dir_path and not item["path"].startswith(dir_path)
        ]
    if has_file:
        return [item for item in files if item["path"] != file_path]
    return None


def _upsert_entry(files: list, raw: str, content: str, is_dir: bool) -> list:
    path = _canonical_path(raw, is_dir)
    if path.endswith("/") and content:
        raise HTTPException(status_code=400, detail="A directory cannot contain text.")
    stored = {"path": path, "content": "" if path.endswith("/") else content, "is_dir": path.endswith("/")}
    updated = []
    found = False
    for item in files:
        if item["path"] == path:
            updated.append(stored)
            found = True
        else:
            updated.append(dict(item))
    if not found:
        updated.append(stored)
    _measure(updated)
    updated.sort(key=lambda entry: entry["path"])
    return updated


async def _write_files(code_id: str, files: list) -> dict:
    await codes_collection.update_one(
        {"code_id": code_id},
        {"$set": {"files": files, "hash": _repo_hash(code_id, files)}},
    )
    doc = await codes_collection.find_one({"code_id": code_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Workspace not found.")
    return doc


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
    "*.github.com",
    "githubusercontent.com",
    "*.githubusercontent.com",
    "huggingface.co",
    "*.huggingface.co",
    "hf.co",
    "*.hf.co",
)


def _is_allowed_proxy_target(raw_url: str) -> bool:
    """Without this the endpoint is an open proxy into the container's network."""
    try:
        validate_outbound_url(
            raw_url,
            allowed_hosts=PROXY_ALLOWED_HOSTS,
            resolve_dns=False,
        )
    except NetworkPolicyError:
        return False
    return True


def _fetch_zip(url: str) -> bytes:
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 Toadcode/1.0'})
    return safe_urlopen(
        req,
        timeout=30,
        allowed_hosts=PROXY_ALLOWED_HOSTS,
        max_bytes=MAX_PROXY_BYTES,
    )


@router.get('/api/proxy-zip', dependencies=[Depends(RateLimiter(limit=30, window_seconds=60))])
async def proxy_zip(url: str):
    """Proxies ZIP downloads for GitHub and HuggingFace to bypass client CORS."""
    if not _is_allowed_proxy_target(url):
        raise HTTPException(status_code=400, detail="Only GitHub and HuggingFace URLs are allowed.")
    try:
        zip_bytes = await asyncio.to_thread(_fetch_zip, url)
    except (ValueError, NetworkPolicyError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        raise HTTPException(status_code=502, detail="Upstream archive could not be fetched.")
    return Response(content=zip_bytes, media_type="application/zip")

@router.get('/api')
async def api_index():
    return {
        "create": "POST /toadcode/api/repos",
        "read": "GET /toadcode/api/repos/{id}",
        "replace": "PUT /toadcode/api/repos/{id}",
        "delete": "DELETE /toadcode/api/repos/{id}",
        "read_file": "GET /toadcode/api/repos/{id}/files/{path}",
        "write_file": "PUT /toadcode/api/repos/{id}/files/{path}",
        "delete_file": "DELETE /toadcode/api/repos/{id}/files/{path}",
    }


@router.post('/api/repos', dependencies=save_guards)
async def create_repo(body: RepoWrite):
    files = _normalize_files(body.files)
    token = secrets.token_urlsafe(32)
    for _ in range(3):
        code_id = uuid.uuid4().hex
        doc = {
            "code_id": code_id,
            "files": files,
            "hash": _repo_hash(code_id, files),
            "token_hash": hashlib.sha256(token.encode("utf-8")).hexdigest(),
        }
        try:
            await codes_collection.insert_one(doc)
            break
        except DuplicateKeyError:
            doc = None
    if not doc:
        raise HTTPException(status_code=500, detail="Could not save the workspace.")
    payload = _view(doc)
    payload["token"] = token
    return JSONResponse(payload, status_code=201)


@router.get('/api/repos/{code_id}')
async def read_repo(code_id: str):
    return _view(await _load(code_id))


@router.put('/api/repos/{code_id}', dependencies=save_guards)
async def replace_repo(code_id: str, body: RepoWrite, request: Request):
    doc = await _load(code_id)
    _authorize(doc, request)
    files = _normalize_files(body.files)
    return _view(await _write_files(doc["code_id"], files))


@router.delete('/api/repos/{code_id}', dependencies=save_guards)
async def delete_repo(code_id: str, request: Request):
    doc = await _load(code_id)
    _authorize(doc, request)
    await codes_collection.delete_one({"code_id": doc["code_id"]})
    return Response(status_code=204)


@router.get('/api/repos/{code_id}/files/{file_path:path}')
async def read_repo_file(code_id: str, file_path: str):
    files = _files_of(await _load(code_id))
    entry = _find_entry(files, file_path)
    if entry is None:
        raise HTTPException(status_code=404, detail="File not found.")
    return entry


@router.put('/api/repos/{code_id}/files/{file_path:path}', dependencies=save_guards)
async def write_repo_file(code_id: str, file_path: str, body: FileWrite, request: Request):
    doc = await _load(code_id)
    _authorize(doc, request)
    files = _upsert_entry(_files_of(doc), file_path, body.content, body.is_dir)
    return _view(await _write_files(doc["code_id"], files))


@router.delete('/api/repos/{code_id}/files/{file_path:path}', dependencies=save_guards)
async def delete_repo_file(code_id: str, file_path: str, request: Request):
    doc = await _load(code_id)
    _authorize(doc, request)
    files = _drop_path(_files_of(doc), file_path)
    if files is None:
        raise HTTPException(status_code=404, detail="File not found.")
    return _view(await _write_files(doc["code_id"], files))


@router.post('/api/save', dependencies=save_guards)
async def toad_save(request: SaveRequest):
    stored = [item.model_dump() for item in request.files]
    for item in stored:
        item["is_dir"] = bool(item.get("is_dir"))
        item["content"] = item.get("content") or ""
    content_hash = _content_hash(stored)

    existing_doc = await codes_collection.find_one({"hash": content_hash})
    if existing_doc:
        return {'status': 'success', 'id': existing_doc['code_id']}

    try:
        await codes_collection.insert_one({
            'code_id': request.id,
            'files': stored,
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