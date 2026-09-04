"""Importers for LDtk levels and Aseprite sprite sheets.

The Atelier is not meant to be the only way to make art for this game, and betting
the project on a browser editor that has to grow into Aseprite would be a bad bet.
So the two obvious professional tools get first-class import paths:

`LDtk <https://ldtk.io>`_ is a free tile-based level editor with a documented JSON
format. Authoring a hub by hand in LDtk and importing it is much better than
placing props through a web UI, and it means level design does not block on this
project's tooling.

`Aseprite <https://aseprite.org>`_ is the standard pixel-art tool. Its
``--format json-array`` export names frames and tags animations, which maps directly
onto the pose-and-frame model the renderer already uses for generated characters.

Both importers are lenient about fields they do not need and strict about the ones
they do, and both return plain dataclasses rather than touching the world. Importing
is a build step, not a runtime feature.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..domain.constants import CHUNK_TILES
from ..domain.tiles import Tile

# LDtk layer identifiers this importer understands. Anything else in the project is
# ignored, so an author can keep helper layers without breaking the import.
TERRAIN_LAYER = "Terrain"
PROPS_LAYER = "Props"


class ImportError_(ValueError):
    """Raised when a file is structurally not what it claims to be."""


# --- LDtk -------------------------------------------------------------------


@dataclass(slots=True)
class ImportedProp:
    """One placed decoration, in tile coordinates relative to the level origin."""

    recipe: str
    tile_x: float
    tile_y: float
    flip_x: bool = False


@dataclass(slots=True)
class ImportedLevel:
    """A hand-authored patch of terrain, ready to apply as a chunk overlay."""

    identifier: str
    width_tiles: int
    height_tiles: int
    # Tile index within the level, row-major, to a :class:`Tile` value.
    tiles: dict[int, int] = field(default_factory=dict)
    props: list[ImportedProp] = field(default_factory=list)

    def chunk_overlays(self) -> dict[tuple[int, int], dict[int, int]]:
        """Split the level into per-chunk overlays.

        Returns ``{(chunk_x, chunk_y): {tile_index: tile}}`` with indices local to
        each chunk, which is exactly the shape
        :meth:`~age.application.world.World.apply_overlay` takes. A level larger than
        one chunk is the normal case for a hub, so splitting is the importer's job
        rather than the caller's.
        """
        overlays: dict[tuple[int, int], dict[int, int]] = {}
        for index, tile in self.tiles.items():
            level_x = index % self.width_tiles
            level_y = index // self.width_tiles
            chunk_x, local_x = divmod(level_x, CHUNK_TILES)
            chunk_y, local_y = divmod(level_y, CHUNK_TILES)
            overlays.setdefault((chunk_x, chunk_y), {})[local_y * CHUNK_TILES + local_x] = tile
        return overlays


def load_ldtk(document: dict[str, Any], *, tile_mapping: dict[int, int] | None = None) -> list[ImportedLevel]:
    """Read an LDtk project into levels.

    ``tile_mapping`` translates LDtk tileset ids to this game's :class:`Tile` values.
    Without it the importer falls back to the ``IntGrid`` values, which is the
    workflow that needs no tileset image at all: paint terrain classes as an IntGrid
    in LDtk and the numbers *are* the tile ids.
    """
    raw_levels = document.get("levels")
    if raw_levels is None:
        raise ImportError_("not an LDtk project: no 'levels' key")
    # Shape-checked rather than trusted. This is a file somebody uploaded through a
    # browser, and every malformed shape has to come back as "that is not an LDtk
    # project" rather than as a stack trace from three frames down.
    if not isinstance(raw_levels, list):
        raise ImportError_("'levels' is not a list")

    grid_size = _dimension(document.get("defaultGridSize"), 32)
    levels: list[ImportedLevel] = []

    for raw_level in raw_levels:
        if not isinstance(raw_level, dict):
            raise ImportError_("a level is not an object")

        level = ImportedLevel(
            identifier=str(raw_level.get("identifier", "level"))[:64],
            width_tiles=max(1, _dimension(raw_level.get("pxWid"), grid_size) // grid_size),
            height_tiles=max(1, _dimension(raw_level.get("pxHei"), grid_size) // grid_size),
        )

        layers = raw_level.get("layerInstances") or ()
        if not isinstance(layers, list):
            raise ImportError_("'layerInstances' is not a list")

        for layer in layers:
            if not isinstance(layer, dict):
                raise ImportError_("a layer is not an object")
            identifier = str(layer.get("__identifier", ""))
            if identifier == TERRAIN_LAYER:
                _read_terrain(layer, level, tile_mapping, grid_size)
            elif identifier == PROPS_LAYER:
                _read_props(layer, level, grid_size)

        levels.append(level)

    return levels


def _dimension(value: Any, default: int) -> int:
    """A size from untrusted JSON. Must be positive; a grid size of zero divides."""
    number = _offset(value, default)
    return number if number > 0 else default


def _offset(value: Any, default: int) -> int:
    """A coordinate or duration from untrusted JSON, falling back rather than raising."""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return number if number >= 0 else default


def _read_terrain(
    layer: dict[str, Any],
    level: ImportedLevel,
    tile_mapping: dict[int, int] | None,
    grid_size: int,
) -> None:
    """Read either an IntGrid or a tile layer into tile ids."""
    width = max(1, int(layer.get("__cWid", level.width_tiles)))

    int_grid = layer.get("intGridCsv")
    if isinstance(int_grid, list) and int_grid:
        for index, value in enumerate(int_grid):
            # Zero is LDtk's "empty", not tile 0. Bare ground has to be painted
            # explicitly, which is the same rule LDtk itself uses.
            if value:
                level.tiles[index] = _valid_tile(int(value) - 1)
        return

    for entry in layer.get("gridTiles") or ():
        position = entry.get("px") or [0, 0]
        tile_x = int(position[0]) // grid_size
        tile_y = int(position[1]) // grid_size
        source = int(entry.get("t", 0))
        mapped = (tile_mapping or {}).get(source, source)
        level.tiles[tile_y * width + tile_x] = _valid_tile(mapped)


def _read_props(layer: dict[str, Any], level: ImportedLevel, grid_size: int) -> None:
    """Read entity instances as prop placements.

    The entity's ``identifier`` is the recipe key, so an LDtk entity called
    ``lantern`` places the ``lantern`` recipe. Naming the two the same is the whole
    integration; there is no mapping table to keep in sync.
    """
    for entity in layer.get("entityInstances") or ():
        position = entity.get("px") or [0, 0]
        level.props.append(
            ImportedProp(
                recipe=str(entity.get("__identifier", "crate")),
                tile_x=int(position[0]) / grid_size,
                tile_y=int(position[1]) / grid_size,
                flip_x=bool(_field(entity, "flipX", False)),
            )
        )


def _field(entity: dict[str, Any], name: str, default: Any) -> Any:
    """Read a custom field from an LDtk entity instance."""
    for entry in entity.get("fieldInstances") or ():
        if entry.get("__identifier") == name:
            return entry.get("__value", default)
    return default


def _valid_tile(value: int) -> int:
    """Clamp an imported id to a real tile.

    An out-of-range id means the author's tileset and this game's tile table have
    drifted. Falling back to bare ground makes that visible on the map instead of
    crashing the import, and bare ground regrows, so the mistake is not permanent.
    """
    try:
        return int(Tile(value))
    except ValueError:
        return int(Tile.BARE_GROUND)


# --- Aseprite ---------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SpriteFrame:
    """One cel: where it sits on the sheet and how long it shows."""

    name: str
    x: int
    y: int
    width: int
    height: int
    duration_ms: int


@dataclass(frozen=True, slots=True)
class SpriteTag:
    """An animation range, from Aseprite's frame tags."""

    name: str
    first: int
    last: int
    direction: str = "forward"

    @property
    def frame_count(self) -> int:
        return self.last - self.first + 1


@dataclass(slots=True)
class ImportedSprite:
    """An Aseprite sheet, described well enough to drive the renderer."""

    image: str
    sheet_width: int
    sheet_height: int
    frames: list[SpriteFrame] = field(default_factory=list)
    tags: list[SpriteTag] = field(default_factory=list)
    slices: dict[str, tuple[int, int, int, int]] = field(default_factory=dict)

    def tag(self, name: str) -> SpriteTag | None:
        for entry in self.tags:
            if entry.name == name:
                return entry
        return None

    @property
    def pivot(self) -> tuple[int, int] | None:
        """The ``anchor`` slice, if the author marked one.

        Aseprite slices are how an artist says "the feet are here", and the renderer
        needs that: anchoring a sprite by its centre puts a tall character's waist on
        the tile instead of their boots.
        """
        rect = self.slices.get("anchor")
        if rect is None:
            return None
        return rect[0] + rect[2] // 2, rect[1] + rect[3]


def load_aseprite(document: dict[str, Any]) -> ImportedSprite:
    """Read an Aseprite ``json-array`` export.

    The hash format is rejected rather than supported. Array order is the frame
    order, and reconstructing it from hash keys means parsing the filename template
    the author happened to use, which is not a contract worth depending on.
    """
    frames = document.get("frames")
    if isinstance(frames, dict):
        raise ImportError_(
            "export with --format json-array: the hash format has no reliable frame order"
        )
    if not isinstance(frames, list):
        raise ImportError_("not an Aseprite export: no 'frames' array")

    meta = document.get("meta") or {}
    size = meta.get("size") or {}

    sprite = ImportedSprite(
        image=str(meta.get("image", "")),
        sheet_width=int(size.get("w", 0)),
        sheet_height=int(size.get("h", 0)),
    )

    for entry in frames:
        if not isinstance(entry, dict):
            raise ImportError_("a frame is not an object")
        rect = entry.get("frame") or {}
        sprite.frames.append(
            SpriteFrame(
                name=str(entry.get("filename", ""))[:128],
                x=_offset(rect.get("x"), 0),
                y=_offset(rect.get("y"), 0),
                width=_offset(rect.get("w"), 0),
                height=_offset(rect.get("h"), 0),
                duration_ms=_dimension(entry.get("duration"), 100),
            )
        )

    for entry in meta.get("frameTags") or ():
        if not isinstance(entry, dict):
            raise ImportError_("a frame tag is not an object")
        sprite.tags.append(
            SpriteTag(
                name=str(entry.get("name", ""))[:64],
                first=_offset(entry.get("from"), 0),
                last=_offset(entry.get("to"), 0),
                direction=str(entry.get("direction", "forward"))[:16],
            )
        )

    for entry in meta.get("slices") or ():
        if not isinstance(entry, dict):
            raise ImportError_("a slice is not an object")
        keys = entry.get("keys") or ()
        if not keys or not isinstance(keys[0], dict):
            continue
        bounds = keys[0].get("bounds") or {}
        sprite.slices[str(entry.get("name", ""))[:64]] = (
            _offset(bounds.get("x"), 0),
            _offset(bounds.get("y"), 0),
            _offset(bounds.get("w"), 0),
            _offset(bounds.get("h"), 0),
        )

    return sprite
