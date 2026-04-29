import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from pathlib import Path

from markbin.markbin import router

app = FastAPI(title="Markbin Standalone")
BASE_DIR = Path(__file__).parent

# Mount exactly as it is mounted in Cutaway superproject
app.mount('/markbin/static', StaticFiles(directory=BASE_DIR / 'static'), name='markbin-static')
app.mount('/markbin/scripts', StaticFiles(directory=BASE_DIR / 'scripts'), name='markbin-scripts')

# Include router WITH the exact same prefix as Cutaway
app.include_router(router, prefix='/markbin')

@app.get('/')
async def root_redirect():
    # Convenience redirect if you just go to localhost:8000
    return RedirectResponse(url='/markbin/')

if __name__ == '__main__':
    uvicorn.run("markbin.main:app", host="0.0.0.0", port=8000, reload=True)