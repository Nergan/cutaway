"""Android app push through Firebase Cloud Messaging HTTP v1.

The Android application registers a device token. Delivery needs a service
account in FCM_SERVICE_ACCOUNT (a file path or the JSON itself). Without that
configuration the token is kept and no request is sent.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from netlazy.config import settings
from netlazy.infrastructure.web_push import b64url_encode
from shared.network import SafeRedirectHandler, validate_outbound_url

FCM_HOSTS = ("fcm.googleapis.com", "oauth2.googleapis.com")
_TOKEN = {"value": "", "exp": 0, "email": ""}


def load_service_account() -> dict | None:
    raw = (settings.fcm_service_account or "").strip()
    if not raw:
        return None
    if raw.startswith("{"):
        data = json.loads(raw)
    else:
        path = Path(raw)
        if not path.is_file():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
    if not data.get("client_email") or not data.get("private_key") or not data.get("project_id"):
        return None
    return data


def _open(request: urllib.request.Request) -> tuple[int, bytes]:
    validate_outbound_url(request.full_url, allowed_hosts=FCM_HOSTS)
    opener = urllib.request.build_opener(SafeRedirectHandler(allowed_hosts=FCM_HOSTS))
    try:
        with opener.open(request, timeout=10) as response:
            return int(response.status), response.read(8192)
    except urllib.error.HTTPError as exc:
        return int(exc.code), exc.read(4096)


def _access_token(account: dict) -> str:
    now = int(time.time())
    if _TOKEN["value"] and _TOKEN["email"] == account["client_email"] and _TOKEN["exp"] - 60 > now:
        return _TOKEN["value"]
    header = b64url_encode(json.dumps({"alg": "RS256", "typ": "JWT"}, separators=(",", ":")).encode("utf-8"))
    claims = {
        "iss": account["client_email"],
        "scope": "https://www.googleapis.com/auth/firebase.messaging",
        "aud": "https://oauth2.googleapis.com/token",
        "iat": now,
        "exp": now + 3600,
    }
    payload = b64url_encode(json.dumps(claims, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{header}.{payload}".encode("ascii")
    key = serialization.load_pem_private_key(account["private_key"].encode("utf-8"), password=None)
    signature = key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    assertion = signing_input + b"." + b64url_encode(signature).encode("ascii")
    body = urllib.parse.urlencode({
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
        "assertion": assertion.decode("ascii"),
    }).encode("ascii")
    request = urllib.request.Request(
        "https://oauth2.googleapis.com/token",
        data=body,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    status, raw = _open(request)
    if status != 200:
        raise RuntimeError("android push authorization failed")
    data = json.loads(raw.decode("utf-8"))
    token = data.get("access_token") or ""
    if not token:
        raise RuntimeError("android push authorization failed")
    _TOKEN["value"] = token
    _TOKEN["email"] = account["client_email"]
    _TOKEN["exp"] = now + int(data.get("expires_in") or 3600)
    return token


def fcm_message(token: str, payload: dict) -> dict:
    icon = payload.get("icon_url") or ""
    notification = {"title": payload["title"], "body": payload["body"]}
    android_notification = {
        "channel_id": "handshakes",
        "color": payload["color"],
        "tag": payload["tag"],
        "icon": "ic_stat_netlazy",
    }
    if icon.startswith("https://"):
        notification["image"] = icon
        android_notification["image"] = icon
    return {
        "message": {
            "token": token,
            "notification": notification,
            "android": {"priority": "HIGH", "notification": android_notification},
            "data": {
                "type": payload["type"],
                "tag": payload["tag"],
                "open_path": payload["open_path"],
                "title": payload["title"],
                "body": payload["body"],
            },
        }
    }


def send_fcm(token: str, payload: dict) -> int:
    account = load_service_account()
    if account is None:
        return 0
    access = _access_token(account)
    url = f"https://fcm.googleapis.com/v1/projects/{account['project_id']}/messages:send"
    body = json.dumps(fcm_message(token, payload)).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"Authorization": f"Bearer {access}", "Content-Type": "application/json"},
    )
    status, raw = _open(request)
    if status in (401, 403):
        _TOKEN["value"] = ""
    text = raw.decode("utf-8", errors="replace")
    if "UNREGISTERED" in text or "NOT_FOUND" in text:
        return 410
    return status
