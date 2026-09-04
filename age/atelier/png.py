"""A PNG encoder and decoder in the standard library only.

Pillow is already a monorepo dependency, so this is not about avoiding a package.
It is about the HF Space image budget: the plugin is 384 MB of RAM and Pillow's
import cost buys nothing here, because the Atelier writes flat RGBA byte arrays it
generated itself and never needs a resampler, a colour manager, or a decoder for
anything but its own output.

Encoding writes 8-bit RGBA with no interlacing. Decoding accepts the subset needed
to round-trip a sheet the Atelier or Aseprite wrote: 8-bit RGB or RGBA, all five
filter types, no interlacing. That is enough to re-import an exported sheet, which
is the only decode path that exists.
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class PngError(ValueError):
    """Raised on malformed or unsupported PNG data."""


@dataclass(frozen=True, slots=True)
class Image:
    """An RGBA raster. ``pixels`` is ``width * height * 4`` bytes, row-major."""

    width: int
    height: int
    pixels: bytes

    def __post_init__(self) -> None:
        expected = self.width * self.height * 4
        if len(self.pixels) != expected:
            raise PngError(
                f"{self.width}x{self.height} needs {expected} bytes, got {len(self.pixels)}"
            )

    def pixel(self, x: int, y: int) -> tuple[int, int, int, int]:
        offset = (y * self.width + x) * 4
        return (
            self.pixels[offset],
            self.pixels[offset + 1],
            self.pixels[offset + 2],
            self.pixels[offset + 3],
        )


def _chunk(tag: bytes, payload: bytes) -> bytes:
    body = tag + payload
    return struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body))


def encode(width: int, height: int, pixels: bytes | bytearray, *, level: int = 9) -> bytes:
    """Encode RGBA bytes as a PNG.

    Uses the Paeth filter on every row. Pixel art is mostly flat colour with hard
    edges, where Paeth predicts from the left neighbour almost perfectly; measured
    against per-row filter selection on the Atelier's own output the difference was
    under a percent, and this way the encoder stays a single pass.
    """
    if width <= 0 or height <= 0:
        raise PngError("an image needs a positive width and height")
    if len(pixels) != width * height * 4:
        raise PngError("pixel buffer does not match the given dimensions")

    stride = width * 4
    raw = bytearray()
    previous = bytes(stride)

    for y in range(height):
        row = bytes(pixels[y * stride : (y + 1) * stride])
        raw.append(4)  # Paeth
        raw.extend(_filter_paeth(row, previous, stride))
        previous = row

    header = struct.pack(
        ">IIBBBBB",
        width,
        height,
        8,  # bit depth
        6,  # colour type: truecolour with alpha
        0,  # deflate
        0,  # adaptive filtering
        0,  # no interlace
    )

    return b"".join(
        (
            PNG_SIGNATURE,
            _chunk(b"IHDR", header),
            _chunk(b"IDAT", zlib.compress(bytes(raw), level)),
            _chunk(b"IEND", b""),
        )
    )


def _filter_paeth(row: bytes, previous: bytes, stride: int) -> bytearray:
    out = bytearray(stride)
    for index in range(stride):
        left = row[index - 4] if index >= 4 else 0
        up = previous[index]
        upper_left = previous[index - 4] if index >= 4 else 0
        out[index] = (row[index] - _paeth(left, up, upper_left)) & 0xFF
    return out


def _paeth(a: int, b: int, c: int) -> int:
    """The PNG Paeth predictor: whichever neighbour the gradient points at."""
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    return b if pb <= pc else c


def decode(data: bytes) -> Image:
    """Decode a non-interlaced 8-bit RGB or RGBA PNG into an :class:`Image`."""
    if not data.startswith(PNG_SIGNATURE):
        raise PngError("not a PNG file")

    offset = len(PNG_SIGNATURE)
    width = height = 0
    colour_type = 0
    compressed = bytearray()

    while offset + 8 <= len(data):
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        tag = data[offset + 4 : offset + 8]
        payload = data[offset + 8 : offset + 8 + length]
        offset += 12 + length

        if tag == b"IHDR":
            width, height, depth, colour_type, compression, filtering, interlace = (
                struct.unpack(">IIBBBBB", payload)
            )
            if depth != 8:
                raise PngError(f"only 8-bit channels are supported, got {depth}")
            if colour_type not in (2, 6):
                raise PngError(f"only RGB and RGBA are supported, got colour type {colour_type}")
            if compression != 0 or filtering != 0:
                raise PngError("unsupported compression or filter method")
            if interlace != 0:
                raise PngError("interlaced PNGs are not supported")
        elif tag == b"IDAT":
            compressed.extend(payload)
        elif tag == b"IEND":
            break

    if not width or not height:
        raise PngError("PNG has no IHDR")

    channels = 4 if colour_type == 6 else 3
    stride = width * channels
    raw = zlib.decompress(bytes(compressed))
    if len(raw) < height * (stride + 1):
        raise PngError("PNG data is truncated")

    rows: list[bytearray] = []
    previous = bytearray(stride)

    for y in range(height):
        start = y * (stride + 1)
        filter_type = raw[start]
        row = bytearray(raw[start + 1 : start + 1 + stride])
        _unfilter(filter_type, row, previous, channels)
        rows.append(row)
        previous = row

    if channels == 4:
        return Image(width, height, b"".join(bytes(row) for row in rows))

    # Opaque RGB widened to RGBA, so callers only ever handle one layout.
    pixels = bytearray(width * height * 4)
    for y, row in enumerate(rows):
        for x in range(width):
            source = x * 3
            target = (y * width + x) * 4
            pixels[target : target + 3] = row[source : source + 3]
            pixels[target + 3] = 255
    return Image(width, height, bytes(pixels))


def _unfilter(filter_type: int, row: bytearray, previous: bytearray, channels: int) -> None:
    """Reverse one row's filter in place."""
    if filter_type == 0:
        return

    stride = len(row)

    if filter_type == 1:  # Sub
        for index in range(channels, stride):
            row[index] = (row[index] + row[index - channels]) & 0xFF
    elif filter_type == 2:  # Up
        for index in range(stride):
            row[index] = (row[index] + previous[index]) & 0xFF
    elif filter_type == 3:  # Average
        for index in range(stride):
            left = row[index - channels] if index >= channels else 0
            row[index] = (row[index] + ((left + previous[index]) >> 1)) & 0xFF
    elif filter_type == 4:  # Paeth
        for index in range(stride):
            left = row[index - channels] if index >= channels else 0
            upper_left = previous[index - channels] if index >= channels else 0
            row[index] = (row[index] + _paeth(left, previous[index], upper_left)) & 0xFF
    else:
        raise PngError(f"unknown filter type {filter_type}")
