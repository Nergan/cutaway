import sys
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="soon standalone")
BASE_DIR = Path(__file__).parent

if (BASE_DIR / "static").exists():
    app.mount("/soon/static", StaticFiles(directory=BASE_DIR / "static"), name="soon_static")
if (BASE_DIR / "scripts").exists():
    app.mount("/soon/scripts", StaticFiles(directory=BASE_DIR / "scripts"), name="soon_scripts")

try:
    from soon.soon import router
except ImportError:
    from soon import router

app.include_router(router, prefix="/soon")


@app.get("/")
def root_redirect():
    from fastapi.responses import RedirectResponse

    return RedirectResponse(url="/soon")


if __name__ == "__main__":
    if "--web" in sys.argv:
        import uvicorn

        uvicorn.run("main:app", host="0.0.0.0", port=8000)
    else:
        try:
            import eel

            eel.init(str(BASE_DIR))
            html_file = (
                "templates/index.html"
                if (BASE_DIR / "templates" / "index.html").exists()
                else "soon.html"
            )
            eel.start(html_file, size=(1100, 800))
        except ImportError:
            print("Eel is not installed. To run the web server, use: python main.py --web")
