"""Temporary public links for pictures taken out of a document.

The upload needs no account. The file is asked to live 24 hours, which is the
longest a formular result is allowed to live. The upload answer is the address
of an HTML page; the picture address is the preview on that page.
"""

from __future__ import annotations

import json
import re
import uuid
import urllib.request
from urllib.parse import urlsplit

from shared.network import NetworkPolicyError, safe_urlopen

UPLOAD_URL = "https://tmpfiles.org/api/v1/upload"
_KEEP_SECONDS = "86400"
_PAGE_HOST = "tmpfiles.org"
_PREVIEW = re.compile(
    r"""(?:src|href)=["'](https://tmpfiles\.org/dl/[^"']+)["']""",
    re.IGNORECASE,
)


def upload_image(data: bytes, suffix: str) -> str | None:
    """Public https address of the picture, or None when the host declines it."""
    try:
        page = _upload(data, suffix)
        html = safe_urlopen(page, timeout=45, max_bytes=512 * 1024)
        return direct_image_url(html.decode("utf-8", "replace"))
    except (NetworkPolicyError, OSError, ValueError, KeyError, json.JSONDecodeError):
        return None


def direct_image_url(page_html: str) -> str | None:
    """Picture address published on the host's page, limited to that host."""
    for match in _PREVIEW.finditer(page_html):
        url = match.group(1)
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower().rstrip(".")
        if parsed.scheme == "https" and host == _PAGE_HOST and parsed.path.startswith("/dl/"):
            return url
    return None


def _upload(data: bytes, suffix: str) -> str:
    if suffix not in {"jpg", "png"}:
        raise ValueError("Unsupported picture type.")
    boundary = "formular" + uuid.uuid4().hex
    body = b"".join(
        (
            (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="expire"\r\n\r\n'
                f"{_KEEP_SECONDS}\r\n"
            ).encode(),
            (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="file"; filename="picture.{suffix}"\r\n'
                f"Content-Type: image/{'jpeg' if suffix == 'jpg' else 'png'}\r\n\r\n"
            ).encode(),
            data,
            f"\r\n--{boundary}--\r\n".encode(),
        )
    )
    request = urllib.request.Request(
        UPLOAD_URL,
        data=body,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "User-Agent": "formular",
        },
        method="POST",
    )
    raw = safe_urlopen(request, timeout=45, max_bytes=64 * 1024)
    payload = json.loads(raw.decode("utf-8", "replace"))
    if payload.get("status") != "success":
        raise ValueError("The picture host declined the upload.")
    page = str(payload["data"]["url"])
    parsed = urlsplit(page)
    host = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme != "https" or host != _PAGE_HOST:
        raise ValueError("The picture host returned an unexpected address.")
    return page
