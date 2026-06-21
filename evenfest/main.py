import sys
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

# 1. Standalone FastAPI Initialization
app = FastAPI(title="evenfest standalone")
BASE_DIR = Path(__file__).parent

# 2. Namespace static mounting (Guarantees parity with root deployment)
if (BASE_DIR / 'static').exists():
    app.mount('/evenfest/static', StaticFiles(directory=BASE_DIR / 'static'), name='evenfest_static')
if (BASE_DIR / 'scripts').exists():
    app.mount('/evenfest/scripts', StaticFiles(directory=BASE_DIR / 'scripts'), name='evenfest_scripts')

# 3. Import and mount the core logic router
from evenfest import router
app.include_router(router, prefix='/evenfest')

@app.get("/")
def root_redirect():
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url='/evenfest')

# 4. The Dual-Boot Entrypoint
if __name__ == '__main__':
    # Launch Web Server if requested: `python main.py --web`
    if "--web" in sys.argv:
        import uvicorn
        uvicorn.run("main:app", host="0.0.0.0", port=8000)
    # Default to Desktop App via Eel
    else:
        try:
            import eel
            eel.init(str(BASE_DIR))
            # Finds the HTML file natively
            html_file = 'templates/index.html' if (BASE_DIR / 'templates' / 'index.html').exists() else 'news.html'
            eel.start(html_file, size=(1000, 850))
        except ImportError:
            print("Eel is not installed. To run the web server, use: python main.py --web")