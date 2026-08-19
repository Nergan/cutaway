import asyncio
import logging
from typing import Callable, Coroutine, Any
from fastapi import Request, Response
from fastapi.routing import APIRoute
from fastapi.responses import JSONResponse

from netlazy.database import db_instance, DatabaseUnavailableError

_init_lock = asyncio.Lock()


async def ensure_database_connected():
    """Guarantees MongoDB connection on demand even if parent app mounted router without running lifespan."""
    if getattr(db_instance, "client", None) is None:
        async with _init_lock:
            if getattr(db_instance, "client", None) is None:
                logging.info("[netlazy] Lazy DB initialization triggered by incoming request...")
                from netlazy.main import startup_clients
                await startup_clients()


class NetlazyRoute(APIRoute):
    """Custom APIRoute handling sub-app lifecycle, exception mapping, and ratchet propagation."""

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        original_route_handler = super().get_route_handler()

        async def custom_route_handler(request: Request) -> Response:
            try:
                await ensure_database_connected()
                response: Response = await original_route_handler(request)
            except DatabaseUnavailableError:
                return JSONResponse(
                    status_code=503,
                    content={"detail": "Service temporarily unavailable. Database connection failed."},
                )

            # Ensure ratchet header propagation without requiring parent app middleware
            if hasattr(request.state, "next_anchor") and request.state.next_anchor:
                response.headers["X-Next-Anchor"] = request.state.next_anchor

            return response

        return custom_route_handler