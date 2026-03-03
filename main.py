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
from httpx import ASGITransport  # добавлено для внутренних запросов
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
db = client.toadbin  # база данных
codes_collection = db.codes  # коллекция для кодов
stats_db = client["main-page"] # бд для счётчика

# Настройки прокси
PROXY_TIMEOUT = 10.0  # секунд
ALLOWED_SCHEMES = {"http", "https"}
DISALLOWED_IPS = {"127.0.0.1", "localhost", "::1"}  # простейшая защита

# Время жизни клиента для IP (в секундах)
CLIENT_MAX_AGE = 600  # 10 минут

# Список реальных User-Agent (браузеры)
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
]

# Хранилище клиентов по IP: {ip: (client, last_used_timestamp, user_agent)}
ip_clients = {}
ip_clients_lock = asyncio.Lock()

async def get_client_for_ip(ip: str) -> tuple[httpx.AsyncClient, str]:
    """Возвращает HTTPX-клиент и User-Agent для указанного IP, создавая новый при необходимости."""
    async with ip_clients_lock:
        now = datetime.utcnow().timestamp()
        # Очистка старых клиентов
        to_delete = []
        for stored_ip, (_, last_used, _) in ip_clients.items():
            if now - last_used > CLIENT_MAX_AGE:
                to_delete.append(stored_ip)
        for stored_ip in to_delete:
            client_to_close, _, _ = ip_clients.pop(stored_ip)
            await client_to_close.aclose()
        
        # Получаем или создаём клиент для данного IP
        if ip in ip_clients:
            client, _, ua = ip_clients[ip]
            ip_clients[ip] = (client, now, ua)  # обновляем время
        else:
            # Выбираем случайный User-Agent для этого IP
            ua = random.choice(USER_AGENTS)
            # Создаём новый клиент с поддержкой cookies
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
    """Проверяет, что URL допустим для проксирования."""
    parsed = urlparse(url)
    if parsed.scheme not in ALLOWED_SCHEMES:
        return False
    # Проверка на локальные адреса (упрощённо)
    netloc = parsed.netloc.split(':')[0]
    if netloc in DISALLOWED_IPS or netloc.startswith(('127.', '192.168.', '10.')):
        return False
    return True

def make_proxy_url(target: str) -> str:
    """Создаёт прокси-URL для заданного целевого URL."""
    return f"/api/yellow-mirror/?target={quote(target, safe='')}"

def replace_urls_in_html(html: str, base_url: str) -> str:
    """Заменяет все ссылки в HTML на прокси-версии и внедряет скрипт для отслеживания навигации."""
    soup = BeautifulSoup(html, 'lxml')
    
    # Замена ссылок
    for tag, attr in [('a', 'href'), ('link', 'href'), ('script', 'src'),
                      ('img', 'src'), ('iframe', 'src'), ('form', 'action')]:
        for element in soup.find_all(tag, **{attr: True}):
            original = element[attr]
            if original and not original.startswith('#') and not original.startswith('data:'):
                absolute = urljoin(base_url, original)
                if is_safe_url(absolute):
                    element[attr] = make_proxy_url(absolute)
    
    # Обработка inline-стилей (упрощённо)
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
    
    # Добавляем минимальный резервный стиль для читаемости на случай, если сайт не задал свои цвета
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
            # Крайний случай – создаём html и head
            html_tag = soup.new_tag('html')
            html_tag.append(head)
            soup.append(html_tag)
    
    # Внедрение скрипта для уведомления родителя об изменении URL
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
    """
    Конвертирует DOCX в PDF без создания временных файлов и без зависимости от MS Office/LibreOffice.
    Использует библиотеки, работающие исключительно в памяти.
    """
    try:        
        # Читаем DOCX из байтов
        docx_file = BytesIO(docx_content)
        doc = Document(docx_file)
        
        # Создаем PDF в памяти
        pdf_buffer = BytesIO()
        
        # Создаем PDF документ
        pdf = SimpleDocTemplate(
            pdf_buffer, 
            pagesize=letter,
            rightMargin=72, 
            leftMargin=72,
            topMargin=72, 
            bottomMargin=72
        )
        
        # Собираем элементы для PDF
        story = []
        styles = getSampleStyleSheet()
        
        # Настройка шрифта для поддержки Unicode символов
        try:
            # Пробуем использовать шрифт, поддерживающий Unicode
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.ttfonts import TTFont
            
            # Регистрируем шрифт DejaVu (должен быть установлен в системе)
            # Если нет, fallback на стандартный шрифт
            try:
                pdfmetrics.registerFont(TTFont('DejaVu', 'DejaVuSans.ttf'))
                styles['Normal'].fontName = 'DejaVu'
            except:
                # Если DejaVu не найден, пробуем Arial Unicode MS (для Windows)
                try:
                    pdfmetrics.registerFont(TTFont('ArialUnicode', 'arialuni.ttf'))
                    styles['Normal'].fontName = 'ArialUnicode'
                except:
                    # Используем стандартный шрифт
                    pass
        except ImportError:
            # Если нет reportlab.pdfbase, используем стандартные шрифты
            pass
        
        # Конвертируем параграфы
        for paragraph in doc.paragraphs:
            if paragraph.text.strip():  # Игнорируем пустые параграфы
                # Сохраняем стили: жирный, курсив, подчеркивание
                text = paragraph.text
                
                # Добавляем параграф в PDF
                p = Paragraph(text.replace('\n', '<br/>'), styles['Normal'])
                story.append(p)
                story.append(Spacer(1, 12))  # Добавляем отступ между параграфами
        
        # Строим PDF
        pdf.build(story)
        
        # Получаем байты PDF
        pdf_buffer.seek(0)
        pdf_bytes = pdf_buffer.read()
        
        return pdf_bytes
        
    except Exception as e:
        # Логируем ошибку для отладки
        import logging
        logging.error(f"PDF conversion error: {str(e)}")
        raise Exception(f"PDF conversion failed: {str(e)}")


# main page

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return FileResponse("index.html")

@app.on_event("startup")
async def startup_event():
    await init_counter()
    
@app.post("/api/track")
async def track_visitor(request: TrackRequest):
    # Пытаемся вставить UUID в коллекцию visitors (в отдельной БД)
    result = await stats_db.visitors.update_one(
        {"_id": request.uuid},
        {"$setOnInsert": {"_id": request.uuid, "first_seen": datetime.utcnow()}},
        upsert=True
    )
    # Если UUID новый, увеличиваем счётчик уникальных посетителей
    if result.upserted_id is not None:
        await stats_db.stats.update_one(
            {"_id": "unique_visitors"},
            {"$inc": {"count": 1}}
        )
    # Получаем текущее значение счётчика
    counter_doc = await stats_db.stats.find_one({"_id": "unique_visitors"})
    count = counter_doc["count"] if counter_doc else 0
    return {"count": count}


# evenfest
@app.get("/evenfest", response_class=HTMLResponse)
@app.get("/evenfest/{page_name}", response_class=HTMLResponse)
async def evenpage(request: Request, page_name: str = "news"):
    if request.url.path.rstrip('/') == "/evenfest":
        return RedirectResponse(url="/evenfest/news")
    
    # Проверяем существование шаблона
    if not exists(f"evenfest/templates/{page_name}.html"):
        raise HTTPException(status_code=404, detail="Страница не найдена")
    
    data = load_data('evenfest/content.json')
    return evenfest.TemplateResponse(
        f"{page_name}.html", 
        {
            "request": request,
            "menu": data.get("menu", []),
            "page_content": data.get("content", {}).get(page_name, "")
        }
    )
    
    
# snake
@app.get('/snake', response_class=HTMLResponse)
async def snakepage(request: Request):
    return FileResponse("snake/snake.html")


# toadbin

@app.get('/toadbin', response_class=HTMLResponse)
async def toadpage(request: Request):
    return toadbin.TemplateResponse(
        "toadbin.html",
        {
            "request": request,
            "code": "",
            "code_id": None,
            "is_readonly": False
        }
    )
    
@app.get("/toadbin/{code_id}")
async def toadbin_codeview(request: Request, code_id: str):
    # Ищем в MongoDB
    doc = await codes_collection.find_one({"code_id": code_id})
    
    if not doc:
        raise HTTPException(status_code=404, detail="Code not found")
    
    return toadbin.TemplateResponse(
        "toadbin.html",
        {
            "request": request,
            "code": doc["content"],
            "code_id": code_id
        }
    )

@app.get("/api/backgrounds")
async def toad_backgrounds():
    try:
        # Проверяем существование папки
        if not toad_background_dir.exists():
            raise HTTPException(status_code=404, detail="Backgrounds directory not found")
        
        # Получаем список файлов GIF
        gif_files = []
        for file in toad_background_dir.iterdir():
            if file.is_file() and file.suffix.lower() == '.mp4':
                gif_files.append(file.name)
        
        # Сортируем для удобства
        gif_files.sort()
        
        return JSONResponse(content={"backgrounds": gif_files})
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@app.get("/api/existing-ids")
async def toad_ids():
    # Получаем все ID из MongoDB
    cursor = codes_collection.find({}, {"code_id": 1})
    docs = await cursor.to_list(length=1000)
    ids = [int(doc["code_id"]) for doc in docs if doc.get("code_id", "").isdigit()]
    return ids

@app.post("/api/save")
async def toad_save(request: dict):
    """Сохраняет код в MongoDB"""
    try:
        code_id = request.get('id')
        code_content = request.get('code')
        
        # Upsert - обновить если есть, создать если нет
        await codes_collection.update_one(
            {"code_id": str(code_id)},
            {"$set": {"code_id": str(code_id), "content": code_content}},
            upsert=True
        )
        
        return {"status": "success", "id": code_id}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
    
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
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")
    
    original_name = file.filename
    # Получаем имя без расширения и добавляем новое расширение
    name_without_ext = original_name.rsplit('.', 1)[0]
    new_name = f"{name_without_ext}.{to_format}"
    
    # Кодируем имя файла для безопасного использования в заголовке
    encoded_filename = quote(new_name)
    
    if from_format == 'docx' and to_format == 'pdf':
        try:
            # Читаем содержимое файла
            content = await file.read()
            
            # Конвертируем в память без создания файлов
            pdf_bytes = await convert_docx_to_pdf(content)
            
            # Возвращаем файл как ответ
            return Response(
                content=pdf_bytes,
                media_type="application/pdf",
                headers={
                    "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"
                }
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Conversion error: {str(e)}")
    if from_format == 'html' and to_format == 'pdf':
        
        from playwright.async_api import async_playwright
        from asyncio import run

        async def html_to_pdf(html_bytes: bytes) -> bytes:
            async with async_playwright() as p:
                browser = await p.chromium.launch(channel="chrome", headless=True)
                page = await browser.new_page()
                await page.set_content(html_bytes.decode('utf-8'))
                pdf_bytes = await page.pdf()
                await browser.close()
                return pdf_bytes
        
        new_name = f"{name_without_ext}.{to_format}"
        encoded_filename = quote(new_name)
        
        html_bytes = run(html_to_pdf(file.read()))
        return Response(
                content=html_bytes,
                media_type="text/html",
                headers={
                    "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"
                }
            )
        
    else:
        raise HTTPException(status_code=400, detail="Unsupported conversion format")
    
    
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

    # Проверяем, не ведёт ли target на наш собственный сайт
    parsed_target = urlparse(target_url)
    our_host = request.url.hostname  # текущий хост, на который пришёл запрос

    if parsed_target.hostname and parsed_target.hostname.lower() == our_host.lower():
        # Если путь запроса ведёт на сам прокси-эндпоинт – предотвращаем зацикливание
        if parsed_target.path.startswith("/api/yellow-mirror"):
            raise HTTPException(status_code=400, detail="Recursive proxy call detected")

        # Внутренний запрос к нашему же приложению через ASGI-транспорт
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url=f"{request.url.scheme}://{our_host}") as client:
            # Копируем заголовки оригинального запроса, убирая ненужные
            headers = dict(request.headers)
            headers.pop("host", None)
            headers.pop("content-length", None)
            headers.pop("connection", None)
            headers.pop("accept-encoding", None)  # чтобы не сжимать ответ

            # Тело запроса (для POST и т.п.)
            body = None
            if request.method in ["POST", "PUT", "PATCH"]:
                body = await request.body()

            # Формируем путь и query для внутреннего запроса
            internal_path = parsed_target.path
            if parsed_target.query:
                internal_path += "?" + parsed_target.query

            # Выполняем запрос к нашему приложению
            resp = await client.request(
                method=request.method,
                url=internal_path,
                headers=headers,
                content=body,
                follow_redirects=True  # ИСПРАВЛЕНО: теперь следуем редиректам, как для внешних запросов
            )

        # Обрабатываем ответ как обычно (модификация HTML и т.д.)
        # Заголовки, которые нельзя передавать клиенту
        PROHIBITED_HEADERS = {
            "content-length",
            "content-encoding",
            "content-security-policy",
            "content-security-policy-report-only",
            "x-frame-options",
            "x-content-type-options",
            "x-xss-protection",
        }
        filtered_headers = {
            k: v for k, v in resp.headers.items()
            if k.lower() not in PROHIBITED_HEADERS
        }

        content_type = resp.headers.get("content-type", "").lower()
        if "text/html" in content_type:
            # Модифицируем HTML, подставляя прокси-ссылки
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

    # Для внешних сайтов используем обычный прокси-клиент с привязкой к IP
    # Получаем IP клиента для сессионного клиента
    client_ip = request.client.host if request.client else "unknown"
    
    # Получаем клиент и его постоянный User-Agent для этого IP
    proxy_client, user_agent = await get_client_for_ip(client_ip)
    
    # Формируем заголовки для целевого запроса
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
    
    # Заголовки, которые нельзя передавать клиенту
    PROHIBITED_HEADERS = {
        "content-length",
        "content-encoding",
        "content-security-policy",
        "content-security-policy-report-only",
        "x-frame-options",
        "x-content-type-options",
        "x-xss-protection",
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
    # Закрываем всех сохранённых клиентов при завершении приложения
    async with ip_clients_lock:
        for ip, (client, _, _) in ip_clients.items():
            await client.aclose()
        ip_clients.clear()