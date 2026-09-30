import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse

app = FastAPI(title="minecraft mods standalone")
BASE_DIR = Path(__file__).parent

try:
    from minecraft_mods.minecraft_mods import router
except ImportError:
    from minecraft_mods import router

app.include_router(router, prefix="/mods")


@app.get("/")
def root_redirect():
    return RedirectResponse(url="/mods")


if __name__ == "__main__":
    if "--web" in sys.argv:
        import uvicorn

        uvicorn.run("main:app", host="0.0.0.0", port=8000)
    else:
        print("To run the web server, use: python main.py --web")
