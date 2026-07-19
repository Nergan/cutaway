import importlib
import logging
import re
from datetime import datetime
from os import environ
from pathlib import Path
from collections import OrderedDict

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MONGO_URL = environ.get('MONGODB_URI', 'mongodb://localhost:27017')
client = AsyncIOMotorClient(MONGO_URL, tls=True, tlsAllowInvalidCertificates=True)
stats_db = client['main-page']

app = FastAPI(title="Nargan's Projects Ecosystem")

# --- Raw ASGI Middleware for Proxy Scheme Alignment ---
# Avoids Starlette's BaseHTTPMiddleware stream bugs (EndOfStream exceptions on 404)
class ReverseProxySchemeMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket"):
            # Normalize double/multiple slashes in path to prevent routing mismatches
            if "path" in scope:
                path = scope["path"]
                if "//" in path:
                    cleaned = re.sub(r'/+', '/', path)
                    scope["path"] = cleaned
                    if "raw_path" in scope:
                        scope["raw_path"] = cleaned.encode("utf-8")

            headers = scope.get("headers", [])
            for key, value in headers:
                if key == b"x-forwarded-proto":
                    scope["scheme"] = value.decode("latin1")
                    break
        await self.app(scope, receive, send)

app.add_middleware(ReverseProxySchemeMiddleware)

# --- Security/CORS Configuration for Capacitor (Mobile Wrapper) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # For native mobile interceptors like capacitor://localhost
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"]
)

BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=BASE_DIR)

# --- Safe Static Mounting ---
def mount_if_exists(path: str, name: str, dir_path: Path):
    if dir_path.exists() and dir_path.is_dir():
        logger.info(f"Mounting static files from {dir_path} at {path}")
        app.mount(path, StaticFiles(directory=dir_path), name=name)
    else:
        logger.warning(f"Static directory not found or invalid: {dir_path}")

# --- Dynamic Plugin Discovery (Resilient Monolith) ---
loaded_plugins = {}
shutdown_callbacks = []

logger.info("Starting dynamic plugin discovery...")
for plugin_dir in BASE_DIR.iterdir():
    if not plugin_dir.is_dir() or plugin_dir.name.startswith(('.', '__')):
        continue

    plugin_name = plugin_dir.name
    
    # Smart Fallback List: Added `plugin_name` to check __init__.py directly
    potential_entrypoints = [
        f"{plugin_name}.main",
        f"{plugin_name}.{plugin_name}",
        f"{plugin_name}.router",
        f"{plugin_name}"
    ]
    
    mounted = False
    plugin_errors = {}
    
    for entrypoint in potential_entrypoints:
        try:
            logger.info(f"Attempting to load plugin: {plugin_name} via {entrypoint}")
            plugin_module = importlib.import_module(entrypoint)
            
            # Check for router contract
            if hasattr(plugin_module, "router"):
                # 1. Mount statics FIRST to prevent catch-all routes from intercepting static files
                mount_if_exists(f'/{plugin_name}/static', f'{plugin_name}_static', plugin_dir / 'static')
                mount_if_exists(f'/{plugin_name}/scripts', f'{plugin_name}_scripts', plugin_dir / 'scripts')

                # 2. Include the router
                prefix = f"/{plugin_name.replace('_', '-')}"
                app.include_router(plugin_module.router, prefix=prefix, tags=[plugin_name.capitalize()])
                
                # Check for shutdown hook contract
                if hasattr(plugin_module, "shutdown_clients"):
                    shutdown_callbacks.append(plugin_module.shutdown_clients)
                    
                loaded_plugins[plugin_name] = {"status": "online", "entrypoint": entrypoint}
                logger.info(f"Successfully mounted plugin: {plugin_name} at {prefix}")
                mounted = True
                break  # Stop searching once successfully mounted
            else:
                plugin_errors[entrypoint] = "Module loaded but missing 'router' attribute."
                
        except Exception as e:
            # Record the error and try the next potential entrypoint
            plugin_errors[entrypoint] = str(e)
            
    if not mounted:
        if plugin_errors:
            logger.error(f"Gracefully degraded plugin {plugin_name}. Failed to load valid router. Errors: {plugin_errors}")
            loaded_plugins[plugin_name] = {"status": "offline", "errors": plugin_errors}
        else:
            loaded_plugins[plugin_name] = {"status": "ignored"}

# --- Root Logic ---
class BaseModelLimit(BaseModel):
    pass


# --- Optimized In-Memory Cache ---
class LRUSet:
    """A lightweight, dependency-free cache to prevent duplicate database queries."""
    def __init__(self, capacity: int = 10000):
        self.cache = OrderedDict()
        self.capacity = capacity

    def __contains__(self, key):
        if key not in self.cache:
            return False
        self.cache.move_to_end(key)
        return True

    def add(self, key):
        self.cache[key] = None
        self.cache.move_to_end(key)
        if len(self.cache) > self.capacity:
            self.cache.popitem(last=False)

seen_visitors = LRUSet(capacity=10000)
TOTAL_VISITORS = 0


@app.get('/api/status')
async def get_system_status():
    """Endpoint for the frontend to determine which projects successfully booted."""
    return JSONResponse(content={"plugins": loaded_plugins})

class TrackRequest(BaseModel):
    uuid: str


@app.on_event('shutdown')
async def shutdown_event():
    for callback in shutdown_callbacks:
        try:
            await callback()
        except Exception as e:
            logger.error(f"Error executing shutdown callback: {e}")

@app.get('/', response_class=HTMLResponse)
async def home(request: Request):
    return FileResponse(BASE_DIR / 'index.html')

# --- Lifecycle & Database ---
async def init_counter():
    global TOTAL_VISITORS
    # Ensure the document exists
    await stats_db.stats.update_one({'_id': 'unique_visitors'}, {'$setOnInsert': {'count': 0}}, upsert=True)
    # Pre-load the total count into RAM
    counter_doc = await stats_db.stats.find_one({'_id': 'unique_visitors'})
    if counter_doc:
        TOTAL_VISITORS = counter_doc.get('count', 0)

@app.on_event('startup')
async def startup_event():
    await init_counter()

# --- Optimized Tracking Endpoint ---
@app.post('/api/track')
async def track_visitor(request: Request, payload: TrackRequest):
    global TOTAL_VISITORS
    
    # 1. RAM Cache Check: 0ms response, 0 DB queries for returning active users
    if payload.uuid in seen_visitors:
        return {'count': TOTAL_VISITORS}
        
    # 2. Extract advanced identifying metrics (IP and Browser)
    # X-Forwarded-For handles standard reverse proxies/Docker routing
    client_ip = request.headers.get("X-Forwarded-For", request.client.host).split(",")[0].strip()
    user_agent = request.headers.get("user-agent", "unknown")
    
    # 3. Perform a single database operation for unknown users
    result = await stats_db.visitors.update_one(
        {'_id': payload.uuid},
        {
            '$setOnInsert': {
                '_id': payload.uuid, 
                'first_seen': datetime.utcnow(),
                'ip_address': client_ip,
                'user_agent': user_agent
            },
            '$set': {
                'last_seen': datetime.utcnow()
            }
        },
        upsert=True
    )
    
    # Add to in-memory cache so they don't hit the DB again today
    seen_visitors.add(payload.uuid)
    
    # 4. If they were genuinely new to the database, increment global counter
    if result.upserted_id is not None:
        TOTAL_VISITORS += 1
        # Fire-and-forget DB update (doesn't block the client response)
        await stats_db.stats.update_one({'_id': 'unique_visitors'}, {'$inc': {'count': 1}})
        
    return {'count': TOTAL_VISITORS}

# --- Refined 404 Exception Handler ---
@app.exception_handler(404)
async def not_found_handler(request: Request, exc: HTTPException):
    path = request.url.path
    
    # 1. Block requests for common bot scanning targets instantly to save CPU/logs
    suspicious_patterns = [
        ".env", ".git", ".yml", ".yaml", ".ini", ".conf", 
        "wp-admin", "wp-login", "xmlrpc", "wp-content",
        "actuator", "cgi-bin", "etc/passwd", "bin/sh",
        "phpinfo", "setup.php", "install.php", "config.php",
        "mysql", "phpmyadmin", "pma", "jenkins", "confluence"
    ]
    if any(pattern in path.lower() for pattern in suspicious_patterns):
        return Response(status_code=404, content="Not Found", media_type="text/plain")

    # 2. Extract path segments to check if the destination is an API endpoint
    path_segments = [seg.lower() for seg in path.split("/") if seg]
    is_api = "api" in path_segments or path.startswith("/api") or path.endswith(".json")
    
    if is_api:
        return JSONResponse(status_code=404, content={"detail": "Not Found"})

    # 3. Prevent redirecting static assets or client scripts
    static_extensions = {
        ".css", ".js", ".png", ".jpg", ".jpeg", ".gif", ".svg", 
        ".ico", ".xml", ".woff", ".woff2", ".ttf", ".mp4", ".webm"
    }
    is_static_ext = any(path.endswith(ext) for ext in static_extensions)
    is_static_path = "static" in path_segments or "scripts" in path_segments

    if is_static_ext or is_static_path:
        return Response(status_code=404, content="Not Found", media_type="text/plain")
        
    # 4. Clean redirect for HTML-requesting browsers
    accept = request.headers.get("accept", "")
    if "text/html" in accept:
        return RedirectResponse(url='/')
        
    # 5. Clean, lightweight fallback for other request types (e.g. text plain clients)
    return Response(status_code=404, content="Not Found", media_type="text/plain")

@app.get('/api/mainpage-backgrounds')
async def get_mainpage_backgrounds():
    mp4_files = ["autumn.mp4", "hardtimes.mp4", "lamp.mp4", "minecraft.mp4", "warmlight.mp4"]
    return JSONResponse(content={'backgrounds': mp4_files})