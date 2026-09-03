"""ASCII City: a multiplayer ASCII city rendered from an authoritative world grid.

Layers follow a hexagonal split:

``domain``
    World model, player and chat entities plus the ports the rest depends on.
``application``
    Use cases: movement, interest management, chat policy and the city room.
``infrastructure``
    Adapters: the procedural generator, binary codecs and the repositories.
``presentation``
    FastAPI routes, the WebSocket adapter and the composition root.
"""

__all__ = ["__version__"]

__version__ = "1.0.0"
