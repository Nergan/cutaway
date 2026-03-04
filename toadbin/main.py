from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from .toadbin import router

app = FastAPI(title="Toadbin")
BASE_DIR = Path(__file__).parent

# Монтируем статику по тем же путям, что используются в HTML
app.mount('/toadbin/static', StaticFiles(directory=BASE_DIR / 'static'), name='toadbin-static')
app.mount('/toadbin/scripts', StaticFiles(directory=BASE_DIR / 'scripts'), name='toadbin-scripts')

# Подключаем роутер без префикса – он отвечает на корень '/'
app.include_router(router)