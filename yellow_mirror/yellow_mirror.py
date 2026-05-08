import asyncio
import json
from pathlib import Path
from urllib.parse import urljoin, urlparse, quote, urlunparse

from curl_cffi import requests as curl_requests  # TLS impersonation
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import Response, FileResponse

from .logic.config import ALLOWED_SCHEMES
from .logic.url_utils import is_safe_url

router = APIRouter()
BASE_DIR = Path(__file__).parent

# -------------------------------------------------------------------
@router.get('/')
async def serve_app():
    """Serve the new SPA shell."""
    return FileResponse(BASE_DIR / 'yellow-mirror.html')

# -------------------------------------------------------------------
@router.api_route('/api/', methods=['GET','POST','PUT','DELETE','PATCH','HEAD','OPTIONS'])
async def proxy(request: Request):
    target = request.query_params.get('target')
    if not target:
        raise HTTPException(status_code=400, detail="Missing 'target'")

    # Security: block private IPs / self‑proxy
    if not is_safe_url(target):
        raise HTTPException(status_code=403, detail="Forbidden target")

    # Build the proxy base URL for rewriting Location headers
    proxy_base = str(request.url).split('?')[0]   # e.g. /yellow-mirror/api/

    # Prepare headers for the target request
    headers = {k: v for k, v in request.headers.items()
               if k.lower() not in ('host', 'content-length', 'connection', 'accept-encoding')}
    # Use a realistic User‑Agent (curl_cffi can spoof, but we set a default)
    if 'user-agent' not in headers:
        headers['user-agent'] = (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
            '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )

    body = None
    if request.method in ('POST', 'PUT', 'PATCH'):
        body = await request.body()

    # ---------------------------------------------------------------
    # Use curl_cffi to fetch with Chrome TLS fingerprint
    try:
        # We run curl_cffi's request in a thread because it's blocking.
        # In a serverless context this is acceptable for short requests.
        loop = asyncio.get_event_loop()
        resp = await loop.run_in_executor(
            None,
            lambda: curl_requests.request(
                method=request.method,
                url=target,
                headers=headers,
                data=body,
                allow_redirects=False,   # we handle redirects in the SW
                timeout=10.0,
                impersonate="chrome110",  # latest impersonate ID as available
                verify=True
            )
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Proxy error: {str(e)}")

    # ---------------------------------------------------------------
    # For redirects, rewrite Location header
    if resp.status_code in (301, 302, 303, 307, 308):
        location = resp.headers.get('Location')
        if location:
            abs_location = urljoin(target, location)
            new_loc = f"{proxy_base}?target={quote(abs_location, safe='')}"
            return Response(
                content=resp.content,
                status_code=resp.status_code,
                headers={**{k: v for k, v in resp.headers.items()
                            if k.lower() != 'location'},
                         'Location': new_loc}
            )
        return Response(content=resp.content, status_code=resp.status_code,
                        headers=resp.headers)

    # ---------------------------------------------------------------
    # Regular response: filter dangerous headers, return raw bytes
    prohibited = {
        'content-length', 'content-encoding', 'content-security-policy',
        'content-security-policy-report-only', 'x-frame-options',
        'x-content-type-options', 'x-xss-protection'
    }
    filtered_headers = {k: v for k, v in resp.headers.items()
                        if k.lower() not in prohibited}

    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers=filtered_headers
    )