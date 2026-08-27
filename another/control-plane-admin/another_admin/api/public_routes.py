"""Публичный портал: redeem invite-кода, статус сборки, скачивание zip."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from another_admin.api.config import ApiConfig
from another_admin.domain.builder import (
    ALLOWED_DESKTOP_PLATFORMS,
    artifact_filename,
    ldflags_for,
    nodes_json_for_control_plane,
)
from another_admin.ports.control_plane_store import ControlPlaneStore

router = APIRouter(prefix="/public/v1", tags=["public"])

INVALID = "invalid or expired invite"
JOB_TTL = timedelta(hours=2)
MAX_ARTIFACT_BYTES = 80 * 1024 * 1024


class RedeemBody(BaseModel):
    token: str = Field(min_length=8, max_length=128)
    platform: str = "windows/amd64"


def _store(request: Request) -> ControlPlaneStore:
    return request.app.state.store


def _cfg(request: Request) -> ApiConfig:
    return request.app.state.cfg


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _rate_ok(request: Request, ip: str, limit: int) -> bool:
    hits: dict[str, list[float]] = getattr(request.app.state, "redeem_hits", None)
    if hits is None:
        hits = {}
        request.app.state.redeem_hits = hits
    now = time.time()
    window = 3600.0
    recent = [t for t in hits.get(ip, []) if now - t < window]
    if len(recent) >= max(1, limit):
        hits[ip] = recent
        return False
    recent.append(now)
    hits[ip] = recent
    return True


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _secret_hash(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def _iso(value: Any) -> str | None:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    if value is None:
        return None
    return str(value)


def artifact_path(cfg: ApiConfig, job_id: str) -> Path:
    return Path(cfg.build_dir) / "installer-jobs" / f"{job_id}.zip"


@router.post("/redeem")
async def redeem(body: RedeemBody, request: Request) -> dict[str, Any]:
    cfg = _cfg(request)
    if not _rate_ok(request, _client_ip(request), cfg.public_redeem_per_hour):
        raise HTTPException(status_code=429, detail="too many requests")
    platform = body.platform.strip()
    if platform not in ALLOWED_DESKTOP_PLATFORMS:
        raise HTTPException(status_code=400, detail="unsupported platform")
    token = body.token.strip()
    store = _store(request)
    found = await store.find_enrollment_by_token_hash(_token_hash(token))
    if found is None:
        raise HTTPException(status_code=400, detail=INVALID)
    client_id, expires = found
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail=INVALID)
    client = await store.find_client(client_id)
    if client is None or client.is_banned:
        raise HTTPException(status_code=400, detail=INVALID)

    download_secret = secrets.token_urlsafe(32)
    job_id = str(uuid.uuid4())
    nodes_json = nodes_json_for_control_plane(cfg.control_plane_url)
    build_id = uuid.uuid4().hex[:12]
    flags = ldflags_for(
        token=token,
        client_id=client_id,
        build_id=build_id,
        nodes_json=nodes_json,
    )
    now = datetime.now(timezone.utc)
    await store.create_installer_job(
        {
            "job_id": job_id,
            "client_id": client_id,
            "platform": platform,
            "status": "queued",
            "enrollment_token": token,
            "nodes_json": nodes_json,
            "ldflags": flags,
            "build_id": build_id,
            "download_secret_hash": _secret_hash(download_secret),
            "filename": artifact_filename(platform),
            "error": None,
            "created_at": now,
            "expires_at": now + JOB_TTL,
        }
    )
    dispatch = getattr(request.app.state, "dispatch_installer", None)
    dispatched = False
    if callable(dispatch):
        try:
            dispatched = bool(await asyncio.to_thread(dispatch, job_id))
        except Exception:
            dispatched = False
    if not dispatched:
        await store.update_installer_job(
            job_id, {"status": "failed", "error": "builder_unconfigured"}
        )
        raise HTTPException(status_code=503, detail="builder unavailable")
    return {
        "job_id": job_id,
        "download_secret": download_secret,
        "status": "queued",
        "platform": platform,
    }


@router.get("/installer-jobs/{job_id}")
async def job_status(job_id: str, request: Request, secret: str = "") -> dict[str, Any]:
    job = await _store(request).get_installer_job(job_id)
    if job is None or not secret:
        raise HTTPException(status_code=404, detail="not found")
    expected = str(job.get("download_secret_hash") or "")
    if not expected or not hmac.compare_digest(expected, _secret_hash(secret)):
        raise HTTPException(status_code=404, detail="not found")
    status = str(job.get("status") or "queued")
    public_error = None
    if status == "failed":
        public_error = "build failed"
    return {
        "job_id": job_id,
        "status": status,
        "platform": job.get("platform"),
        "filename": job.get("filename"),
        "error": public_error,
        "expires_at": _iso(job.get("expires_at")),
    }


@router.get("/installer-jobs/{job_id}/download")
async def job_download(job_id: str, request: Request, secret: str = ""):
    cfg = _cfg(request)
    job = await _store(request).get_installer_job(job_id)
    if job is None or not secret:
        raise HTTPException(status_code=404, detail="not found")
    expected = str(job.get("download_secret_hash") or "")
    if not expected or not hmac.compare_digest(expected, _secret_hash(secret)):
        raise HTTPException(status_code=404, detail="not found")
    if str(job.get("status")) != "ready":
        raise HTTPException(status_code=409, detail="not ready")
    path = artifact_path(cfg, job_id)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="not found")
    name = str(job.get("filename") or path.name)
    return FileResponse(path, filename=name, media_type="application/zip")
