"""Public links for pictures taken out of a document.

Anonymous upload uses the Client ID from the Space secret. The identifier is
not a user token. A missing identifier, a spent upload quota, or a refused
upload leaves that picture out of the markdown. The text is still returned.
"""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request
import uuid
from urllib.parse import urlsplit

from shared.network import NetworkPolicyError, safe_urlopen

CLIENT_ID_ENV = "SHAREX_IMGUR_CLIENT_ID"
_UPLOAD_URL = "https://api.imgur.com/3/image"
_CREDITS_URL = "https://api.imgur.com/3/credits"
_UPLOAD_COST = 10
_RETRY_AFTER_SECONDS = 15 * 60
_LINK_HOSTS = frozenset({"i.imgur.com", "imgur.com"})
_QUOTA_WORDS = ("capacity", "rate limit", "rate-limit", "too many requests", "upload limit")

_lock = threading.Lock()
_blocked_until = 0.0
_credits_checked_at = 0.0
_credits_open = False


def reset_upload_state() -> None:
    global _blocked_until, _credits_checked_at, _credits_open
    with _lock:
        _blocked_until = 0.0
        _credits_checked_at = 0.0
        _credits_open = False


def upload_image(data: bytes, suffix: str) -> str | None:
    """Direct https address of the picture, or None when it cannot be published."""
    client_id = _client_id()
    if client_id is None or suffix not in {"jpg", "png"}:
        return None
    if not _quota_open(client_id):
        return None
    try:
        return _post_image(client_id, data, suffix)
    except urllib.error.HTTPError as exc:
        _note_http_failure(exc.code, _error_body(exc))
        return None
    except (NetworkPolicyError, OSError, ValueError, KeyError, json.JSONDecodeError):
        return None


def image_link(payload: dict) -> str | None:
    """Picture address from a successful upload answer, limited to the image host."""
    if payload.get("success") is not True:
        return None
    data = payload.get("data")
    if not isinstance(data, dict):
        return None
    link = str(data.get("link") or "")
    parsed = urlsplit(link)
    host = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme == "https" and host in _LINK_HOSTS:
        return link
    return None


def _client_id() -> str | None:
    raw = os.environ.get(CLIENT_ID_ENV, "").strip()
    if not raw or len(raw) > 80 or any(character.isspace() for character in raw):
        return None
    return raw


def _quota_open(client_id: str) -> bool:
    global _blocked_until, _credits_checked_at, _credits_open
    with _lock:
        if time.time() < _blocked_until:
            return False
        if _credits_open and time.time() - _credits_checked_at < 60:
            return True
    try:
        allowed, block_until = _read_credits(client_id)
    except urllib.error.HTTPError as exc:
        _note_http_failure(exc.code, _error_body(exc))
        return False
    except (NetworkPolicyError, OSError, ValueError, json.JSONDecodeError):
        return True
    with _lock:
        _credits_checked_at = time.time()
        _credits_open = allowed
        if block_until is not None:
            _blocked_until = max(_blocked_until, block_until)
        return allowed and time.time() >= _blocked_until


def _read_credits(client_id: str) -> tuple[bool, float | None]:
    payload = json.loads(_open(_credits_request(client_id)).decode("utf-8", "replace"))
    data = payload.get("data")
    if not isinstance(data, dict):
        return True, None
    remaining = [
        value
        for key in ("UserRemaining", "ClientRemaining")
        if isinstance((value := data.get(key)), int)
    ]
    if any(value < _UPLOAD_COST for value in remaining):
        reset = data.get("UserReset")
        when = float(reset) if isinstance(reset, (int, float)) and float(reset) > time.time() else time.time() + _RETRY_AFTER_SECONDS
        return False, when
    return True, None


def _post_image(client_id: str, data: bytes, suffix: str) -> str | None:
    boundary = "formular" + uuid.uuid4().hex
    body = b"".join(
        (
            (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="image"; filename="picture.{suffix}"\r\n'
                f"Content-Type: image/{'jpeg' if suffix == 'jpg' else 'png'}\r\n\r\n"
            ).encode(),
            data,
            (
                f"\r\n--{boundary}\r\n"
                f'Content-Disposition: form-data; name="type"\r\n\r\n'
                f"file\r\n"
                f"--{boundary}--\r\n"
            ).encode(),
        )
    )
    request = urllib.request.Request(
        _UPLOAD_URL,
        data=body,
        headers={
            "Authorization": f"Client-ID {client_id}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "User-Agent": "formular",
        },
        method="POST",
    )
    payload = json.loads(_open(request).decode("utf-8", "replace"))
    link = image_link(payload)
    if link is None:
        status = payload.get("status")
        _note_http_failure(int(status) if isinstance(status, int) else 0, json.dumps(payload).encode())
    return link


def _credits_request(client_id: str) -> urllib.request.Request:
    return urllib.request.Request(
        _CREDITS_URL,
        headers={
            "Authorization": f"Client-ID {client_id}",
            "User-Agent": "formular",
        },
    )


def _open(request: urllib.request.Request) -> bytes:
    return safe_urlopen(request, timeout=45, max_bytes=64 * 1024)


def _error_body(exc: urllib.error.HTTPError) -> bytes:
    try:
        return exc.read()
    except Exception:
        return b""


def _note_http_failure(status: int, body: bytes) -> None:
    global _blocked_until, _credits_open
    text = body.decode("utf-8", "replace").lower()
    if status not in {401, 403, 429} and not any(phrase in text for phrase in _QUOTA_WORDS):
        return
    with _lock:
        _credits_open = False
        _blocked_until = max(_blocked_until, time.time() + _RETRY_AFTER_SECONDS)
