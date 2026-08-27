"""Админ-API: challenge/bootstrap + подписанные команды (docs/auth-spec.md)."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from another_admin.adapters.hybrid_crypto import HybridVerifyError, hybrid_verify
from another_admin.domain.admin_auth import (
    AdminAuthError,
    body_hash,
    bootstrap_message,
    command_message,
    commit_command,
    decide_command,
)
from another_admin.domain.anomaly import (
    AlertThresholds,
    evaluate,
    fingerprint_from_event,
)
from another_admin.domain.async_provisioning import AsyncDeviceProvisioningService
from another_admin.domain.builder import plan_installer, try_compile
from another_admin.domain.device_provisioning_service import ClientNotFoundError
from another_admin.domain.models import PingTarget
from another_admin.domain.quota_report_service import QuotaReportService
from another_admin.ports.control_plane_store import ControlPlaneStore

router = APIRouter(prefix="/admin/v1", tags=["admin"])

CHALLENGE_TTL = timedelta(seconds=60)


def _store(request: Request) -> ControlPlaneStore:
    return request.app.state.store


def _provisioning(request: Request) -> AsyncDeviceProvisioningService:
    return AsyncDeviceProvisioningService(
        store=_store(request),
        control_plane_url=request.app.state.cfg.control_plane_url,
    )


class BootstrapBody(BaseModel):
    admin_id: str
    challenge_hex: str
    sig_ed_hex: str
    sig_pq_hex: str


class CommandBody(BaseModel):
    admin_id: str
    seq: int = Field(ge=1)
    chain_head_prev_hex: str
    body: dict[str, Any]
    sig_ed_hex: str
    sig_pq_hex: str


def _hex_bytes(value: str, *, what: str) -> bytes:
    try:
        return bytes.fromhex(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"invalid hex: {what}") from exc


@router.get("/challenge")
async def issue_challenge(request: Request) -> dict[str, Any]:
    challenge = os.urandom(16)
    expires = datetime.now(timezone.utc) + CHALLENGE_TTL
    await _store(request).put_challenge(challenge.hex(), expires)
    return {"challenge_hex": challenge.hex(), "ttl_seconds": int(CHALLENGE_TTL.total_seconds())}


@router.post("/bootstrap")
async def bootstrap(body: BootstrapBody, request: Request) -> dict[str, Any]:
    admin = await _store(request).get_admin(body.admin_id)
    if admin is None or admin.revoked:
        raise HTTPException(status_code=403, detail="unknown admin")
    if not await _store(request).consume_challenge(body.challenge_hex):
        raise HTTPException(status_code=403, detail="invalid or expired challenge")
    challenge = _hex_bytes(body.challenge_hex, what="challenge")
    message = bootstrap_message(challenge)
    try:
        hybrid_verify(
            admin.ed25519_public_hex,
            admin.mldsa65_public_hex,
            message,
            _hex_bytes(body.sig_ed_hex, what="sig_ed"),
            _hex_bytes(body.sig_pq_hex, what="sig_pq"),
        )
    except (HybridVerifyError, AdminAuthError) as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return {
        "admin_id": admin.admin_id,
        "last_seq": admin.last_seq,
        "chain_head_hex": admin.chain_head_hex,
    }


@router.post("/command")
async def command(body: CommandBody, request: Request) -> dict[str, Any]:
    store = _store(request)
    admin = await store.get_admin(body.admin_id)
    if admin is None:
        raise HTTPException(status_code=403, detail="unknown admin")

    hashed = body_hash(body.body)
    chain_prev = _hex_bytes(body.chain_head_prev_hex, what="chain_head_prev")
    sig_ed = _hex_bytes(body.sig_ed_hex, what="sig_ed")
    sig_pq = _hex_bytes(body.sig_pq_hex, what="sig_pq")
    try:
        message = command_message(body.seq, chain_prev, hashed)
        hybrid_verify(admin.ed25519_public_hex, admin.mldsa65_public_hex, message, sig_ed, sig_pq)
        decision = decide_command(admin, body.seq, chain_prev, hashed, sig_ed, sig_pq)
    except (HybridVerifyError, AdminAuthError) as exc:
        code = getattr(exc, "code", "auth")
        if code == "fork":
            await store.append_event(
                {
                    "category": "anomaly",
                    "detail": {"type": "admin_fork", "admin_id": body.admin_id, "seq": body.seq},
                    "source": "admin-api",
                }
            )
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    if decision.kind == "replay":
        return {
            "replayed": True,
            "last_seq": admin.last_seq,
            "chain_head_hex": admin.chain_head_hex,
            "result": decision.cached_response,
        }

    try:
        result = await _execute_op(request, body.body)
    except ClientNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    committed = commit_command(admin, body.seq, hashed, sig_ed, sig_pq, result)
    ok = await store.replace_admin(admin.last_seq, committed)
    if not ok:
        raise HTTPException(status_code=409, detail="admin seq raced, retry")
    return {
        "replayed": False,
        "last_seq": committed.last_seq,
        "chain_head_hex": committed.chain_head_hex,
        "result": result,
    }


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _client_json(c) -> dict[str, Any]:
    pending = bool(c.enrollment_token_hash) and not c.is_enrolled and not c.is_banned
    return {
        "client_id": c.client_id,
        "user_id": c.user_id,
        "comment": c.comment,
        "is_banned": c.is_banned,
        "is_enrolled": c.is_enrolled,
        "quota_limit_bytes": c.quota_limit_bytes,
        "bytes_used": c.bytes_used,
        "public_key_hex": c.public_key_hex,
        "last_activity": _iso(c.last_activity),
        "enrollment_expires_at": _iso(c.enrollment_expires_at) if pending else None,
        "invite_pending": pending,
    }


def _invite_payload(result) -> dict[str, Any]:
    return {
        "client_id": result.client_id,
        "enrollment_token": result.enrollment_token,
        "qr_payload": result.qr_payload,
        "enrollment_expires_at": _iso(result.enrollment_expires_at),
        "invite_ttl_hours": 24,
    }


async def _invalidate_edge_ban(request: Request, client_id: str) -> None:
    cfg = request.app.state.cfg
    base = (cfg.edge_internal_url or "").rstrip("/")
    if not base or _is_loopback_url(base):
        return
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            res = await client.post(
                f"{base}/internal/ban-invalidate",
                json={"client_id": client_id},
                headers={"X-Another-Proxy-Secret": cfg.service_secret},
            )
        if res.status_code < 400:
            return
        detail: dict[str, Any] = {
            "type": "edge_ban_invalidate_failed",
            "status": res.status_code,
        }
    except httpx.HTTPError as err:
        detail = {
            "type": "edge_ban_invalidate_failed",
            "error": str(err)[:240],
        }
    await _store(request).append_event(
        {
            "category": "ops",
            "client_id": client_id,
            "detail": detail,
            "source": "admin-api",
        }
    )


def _is_loopback_url(url: str) -> bool:
    lowered = url.lower()
    return "127.0.0.1" in lowered or "localhost" in lowered or "[::1]" in lowered


async def _execute_op(request: Request, body: dict[str, Any]) -> dict[str, Any]:
    op = body.get("op")
    if not isinstance(op, str):
        raise ValueError("body.op is required")
    store = _store(request)
    provisioning = _provisioning(request)

    if op == "invite":
        comment = str(body.get("comment") or "").strip()
        if not comment:
            raise ValueError("comment is required")
        quota = int(body.get("quota_limit_bytes") or 0)
        result = await provisioning.create_invite(comment, quota)
        return _invite_payload(result)

    if op == "revoke":
        client_id = str(body.get("client_id") or "")
        await provisioning.revoke_device(client_id)
        await _invalidate_edge_ban(request, client_id)
        return {"client_id": client_id, "banned": True}

    if op == "unban":
        client_id = str(body.get("client_id") or "")
        await provisioning.unban_device(client_id)
        await _invalidate_edge_ban(request, client_id)
        return {"client_id": client_id, "banned": False}

    if op == "delete":
        client_id = str(body.get("client_id") or "")
        await provisioning.delete_device(client_id)
        await _invalidate_edge_ban(request, client_id)
        return {"client_id": client_id, "deleted": True}

    if op == "reissue":
        client_id = str(body.get("client_id") or "")
        result = await provisioning.reissue_device(client_id)
        await _invalidate_edge_ban(request, client_id)
        return {
            "revoked_client_id": client_id,
            **_invite_payload(result),
        }

    if op == "list_devices":
        devices = await provisioning.list_devices()
        return {"devices": [_client_json(c) for c in devices]}

    if op == "report":
        # QuotaReportService синхронный и ждёт UserRepositoryPort.
        # Для API считаем из уже загруженного списка — тот же смысл.
        devices = await store.list_clients()

        class _ListRepo:
            def list_clients(self_inner, _devices=devices):
                return _devices

        rows = QuotaReportService(repo=_ListRepo()).generate_report()
        return {
            "rows": [
                {
                    "client_id": r.client_id,
                    "comment": r.comment,
                    "bytes_used": r.bytes_used,
                    "quota_limit_bytes": r.quota_limit_bytes,
                    "percent_used": r.percent_used,
                    "is_banned": r.is_banned,
                }
                for r in rows
            ]
        }

    if op == "ping_targets_get":
        targets = await store.get_ping_targets()
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

    if op == "ping_targets_set":
        raw = body.get("targets")
        if not isinstance(raw, list):
            raise ValueError("targets must be a list")
        targets = [
            PingTarget(
                name=str(t["name"]),
                url=str(t["url"]),
                interval_s=int(t.get("interval_s", 300)),
                expect_status=int(t.get("expect_status", 200)),
            )
            for t in raw
        ]
        await store.set_ping_targets(targets)
        return {"ok": True, "count": len(targets)}

    if op == "events":
        unacked = bool(body.get("unacked_only", False))
        limit = int(body.get("limit") or 100)
        return {"events": await store.list_events(limit=limit, unacked_only=unacked)}

    if op == "ack_event":
        event_id = str(body.get("event_id") or "")
        ok = await store.ack_event(event_id)
        return {"ok": ok}

    if op == "sessions":
        active_s = int(body.get("active_within_s") or 180)
        return {"sessions": await store.list_sessions(active_within_s=active_s)}

    if op == "alert_thresholds_get":
        stored = await store.get_alert_thresholds()
        th = AlertThresholds.from_dict(stored)
        return {"thresholds": th.to_dict()}

    if op == "alert_thresholds_set":
        raw = body.get("thresholds")
        if not isinstance(raw, dict):
            raise ValueError("thresholds must be an object")
        th = AlertThresholds.from_dict(raw)
        await store.set_alert_thresholds(th.to_dict())
        return {"ok": True, "thresholds": th.to_dict()}

    if op == "investigation_get":
        return {"enabled": await store.get_investigation_mode()}

    if op == "investigation_set":
        enabled = bool(body.get("enabled"))
        await store.set_investigation_mode(enabled)
        return {"ok": True, "enabled": enabled}

    if op == "evaluate_alerts":
        th = AlertThresholds.from_dict(await store.get_alert_thresholds())
        events = await store.list_events(limit=int(body.get("limit") or 200))
        sessions = await store.list_sessions(active_within_s=th.session_active_s)
        existing = {
            fingerprint_from_event(e)
            for e in events
            if not e.get("acked") and fingerprint_from_event(e)
        }
        created: list[str] = []
        for alert in evaluate(events=events, sessions=sessions, thresholds=th):
            if alert.fingerprint in existing:
                continue
            event_id = await store.append_event(alert.as_event())
            created.append(event_id)
            existing.add(alert.fingerprint)
        return {"created": created, "count": len(created)}

    if op == "build_installer":
        client_id = str(body.get("client_id") or "")
        if not client_id:
            raise ValueError("client_id is required")
        result = await provisioning.reissue_device(client_id)
        await _invalidate_edge_ban(request, client_id)
        cfg = request.app.state.cfg
        platforms = body.get("platforms")
        if platforms is not None and not isinstance(platforms, list):
            raise ValueError("platforms must be a list")
        nodes_json = str(body.get("nodes_json") or cfg.nodes_json or "[]")
        plan = plan_installer(
            client_id=result.client_id,
            enrollment_token=result.enrollment_token,
            nodes_json=nodes_json,
            platforms=list(platforms) if platforms else None,
            core_src=cfg.core_src or "",
            output_dir=cfg.build_dir or "",
        )
        compiled = try_compile(plan, enabled=bool(cfg.build_enabled))
        payload = compiled.to_dict()
        payload["revoked_client_id"] = client_id
        payload.update(_invite_payload(result))
        return payload

    raise ValueError(f"unknown op: {op}")
