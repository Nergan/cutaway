"""Show the macaroni-rate dashboard on /mikchan-rate.

The dashboard refuses to be framed, so this route fetches it and serves the
page from the hub. A failed fetch becomes a short error page.
"""

from __future__ import annotations

import asyncio
import http.client
import logging
import re
import socket
import ssl
from dataclasses import dataclass
from html import escape
from urllib.parse import urljoin

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response

from shared.network import NetworkPolicyError, preferred_outbound_ip, validate_outbound_url


logger = logging.getLogger(__name__)
router = APIRouter()

PREFIX = "/mikchan-rate"
UPSTREAM = "https://mikchan-dashboard-worker.makarka7923.workers.dev"
ALLOWED_HOSTS = ("mikchan-dashboard-worker.makarka7923.workers.dev",)
TIMEOUT_SECONDS = 25
MAX_BYTES = 2_000_000
_BROWSER = {"User-Agent": "Mozilla/5.0", "Accept": "*/*", "Accept-Encoding": "identity"}
_SAFE_PATH = re.compile(r"[A-Za-z0-9._~/-]{1,200}\Z")
_SAFE_QUERY = re.compile(r"[A-Za-z0-9._~=&%+-]{1,200}\Z")
_ROOT_REF = re.compile(r"""(?P<quote>["'(])/(?P<path>[A-Za-z0-9._~/?&=%+-]*)""")


@dataclass(frozen=True)
class Upstream:
    status: int
    content_type: str
    body: bytes


class UpstreamError(Exception):
    def __init__(self, message: str, status: int = 502) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """Connect to one checked address and keep the certificate name."""

    def __init__(self, ip: str, server_hostname: str, timeout: float) -> None:
        super().__init__(ip, timeout=timeout, context=ssl.create_default_context())
        self._server_hostname = server_hostname

    def connect(self) -> None:
        sock = socket.create_connection((self.host, self.port), self.timeout, self.source_address)
        try:
            self.sock = self._context.wrap_socket(sock, server_hostname=self._server_hostname)
        except Exception:
            sock.close()
            raise


def fetch_upstream(url: str) -> Upstream:
    current = url
    try:
        for _ in range(3):
            parsed = validate_outbound_url(current, allowed_hosts=ALLOWED_HOSTS)
            host = parsed.hostname or ""
            if parsed.scheme != "https" or not host:
                break
            port = parsed.port or 443
            ip = preferred_outbound_ip(host, port, allow_private=False)
            path = parsed.path or "/"
            if parsed.query:
                path = f"{path}?{parsed.query}"
            status, headers, body = _exchange(ip, host, port, path)
            if status not in {301, 302, 303, 307, 308}:
                content_type = headers.get("content-type", "")
                return Upstream(status, content_type, body)
            location = headers.get("location", "")
            if not location:
                break
            current = urljoin(current, location)
    except UpstreamError:
        raise
    except (TimeoutError, OSError, ssl.SSLError, NetworkPolicyError) as error:
        logger.warning("mikchan rate upstream failed: %s", error)
        raise UpstreamError("Страница курса не отвечает.") from error
    raise UpstreamError("Страница курса не отвечает.")


def _exchange(ip: str, host: str, port: int, path: str) -> tuple[int, dict[str, str], bytes]:
    connection = _PinnedHTTPSConnection(ip, host, TIMEOUT_SECONDS)
    try:
        connection.request(
            "GET",
            path,
            headers={**_BROWSER, "Host": host, "Connection": "close"},
        )
        response = connection.getresponse()
        body = response.read(MAX_BYTES + 1)
        headers = {key.lower(): value for key, value in response.getheaders()}
        status = int(response.status)
    finally:
        connection.close()
    if len(body) > MAX_BYTES:
        raise UpstreamError("Страница курса слишком большая.")
    return status, headers, body


def upstream_url(path: str, query: str) -> str:
    cleaned = path.strip("/")
    if cleaned:
        if ".." in cleaned.split("/") or _SAFE_PATH.fullmatch(cleaned) is None:
            raise UpstreamError("Некорректный адрес страницы курса.", 400)
        target = f"{UPSTREAM}/{cleaned}"
    else:
        target = f"{UPSTREAM}/"
    if query:
        if _SAFE_QUERY.fullmatch(query) is None:
            raise UpstreamError("Некорректный адрес страницы курса.", 400)
        target = f"{target}?{query}"
    return target


def rewrite(text: str) -> str:
    return _ROOT_REF.sub(lambda match: f"{match.group('quote')}{PREFIX}/{match.group('path')}", text)


def _rewritten(upstream: Upstream) -> bytes:
    kind = upstream.content_type.lower()
    if not any(token in kind for token in ("html", "javascript", "css")):
        return upstream.body
    return rewrite(upstream.body.decode("utf-8", "replace")).encode("utf-8")


def error_page(message: str, status: int = 502) -> HTMLResponse:
    text = escape(message)
    document = f"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Курс макарок</title>
  <style>
    body {{
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      background: #0a0a0a;
      color: #f4f1ea;
      font: 16px/1.5 Inter, Segoe UI, sans-serif;
    }}
    main {{ max-width: 34rem; padding: 2rem; }}
    h1 {{ font-size: 1.4rem; font-weight: 500; margin: 0 0 0.6rem; }}
    p {{ margin: 0; color: #b7b2a8; }}
  </style>
</head>
<body>
  <main>
    <h1>Не удалось показать курс</h1>
    <p>{text}</p>
  </main>
</body>
</html>
"""
    return HTMLResponse(document, status_code=status)


async def serve(path: str, query: str) -> Response:
    try:
        url = upstream_url(path, query)
        upstream = await asyncio.to_thread(fetch_upstream, url)
    except UpstreamError as error:
        return error_page(error.message, error.status)

    document = path.strip("/") == ""
    if document and upstream.status != 200:
        return error_page(f"Страница курса ответила ошибкой {upstream.status}.")
    if document and not upstream.body:
        return error_page("Страница курса пришла пустой.")
    if document and "html" not in upstream.content_type.lower():
        return error_page("Страница курса пришла в неожиданном виде.")
    if not document and upstream.status >= 400:
        return Response(status_code=upstream.status, content=b"", media_type="text/plain")

    media = upstream.content_type or "application/octet-stream"
    return Response(
        content=_rewritten(upstream),
        status_code=upstream.status,
        media_type=media.split(";")[0],
        headers={"cache-control": "no-store", "x-content-type-options": "nosniff"},
    )


@router.get("/")
async def dashboard(request: Request) -> Response:
    return await serve("", request.url.query)


@router.get("/{asset_path:path}")
async def dashboard_asset(asset_path: str, request: Request) -> Response:
    return await serve(asset_path, request.url.query)
