from io import BytesIO
from json import load
from os import environ
from os.path import exists
from pathlib import Path
from urllib.parse import quote

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

app = FastAPI()
app.mount("/evenfest/static", StaticFiles(directory="evenfest/static"), name="evenfest")
app.mount('/snake/static', StaticFiles(directory="snake/static"), name="snake-static")
app.mount('/snake/scripts', StaticFiles(directory="snake/scripts"), name="snake-scripts")
app.mount('/toadbin/static', StaticFiles(directory="toadbin/static"), name="toadbin-static")
app.mount('/toadbin/scripts', StaticFiles(directory="toadbin/scripts"), name="toadbin-scripts")
app.mount('/formular/static', StaticFiles(directory="formular/static"), name="formular-static")
app.mount('/formular/scripts', StaticFiles(directory="formular/scripts"), name="formular-scripts")
evenfest = Jinja2Templates(directory="evenfest/templates")
toadbin = Jinja2Templates(directory="toadbin")

toad_background_dir = Path("toadbin/static/backgrounds")
toad_code_dir = Path("toadbin/codes")


def load_data(path):
    file_path = Path(path)
    if file_path.exists():
        with open(file_path, encoding="utf-8") as f:
            return load(f)
    raise Exception(f'{path} not found')


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
            if file.is_file() and file.suffix.lower() == '.gif':
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
        
        from playwright.sync_api import sync_playwright

        def html_to_pdf(html_bytes: bytes) -> bytes:
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page()
                
                # Загружаем HTML из байтов
                page.set_content(html_bytes.decode('utf-8'))
                
                # Генерируем PDF через браузерный механизм печати
                pdf_bytes = page.pdf()
                
                browser.close()
                return pdf_bytes
        
        new_name = f"{name_without_ext}.{to_format}"
        encoded_filename = quote(new_name)
        
        html_bytes = html_to_pdf(file.read())
        return Response(
                content=html_bytes,
                media_type="text/html",
                headers={
                    "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"
                }
            )
        
    else:
        raise HTTPException(status_code=400, detail="Unsupported conversion format")