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

from formular.core.detector import detect_file_format, get_allowed_targets
from formular.core.converter import convert_document
from formular.core import speech
from shared_limits import RateLimiter, body_size_limit, too_large_detail

router = APIRouter()

TEMP_DIR = Path(tempfile.gettempdir()) / "formular_sessions"
TEMP_DIR.mkdir(parents=True, exist_ok=True)

MAX_UPLOAD_BYTES = int(os.environ.get("FORMULAR_MAX_UPLOAD_BYTES", 256 * 1024 * 1024))
MAX_OUTPUT_BYTES = int(os.environ.get("FORMULAR_MAX_OUTPUT_BYTES", 512 * 1024 * 1024))
SESSION_TTL_SECONDS = int(os.environ.get("FORMULAR_SESSION_TTL_SECONDS", 3600))
CONVERSION_SLOTS = asyncio.Semaphore(
    max(1, int(os.environ.get("FORMULAR_MAX_CONCURRENT_JOBS", "2")))
)
UPLOAD_RATE = RateLimiter(limit=10, window_seconds=60)
CONVERT_RATE = RateLimiter(limit=10, window_seconds=60)
SAMPLE_RATE = RateLimiter(limit=20, window_seconds=60)


def session_dir(raw_id: str) -> Path:
    """Session ids are server-generated UUIDs; anything else is a traversal attempt."""
    try:
        return TEMP_DIR / str(uuid.UUID(raw_id))
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid session id.")


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


def _api_index() -> dict:
    budget = file_budget()
    return {
        "max_upload_bytes": MAX_UPLOAD_BYTES,
        "max_file_bytes": budget,
        "max_output_bytes": MAX_OUTPUT_BYTES,
        "create_files": "POST /formular/api/files",
        "read_file": "GET /formular/api/files/{id}",
        "create_conversion": "POST /formular/api/files/{id}/conversions",
        "voices": "GET /formular/api/voices",
        "voice_sample": "GET /formular/api/voices/{id}/sample",
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
    detected_format = detect_file_format(str(input_file), original_name)
    
    working_input = task_dir / f"working_input.{detected_format}"
    shutil.copy(input_file, working_input)
    operation = speech.kind(detected_format, to_format)
    
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
                await asyncio.wait_for(
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
async def list_voices():
    return {"ai": True, "operation": "speech.speak", "voices": speech.public_voices()}


@router.get('/voices/{voice_id}/sample', dependencies=[Depends(SAMPLE_RATE)])
async def voice_sample(voice_id: str):
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