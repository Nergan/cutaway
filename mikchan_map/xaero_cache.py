"""Read Xaero's World Map .xwmc caches into 512×512 images.

The layout matches the cache written by Xaero's World Map (major 1–3, minor
13–25): a zip with one ``cache.xaero``. Level 0 (``cache_1``) is 512 blocks
per file, one pixel per block. Each next ``cache/<level>`` doubles the blocks
a file covers. Unexplored pixels stay transparent.
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass

_GL_RGBA = 32856
_CHUNK = 64
_REGION = 512


class CacheFormatError(ValueError):
    pass


@dataclass(frozen=True)
class MapImage:
    rgba: bytes
    major: int
    minor: int
    width: int = _REGION
    height: int = _REGION

    def opaque_pixels(self) -> int:
        count = 0
        data = self.rgba
        for index in range(3, len(data), 4):
            if data[index]:
                count += 1
        return count


class _Reader:
    def __init__(self, data: bytes) -> None:
        self._data = data
        self._at = 0

    def u8(self) -> int:
        if self._at >= len(self._data):
            raise CacheFormatError("unexpected end")
        value = self._data[self._at]
        self._at += 1
        return value

    def i32(self) -> int:
        if self._at + 4 > len(self._data):
            raise CacheFormatError("unexpected end")
        value = int.from_bytes(self._data[self._at : self._at + 4], "big", signed=True)
        self._at += 4
        return value

    def skip(self, count: int) -> None:
        if count < 0 or self._at + count > len(self._data):
            raise CacheFormatError("unexpected end")
        self._at += count

    def take(self, count: int) -> bytes:
        if count < 0 or self._at + count > len(self._data):
            raise CacheFormatError("unexpected end")
        chunk = self._data[self._at : self._at + count]
        self._at += count
        return chunk

    def utf(self) -> None:
        length = int.from_bytes(self.take(2), "big")
        self.skip(length)

    def peek(self) -> int:
        if self._at >= len(self._data):
            raise CacheFormatError("unexpected end")
        return self._data[self._at]


def cache_bytes(blob: bytes) -> bytes:
    try:
        with zipfile.ZipFile(io.BytesIO(blob)) as archive:
            name = next(info.filename for info in archive.infolist() if info.filename.endswith("cache.xaero"))
            return archive.read(name)
    except (zipfile.BadZipFile, StopIteration, KeyError) as exc:
        raise CacheFormatError("not an xwmc cache") from exc


def _skip_palette(reader: _Reader, minor: int) -> None:
    if minor < 19:
        return
    size = reader.i32()
    for _ in range(size):
        kind = reader.u8()
        if kind == 0xFF:
            continue
        if kind == 0:
            reader.utf()
        else:
            reader.i32()
        if minor <= 20:
            reader.skip(2)


def _paste(canvas: bytearray, x: int, y: int, raw: bytes, *, rgb_last: bool) -> None:
    for row in range(_CHUNK):
        src = row * _CHUNK * 4
        dst = ((y + row) * _REGION + x) * 4
        for col in range(_CHUNK):
            pixel = raw[src + col * 4 : src + col * 4 + 4]
            if rgb_last:
                red, green, blue, alpha = pixel
            else:
                alpha, red, green, blue = pixel
            if alpha == 0:
                continue
            canvas[dst + col * 4 : dst + col * 4 + 4] = bytes((red, green, blue, 255))


def parse_cache(data: bytes, *, leaf: bool, level: int) -> MapImage:
    reader = _Reader(data)
    version = reader.i32() & 0xFFFFFFFF
    major, minor = version >> 16, version & 0xFFFF
    if major > 3 or not 13 <= minor <= 25:
        raise CacheFormatError(f"unsupported cache {major}.{minor}")
    if leaf:
        for gate in (9, 11, 18, 23, 24):
            if minor >= gate:
                reader.skip(4)
    coords: list[tuple[int, int]] = []
    while True:
        mark = reader.u8()
        if mark == 0xFF:
            break
        coords.append((mark >> 4, mark & 0xF))
        reader.i32()
    _skip_palette(reader, minor)
    canvas = bytearray(_REGION * _REGION * 4)
    rgb_last = major >= 2
    for _cx, _cy in coords:
        coord = reader.u8()
        chunk_x, chunk_y = coord >> 4, coord & 0xF
        if major >= 2:
            raw = reader.take(16384)
            fmt = _GL_RGBA
        else:
            compressed = reader.u8() == 1 if minor > 1 else True
            fmt = reader.i32()
            length = reader.i32()
            raw = reader.take(length)
            if not (leaf and length == 16384 and compressed):
                raw = b""
        if minor >= 14:
            reader.u8()
        elif minor > 2:
            light_length = reader.i32()
            if light_length > 0:
                reader.skip(light_length)
        if minor >= 13:
            heights = 586 if major == 0 else 1024
            reader.skip(heights * 8)
            if minor >= 17:
                reader.skip(heights * 8)
            if minor >= 19:
                stored = reader.i32()
                if stored > 0:
                    for _ in range(stored):
                        value = reader.i32()
                        if value != -1:
                            reader.skip(2)
                    if minor == 19:
                        reader.skip(1024 * 8)
                    elif reader.u8() == 1:
                        reader.skip(1024 * 8)
            if minor == 16:
                reader.skip(64 * 8)
        if level > 0 and minor >= 15:
            reader.skip(16)
        if fmt == _GL_RGBA and len(raw) == 16384:
            _paste(canvas, chunk_x * _CHUNK, chunk_y * _CHUNK, raw, rgb_last=rgb_last)
    if reader.peek() != 0xFF:
        raise CacheFormatError("missing end marker")
    return MapImage(bytes(canvas), major, minor)


def parse_xwmc(blob: bytes, *, leaf: bool, level: int) -> MapImage:
    return parse_cache(cache_bytes(blob), leaf=leaf, level=level)
