import sys
import logging
import mimetypes
import asyncio
import re
import time
import urllib.request
import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, APIRouter, HTTPException, Request, Depends
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from netlazy.config import settings
from netlazy.database import connect_to_mongo, close_mongo_connection, db_instance
from netlazy.presentation import auth_router, profile_router, tag_router, feed_router, inbox_router, security_router
from netlazy.presentation.dependencies import tag_service

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


def _get_base_path(request: Request) -> str:
    return "/netlazy" if request.url.path.startswith("/netlazy") else ""


async def block_browser_api(request: Request):
    accept = request.headers.get("accept", "")
    if "text/html" in accept:
        base = _get_base_path(request)
        raise HTTPException(status_code=303, headers={"Location": f"{base}/profile"})

# Define global application and attach CORS globally to avoid missing headers in container mode
app = FastAPI(title="netlazy")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Next-Anchor"]
)

router = APIRouter()
api_deps = [Depends(block_browser_api)]

router.include_router(auth_router.router, prefix="/api", dependencies=api_deps)
router.include_router(tag_router.router, prefix="/api", dependencies=api_deps)
router.include_router(profile_router.router, prefix="/api", dependencies=api_deps)
router.include_router(feed_router.router, prefix="/api", dependencies=api_deps)
router.include_router(inbox_router.router, prefix="/api", dependencies=api_deps)
router.include_router(security_router.router, prefix="/api", dependencies=api_deps)


_cached_version = None
_cached_time = 0

def fetch_gh_version():
    req = urllib.request.Request("https://api.github.com/repos/Nergan/cdn/contents/netlazy/apk")
    with urllib.request.urlopen(req, timeout=5) as res:
        return json.loads(res.read())

@router.get("/api/app-version")
async def get_app_version():
    global _cached_version, _cached_time
    if time.time() - _cached_time > 3600:
        try:
            files = await asyncio.to_thread(fetch_gh_version)
            for f in files:
                if f["name"].endswith(".apk") and f["name"].startswith("netlazy-"):
                    match = re.search(r'netlazy-v?([\d\.]+)\.apk', f["name"])
                    if match:
                        _cached_version = {"version": match.group(1), "url": f"https://cdn.jsdelivr.net/gh/Nergan/cdn@main/netlazy/apk/{f['name']}"}
                        _cached_time = time.time()
                        break
        except Exception:
            pass
    return _cached_version or {"version": "0.0.1", "url": ""}


@router.on_event("startup")
async def startup_event():
    await connect_to_mongo()
    logging.getLogger().addHandler(mongo_handler)

    synced_count = await tag_service.sync_from_yaml(settings.tags_yaml_path)
    logging.info(f"Tag registry synced: {synced_count} tags loaded from {settings.tags_yaml_path}")


@router.on_event("shutdown")
async def shutdown_clients():
    logging.getLogger().removeHandler(mongo_handler)
    await close_mongo_connection()

@router.get("/api/health")
def health_check():
    return {"status": "ok", "auth_type": "per-request-signature"}


@router.get("/")
async def root_redirect(request: Request):
    base = _get_base_path(request)
    return RedirectResponse(url=f"{base}/profile", status_code=303)

@router.get("/{full_path:path}", include_in_schema=False)
async def serve_spa(request: Request, full_path: str = ""):
    if full_path.startswith("api/") or full_path == "api":
        accept = request.headers.get("accept", "")
        if "text/html" in accept:
            base = _get_base_path(request)
            return RedirectResponse(url=f"{base}/profile", status_code=303)
        raise HTTPException(status_code=404)
    
    index_file = BASE_DIR / "static" / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    
    return HTMLResponse(
        content="<html><body><h1>Frontend Not Built Yet</h1></body></html>",
        status_code=200
    )

app.include_router(router)
if (BASE_DIR / 'static').exists():
    app.mount('/static', StaticFiles(directory=BASE_DIR / 'static'), name='netlazy_static')

if __name__ == '__main__':
    if "--web" in sys.argv:
        import uvicorn
        uvicorn.run(app, host="0.0.0.0", port=8000)
    else:
        try:
            import eel
            eel.init(str(BASE_DIR))
            html_file = 'static/index.html' if (BASE_DIR / 'static' / 'index.html').exists() else 'index.html'
            eel.start(html_file, size=(1000, 850))
        except ImportError:
            print("Eel is not installed. To run the web server, use: python main.py --web")