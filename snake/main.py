from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from .snake import router

app = FastAPI(title="Snake Game")

# Монтируем статику по тем же путям, что используются в HTML
BASE_DIR = Path(__file__).parent
app.mount('/snake/static', StaticFiles(directory=BASE_DIR / 'static'), name='snake-static')
app.mount('/snake/scripts', StaticFiles(directory=BASE_DIR / 'scripts'), name='snake-scripts')

# Подключаем роутер без префикса – он обрабатывает корень '/'
app.include_router(router)