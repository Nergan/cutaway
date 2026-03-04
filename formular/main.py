from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from .formular import router

app = FastAPI(title="Formular Converter")
BASE_DIR = Path(__file__).parent

# Монтируем статику по тем же путям, что используются в HTML
app.mount('/formular/static', StaticFiles(directory=BASE_DIR / 'static'), name='formular-static')
app.mount('/formular/scripts', StaticFiles(directory=BASE_DIR / 'scripts'), name='formular-scripts')

# Подключаем роутер без префикса – он отвечает на корень '/'
app.include_router(router)