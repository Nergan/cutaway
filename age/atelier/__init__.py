"""The Atelier: the art pipeline, and the answer to "who draws all this?".

Hand-drawing a tileset, a prop set, and animated characters is weeks of work, and
generating them with an image model produces art that cannot be edited, cannot be
kept consistent, and cannot be animated. So the sprites here are *programs*: a
recipe is a short list of drawing operations, and baking it produces colour, a
height field, and a material index.

That has three consequences worth stating, because they are why this exists:

Recipes are data. A recipe is JSON, so the browser editor at ``/age/atelier`` reads
and writes the same definitions the server bakes, and a change to a tileset is a
reviewable diff rather than a binary blob.

Animation is free. A recipe takes a frame index, so a swaying tree is one extra
operation rather than four hand-drawn frames.

Lighting comes out of the height field. Authoring "how far does this stick out" is
something a person can do; authoring a normal map by hand is not.

None of that replaces a real artist, which is why :mod:`age.atelier.importers`
exists: LDtk for levels, Aseprite for sprites, both importable without touching the
renderer. The generated art is the floor, not the ceiling.

This package is a supporting subdomain rather than part of the hexagon. The
simulation never imports it, and it never imports the simulation; the only shared
vocabulary is the tile table.
"""

from . import (
    canvas,
    character,
    importers,
    normals,
    palette,
    png,
    recipes,
    sheet,
)

__all__ = [
    "canvas",
    "character",
    "importers",
    "normals",
    "palette",
    "png",
    "recipes",
    "sheet",
]
