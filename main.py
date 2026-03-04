# Стандартные библиотеки
from datetime import datetime
from os import environ

# Установленные библиотеки
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel

# Локальные модули
from evenfest.evenfest import router as evenfest_router
from snake.snake import router as snake_router
from toadbin.toadbin import router as toadbin_router
from formular.formular import router as formular_router
from yellow_mirror.yellow_mirror import router as yellow_mirror_router, shutdown_clients

load_dotenv()

# MongoDB для статистики главной страницы
MONGO_URL = environ.get('MONGODB_URI', 'mongodb://localhost:27017')
client = AsyncIOMotorClient(MONGO_URL, tls=True, tlsAllowInvalidCertificates=True)
stats_db = client['main-page']

app = FastAPI()

# Монтирование статических директорий
app.mount('/evenfest/static', StaticFiles(directory='evenfest/static'), name='evenfest')
app.mount('/snake/static', StaticFiles(directory='snake/static'), name='snake-static')
app.mount('/snake/scripts', StaticFiles(directory='snake/scripts'), name='snake-scripts')
app.mount('/toadbin/static', StaticFiles(directory='toadbin/static'), name='toadbin-static')
app.mount('/toadbin/scripts', StaticFiles(directory='toadbin/scripts'), name='toadbin-scripts')
app.mount('/formular/static', StaticFiles(directory='formular/static'), name='formular-static')
app.mount('/formular/scripts', StaticFiles(directory='formular/scripts'), name='formular-scripts')
app.mount('/yellow_mirror/static', StaticFiles(directory='yellow_mirror/static'), name='yellow-mirror-static')
app.mount('/yellow_mirror/scripts', StaticFiles(directory='yellow_mirror/scripts'), name='yellow-mirror-scripts')

# Подключение роутеров подпроектов
app.include_router(evenfest_router)
app.include_router(snake_router)
app.include_router(toadbin_router)
app.include_router(formular_router)
app.include_router(yellow_mirror_router)


class TrackRequest(BaseModel):
    uuid: str


async def init_counter():
    await stats_db.stats.update_one(
        {'_id': 'unique_visitors'},
        {'$setOnInsert': {'count': 0}},
        upsert=True
    )


@app.on_event('startup')
async def startup_event():
    await init_counter()


@app.on_event('shutdown')
async def shutdown_event():
    await shutdown_clients()


@app.get('/', response_class=HTMLResponse)
async def home(request: Request):
    return FileResponse('index.html')


@app.post('/api/track')
async def track_visitor(request: TrackRequest):
    result = await stats_db.visitors.update_one(
        {'_id': request.uuid},
        {'$setOnInsert': {'_id': request.uuid, 'first_seen': datetime.utcnow()}},
        upsert=True
    )
    if result.upserted_id is not None:
        await stats_db.stats.update_one(
            {'_id': 'unique_visitors'},
            {'$inc': {'count': 1}}
        )
    counter_doc = await stats_db.stats.find_one({'_id': 'unique_visitors'})
    count = counter_doc['count'] if counter_doc else 0
    return {'count': count}