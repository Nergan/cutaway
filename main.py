from json import load
from os.path import exists, join
from os import listdir, makedirs, environ
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException, UploadFile, Form, File
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse, JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from docx2pdf import convert
from aiofiles import open as aiopen
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
import certifi
 
 
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
    # Проверяем что файл загружен
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")
    
    newname = '.'.join(file.filename.split('.')[:-1]) + f".{to_format}"
    
    file_path = join('formular/static/files', file.filename)
    async with aiopen(file_path, 'wb') as out_file:
        content = await file.read()
        await out_file.write(content)
    
    if from_format == 'docx' and to_format == 'pdf':
        convert(
            f'formular/static/files/{file.filename}',
            f'formular/static/files/{newname}'
        )
    
    return JSONResponse({
        "success": True,
        "filename": newname,
        "download_url": f"/formular/static/files/{newname}"
    })