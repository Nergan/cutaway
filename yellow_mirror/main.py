from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from .yellow_mirror import router, shutdown_clients

app = FastAPI(title="Yellow Mirror")
BASE_DIR = Path(__file__).parent

# Монтируем статику по тем же путям, что используются в HTML
app.mount('/yellow_mirror/static', StaticFiles(directory=BASE_DIR / 'static'), name='yellow-mirror-static')
app.mount('/yellow_mirror/scripts', StaticFiles(directory=BASE_DIR / 'scripts'), name='yellow-mirror-scripts')

# Подключаем роутер без префикса – он отвечает на корень '/'
app.include_router(router)


@app.on_event('shutdown')
async def shutdown_event():
    await shutdown_clients()