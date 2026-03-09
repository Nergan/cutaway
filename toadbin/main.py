from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from toadbin import router

app = FastAPI(title="Toadbin")
BASE_DIR = Path(__file__).parent

# Mount static files and scripts
app.mount('/toadbin/static', StaticFiles(directory=BASE_DIR / 'static'), name='toadbin-static')
app.mount('/toadbin/scripts', StaticFiles(directory=BASE_DIR / 'scripts'), name='toadbin-scripts')

# Include the router without a prefix (it handles its own paths)
app.include_router(router)