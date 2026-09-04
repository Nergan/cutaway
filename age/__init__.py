"""Age: a browser MMO vertical slice built on a topological accordion world.

The package follows a hexagonal split. Dependencies only ever point inwards,
which is what lets the simulation core be replaced by a Go or Rust process later
without touching the protocol or the HTTP surface.

``domain``
    Pure model with no I/O: coordinates, chunk topology, tiles, classes, NPC
    archetypes, entity components, and the ports every outer layer implements.
    ``domain.constants`` is the single source of truth mirrored by the client.
``application``
    Use cases driving the model: movement, combat, NPC AI, terrain mutation,
    chat, area-of-interest streaming, the accordion world manager, and the
    fixed-step simulation loop. Talks to the outside world only through ports.
``infrastructure``
    Adapters: the deterministic chunk generator, the binary wire codec, the
    in-memory and MongoDB repositories, the clock, and the Atelier art pipeline.
``presentation``
    FastAPI application, WebSocket adapter, and the composition root.
"""

__all__ = ["__version__"]

__version__ = "0.1.0"
