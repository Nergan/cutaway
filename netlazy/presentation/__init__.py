from netlazy.presentation.route_handler import NetlazyRoute
from netlazy.presentation import (
    auth_router,
    feed_router,
    inbox_router,
    profile_router,
    security_router,
    tag_router,
    dependencies,
)

__all__ = [
    "NetlazyRoute",
    "auth_router",
    "feed_router",
    "inbox_router",
    "profile_router",
    "security_router",
    "tag_router",
    "dependencies",
]