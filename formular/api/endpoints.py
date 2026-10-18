import asyncio
import json
import os
import time
import uuid
import shutil
import tempfile
from pathlib import Path
from typing import Optional
from urllib.parse import quote
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from pydantic import BaseModel, Field

from formular.core import speech
from shared.limits import RateLimiter, body_size_limit, too_large_detail

router = APIRouter()

TEMP_DIR = Path(tempfile.gettempdir()) / "formular_sessions"
TEMP_DIR.mkdir(parents=True, exist_ok=True)

MAX_UPLOAD_BYTES = int(os.environ.get("FORMULAR_MAX_UPLOAD_BYTES", 256 * 1024 * 1024))
MAX_OUTPUT_BYTES = int(os.environ.get("FORMULAR_MAX_OUTPUT_BYTES", 512 * 1024 * 1024))
# One assembled file. The public profile sets 3 GiB: under the 4 GiB file cap,
# with the model cache and the result still fitting in the 8 GiB temp dir.
MAX_STORED_BYTES = int(os.environ.get("FORMULAR_MAX_STORED_BYTES", str(1024 * 1024 * 1024)))
CHUNK_TARGET = 32 * 1024 * 1024
SESSION_TTL_SECONDS = int(os.environ.get("FORMULAR_SESSION_TTL_SECONDS", 3600))
CONVERSION_SLOTS = asyncio.Semaphore(
    max(1, int(os.environ.get("FORMULAR_MAX_CONCURRENT_JOBS", "2")))
)
UPLOAD_RATE = RateLimiter(limit=10, window_seconds=60)
CHUNK_RATE = RateLimiter(limit=40, window_seconds=60)
CONVERT_RATE = RateLimiter(limit=10, window_seconds=60)
SAMPLE_RATE = RateLimiter(limit=20, window_seconds=60)


def session_dir(raw_id: str) -> Path:
    """Session ids are server-generated UUIDs; anything else is a traversal attempt."""
    try:
        return TEMP_DIR / str(uuid.UUID(raw_id))
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid session id.")


class UploadStart(BaseModel):
    filename: str = Field(..., min_length=1, max_length=240)
    size: int = Field(..., ge=0)


class ConversionRequest(BaseModel):
    to: str = Field(..., max_length=32)
    audio: Optional[dict] = None
    video: Optional[dict] = None
    ffmpeg: Optional[str] = Field(None, max_length=4000)
    merge_id: Optional[str] = None
    merge_loop: bool = False


def file_budget() -> int:
    """Largest single file that still fits in the request once multipart framing is added."""
    margin = 64 * 1024 if MAX_UPLOAD_BYTES > 128 * 1024 else 0
    return max(1, MAX_UPLOAD_BYTES - margin)


def stored_budget() -> int:
    """Largest file the session disk will keep, whether it arrived in one request or several."""
    return max(file_budget(), MAX_STORED_BYTES)


def chunk_budget() -> int:
    """One piece stays inside the single-request cap, with room for a slow link to finish it."""
    return max(1, min(CHUNK_TARGET, file_budget(), stored_budget()))


def _api_index() -> dict:
    budget = file_budget()
    return {
        "max_upload_bytes": MAX_UPLOAD_BYTES,
        "max_file_bytes": budget,
        "max_stored_bytes": stored_budget(),
        "chunk_bytes": chunk_budget(),
        "max_output_bytes": MAX_OUTPUT_BYTES,
        "create_files": "POST /formular/api/files",
        "read_file": "GET /formular/api/files/{id}",
        "create_conversion": "POST /formular/api/files/{id}/conversions",
        "voices": "GET /formular/api/voices",
        "voice_sample": "GET /formular/api/voices?sample={id}",
    }


async def enforce_upload_limit(request: Request):
    """Reject oversized bodies before FastAPI parses the multipart form.

    Starlette spools uploads to disk while parsing, so a check inside the
    handler would run only after the bytes already landed there.
    """
    declared = request.headers.get("content-length")
    if declared is None:
        return
    try:
        length = int(declared)
    except ValueError:
        raise HTTPException(status_code=400, detail="Malformed Content-Length.")
    if length > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=too_large_detail("This request", length, MAX_UPLOAD_BYTES),
        )


def _sweep_stale_sessions():
    """Sessions are only cleaned up on a successful convert, so reap the rest."""
    cutoff = time.time() - SESSION_TTL_SECONDS
    for entry in TEMP_DIR.iterdir():
        try:
            if entry.is_dir() and entry.stat().st_mtime < cutoff:
                shutil.rmtree(entry, ignore_errors=True)
        except OSError:
            continue


def _describe_stored(file_id: str, original_name: str, file_path: Path, size: int) -> dict:
    # The format stack pulls in libmagic. Upload limits are checked before this.
    from formular.core.detector import detect_file_format, get_ai_targets, get_allowed_targets

    detected_format = detect_file_format(str(file_path), original_name)
    allowed_targets = get_allowed_targets(detected_format)
    if detected_format == "unknown" or not allowed_targets:
        return {"filename": original_name, "error": "Unsupported file format."}
    return {
        "id": file_id,
        "filename": original_name,
        "size": size,
        "format": detected_format,
        "allowed_targets": allowed_targets,
        "ai_targets": get_ai_targets(detected_format),
    }


async def _ingest(files: list[UploadFile]) -> list:
    try:
        await asyncio.to_thread(_sweep_stale_sessions)
    except OSError:
        pass

    budget = file_budget()
    results = []
    for file in files:
        file_id = str(uuid.uuid4())
        safe_dir = TEMP_DIR / file_id
        input_dir = safe_dir / "input"
        input_dir.mkdir(parents=True, exist_ok=True)

        original_name = Path(file.filename or "").name
        if not original_name:
            shutil.rmtree(safe_dir, ignore_errors=True)
            results.append({"filename": file.filename, "error": "Missing file name."})
            continue
        file_path = input_dir / original_name

        size = 0
        oversized = False
        with open(file_path, "wb") as handle:
            while chunk := await file.read(8192 * 1024):
                size += len(chunk)
                if size > budget:
                    oversized = True
                    break
                handle.write(chunk)

        if oversized:
            shutil.rmtree(safe_dir, ignore_errors=True)
            results.append({
                "filename": original_name,
                "error": too_large_detail(original_name, size, budget),
            })
            continue

        described = _describe_stored(file_id, original_name, file_path, size)
        if "error" in described:
            shutil.rmtree(safe_dir, ignore_errors=True)
        results.append(described)
    return results


def _stored_input(file_id: str) -> tuple[Path, Path, str]:
    safe_dir = session_dir(file_id)
    input_dir = safe_dir / "input"
    if not safe_dir.exists() or not input_dir.exists():
        raise HTTPException(status_code=404, detail="File session expired or not found.")
    try:
        input_file = next(input_dir.iterdir())
    except StopIteration:
        raise HTTPException(status_code=404, detail="File session expired or not found.")
    return safe_dir, input_file, input_file.name


@router.get("")
@router.get("/")
async def api_index():
    return _api_index()


@router.post(
    "/files",
    status_code=201,
    dependencies=[Depends(enforce_upload_limit), Depends(UPLOAD_RATE)],
)
async def create_files(files: list[UploadFile] = File(...)):
    return {"files": await _ingest(files)}


@router.get("/files/{file_id}")
async def read_file(file_id: str):
    _safe_dir, input_file, original_name = _stored_input(file_id)
    described = _describe_stored(file_id, original_name, input_file, input_file.stat().st_size)
    if "error" in described:
        raise HTTPException(status_code=422, detail=described["error"])
    return described


@router.post("/upload", dependencies=[Depends(enforce_upload_limit), Depends(UPLOAD_RATE)])
async def upload_files(files: list[UploadFile] = File(...)):
    """Same creation as POST /files. Kept so the current page does not have to change its URL."""
    return {"files": await _ingest(files)}


def _safe_name(raw: str) -> str:
    name = Path(raw or "").name.strip()
    if not name or name in {".", ".."}:
        raise HTTPException(status_code=400, detail="Missing file name.")
    return name


def _upload_meta(file_id: str) -> tuple[Path, dict]:
    folder = session_dir(file_id)
    meta_path = folder / "meta.json"
    if not meta_path.is_file():
        raise HTTPException(status_code=404, detail="Upload not found.")
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise HTTPException(status_code=404, detail="Upload not found.")
    return folder, meta


def _touch(folder: Path):
    try:
        os.utime(folder, None)
    except OSError:
        pass


@router.post("/uploads", status_code=201, dependencies=[Depends(UPLOAD_RATE)])
async def open_upload(body: UploadStart):
    """Reserve a session for a file that is larger than one request."""
    name = _safe_name(body.filename)
    limit = stored_budget()
    if body.size > limit:
        raise HTTPException(status_code=413, detail=too_large_detail(name, body.size, limit))
    try:
        await asyncio.to_thread(_sweep_stale_sessions)
    except OSError:
        pass
    file_id = str(uuid.uuid4())
    folder = TEMP_DIR / file_id
    (folder / "parts").mkdir(parents=True)
    meta = {"filename": name, "size": body.size}
    (folder / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    return {
        "id": file_id,
        "chunk_bytes": chunk_budget(),
        "max_stored_bytes": limit,
    }


@router.put(
    "/uploads/{file_id}/{index}",
    dependencies=[Depends(enforce_upload_limit), Depends(CHUNK_RATE)],
)
async def write_chunk(file_id: str, index: int, request: Request):
    if index < 0:
        raise HTTPException(status_code=400, detail="Invalid piece.")
    folder, meta = _upload_meta(file_id)
    declared = int(meta["size"])
    piece = chunk_budget()
    if declared == 0 or index * piece >= declared:
        raise HTTPException(status_code=400, detail="This piece is outside the file.")
    room = declared - index * piece
    expected = min(piece, room)
    data = await request.body()
    if len(data) != expected:
        raise HTTPException(
            status_code=413 if len(data) > expected else 400,
            detail=too_large_detail("This piece", len(data), expected)
            if len(data) > expected
            else "This piece is the wrong size.",
        )
    part = folder / "parts" / f"{index:08d}"
    part.write_bytes(data)
    _touch(folder)
    return {"received": index}


@router.post("/uploads/{file_id}/complete", dependencies=[Depends(UPLOAD_RATE)])
async def complete_upload(file_id: str):
    folder, meta = _upload_meta(file_id)
    name = meta["filename"]
    declared = int(meta["size"])
    input_dir = folder / "input"
    existing = [path for path in input_dir.iterdir() if path.is_file()] if input_dir.exists() else []
    if len(existing) == 1 and existing[0].stat().st_size == declared:
        described = await asyncio.to_thread(_describe_stored, file_id, name, existing[0], declared)
        return {"files": [described]}
    if input_dir.exists():
        shutil.rmtree(input_dir, ignore_errors=True)

    parts = folder / "parts"
    piece = chunk_budget()
    count = 0 if declared == 0 else (declared + piece - 1) // piece
    names = {path.name for path in parts.iterdir()} if parts.exists() else set()
    expected_names = {f"{index:08d}" for index in range(count)}
    if names != expected_names:
        raise HTTPException(status_code=400, detail="Upload is missing a piece.")

    input_dir.mkdir(parents=True, exist_ok=True)
    target = input_dir / name
    with open(target, "wb") as handle:
        for index in range(count):
            with open(parts / f"{index:08d}", "rb") as src:
                shutil.copyfileobj(src, handle)
    shutil.rmtree(parts, ignore_errors=True)
    if target.stat().st_size != declared:
        shutil.rmtree(folder, ignore_errors=True)
        raise HTTPException(status_code=400, detail="Upload size does not match.")
    described = await asyncio.to_thread(_describe_stored, file_id, name, target, declared)
    if "error" in described:
        shutil.rmtree(folder, ignore_errors=True)
    return {"files": [described]}


@router.delete("/uploads/{file_id}", status_code=204)
async def discard_upload(file_id: str):
    folder = session_dir(file_id)
    if folder.exists():
        shutil.rmtree(folder, ignore_errors=True)


async def _convert(
    file_id: str,
    to_format: str,
    audio_opts: str | None,
    video_opts: str | None,
    custom_ffmpeg: str | None,
    merge_id: str | None,
    merge_loop: bool,
):
    safe_dir, input_file, original_name = _stored_input(file_id)
    input_dir = safe_dir / "input"
    
    if not safe_dir.exists() or not input_dir.exists():
        raise HTTPException(status_code=404, detail="File session expired or not found.")
        
    input_file = next(input_dir.iterdir())
    original_name = input_file.name
    
    merge_path = None
    if merge_id:
        m_dir = session_dir(merge_id) / "input"
        if m_dir.exists():
            merge_path = str(next(m_dir.iterdir()))

    is_merge_loop = bool(merge_loop)
    
    if '.' in original_name:
        name_without_ext = original_name.rsplit('.', 1)[0]
    else:
        name_without_ext = original_name
    
    out_ext = 'tar.gz' if to_format == 'gz' else to_format
    output_filename = f"{name_without_ext}.{out_ext}"
    
    task_id = uuid.uuid4().hex
    task_dir = safe_dir / task_id
    task_dir.mkdir(parents=True, exist_ok=True)
    
    output_path = task_dir / output_filename
    from formular.core.detector import detect_file_format

    detected_format = detect_file_format(str(input_file), original_name)
    
    working_input = task_dir / f"working_input.{detected_format}"
    shutil.copy(input_file, working_input)
    operation = speech.kind(detected_format, to_format)
    chain_ops: list[str] = []
    spoken_text = None
    
    try:
        async with CONVERSION_SLOTS:
            if operation is not None:
                await asyncio.wait_for(
                    asyncio.to_thread(
                        speech.convert,
                        operation,
                        working_input,
                        output_path,
                        to_format,
                        audio_opts,
                    ),
                    timeout=900,
                )
            else:
                from formular.core.converter import convert_document

                produced = await asyncio.wait_for(
                    convert_document(
                        str(working_input),
                        str(output_path),
                        detected_format,
                        to_format,
                        audio_opts,
                        video_opts,
                        custom_ffmpeg,
                        merge_path,
                        is_merge_loop,
                    ),
                    timeout=900,
                )
                chain_ops = produced.get("operations") or []
                spoken_text = produced.get("spoken_text")
        if not output_path.is_file() or output_path.stat().st_size > MAX_OUTPUT_BYTES:
            raise ValueError("Converted output exceeds the configured limit.")
    except asyncio.TimeoutError:
        shutil.rmtree(task_dir, ignore_errors=True)
        raise HTTPException(status_code=504, detail="Conversion timed out.")
    except speech.SpeechError as exc:
        shutil.rmtree(task_dir, ignore_errors=True)
        raise HTTPException(status_code=exc.status, detail=str(exc))
    except Exception as e:
        shutil.rmtree(task_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=str(e))
        
    encoded_filename = quote(output_filename)
    headers = {'Content-Disposition': f"attachment; filename*=UTF-8''{encoded_filename}"}
    if operation is not None:
        source = working_input if operation == "speak" else None
        headers.update(speech.public_headers(operation, audio_opts, source))
    elif chain_ops:
        headers.update(speech.chain_headers(chain_ops, audio_opts, spoken_text))
    
    return FileResponse(
        path=output_path,
        filename=output_filename,
        media_type='application/octet-stream',
        headers=headers,
        background=BackgroundTask(shutil.rmtree, task_dir, ignore_errors=True)
    )


@router.post(
    "/files/{file_id}/conversions",
    dependencies=[Depends(body_size_limit(128 * 1024)), Depends(CONVERT_RATE)],
)
async def create_conversion(file_id: str, body: ConversionRequest):
    return await _convert(
        file_id,
        body.to,
        json.dumps(body.audio) if body.audio is not None else None,
        json.dumps(body.video) if body.video is not None else None,
        body.ffmpeg,
        body.merge_id,
        body.merge_loop,
    )


@router.post(
    '/convert',
    dependencies=[Depends(body_size_limit(128 * 1024)), Depends(CONVERT_RATE)],
)
async def convert_file(
    file_id: str = Form(...),
    to_format: str = Form(...),
    audio_opts: str = Form(None),
    video_opts: str = Form(None),
    custom_ffmpeg: str = Form(None),
    merge_id: str = Form(None),
    merge_loop: str = Form(None),
):
    return await _convert(
        file_id,
        to_format,
        audio_opts,
        video_opts,
        custom_ffmpeg,
        merge_id,
        merge_loop == "true",
    )


@router.get('/voices')
async def list_voices(request: Request, sample: str = ""):
    if sample:
        await SAMPLE_RATE(request)
        return await _voice_sample(sample)
    return {"ai": True, "operation": "speech.speak", "voices": speech.public_voices()}


async def _voice_sample(voice_id: str):
    try:
        path = await asyncio.to_thread(speech.sample_path, voice_id)
        headers = speech.public_headers("speak", json.dumps({"voice": voice_id}))
    except speech.SpeechError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc))
    headers['Content-Disposition'] = f'attachment; filename="{voice_id}-sample.wav"'
    return FileResponse(
        path=path,
        media_type='audio/wav',
        filename=f'{voice_id}-sample.wav',
        headers=headers,
    )