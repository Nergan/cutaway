import asyncio
import os
import time
import uuid
import shutil
import tempfile
from pathlib import Path
from urllib.parse import quote
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from formular.core.detector import detect_file_format, get_allowed_targets
from formular.core.converter import convert_document

router = APIRouter()

TEMP_DIR = Path(tempfile.gettempdir()) / "formular_sessions"
TEMP_DIR.mkdir(parents=True, exist_ok=True)

MAX_UPLOAD_BYTES = int(os.environ.get("FORMULAR_MAX_UPLOAD_BYTES", 256 * 1024 * 1024))
SESSION_TTL_SECONDS = int(os.environ.get("FORMULAR_SESSION_TTL_SECONDS", 3600))


def session_dir(raw_id: str) -> Path:
    """Session ids are server-generated UUIDs; anything else is a traversal attempt."""
    try:
        return TEMP_DIR / str(uuid.UUID(raw_id))
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid session id.")


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
            detail=f"Upload exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MiB limit.",
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


@router.post('/upload', dependencies=[Depends(enforce_upload_limit)])
async def upload_files(files: list[UploadFile] = File(...)):
    try:
        await asyncio.to_thread(_sweep_stale_sessions)
    except OSError:
        pass

    results = []
    for file in files:
        file_id = str(uuid.uuid4())
        safe_dir = TEMP_DIR / file_id
        
        input_dir = safe_dir / "input"
        input_dir.mkdir(parents=True, exist_ok=True)
        
        # Strip any directory component the client put in the upload name.
        original_name = Path(file.filename or "").name
        if not original_name:
            results.append({"filename": file.filename, "error": "Missing file name."})
            continue
        file_path = input_dir / original_name
        
        # Backstop for chunked requests that arrive without a Content-Length.
        size = 0
        oversized = False
        with open(file_path, "wb") as f:
            while chunk := await file.read(8192 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    oversized = True
                    break
                f.write(chunk)

        if oversized:
            shutil.rmtree(safe_dir, ignore_errors=True)
            results.append({
                "filename": original_name,
                "error": f"File exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MiB limit.",
            })
            continue
        
        detected_format = detect_file_format(str(file_path), original_name)
        allowed_targets = get_allowed_targets(detected_format)
        
        if detected_format == 'unknown' or not allowed_targets:
            shutil.rmtree(safe_dir, ignore_errors=True)
            results.append({"filename": original_name, "error": "Unsupported file format."})
            continue
            
        results.append({
            "id": file_id,
            "filename": original_name,
            "size": size,
            "format": detected_format,
            "allowed_targets": allowed_targets
        })
    return {"files": results}

@router.post('/convert')
async def convert_file(
    file_id: str = Form(...), 
    to_format: str = Form(...),
    audio_opts: str = Form(None),
    video_opts: str = Form(None),
    custom_ffmpeg: str = Form(None),
    merge_id: str = Form(None),
    merge_loop: str = Form(None)
):
    safe_dir = session_dir(file_id)
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
            
    is_merge_loop = merge_loop == 'true'
    
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
    
    try:
        await convert_document(str(working_input), str(output_path), detected_format, to_format, audio_opts, video_opts, custom_ffmpeg, merge_path, is_merge_loop)
    except Exception as e:
        shutil.rmtree(task_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=str(e))
        
    encoded_filename = quote(output_filename)
    
    return FileResponse(
        path=output_path,
        filename=output_filename,
        media_type='application/octet-stream',
        headers={'Content-Disposition': f"attachment; filename*=UTF-8''{encoded_filename}"},
        background=BackgroundTask(shutil.rmtree, task_dir, ignore_errors=True)
    )