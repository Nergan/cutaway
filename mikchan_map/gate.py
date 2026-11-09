"""Password gate for the map.

The browser never receives the key list. A valid key becomes an HttpOnly
cookie that stores only a hash, and every request checks that hash against
the keys currently stored in MongoDB.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import time
from typing import Any

from fastapi import HTTPException, Request

_COOKIE = "mikchan_map"
_HASH = re.compile(r"^[0-9a-f]{64}$")
_SIG = re.compile(r"^[0-9a-f]{64}$")
_cache: dict[str, Any] = {"at": 0.0, "keys": []}
_fails: dict[str, list[float]] = {}
SEED_KEYS = ("3301", "rei", "muda muda")


def gate_secret() -> bytes:
    raw = (os.getenv("MAP_GATE_SECRET") or os.getenv("CLOUDINARY_API_SECRET") or "").strip()
    if len(raw) < 16:
        url = os.getenv("CLOUDINARY_URL", "")
        if "://" in url and "@" in url:
            creds = url.split("://", 1)[1].split("@", 1)[0]
            raw = creds.split(":", 1)[1].strip() if ":" in creds else ""
    return raw.encode() if len(raw) >= 16 else b""


_seal_cache = b""


async def active_secret() -> bytes:
    global _seal_cache
    env_secret = gate_secret()
    if env_secret:
        return env_secret
    if _seal_cache:
        return _seal_cache
    from mikchan_map.mikchan_map import get_store

    _seal_cache = await get_store().gate_seal()
    return _seal_cache


def normalize_key(value: str) -> str:
    return value.strip()


def issue_cookie(key: str, now: float | None = None, secret: bytes | None = None) -> str:
    secret = gate_secret() if secret is None else secret
    if not secret:
        raise RuntimeError("gate secret is missing")
    expiry = int((now if now is not None else time.time()) + 30 * 24 * 3600)
    body = f"{hashlib.sha256(key.encode()).hexdigest()}.{expiry}"
    signature = hmac.new(secret, body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{signature}"


def cookie_hash(token: str, now: float | None = None, secret: bytes | None = None) -> str | None:
    secret = gate_secret() if secret is None else secret
    if not secret or token.count(".") != 2:
        return None
    digest, expiry, signature = token.split(".")
    if not _HASH.fullmatch(digest) or not _SIG.fullmatch(signature):
        return None
    try:
        if int(expiry) < (now if now is not None else time.time()):
            return None
    except ValueError:
        return None
    expected = hmac.new(secret, f"{digest}.{expiry}".encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        return None
    return digest


def clear_gate_cache() -> None:
    _cache["at"] = 0.0
    _cache["keys"] = []


def too_many_attempts(host: str, now: float | None = None) -> bool:
    moment = now if now is not None else time.monotonic()
    recent = [item for item in _fails.get(host, []) if moment - item < 600]
    _fails[host] = recent
    return len(recent) >= 8


def note_failure(host: str, now: float | None = None) -> None:
    _fails.setdefault(host, []).append(now if now is not None else time.monotonic())


def client_host(request: Request) -> str:
    return request.client.host if request.client else "unknown"


async def current_keys() -> list[str]:
    from mikchan_map.mikchan_map import get_store

    moment = time.monotonic()
    if _cache["at"] and moment - _cache["at"] < 20:
        return list(_cache["keys"])
    raw = await get_store().access_keys()
    keys = []
    for item in raw:
        if not isinstance(item, str):
            continue
        key = normalize_key(item)
        if key and len(key) <= 80 and key not in keys:
            keys.append(key)
    _cache["at"] = moment
    _cache["keys"] = keys
    return list(keys)


async def gate_open(request: Request) -> bool:
    secret = await active_secret()
    if not secret:
        return False
    digest = cookie_hash(request.cookies.get(_COOKIE, ""), secret=secret)
    if not digest:
        return False
    for key in await current_keys():
        if hmac.compare_digest(hashlib.sha256(key.encode()).hexdigest(), digest):
            return True
    return False


async def require_gate(request: Request) -> None:
    try:
        secret = await active_secret()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="gate") from exc
    if not secret or not await gate_open(request):
        raise HTTPException(status_code=503 if not secret else 401, detail="gate" if not secret else "key")
