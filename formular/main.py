import sys
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

# 1. Standalone FastAPI Initialization
app = FastAPI(title="formular standalone")
BASE_DIR = Path(__file__).parent

# 2. Namespace static mounting (Guarantees parity with root deployment)
if (BASE_DIR / 'static').exists():
    app.mount('/formular/static', StaticFiles(directory=BASE_DIR / 'static'), name='formular_static')
if (BASE_DIR / 'scripts').exists():
    app.mount('/formular/scripts', StaticFiles(directory=BASE_DIR / 'scripts'), name='formular_scripts')

# 3. Import and mount the core logic router
from formular import router
app.include_router(router, prefix='/formular')

@app.get("/")
def root_redirect():
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url='/formular')

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
            import threading
            import uvicorn
            import time
            import socket

            # Dynamically hook a free port to avoid conflicts
            def find_free_port():
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.bind(('', 0))
                    return s.getsockname()[1]
                    
            port = find_free_port()
            
            def run_uvicorn():
                uvicorn.run("main:app", host="127.0.0.1", port=port, log_level="error")
                
            # Run the heavy FastAPI logic securely in the background
            threading.Thread(target=run_uvicorn, daemon=True).start()
            time.sleep(1) # Provide binding margin
            
            eel.init(str(BASE_DIR))
            # Eel launches effectively as a seamless WebView bridging back to Uvicorn routing
            eel.start(f"http://127.0.0.1:{port}/formular", size=(1000, 850))
        except ImportError:
            print("Eel is not installed. To run the web server, use: python main.py --web")