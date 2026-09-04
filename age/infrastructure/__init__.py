"""The driven side of the hexagon: adapters for every port.

Two implementations of each persistence port, in-memory and MongoDB, chosen at
startup by whether a URI is configured. The deterministic world generator lives
here too: it is an adapter for :class:`~age.domain.ports.ChunkGenerator`, and the
one most likely to be replaced by a compiled implementation later.
"""

from . import (
    clock,
    generator,
    memory_repositories,
    noise,
    wire,
)

__all__ = [
    "clock",
    "generator",
    "memory_repositories",
    "noise",
    "wire",
]
