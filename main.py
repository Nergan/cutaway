from datetime import datetime
from os import environ
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import HTTPException
from fastapi.templating import Jinja2Templates
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel

# Import sub-project routers
from evenfest.evenfest import router as evenfest_router
from snake.snake import router as snake_router
from toadbin.toadbin import router as toadbin_router
from formular.formular import router as formular_router
from yellow_mirror.yellow_mirror import router as yellow_mirror_router, shutdown_clients
from markbin.markbin import router as markbin_router
from kanban.kanban import router as kanban_router
from dnd.router import router as dnd_router

load_dotenv()

MONGO_URL = environ.get('MONGODB_URI', 'mongodb://localhost:27017')
client = AsyncIOMotorClient(MONGO_URL, tls=True, tlsAllowInvalidCertificates=True)
stats_db = client['main-page']

app = FastAPI(title="Nargan's Projects Ecosystem")
BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=BASE_DIR)

# --- Safe Static Mounting ---
def mount_if_exists(path: str, name: str, dir_path: Path):
    if dir_path.exists():
        app.mount(path, StaticFiles(directory=dir_path), name=name)

# Mount statics (Updated 'foundry_blank_viewer' to 'dnd')
for project in ['evenfest', 'snake', 'toadbin', 'formular', 'yellow_mirror', 'markbin', 'dnd']:
    mount_if_exists(f'/{project}/static', f'{project}_static', BASE_DIR / f'{project}/static')
    mount_if_exists(f'/{project}/scripts', f'{project}_scripts', BASE_DIR / f'{project}/scripts')

# --- Sub-Project Router Integration ---
app.include_router(evenfest_router, prefix='/evenfest', tags=['Evenfest'])
app.include_router(snake_router, prefix='/snake', tags=['Snake'])
app.include_router(toadbin_router, prefix='/toadbin', tags=['Toadbin'])
app.include_router(formular_router, prefix='/formular', tags=['Formular'])
app.include_router(yellow_mirror_router, prefix='/yellow-mirror', tags=['Yellow Mirror'])
app.include_router(markbin_router, prefix='/markbin', tags=['Markbin'])
app.include_router(kanban_router, prefix='/kanban', tags=['Kanban'])
app.include_router(dnd_router, prefix="/dnd", tags=["D&D Tools"])

# --- Root Logic ---
class TrackRequest(BaseModel):
    uuid: str

async def init_counter():
    await stats_db.stats.update_one({'_id': 'unique_visitors'}, {'$setOnInsert': {'count': 0}}, upsert=True)

@app.on_event('startup')
async def startup_event():
    await init_counter()

@app.on_event('shutdown')
async def shutdown_event():
    await shutdown_clients()

@app.get('/', response_class=HTMLResponse)
async def home(request: Request):
    return FileResponse(BASE_DIR / 'index.html')

@app.post('/api/track')
async def track_visitor(request: TrackRequest):
    result = await stats_db.visitors.update_one(
        {'_id': request.uuid},
        {'$setOnInsert': {'_id': request.uuid, 'first_seen': datetime.utcnow()}},
        upsert=True
    )
    if result.upserted_id is not None:
        await stats_db.stats.update_one({'_id': 'unique_visitors'}, {'$inc': {'count': 1}})
    counter_doc = await stats_db.stats.find_one({'_id': 'unique_visitors'})
    return {'count': counter_doc['count'] if counter_doc else 0}

@app.exception_handler(404)
async def not_found_handler(request: Request, exc: HTTPException):
    return RedirectResponse(url='/')

@app.get('/api/mainpage-backgrounds')
async def get_mainpage_backgrounds():
    mp4_files = ["autumn.mp4", "hardtimes.mp4", "lamp.mp4", "minecraft.mp4", "warmlight.mp4"]
    return JSONResponse(content={'backgrounds': mp4_files})