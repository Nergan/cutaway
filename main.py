from json import load
from os.path import exists, join
from os import listdir, makedirs, environ, unlink
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException, UploadFile, Form, File
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse, JSONResponse, StreamingResponse, Response
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from docx2pdf import convert
from aiofiles import open as aiopen
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
import certifi
from tempfile import NamedTemporaryFile
from docx import Document
from asyncio import get_event_loop
from urllib.parse import quote
 
 
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


async def convert_docx_to_pdf(docx_filepath: str) -> bytes:
    # Создаем временный файл для PDF
    with NamedTemporaryFile(suffix='.pdf', delete=False) as pdf_temp:
        pdf_temp_path = pdf_temp.name
    
    try:
        # Запускаем конвертацию в отдельном потоке, чтобы избежать блокировок
        loop = get_event_loop()
        await loop.run_in_executor(None, convert, docx_filepath, pdf_temp_path)
        
        # Читаем PDF
        with open(pdf_temp_path, 'rb') as f:
            pdf_content = f.read()
    finally:
        # Удаляем временный PDF файл
        try:
            unlink(pdf_temp_path)
        except:
            pass
    
    return pdf_content
 
 
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
    
    if from_format == 'docx' and to_format == 'pdf':
        # Создаем временные файлы с уникальными именами
        with NamedTemporaryFile(suffix='.docx', delete=False) as docx_temp:
            docx_temp.write(await file.read())
            docx_temp_path = docx_temp.name
        
        try:
            # Конвертируем
            pdf_bytes = await convert_docx_to_pdf(docx_temp_path)
        finally:
            # Удаляем временный файл после конвертации
            try:
                unlink(docx_temp_path)
            except:
                pass
        
        # Кодируем имя файла для безопасного использования в заголовке
        encoded_filename = quote(new_name)
        
        # Возвращаем файл как ответ
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"
            }
        )