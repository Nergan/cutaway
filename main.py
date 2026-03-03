from io import BytesIO
from json import load
from os import environ
from os.path import exists
from pathlib import Path
from urllib.parse import quote
from datetime import datetime, timedelta
from urllib.parse import urljoin, urlparse, quote
import asyncio
import random

from pydantic import BaseModel
import httpx
from httpx import ASGITransport
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from motor.motor_asyncio import AsyncIOMotorClient
from docx import Document
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.units import inch


load_dotenv()

# MongoDB подключение
MONGO_URL = environ.get("MONGODB_URI", "mongodb://localhost:27017")
client = AsyncIOMotorClient(
    MONGO_URL,
    tls=True,
    tlsAllowInvalidCertificates=True
)
db = client.toadbin
codes_collection = db.codes
stats_db = client["main-page"]

# Настройки прокси
PROXY_TIMEOUT = 10.0
ALLOWED_SCHEMES = {"http", "https"}
DISALLOWED_IPS = {"127.0.0.1", "localhost", "::1"}

CLIENT_MAX_AGE = 600

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
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

app = FastAPI()
app.mount("/evenfest/static", StaticFiles(directory="evenfest/static"), name="evenfest")
app.mount('/snake/static', StaticFiles(directory="snake/static"), name="snake-static")
app.mount('/snake/scripts', StaticFiles(directory="snake/scripts"), name="snake-scripts")
app.mount('/toadbin/static', StaticFiles(directory="toadbin/static"), name="toadbin-static")
app.mount('/toadbin/scripts', StaticFiles(directory="toadbin/scripts"), name="toadbin-scripts")
app.mount('/formular/static', StaticFiles(directory="formular/static"), name="formular-static")
app.mount('/formular/scripts', StaticFiles(directory="formular/scripts"), name="formular-scripts")
app.mount('/yellow mirror/static', StaticFiles(directory="yellow mirror/static"), name="yellow-mirror-static")
app.mount('/yellow mirror/scripts', StaticFiles(directory="yellow mirror/scripts"), name="yellow-mirror-scripts")
evenfest = Jinja2Templates(directory="evenfest/templates")
toadbin = Jinja2Templates(directory="toadbin")

toad_background_dir = Path("toadbin/static/backgrounds")


class TrackRequest(BaseModel):
    uuid: str


def is_safe_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in ALLOWED_SCHEMES:
        return False
    netloc = parsed.netloc.split(':')[0]
    if netloc in DISALLOWED_IPS or netloc.startswith(('127.', '192.168.', '10.')):
        return False
    return True

def make_proxy_url(target: str) -> str:
    return f"/api/yellow-mirror/?target={quote(target, safe='')}"

def replace_urls_in_html(html: str, base_url: str) -> str:
    """Заменяет ссылки в HTML на прокси-версии. Для ссылок на собственное приложение (/yellow-mirror)
       устанавливает target="_top" и оставляет прямую ссылку."""
    soup = BeautifulSoup(html, 'lxml')
    
    # Определяем хост и путь собственного приложения
    parsed_base = urlparse(base_url)
    our_host = parsed_base.netloc.split(':')[0]  # без порта
    our_app_path = "/yellow-mirror"  # путь к странице приложения
    
    # Замена ссылок
    for tag, attr in [('a', 'href'), ('link', 'href'), ('script', 'src'),
                      ('img', 'src'), ('iframe', 'src'), ('form', 'action')]:
        for element in soup.find_all(tag, **{attr: True}):
            original = element[attr]
            if original and not original.startswith('#') and not original.startswith('data:'):
                absolute = urljoin(base_url, original)
                if is_safe_url(absolute):
                    # Проверяем, ведёт ли ссылка на наше приложение
                    parsed_abs = urlparse(absolute)
                    abs_host = parsed_abs.netloc.split(':')[0]
                    abs_path = parsed_abs.path.rstrip('/')
                    
                    if (abs_host.lower() == our_host.lower() and 
                        abs_path == our_app_path and
                        tag in ('a', 'form')):  # только для ссылок и форм
                        # Оставляем прямую ссылку, но добавляем target="_top" для выхода из iframe
                        element[attr] = absolute  # уже абсолютная
                        if tag == 'a':
                            element['target'] = '_top'
                            element['rel'] = 'noopener noreferrer'
                        elif tag == 'form':
                            element['target'] = '_top'
                    else:
                        # Обычная замена на прокси
                        element[attr] = make_proxy_url(absolute)
    
    # Обработка inline-стилей (без изменений)
    for element in soup.find_all(style=True):
        style = element['style']
        new_style = []
        for part in style.split('url('):
            if part and ')' in part:
                before, rest = part.split(')', 1)
                url_candidate = before.strip('\'" ')
                absolute = urljoin(base_url, url_candidate)
                if is_safe_url(absolute):
                    new_style.append(f"url({make_proxy_url(absolute)}){rest}")
                else:
                    new_style.append(f"url({before}){rest}")
            else:
                new_style.append(part)
        element['style'] = ''.join(new_style)
    
    # Добавляем минимальный резервный стиль
    style_tag = soup.new_tag('style')
    style_tag.string = """
        body { background-color: white; color: black; }
    """
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
    
    # Внедрение скрипта для уведомления об изменении URL (без изменений)
    if not soup.body:
        if not soup.html:
            soup.append(soup.new_tag('html'))
        soup.html.append(soup.new_tag('body'))
    
    script_tag = soup.new_tag('script')
    script_tag.string = """
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
    """
    soup.body.append(script_tag)
    
    return str(soup)


def load_data(path):
    file_path = Path(path)
    if file_path.exists():
        with open(file_path, encoding="utf-8") as f:
            return load(f)
    raise Exception(f'{path} not found')


async def init_counter():
    await stats_db.stats.update_one(
        {"_id": "unique_visitors"},
        {"$setOnInsert": {"count": 0}},
        upsert=True
    )


async def convert_docx_to_pdf(docx_content: bytes) -> bytes:
    # ... (без изменений)
    pass


# main page
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return FileResponse("index.html")

@app.on_event("startup")
async def startup_event():
    await init_counter()
    
@app.post("/api/track")
async def track_visitor(request: TrackRequest):
    # ... (без изменений)
    pass


# evenfest
@app.get("/evenfest", response_class=HTMLResponse)
@app.get("/evenfest/{page_name}", response_class=HTMLResponse)
async def evenpage(request: Request, page_name: str = "news"):
    # ... (без изменений)
    pass
    
    
# snake
@app.get('/snake', response_class=HTMLResponse)
async def snakepage(request: Request):
    return FileResponse("snake/snake.html")


# toadbin
@app.get('/toadbin', response_class=HTMLResponse)
async def toadpage(request: Request):
    # ... (без изменений)
    pass
    
@app.get("/toadbin/{code_id}")
async def toadbin_codeview(request: Request, code_id: str):
    # ... (без изменений)
    pass

@app.get("/api/backgrounds")
async def toad_backgrounds():
    # ... (без изменений)
    pass
    
@app.get("/api/existing-ids")
async def toad_ids():
    # ... (без изменений)
    pass

@app.post("/api/save")
async def toad_save(request: dict):
    # ... (без изменений)
    pass
    
    
# formular
@app.get("/formular", response_class=HTMLResponse)
async def flormularpage(request: Request):
    return FileResponse("formular/formular.html")

@app.post("/api/convert")
async def formular_convert(
    file: UploadFile = File(...),
    from_format: str = Form(...),
    to_format: str = Form(...)
):
    # ... (без изменений)
    pass
    
    
# yellow mirror
@app.get("/yellow-mirror", response_class=HTMLResponse)
async def jitsiroom(request: Request):
    return FileResponse("yellow mirror/yellow mirror.html")

@app.api_route("/api/yellow-mirror/", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def proxy(request: Request):
    target_url = request.query_params.get("target")
    if not target_url:
        raise HTTPException(status_code=400, detail="Missing 'target' query parameter")
    
    if not is_safe_url(target_url):
        raise HTTPException(status_code=400, detail="Invalid or disallowed URL")

    parsed_target = urlparse(target_url)
    our_host = request.url.hostname

    # Если запрос ведёт на наш собственный сайт
    if parsed_target.hostname and parsed_target.hostname.lower() == our_host.lower():
        # Предотвращаем зацикливание
        if parsed_target.path.startswith("/api/yellow-mirror"):
            raise HTTPException(status_code=400, detail="Recursive proxy call detected")

        # Если целевой URL ведёт на страницу самого приложения (/yellow-mirror)
        # выполняем редирект, чтобы выйти из iframe
        if parsed_target.path.rstrip('/') == "/yellow-mirror":
            # Перенаправляем на чистый URL приложения (без параметра target)
            redirect_url = "/yellow-mirror"
            # Можно сохранить прочие query-параметры, но для простоты опустим
            return RedirectResponse(url=redirect_url, status_code=302)

        # Внутренний запрос к другой странице нашего сайта (не /yellow-mirror)
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url=f"{request.url.scheme}://{our_host}") as client:
            headers = dict(request.headers)
            headers.pop("host", None)
            headers.pop("content-length", None)
            headers.pop("connection", None)
            headers.pop("accept-encoding", None)

            body = None
            if request.method in ["POST", "PUT", "PATCH"]:
                body = await request.body()

            internal_path = parsed_target.path
            if parsed_target.query:
                internal_path += "?" + parsed_target.query

            resp = await client.request(
                method=request.method,
                url=internal_path,
                headers=headers,
                content=body,
                follow_redirects=True
            )

        PROHIBITED_HEADERS = {
            "content-length", "content-encoding", "content-security-policy",
            "content-security-policy-report-only", "x-frame-options",
            "x-content-type-options", "x-xss-protection",
        }
        filtered_headers = {
            k: v for k, v in resp.headers.items()
            if k.lower() not in PROHIBITED_HEADERS
        }

        content_type = resp.headers.get("content-type", "").lower()
        if "text/html" in content_type:
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

    # Для внешних сайтов используем обычный прокси-клиент
    client_ip = request.client.host if request.client else "unknown"
    proxy_client, user_agent = await get_client_for_ip(client_ip)
    
    headers = dict(request.headers)
    headers.pop("host", None)
    headers.pop("content-length", None)
    headers.pop("connection", None)
    headers.pop("accept-encoding", None)
    
    headers["user-agent"] = user_agent
    if "accept" not in headers:
        headers["accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
    if "accept-language" not in headers:
        headers["accept-language"] = "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7"
    
    body = None
    if request.method in ["POST", "PUT", "PATCH"]:
        body = await request.body()
    
    try:
        resp = await proxy_client.request(
            method=request.method,
            url=target_url,
            headers=headers,
            content=body,
        )
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Target server timeout")
    except httpx.TooManyRedirects:
        raise HTTPException(status_code=502, detail="Too many redirects")
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Proxy error: {str(e)}")
    
    PROHIBITED_HEADERS = {
        "content-length", "content-encoding", "content-security-policy",
        "content-security-policy-report-only", "x-frame-options",
        "x-content-type-options", "x-xss-protection",
    }
    
    filtered_headers = {
        k: v for k, v in resp.headers.items()
        if k.lower() not in PROHIBITED_HEADERS
    }
    
    content_type = resp.headers.get("content-type", "").lower()
    
    if "text/html" in content_type:
        html_content = resp.text
        modified_html = replace_urls_in_html(html_content, str(resp.url))
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
        
@app.on_event("shutdown")
async def shutdown_event():
    async with ip_clients_lock:
        for ip, (client, _, _) in ip_clients.items():
            await client.aclose()
        ip_clients.clear()