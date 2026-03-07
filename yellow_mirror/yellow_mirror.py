import asyncio
import random
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse, quote

import httpx
from bs4 import BeautifulSoup
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import Response, FileResponse, RedirectResponse
from httpx import ASGITransport

from .logic.client_manager import get_client_for_ip, shutdown_clients
from .logic.url_utils import is_safe_url
from .logic.html_rewriter import replace_urls_in_html

router = APIRouter()
BASE_DIR = Path(__file__).parent


@router.get('/', response_class=FileResponse, name='ym_root')
async def yellow_mirror_page():
    """Главная страница yellow mirror."""
    return FileResponse(BASE_DIR / 'yellow-mirror.html')


@router.api_route('/api/', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS'])
async def proxy(request: Request):
    target_url = request.query_params.get('target')
    if not target_url:
        raise HTTPException(status_code=400, detail="Missing 'target' query parameter")

    # Удалена проверка is_safe_url(target_url)

    proxy_base_url = str(request.url).split('?')[0]

    parsed_target = urlparse(target_url)
    our_host = request.url.hostname

    client_ip = request.client.host if request.client else 'unknown'
    proxy_client, user_agent = await get_client_for_ip(client_ip)

    headers = dict(request.headers)
    headers.pop('host', None)
    headers.pop('content-length', None)
    headers.pop('connection', None)
    headers.pop('accept-encoding', None)

    headers['user-agent'] = user_agent
    if 'accept' not in headers:
        headers['accept'] = 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8'
    if 'accept-language' not in headers:
        headers['accept-language'] = 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7'

    body = None
    if request.method in ['POST', 'PUT', 'PATCH']:
        body = await request.body()

    try:
        resp = await proxy_client.request(
            method=request.method,
            url=target_url,
            headers=headers,
            content=body,
        )
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail='Target server timeout')
    except httpx.TooManyRedirects:
        raise HTTPException(status_code=502, detail='Too many redirects')
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f'Proxy error: {str(e)}')

    prohibited_headers = {
        'content-length',
        'content-encoding',
        'content-security-policy',
        'content-security-policy-report-only',
        'x-frame-options',
        'x-content-type-options',
        'x-xss-protection',
    }
    filtered_headers = {
        k: v for k, v in resp.headers.items()
        if k.lower() not in prohibited_headers
    }

    content_type = resp.headers.get('content-type', '').lower()
    if 'text/html' in content_type:
        # Используем финальный URL после редиректов как базовый для замены ссылок
        modified_html = replace_urls_in_html(resp.text, str(resp.url), proxy_base_url)
        return Response(
            content=modified_html.encode('utf-8'),
            status_code=resp.status_code,
            headers=filtered_headers
        )
    else:
        return Response(
            content=resp.content,
            status_code=resp.status_code,
            headers=filtered_headers
        )