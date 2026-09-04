"""The pure model. No I/O, no framework, no async.

``constants`` is the single source of truth mirrored by the TypeScript client.
Everything else here is either a value object or a pure function over one, which
is what lets the accordion and the AI be tested with a fake clock and nothing else.
"""

from . import (
    classes,
    constants,
    coordinates,
    entities,
    hashing,
    npc,
    ports,
    tiles,
    topology,
)

__all__ = [
    "classes",
    "constants",
    "coordinates",
    "entities",
    "hashing",
    "npc",
    "ports",
    "tiles",
    "topology",
]
