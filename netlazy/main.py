import sys
import logging
import mimetypes
import asyncio
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from netlazy.config import settings
from netlazy.database import connect_to_mongo, close_mongo_connection, db_instance
from netlazy.presentation import auth_router, profile_router, tag_router, feed_router, inbox_router, security_router
from netlazy.presentation.dependencies import tag_service

# Windows registry fix: explicitly map module files to correct types
mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("text/css", ".css")

BASE_DIR = Path(__file__).resolve().parent

class SensitiveRouteFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if record.args and len(record.args) >= 3:
            path = record.args[2]
            if isinstance(path, str) and ("/resolve" in path or "/handshakes" in path or "/me" in path):
                return False
        message = record.getMessage()
        if "/resolve" in message or "/handshakes" in message or "/me" in message:
            return False
        return True

logging.getLogger("uvicorn.access").addFilter(SensitiveRouteFilter())

async def _async_insert_log(log_doc):
    """Helper coroutine to safely execute the asynchronous write operation to MongoDB."""
    try:
        await db_instance.logs_collection.insert_one(log_doc)
    except Exception:
        pass

class MongoLogHandler(logging.Handler):
    def emit(self, record):
        if db_instance.logs_collection is None:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
            
        log_doc = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc),
            "level": record.levelname,
            "name": record.name,
            "message": self.format(record)
        }
        loop.create_task(_async_insert_log(log_doc))

mongo_handler = MongoLogHandler()
mongo_handler.setLevel(logging.INFO)
mongo_handler.setFormatter(logging.Formatter('%(message)s'))

# Standard API routing interface
router = APIRouter()

router.include_router(auth_router.router, prefix="/api")
router.include_router(tag_router.router, prefix="/api")
router.include_router(profile_router.router, prefix="/api")
router.include_router(feed_router.router, prefix="/api")
router.include_router(inbox_router.router, prefix="/api")
router.include_router(security_router.router, prefix="/api")

@router.on_event("startup")
async def startup_event():
    await connect_to_mongo()
    logging.getLogger().addHandler(mongo_handler)

    synced_count = await tag_service.sync_from_yaml(settings.tags_yaml_path)
    logging.info(f"Tag registry synced: {synced_count} tags loaded from {settings.tags_yaml_path}")

async def shutdown_clients():
    logging.getLogger().removeHandler(mongo_handler)
    await close_mongo_connection()

@router.get("/api/health")
def health_check():
    return {"status": "ok", "auth_type": "per-request-signature"}

# SPA Catch-all handling allowing deep Vue Router links bypassing the internal API bounds
@router.get("/")
@router.get("/{full_path:path}", include_in_schema=False)
async def serve_spa(request: Request, full_path: str = ""):
    if full_path.startswith("api/") or full_path == "api":
        raise HTTPException(status_code=404)
    
    index_file = BASE_DIR / "static" / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"error": "Frontend build not found. Run Vite build first."}

# Dual-Boot Support Hook
if __name__ == '__main__':
    if "--web" in sys.argv:
        import uvicorn
        from fastapi import FastAPI
        from fastapi.middleware.cors import CORSMiddleware
        
        standalone_app = FastAPI(title="netlazy standalone")
        
        standalone_app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
            expose_headers=["*"]
        )
        
        if (BASE_DIR / 'static').exists():
            standalone_app.mount('/netlazy/static', StaticFiles(directory=BASE_DIR / 'static'), name='netlazy_static')
        standalone_app.include_router(router, prefix='/netlazy')
        uvicorn.run(standalone_app, host="0.0.0.0", port=8000)
    else:
        try:
            import eel
            eel.init(str(BASE_DIR))
            html_file = 'static/index.html' if (BASE_DIR / 'static' / 'index.html').exists() else 'index.html'
            eel.start(html_file, size=(1000, 850))
        except ImportError:
            print("Eel is not installed. To run the web server, use: python main.py --web")