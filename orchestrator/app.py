"""Public FastAPI hub with optional process-isolated project workers."""

from __future__ import annotations

import logging
import os
import re
from collections import OrderedDict
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from pydantic import BaseModel

from shared_limits import RateLimiter, body_size_limit

from .config import RuntimeConfig, load_runtime_config
from .loader import LoadedProject, call_lifecycle, install_project
from .proxy import ProjectProxy
from .supervisor import ProjectSupervisor


ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
CONFIG = load_runtime_config(ROOT)
if CONFIG.profile == "hf":
    os.environ.setdefault("MONGO_MAX_POOL_SIZE", "3")
    os.environ.setdefault("MONGO_TLS_ALLOW_INVALID_CERTS", "0")

import shared_mongo  # noqa: E402  (profile defaults must be applied first)


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ReverseProxySchemeMiddleware:
    """Normalise paths and honour the scheme supplied by the hosting proxy."""

    def __init__(self, app: Any):
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] in ("http", "websocket"):
            path = scope.get("path", "")
            if "//" in path:
                cleaned = re.sub(r"/+", "/", path)
                scope["path"] = cleaned
                if "raw_path" in scope:
                    scope["raw_path"] = cleaned.encode("utf-8")
            for key, value in scope.get("headers", []):
                if key.lower() == b"x-forwarded-proto":
                    scope["scheme"] = value.decode("latin1")
                    break
        await self.app(scope, receive, send)


class LRUSet:
    def __init__(self, capacity: int = 10_000):
        self.cache: OrderedDict[str, None] = OrderedDict()
        self.capacity = capacity

    def __contains__(self, key: str) -> bool:
        if key not in self.cache:
            return False
        self.cache.move_to_end(key)
        return True

    def add(self, key: str) -> None:
        self.cache[key] = None
        self.cache.move_to_end(key)
        if len(self.cache) > self.capacity:
            self.cache.popitem(last=False)


class TrackRequest(BaseModel):
    uuid: str


def create_hub_app(config: RuntimeConfig = CONFIG) -> FastAPI:
    loaded: list[LoadedProject] = []
    embedded_status: dict[str, dict[str, Any]] = {
        project_id: (
            {"status": "pending"}
            if project.run
            else {
                "status": "disabled",
                "reason": project.reason or f"disabled for profile {config.profile}",
            }
        )
        for project_id, project in config.projects.items()
    }
    supervisor = ProjectSupervisor(config) if config.isolation == "isolated" else None
    http_client = (
        httpx.AsyncClient(
            timeout=None,
            trust_env=False,
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=30),
        )
        if supervisor is not None
        else None
    )
    stats_db = shared_mongo.get_client()["main-page"]
    seen_visitors = LRUSet()

    async def init_counter(app: FastAPI) -> None:
        await stats_db.stats.update_one(
            {"_id": "unique_visitors"},
            {"$setOnInsert": {"count": 0}},
            upsert=True,
        )
        counter_doc = await stats_db.stats.find_one({"_id": "unique_visitors"})
        app.state.total_visitors = counter_doc.get("count", 0) if counter_doc else 0
        app.state.stats_available = True

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        try:
            await init_counter(app)
        except Exception as exc:
            app.state.stats_available = False
            logger.error("Visitor counter unavailable, starting without it: %s", exc)

        if supervisor is not None:
            await supervisor.start()
        else:
            for project in loaded:
                try:
                    await call_lifecycle(project.startup)
                    embedded_status[project.project.project_id]["status"] = "online"
                except Exception as exc:
                    embedded_status[project.project.project_id] = {
                        "status": "offline",
                        "reason": type(exc).__name__,
                    }
                    logger.exception("Project %s failed during startup", project.project.project_id)
        try:
            yield
        finally:
            if supervisor is not None:
                await supervisor.stop()
            else:
                for project in reversed(loaded):
                    try:
                        await call_lifecycle(project.shutdown)
                    except Exception:
                        logger.exception("Project %s failed during shutdown", project.project.project_id)
            if http_client is not None:
                await http_client.aclose()
            shared_mongo.close_client()

    app = FastAPI(title="Nargan's Projects Ecosystem", lifespan=lifespan)
    app.state.total_visitors = 0
    app.state.stats_available = False
    app.state.runtime_config = config
    app.state.project_supervisor = supervisor
    app.add_middleware(ReverseProxySchemeMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*"],
    )

    track_rate = RateLimiter(limit=30, window_seconds=60)
    track_body = body_size_limit(16 * 1024)

    @app.get("/healthz", include_in_schema=False)
    async def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "profile": config.profile,
            "isolation": config.isolation,
            "database": "online" if app.state.stats_available else "degraded",
        }

    @app.get("/api/status")
    async def get_system_status() -> JSONResponse:
        projects = supervisor.snapshot() if supervisor is not None else embedded_status
        return JSONResponse(
            content={
                "profile": config.profile,
                "isolation": config.isolation,
                "plugins": projects,
            }
        )

    @app.get("/", response_class=HTMLResponse)
    async def home(_: Request) -> FileResponse:
        return FileResponse(ROOT / "index.html")

    @app.post("/api/track", dependencies=[Depends(track_rate), Depends(track_body)])
    async def track_visitor(request: Request, payload: TrackRequest) -> dict[str, int]:
        if payload.uuid in seen_visitors:
            return {"count": app.state.total_visitors}

        if not app.state.stats_available:
            return {"count": app.state.total_visitors}

        client_ip = (
            request.headers.get("X-Forwarded-For", request.client.host if request.client else "unknown")
            .split(",")[0]
            .strip()
        )
        try:
            result = await stats_db.visitors.update_one(
                {"_id": payload.uuid},
                {
                    "$setOnInsert": {
                        "_id": payload.uuid,
                        "first_seen": datetime.now(timezone.utc),
                        "ip_address": client_ip,
                        "user_agent": request.headers.get("user-agent", "unknown"),
                    },
                    "$set": {"last_seen": datetime.now(timezone.utc)},
                },
                upsert=True,
            )
            seen_visitors.add(payload.uuid)
            if result.upserted_id is not None:
                app.state.total_visitors += 1
                await stats_db.stats.update_one(
                    {"_id": "unique_visitors"},
                    {"$inc": {"count": 1}},
                )
        except Exception as exc:
            app.state.stats_available = False
            logger.error("Visitor tracking degraded after database error: %s", exc)
        return {"count": app.state.total_visitors}

    @app.get("/api/mainpage-backgrounds")
    async def get_mainpage_backgrounds() -> JSONResponse:
        return JSONResponse(
            content={
                "backgrounds": [
                    "autumn.mp4",
                    "hardtimes.mp4",
                    "lamp.mp4",
                    "minecraft.mp4",
                    "warmlight.mp4",
                ]
            }
        )

    @app.exception_handler(404)
    async def not_found_handler(request: Request, _: HTTPException) -> Response:
        path = request.url.path
        suspicious_patterns = (
            ".env",
            ".git",
            ".yml",
            ".yaml",
            ".ini",
            ".conf",
            "wp-admin",
            "wp-login",
            "xmlrpc",
            "wp-content",
            "actuator",
            "cgi-bin",
            "etc/passwd",
            "bin/sh",
            "phpinfo",
            "setup.php",
            "install.php",
            "config.php",
            "mysql",
            "phpmyadmin",
            "pma",
            "jenkins",
            "confluence",
        )
        if any(pattern in path.lower() for pattern in suspicious_patterns):
            return Response(status_code=404, content="Not Found", media_type="text/plain")
        segments = [segment.lower() for segment in path.split("/") if segment]
        if "api" in segments or path.startswith("/api") or path.endswith(".json"):
            return JSONResponse(status_code=404, content={"detail": "Not Found"})
        static_extensions = {
            ".css",
            ".js",
            ".png",
            ".jpg",
            ".jpeg",
            ".gif",
            ".svg",
            ".ico",
            ".xml",
            ".woff",
            ".woff2",
            ".ttf",
            ".mp4",
            ".webm",
        }
        if any(path.endswith(ext) for ext in static_extensions) or {"static", "scripts"} & set(segments):
            return Response(status_code=404, content="Not Found", media_type="text/plain")
        if "text/html" in request.headers.get("accept", ""):
            return RedirectResponse(url="/")
        return Response(status_code=404, content="Not Found", media_type="text/plain")

    if supervisor is not None:
        assert http_client is not None
        for project in config.for_phase("run"):
            proxy = ProjectProxy(project, supervisor, http_client)
            # Legacy yellow_mirror assets use an underscore while its app prefix uses a dash.
            legacy_base = f"/{project.project_id}"
            if legacy_base != project.prefix:
                app.mount(f"{legacy_base}/static", proxy, name=f"{project.project_id}_static_proxy")
                app.mount(f"{legacy_base}/scripts", proxy, name=f"{project.project_id}_scripts_proxy")
            app.mount(project.prefix, proxy, name=f"{project.project_id}_proxy")
    else:
        for project in config.for_phase("run"):
            try:
                loaded_project = install_project(app, project)
                loaded.append(loaded_project)
                embedded_status[project.project_id] = {
                    "status": "online",
                    "entrypoint": loaded_project.module_name,
                }
            except Exception as exc:
                embedded_status[project.project_id] = {
                    "status": "offline",
                    "reason": type(exc).__name__,
                }
                logger.exception("Project %s could not be loaded", project.project_id)

    return app


app = create_hub_app()
