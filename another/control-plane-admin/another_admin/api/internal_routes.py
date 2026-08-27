"""Внутренний API для Cloudflare Worker. Секрет сервиса, не пользовательский."""

from __future__ import annotations

import hmac
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from another_admin.api.config import ApiConfig
from another_admin.api.public_routes import MAX_ARTIFACT_BYTES, artifact_path
from another_admin.ports.control_plane_store import ControlPlaneStore


def _store(request: Request) -> ControlPlaneStore:
    return request.app.state.store


def _cfg(request: Request) -> ApiConfig:
    return request.app.state.cfg


async def require_proxy_secret(
    request: Request,
    x_another_proxy_secret: str | None = Header(default=None, alias="X-Another-Proxy-Secret"),
) -> None:
    """Гейт на весь роутер.

    Зависимости роутера решаются раньше валидации тела запроса, поэтому чужой
    запрос получает 401, а не 422 с описанием схемы. Проверять секрет внутри
    обработчика для этого поздно.
    """
    expected = _cfg(request).service_secret
    if not expected or not x_another_proxy_secret:
        raise HTTPException(status_code=401, detail="invalid proxy secret")
    if not hmac.compare_digest(x_another_proxy_secret, expected):
        raise HTTPException(status_code=401, detail="invalid proxy secret")


router = APIRouter(
    prefix="/internal/v1",
    tags=["internal"],
    dependencies=[Depends(require_proxy_secret)],
)


class FindClientBody(BaseModel):
    client_id: str


class FindEnrollmentBody(BaseModel):
    token_hash: str


class BindBody(BaseModel):
    client_id: str
    public_key_hex: str
    vless_user_id_hex: str
    public_key_mldsa65_hex: str | None = None


class ConsumeBody(BaseModel):
    token_hash: str


class UsageBody(BaseModel):
    client_id: str
    bytes_delta: int = Field(ge=0)


class EventBody(BaseModel):
    category: str
    client_id: str | None = None
    detail: dict[str, Any] = Field(default_factory=dict)


class SessionUpsertBody(BaseModel):
    client_id: str
    ip_hash: str
    node: str | None = None
    entrypoint: str | None = None
    ip: str | None = None
    bytes_delta: int = Field(default=0, ge=0)


class SessionCloseBody(BaseModel):
    client_id: str
    ip_hash: str
    bytes_delta: int = Field(default=0, ge=0)


def _client_json(c) -> dict[str, Any]:
    return {
        "client_id": c.client_id,
        "public_key_hex": c.public_key_hex,
        "public_key_mldsa65_hex": c.public_key_mldsa65_hex,
        "vless_user_id_hex": c.vless_user_id_hex,
        "is_banned": c.is_banned,
        "quota_limit_bytes": c.quota_limit_bytes,
        "bytes_used": c.bytes_used,
    }


@router.post("/clients/find")
async def find_client(
    body: FindClientBody,
    request: Request,
) -> dict[str, Any]:
    found = await _store(request).find_client(body.client_id)
    if found is None:
        raise HTTPException(status_code=404, detail="not found")
    return _client_json(found)


@router.post("/enrollments/find")
async def find_enrollment(
    body: FindEnrollmentBody,
    request: Request,
) -> dict[str, Any]:
    found = await _store(request).find_enrollment_by_token_hash(body.token_hash)
    if found is None:
        raise HTTPException(status_code=404, detail="not found")
    client_id, expires = found
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    return {
        "client_id": client_id,
        "expires_at_unix_seconds": int(expires.timestamp()),
    }


@router.post("/clients/bind")
async def bind_identity(
    body: BindBody,
    request: Request,
) -> dict[str, bool]:
    await _store(request).bind_device_identity(
        body.client_id,
        body.public_key_hex,
        body.vless_user_id_hex,
        body.public_key_mldsa65_hex,
    )
    return {"ok": True}


@router.post("/enrollments/consume")
async def consume_enrollment(
    body: ConsumeBody,
    request: Request,
) -> dict[str, bool]:
    await _store(request).consume_enrollment_token(body.token_hash)
    return {"ok": True}


@router.post("/clients/usage")
async def increment_usage(
    body: UsageBody,
    request: Request,
) -> dict[str, bool]:
    await _store(request).increment_usage(body.client_id, body.bytes_delta)
    return {"ok": True}


@router.get("/ping-targets")
async def ping_targets(
    request: Request,
) -> dict[str, Any]:
    targets = await _store(request).get_ping_targets()
    return {
        "targets": [
            {
                "name": t.name,
                "url": t.url,
                "interval_s": t.interval_s,
                "expect_status": t.expect_status,
            }
            for t in targets
        ]
    }


@router.post("/events")
async def post_event(
    body: EventBody,
    request: Request,
) -> dict[str, str]:
    event_id = await _store(request).append_event(
        {
            "category": body.category,
            "client_id": body.client_id,
            "detail": body.detail,
            "source": "worker",
        }
    )
    return {"event_id": event_id}


@router.post("/sessions/upsert")
async def upsert_session(
    body: SessionUpsertBody,
    request: Request,
) -> dict[str, str]:
    session_id = await _store(request).upsert_session(body.model_dump())
    return {"session_id": session_id}


@router.post("/sessions/close")
async def close_session(
    body: SessionCloseBody,
    request: Request,
) -> dict[str, bool]:
    ok = await _store(request).close_session(
        client_id=body.client_id,
        ip_hash=body.ip_hash,
        bytes_delta=body.bytes_delta,
    )
    return {"ok": ok}


@router.get("/installer-jobs/{job_id}")
async def get_installer_job(job_id: str, request: Request) -> dict[str, Any]:
    job = await _store(request).get_installer_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="not found")
    if str(job.get("status")) == "queued":
        await _store(request).update_installer_job(job_id, {"status": "building"})
        job["status"] = "building"
    created = job.get("created_at")
    expires = job.get("expires_at")
    return {
        "job_id": job["job_id"],
        "client_id": job.get("client_id"),
        "platform": job.get("platform"),
        "status": job.get("status"),
        "enrollment_token": job.get("enrollment_token") or "",
        "nodes_json": job.get("nodes_json") or "[]",
        "ldflags": job.get("ldflags") or "",
        "build_id": job.get("build_id") or "",
        "filename": job.get("filename"),
        "created_at": created.isoformat() if hasattr(created, "isoformat") else created,
        "expires_at": expires.isoformat() if hasattr(expires, "isoformat") else expires,
    }


class InstallerStatusBody(BaseModel):
    status: str
    error: str | None = None


@router.post("/installer-jobs/{job_id}/status")
async def set_installer_status(
    job_id: str, body: InstallerStatusBody, request: Request
) -> dict[str, bool]:
    if body.status not in {"queued", "building", "ready", "failed"}:
        raise HTTPException(status_code=400, detail="invalid status")
    fields: dict[str, Any] = {"status": body.status, "error": body.error}
    ok = await _store(request).update_installer_job(job_id, fields)
    if not ok:
        raise HTTPException(status_code=404, detail="not found")
    return {"ok": True}


@router.put("/installer-jobs/{job_id}/artifact")
async def put_installer_artifact(job_id: str, request: Request) -> dict[str, bool]:
    job = await _store(request).get_installer_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="not found")
    data = await request.body()
    if not data or len(data) > MAX_ARTIFACT_BYTES:
        raise HTTPException(status_code=413, detail="artifact too large")
    path = artifact_path(_cfg(request), job_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    ok = await _store(request).update_installer_job(
        job_id,
        {
            "status": "ready",
            "error": None,
            "enrollment_token": None,
        },
    )
    if not ok:
        raise HTTPException(status_code=404, detail="not found")
    return {"ok": True}
