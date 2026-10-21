"""Show the macaroni-rate dashboard on /mikchan-rate.

The browser loads the chart from the dashboard. This route only copies the
embed document into a frame so the tab can use the dashboard icon and the
link back to the original chart can be left out. A failed copy becomes a
short error page.
"""

from __future__ import annotations

import asyncio
import http.client
import logging
import re
import socket
import ssl
import threading
import time
from html import escape

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from shared.network import NetworkPolicyError, preferred_outbound_ip, validate_outbound_url


logger = logging.getLogger(__name__)
router = APIRouter()

ORIGIN = "https://mikchan-dashboard-worker.makarka7923.workers.dev"
EMBED_URL = f"{ORIGIN}/embed"
FAVICON = f"{ORIGIN}/favicon.svg"
ALLOWED_HOSTS = ("mikchan-dashboard-worker.makarka7923.workers.dev",)
TIMEOUT_SECONDS = 12
MAX_BYTES = 500_000
CACHE_SECONDS = 600
_FETCH_LOCK = threading.Lock()
_FETCH_ATTEMPTS = 3
_BROWSER = {"User-Agent": "Mozilla/5.0", "Accept": "text/html", "Accept-Encoding": "identity"}

_OPEN_LINK = re.compile(
    r"""<a\b[^>]*\bclass=["']embed-open["'][^>]*>.*?</a>""",
    re.IGNORECASE | re.DOTALL,
)
_CHART_SCRIPT = re.compile(
    r"""<script\b[^>]*\bsrc=["']/chart\.js["'][^>]*>\s*</script>""",
    re.IGNORECASE,
)
_HEAD = re.compile(r"<head\b[^>]*>", re.IGNORECASE)
_HTML = re.compile(r"<html\b[^>]*>", re.IGNORECASE)

_cached_html = ""
_cached_at = 0.0

_HEIGHT_SCRIPT = """<script>
    const reportHeight = () => {
      const height = Math.ceil(document.documentElement.scrollHeight);
      parent.postMessage({ source: "mikchan-rate", height }, "*");
    };
    addEventListener("load", reportHeight);
    addEventListener("resize", reportHeight);
    if (window.ResizeObserver) new ResizeObserver(reportHeight).observe(document.documentElement);
  </script>
"""


class UpstreamError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


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


def prepare_embed(html: str) -> str:
    """Drop the link back to the chart and keep its files on the dashboard."""
    if "<html" not in html.lower() or "/chart.js" not in html:
        raise UpstreamError("Страница курса пришла в неожиданном виде.")
    prepared = _OPEN_LINK.sub("", html)
    if "embed-open" in prepared or "открыть график" in prepared:
        raise UpstreamError("Страница курса пришла в неожиданном виде.")
    prepared, count = _CHART_SCRIPT.subn('<script src="/chart.js"></script>', prepared, count=1)
    if count != 1:
        raise UpstreamError("Страница курса пришла в неожиданном виде.")
    if not re.search(r"<base\b", prepared, re.IGNORECASE):
        prepared, count = _HEAD.subn(lambda match: match.group(0) + f'<base href="{ORIGIN}/">', prepared, count=1)
        if count != 1:
            raise UpstreamError("Страница курса пришла в неожиданном виде.")
    if "</body>" not in prepared.lower():
        raise UpstreamError("Страница курса пришла в неожиданном виде.")
    prepared = _HTML.sub(_mark_embed, prepared, count=1)
    return prepared.replace("</body>", _HEIGHT_SCRIPT + "</body>", 1)


def _mark_embed(match: re.Match[str]) -> str:
    """Keep the embed layout. The open-chart link is already gone."""
    tag = match.group(0)
    if re.search(r"\bis-embed\b", tag):
        return tag
    class_attr = re.search(r"""\bclass=(["'])""", tag)
    if class_attr is None:
        return tag[:-1] + ' class="is-embed">'
    quote = class_attr.group(1)
    return re.sub(rf"""\bclass={quote}""", f"class={quote}is-embed ", tag, count=1)


def fetch_embed_html() -> str:
    last_error: Exception | None = None
    for attempt in range(_FETCH_ATTEMPTS):
        try:
            with _FETCH_LOCK:
                return _fetch_embed_once()
        except UpstreamError:
            raise
        except (TimeoutError, OSError, ssl.SSLError, NetworkPolicyError) as error:
            last_error = error
            logger.warning("mikchan rate embed failed: %s", error)
            if attempt + 1 < _FETCH_ATTEMPTS:
                time.sleep(0.4 * (attempt + 1))
    raise UpstreamError("Страница курса не отвечает.") from last_error


def _fetch_embed_once() -> str:
    parsed = validate_outbound_url(EMBED_URL, allowed_hosts=ALLOWED_HOSTS)
    host = parsed.hostname or ""
    port = parsed.port or 443
    ip = preferred_outbound_ip(host, port, allow_private=False)
    connection = _PinnedHTTPSConnection(ip, host, TIMEOUT_SECONDS)
    try:
        connection.request(
            "GET",
            "/embed",
            headers={**_BROWSER, "Host": host, "Connection": "close"},
        )
        response = connection.getresponse()
        body = response.read(MAX_BYTES + 1)
        content_type = ""
        for key, value in response.getheaders():
            if key.lower() == "content-type":
                content_type = value
        status = int(response.status)
    finally:
        connection.close()
    if len(body) > MAX_BYTES:
        raise UpstreamError("Страница курса слишком большая.")
    if status != 200:
        raise UpstreamError(f"Страница курса ответила ошибкой {status}.")
    if not body:
        raise UpstreamError("Страница курса пришла пустой.")
    if "html" not in content_type.lower():
        raise UpstreamError("Страница курса пришла в неожиданном виде.")
    return body.decode("utf-8", "replace")


def load_inner_html() -> str:
    global _cached_html, _cached_at
    now = time.monotonic()
    with _FETCH_LOCK:
        if _cached_html and now - _cached_at < CACHE_SECONDS:
            return _cached_html
    try:
        prepared = prepare_embed(fetch_embed_html())
    except UpstreamError:
        if _cached_html:
            logger.warning("mikchan rate embed refresh failed; using the previous copy")
            return _cached_html
        raise
    with _FETCH_LOCK:
        _cached_html = prepared
        _cached_at = time.monotonic()
    return prepared


def _document(body: str, *, status: int = 200) -> HTMLResponse:
    favicon = escape(FAVICON, quote=True)
    page = f"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Курс макарок</title>
  <link rel="icon" href="{favicon}" type="image/svg+xml">
  <style>
    html, body {{ margin: 0; min-height: 100%; background: #0a0a0a; color: #f4f1ea; }}
    body {{ font: 16px/1.5 Inter, Segoe UI, sans-serif; }}
    iframe {{
      width: 100%;
      height: 760px;
      border: 0;
      background: #0a0a0a;
      color-scheme: dark;
      display: block;
    }}
    iframe[hidden], main[hidden] {{ display: none; }}
    main {{ max-width: 34rem; padding: 2rem; }}
    h1 {{ font-size: 1.4rem; font-weight: 500; margin: 0 0 0.6rem; }}
    p {{ margin: 0; color: #b7b2a8; }}
  </style>
</head>
<body>
  {body}
</body>
</html>
"""
    return HTMLResponse(page, status_code=status, headers={"cache-control": "no-store"})


def _frame(inner: str) -> str:
    srcdoc = escape(inner, quote=True)
    return f"""<iframe sandbox="allow-scripts" srcdoc="{srcdoc}" title="Курс макарок"></iframe>
  <main hidden>
    <h1>Не удалось показать курс</h1>
    <p>Страница курса не отвечает.</p>
  </main>
  <script>
    const frame = document.querySelector("iframe");
    const error = document.querySelector("main");
    let shown = false;
    window.addEventListener("message", (event) => {{
      if (event.source !== frame.contentWindow) return;
      const data = event.data;
      if (!data || data.source !== "mikchan-rate") return;
      shown = true;
      const height = Number(data.height);
      if (height >= 320 && height <= 4000) frame.style.height = Math.ceil(height) + "px";
    }});
    setTimeout(() => {{
      if (shown) return;
      frame.hidden = true;
      error.hidden = false;
    }}, 12000);
  </script>"""


def error_page(message: str) -> HTMLResponse:
    text = escape(message)
    body = f"""<main>
    <h1>Не удалось показать курс</h1>
    <p>{text}</p>
  </main>"""
    return _document(body, status=424)


@router.get("/", response_class=HTMLResponse)
async def dashboard() -> HTMLResponse:
    try:
        inner = await asyncio.to_thread(load_inner_html)
    except UpstreamError as error:
        return error_page(error.message)
    return _document(_frame(inner))
