"""The application layer: systems that make the world move.

Each module here is one system with one job, taking the world as its first
argument and mutating it. Nothing in this package touches a socket, a database, or
the clock directly: time arrives through a port and writes leave through
repositories. :mod:`age.application.simulation` is the only module that knows the
order the systems run in.
"""

from . import (
    accordion,
    ai,
    chat,
    combat,
    events,
    interest,
    movement,
    session,
    simulation,
    terrain,
    weather,
    world,
)

__all__ = [
    "accordion",
    "ai",
    "chat",
    "combat",
    "events",
    "interest",
    "movement",
    "session",
    "simulation",
    "terrain",
    "weather",
    "world",
]
