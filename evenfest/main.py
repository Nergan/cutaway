from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from .evenfest import router

app = FastAPI(title="EVENFEST")
BASE_DIR = Path(__file__).parent

# Монтируем статику по тому же пути, который используется в шаблонах (через url_for)
app.mount('/evenfest/static', StaticFiles(directory=BASE_DIR / 'static'), name='evenfest')

# Подключаем роутер без префикса – он отвечает на корень '/'
app.include_router(router)