"""Binary tile container. See ``docs/world-format.md`` for the byte layout.

One 128 x 128 tile encodes to roughly 55 KB and compresses to well under
10 KB, because the three cell layers are highly repetitive. The client decodes
this inside a Web Worker so the game loop never stalls on it.
"""

from __future__ import annotations

import struct
from typing import Sequence

from ..domain.errors import WorldDataError
from ..domain.world import Building, Prop, Road, SpawnPoint, WorldTile
from .quantise import round_half_up

MAGIC = b"ACT1"
FORMAT_VERSION = 1

_HEADER = struct.Struct("<4sHHiiHfI")
_BUILDING_TAIL = struct.Struct("<BBBBBBBBB")
_PROP = struct.Struct("<HHHB")
_SPAWN = struct.Struct("<HHH")

_ANGLE_UNITS = 65536.0
_TAU = 6.283185307179586


class _Reader:
    __slots__ = ("_data", "_offset")

    def __init__(self, data: bytes) -> None:
        self._data = data
        self._offset = 0

    def take(self, size: int) -> bytes:
        end = self._offset + size
        if end > len(self._data):
            raise WorldDataError("Tile payload is truncated.")
        chunk = self._data[self._offset : end]
        self._offset = end
        return chunk

    def unpack(self, layout: struct.Struct) -> tuple:
        return layout.unpack(self.take(layout.size))

    def u8(self) -> int:
        return self.take(1)[0]

    def u16(self) -> int:
        return int.from_bytes(self.take(2), "little")

    def i16(self) -> int:
        return int.from_bytes(self.take(2), "little", signed=True)

    def text(self, length: int) -> str:
        return self.take(length).decode("utf-8")


def encode_tile(tile: WorldTile) -> bytes:
    out = bytearray()
    identifier = tile.id.encode("utf-8")
    out += _HEADER.pack(
        MAGIC,
        FORMAT_VERSION,
        0,
        tile.tile_x,
        tile.tile_y,
        tile.cells,
        tile.cell_size,
        tile.version,
    )
    out += len(identifier).to_bytes(2, "little")
    out += identifier

    out += tile.collision
    out += tile.heights
    out += tile.styles

    out += len(tile.buildings).to_bytes(2, "little")
    for building in tile.buildings:
        out += building.id.to_bytes(2, "little")
        out.append(building.vertex_count)
        for value in building.footprint:
            out += int(value).to_bytes(2, "little", signed=True)
        out += _BUILDING_TAIL.pack(
            min(255, building.height),
            min(255, building.min_height),
            min(255, building.levels),
            building.roof_type,
            building.category,
            building.facade_style,
            building.window_style,
            building.color,
            (1 if building.walkable else 0) | (2 if building.interior_id else 0),
        )

    out += len(tile.roads).to_bytes(2, "little")
    for road in tile.roads:
        name = (road.name or "").encode("utf-8")[:255]
        out += road.id.to_bytes(2, "little")
        out.append(road.type)
        out.append(min(255, max(1, int(round(road.width * 10)))))
        out.append(road.surface_style)
        out.append(len(road.centerline) // 2)
        for value in road.centerline:
            out += int(value).to_bytes(2, "little", signed=True)
        out.append(len(name))
        out += name

    out += len(tile.props).to_bytes(2, "little")
    for prop in tile.props:
        out += _PROP.pack(prop.id, prop.x, prop.y, prop.kind)

    out += len(tile.spawn_points).to_bytes(2, "little")
    for spawn in tile.spawn_points:
        out += _SPAWN.pack(spawn.x, spawn.y, _encode_heading(spawn.heading))

    return bytes(out)


def decode_tile(payload: bytes) -> WorldTile:
    reader = _Reader(payload)
    magic, version, _flags, tile_x, tile_y, cells, cell_size, world_version = reader.unpack(_HEADER)
    if magic != MAGIC:
        raise WorldDataError("Not an ASCII City tile payload.")
    if version != FORMAT_VERSION:
        raise WorldDataError(f"Unsupported tile format version {version}.")
    identifier = reader.text(reader.u16())

    area = cells * cells
    collision = bytearray(reader.take(area))
    heights = bytearray(reader.take(area))
    styles = bytearray(reader.take(area))

    buildings: list[Building] = []
    for _ in range(reader.u16()):
        building_id = reader.u16()
        vertex_count = reader.u8()
        footprint = tuple(reader.i16() for _ in range(vertex_count * 2))
        (
            height,
            min_height,
            levels,
            roof_type,
            category,
            facade_style,
            window_style,
            color,
            flags,
        ) = reader.unpack(_BUILDING_TAIL)
        buildings.append(
            Building(
                id=building_id,
                footprint=footprint,
                height=height,
                min_height=min_height,
                levels=levels,
                roof_type=roof_type,
                category=category,
                facade_style=facade_style,
                window_style=window_style,
                color=color,
                walkable=bool(flags & 1),
                interior_id="pending" if flags & 2 else None,
            )
        )

    roads: list[Road] = []
    for _ in range(reader.u16()):
        road_id = reader.u16()
        road_type = reader.u8()
        width = reader.u8() / 10.0
        surface_style = reader.u8()
        point_count = reader.u8()
        centerline = tuple(reader.i16() for _ in range(point_count * 2))
        name = reader.text(reader.u8()) or None
        roads.append(
            Road(
                id=road_id,
                centerline=centerline,
                width=width,
                type=road_type,
                walkable=True,
                surface_style=surface_style,
                name=name,
            )
        )

    props = tuple(
        Prop(*reader.unpack(_PROP)) for _ in range(reader.u16())
    )

    spawns: list[SpawnPoint] = []
    for _ in range(reader.u16()):
        x, y, heading = reader.unpack(_SPAWN)
        spawns.append(SpawnPoint(x=x, y=y, heading=heading / _ANGLE_UNITS * _TAU))

    return WorldTile(
        id=identifier,
        version=world_version,
        tile_x=tile_x,
        tile_y=tile_y,
        cells=cells,
        cell_size=cell_size,
        collision=collision,
        heights=heights,
        styles=styles,
        buildings=tuple(buildings),
        roads=tuple(roads),
        props=props,
        spawn_points=tuple(spawns),
    )


def _encode_heading(heading: float) -> int:
    return round_half_up((heading % _TAU) / _TAU * _ANGLE_UNITS) & 0xFFFF


def describe_tiles(tiles: Sequence[WorldTile]) -> dict[str, object]:
    """Small JSON summary used by the world metadata endpoint and the tests."""
    return {
        "count": len(tiles),
        "buildings": sum(len(tile.buildings) for tile in tiles),
        "roads": sum(len(tile.roads) for tile in tiles),
        "props": sum(len(tile.props) for tile in tiles),
        "spawnPoints": sum(len(tile.spawn_points) for tile in tiles),
    }
