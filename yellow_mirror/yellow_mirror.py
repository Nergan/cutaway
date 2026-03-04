import asyncio
import random
from datetime import datetime
from urllib.parse import urljoin, urlparse, quote

import httpx
from bs4 import BeautifulSoup
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import Response, FileResponse
from httpx import ASGITransport

router = APIRouter()

# Прокси‑конфигурация
PROXY_TIMEOUT = 10.0
ALLOWED_SCHEMES = {'http', 'https'}
DISALLOWED_IPS = {'127.0.0.1', 'localhost', '::1'}
CLIENT_MAX_AGE = 600  # 10 минут

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
]

ip_clients = {}
ip_clients_lock = asyncio.Lock()


async def get_client_for_ip(ip: str) -> tuple[httpx.AsyncClient, str]:
    async with ip_clients_lock:
        now = datetime.utcnow().timestamp()
        to_delete = []
        for stored_ip, (_, last_used, _) in ip_clients.items():
            if now - last_used > CLIENT_MAX_AGE:
                to_delete.append(stored_ip)
        for stored_ip in to_delete:
            client_to_close, _, _ = ip_clients.pop(stored_ip)
            await client_to_close.aclose()

        if ip in ip_clients:
            client, _, ua = ip_clients[ip]
            ip_clients[ip] = (client, now, ua)
        else:
            ua = random.choice(USER_AGENTS)
            client = httpx.AsyncClient(
                timeout=PROXY_TIMEOUT,
                follow_redirects=True,
                max_redirects=5,
                limits=httpx.Limits(max_keepalive_connections=10)
            )
            ip_clients[ip] = (client, now, ua)
        return client, ua


def is_safe_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in ALLOWED_SCHEMES:
        return False
    netloc = parsed.netloc.split(':')[0]
    if netloc in DISALLOWED_IPS or netloc.startswith(('127.', '192.168.', '10.')):
        return False
    return True


def make_proxy_url(target: str) -> str:
    return f'/api/yellow-mirror/?target={quote(target, safe="")}'


def replace_urls_in_html(html: str, base_url: str) -> str:
    soup = BeautifulSoup(html, 'lxml')

    for tag, attr in [('a', 'href'), ('link', 'href'), ('script', 'src'),
                      ('img', 'src'), ('iframe', 'src'), ('form', 'action')]:
        for element in soup.find_all(tag, **{attr: True}):
            original = element[attr]
            if original and not original.startswith('#') and not original.startswith('data:'):
                absolute = urljoin(base_url, original)
                if is_safe_url(absolute):
                    element[attr] = make_proxy_url(absolute)

    for element in soup.find_all(style=True):
        style = element['style']
        new_style = []
        for part in style.split('url('):
            if part and ')' in part:
                before, rest = part.split(')', 1)
                url_candidate = before.strip('\'" ')
                absolute = urljoin(base_url, url_candidate)
                if is_safe_url(absolute):
                    new_style.append(f'url({make_proxy_url(absolute)}){rest}')
                else:
                    new_style.append(f'url({before}){rest}')
            else:
                new_style.append(part)
        element['style'] = ''.join(new_style)

    style_tag = soup.new_tag('style')
    style_tag.string = '''
        body { background-color: white; color: black; }
    '''
    if soup.head:
        soup.head.insert(0, style_tag)
    else:
        head = soup.new_tag('head')
        head.append(style_tag)
        if soup.html:
            soup.html.insert(0, head)
        else:
            html_tag = soup.new_tag('html')
            html_tag.append(head)
            soup.append(html_tag)

    if not soup.body:
        if not soup.html:
            soup.append(soup.new_tag('html'))
        soup.html.append(soup.new_tag('body'))

    script_tag = soup.new_tag('script')
    script_tag.string = '''
    (function() {
        var lastUrl = location.href;
        setInterval(function() {
            if (location.href !== lastUrl) {
                lastUrl = location.href;
                window.top.postMessage({ type: 'iframe-navigation', url: lastUrl }, '*');
            }
        }, 300);
        window.top.postMessage({ type: 'iframe-navigation', url: lastUrl }, '*');
    })();
    '''
    soup.body.append(script_tag)

    return str(soup)


@router.get('/yellow-mirror', response_class=FileResponse)
async def jitsiroom():
    return FileResponse('yellow_mirror/yellow-mirror.html')


@router.api_route('/api/yellow-mirror/', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS'])
async def proxy(request: Request):
    target_url = request.query_params.get('target')
    if not target_url:
        raise HTTPException(status_code=400, detail="Missing 'target' query parameter")

    if not is_safe_url(target_url):
        raise HTTPException(status_code=400, detail='Invalid or disallowed URL')

    parsed_target = urlparse(target_url)
    our_host = request.url.hostname

    # Внутренний запрос к тому же приложению
    if parsed_target.hostname and parsed_target.hostname.lower() == our_host.lower():
        if parsed_target.path.startswith('/api/yellow-mirror'):
            raise HTTPException(status_code=400, detail='Recursive proxy call detected')

        async with httpx.AsyncClient(
            transport=ASGITransport(app=request.app),
            base_url=f'{request.url.scheme}://{our_host}'
        ) as client:
            headers = dict(request.headers)
            headers.pop('host', None)
            headers.pop('content-length', None)
            headers.pop('connection', None)
            headers.pop('accept-encoding', None)

            body = None
            if request.method in ['POST', 'PUT', 'PATCH']:
                body = await request.body()

            internal_path = parsed_target.path
            if parsed_target.query:
                internal_path += '?' + parsed_target.query

            resp = await client.request(
                method=request.method,
                url=internal_path,
                headers=headers,
                content=body,
                follow_redirects=True
            )

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
            modified_html = replace_urls_in_html(resp.text, str(resp.url))
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

    # Внешний запрос с привязкой к IP
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
        modified_html = replace_urls_in_html(resp.text, str(resp.url))
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


async def shutdown_clients():
    async with ip_clients_lock:
        for ip, (client, _, _) in ip_clients.items():
            await client.aclose()
        ip_clients.clear()