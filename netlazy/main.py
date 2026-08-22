import sys
import logging
import mimetypes
import asyncio
import re
import time
import urllib.request
import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, APIRouter, HTTPException, Request, Depends, Response
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from netlazy.config import settings
from netlazy.database import connect_to_mongo, close_mongo_connection, db_instance, DatabaseUnavailableError
from netlazy.presentation.route_handler import NetlazyRoute
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


class MongoLogHandler(logging.Handler):
    def __init__(self, maxsize: int = 1000):
        super().__init__()
        self._maxsize = maxsize
        self._queue: asyncio.Queue | None = None
        self._worker_task: asyncio.Task | None = None
        self._running = False
        self._loop: asyncio.AbstractEventLoop | None = None

    def start_worker(self):
        self._loop = asyncio.get_running_loop()
        self._queue = asyncio.Queue(maxsize=self._maxsize)
        self._running = True
        self._worker_task = asyncio.create_task(self._process_logs())

    async def stop_worker(self):
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

    async def _process_logs(self):
        while self._running and self._queue is not None:
            try:
                doc = await self._queue.get()
                try:
                    logs_col = getattr(db_instance, 'logs_collection', None)
                    if logs_col is not None:
                        await logs_col.insert_one(doc)
                except Exception as e:
                    print(f"Failed to insert application log into MongoDB: {e}", file=sys.stderr)
                finally:
                    self._queue.task_done()
            except asyncio.CancelledError:
                break

    def emit(self, record):
        if not self._running or not self._loop or self._loop.is_closed():
            return
            
        if getattr(db_instance, 'logs_collection', None) is None:
            return

        log_doc = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc),
            "level": record.levelname,
            "name": record.name,
            "message": self.format(record)
        }

        def _put():
            if self._queue is not None:
                try:
                    self._queue.put_nowait(log_doc)
                except asyncio.QueueFull:
                    pass

        try:
            self._loop.call_soon_threadsafe(_put)
        except RuntimeError:
            pass


mongo_handler = MongoLogHandler()
mongo_handler.setLevel(logging.WARNING)
mongo_handler.setFormatter(logging.Formatter('%(message)s'))


async def startup_clients():
    """Explicit startup hook called by monorepo loaders and internal lifespan."""
    logging.info("[netlazy] Running startup hooks: connecting MongoDB and syncing registries...")
    await connect_to_mongo()
    mongo_handler.start_worker()
    logging.getLogger().addHandler(mongo_handler)

    synced_count = await tag_service.sync_from_yaml(settings.tags_yaml_path)
    logging.info(f"[netlazy] Tag registry synced: {synced_count} tags loaded from {settings.tags_yaml_path}")


async def shutdown_clients():
    """Explicit shutdown hook called by monorepo loaders and internal lifespan."""
    logging.info("[netlazy] Running shutdown hooks: closing connections...")
    logging.getLogger().removeHandler(mongo_handler)
    await mongo_handler.stop_worker()
    await close_mongo_connection()


def _get_base_path(request: Request) -> str:
    return "/netlazy" if request.url.path.startswith("/netlazy") else ""


async def block_browser_api(request: Request):
    accept = request.headers.get("accept", "")
    if "text/html" in accept:
        base = _get_base_path(request)
        raise HTTPException(status_code=303, headers={"Location": f"{base}/profile"})


@asynccontextmanager
async def lifespan(app: FastAPI):
    await startup_clients()
    yield
    await shutdown_clients()


app = FastAPI(
    title="netlazy", 
    lifespan=lifespan,
    docs_url=None if settings.environment == "production" else "/docs",
    redoc_url=None if settings.environment == "production" else "/redoc",
    openapi_url=None if settings.environment == "production" else "/openapi.json"
)

_cors_origins = settings.cors_origins
if "*" in _cors_origins and settings.cors_allow_credentials:
    _cors_origins = [origin for origin in _cors_origins if origin != "*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins if _cors_origins else ["*"],
    allow_credentials=False if "*" in settings.cors_origins else settings.cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Next-Anchor"]
)


@app.exception_handler(DatabaseUnavailableError)
async def database_unavailable_handler(request: Request, exc: DatabaseUnavailableError):
    return JSONResponse(
        status_code=503,
        content={"detail": "Service temporarily unavailable. Database connection failed."},
    )


router = APIRouter(route_class=NetlazyRoute)
api_deps = [Depends(block_browser_api)]

router.include_router(auth_router.router, prefix="/api", dependencies=api_deps)
router.include_router(tag_router.router, prefix="/api", dependencies=api_deps)
router.include_router(profile_router.router, prefix="/api", dependencies=api_deps)
router.include_router(feed_router.router, prefix="/api", dependencies=api_deps)
router.include_router(inbox_router.router, prefix="/api", dependencies=api_deps)
router.include_router(security_router.router, prefix="/api", dependencies=api_deps)

_cached_version = None
_cached_time = 0
_version_lock = asyncio.Lock()


def fetch_gh_version():
    req = urllib.request.Request(
        "https://api.github.com/repos/Nergan/cdn/contents/netlazy/apk",
        headers={"User-Agent": "netlazy-app/1.0"}
    )
    with urllib.request.urlopen(req, timeout=5) as res:
        return json.loads(res.read())


@router.get("/api/app-version")
async def get_app_version():
    global _cached_version, _cached_time
    if time.time() - _cached_time > 3600:
        async with _version_lock:
            if time.time() - _cached_time > 3600:
                try:
                    files = await asyncio.to_thread(fetch_gh_version)
                    for f in files:
                        if f["name"].endswith(".apk") and f["name"].startswith("netlazy-"):
                            match = re.search(r'netlazy-v?([\d\.]+)\.apk', f["name"])
                            if match:
                                _cached_version = {
                                    "version": match.group(1),
                                    "url": f"https://cdn.jsdelivr.net/gh/Nergan/cdn@main/netlazy/apk/{f['name']}"
                                }
                                _cached_time = time.time()
                                break
                except Exception:
                    pass
    return _cached_version or {"version": "0.0.1", "url": ""}


@router.get("/api/health")
async def health_check():
    try:
        await db_instance.client.admin.command('ping')
        return {"status": "ok", "auth_type": "per-request-signature", "database": "connected"}
    except Exception as e:
        logging.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail="Database unavailable")


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