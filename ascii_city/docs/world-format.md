# World format

A district is a rectangular grid of **tiles**. A tile is 128 × 128 cells of
2 m each, so 256 m on a side, and it is the unit of transfer, caching and
storage. `infrastructure/tile_codec.py` writes the container and
`frontend/src/world/tileCodec.ts` reads it.

## Why a tile rather than a mesh

The renderer is a raycaster over a uniform grid, so what it needs per cell is a
material code, a height and a style — three bytes. Everything else in a tile
(building outlines, road centrelines, prop positions, spawn points) is
metadata for gameplay, labels and future features, not geometry the renderer
walks.

That makes the payload small enough to be uninteresting. One tile encodes to
about 55 kB and gzips to well under 10 kB, because the three cell layers are
long runs of repeated bytes. The default two-by-two district is around 40 kB
compressed — less than one photograph — which is why there is no CDN in the
architecture and no streaming-by-distance logic in the client. It fetches the
whole district in parallel at load and never fetches again.

## Coordinates

Local metric only: **x east, y north, z up**, origin at the district's
south-west corner. Latitude and longitude never reach the runtime; an OSM
import projects into this frame before anything else happens (see
[osm-import.md](osm-import.md)).

Cell `(cx, cy)` of tile `(tx, ty)` sits at world metres
`((tx × 128 + cx) × 2, (ty × 128 + cy) × 2)`. Cell indices inside a tile are
row-major: `index = cy × 128 + cx`.

A district may not exceed `MAX_TILES_PER_AXIS` tiles per axis, which is derived
from the largest position the wire can name (655.35 m, so two tiles). The
configuration loader clamps to it rather than trusting the environment, because
the failure would otherwise be silent: a player past the limit would encode to
the maximum and appear frozen against the edge. Growing the district means
widening the position field, which is a protocol version.

## Cell layers

Three parallel byte arrays of `cells²` entries each.

**Collision** — what the cell is made of:

| Code | Meaning | Solid |
| --- | --- | --- |
| 0 | free | no |
| 1 | building | yes |
| 2 | water | yes |
| 3 | blocked | yes |
| 4 | road | no |
| 5 | sidewalk | no |
| 6 | interactive | no |

Solidity is a property of the code, not of the tile, so the same table governs
the server's collision test, the client's prediction and the raycaster. There
is exactly one definition of "can I walk here" and both languages read it from
their constants module.

**Heights** — metres as one unsigned byte, so 255 m is a hard ceiling. Zero on
walkable cells. The raycaster uses this directly as the wall height, which is
what lets a tower behind a low wall still cut its silhouette into the sky.

**Styles** — three fields packed into one byte:

```
bit 7 6 | 5 4 3 | 2 1 0
   window   facade  category
```

Category is the building class (0 house, 1 shop, 2 apartment, 3 office,
4 skyscraper, 5 warehouse, 6 station, 7 other) and drives the facade and neon
palettes. Facade and window are decorative variation, hashed into window
patterns and structural banding so that two adjacent towers of the same class
do not look identical.

## Container layout

Little-endian throughout, no padding.

### Header — 26 bytes

| Type | Field |
| --- | --- |
| `char[4]` | magic, `ACT1` |
| `u16` | format version, currently 1 |
| `u16` | flags, reserved, 0 |
| `i32` | tile x |
| `i32` | tile y |
| `u16` | cells per edge |
| `f32` | cell size in metres |
| `u32` | world version |

Then `u16` id byte length and the tile id as UTF-8.

### Cell layers

`cells²` bytes of collision, then the same of heights, then the same of styles.
For a 128-cell tile that is three blocks of 16384 bytes.

### Buildings

`u16` count, then per building:

| Type | Field |
| --- | --- |
| `u16` | id, unique within the tile |
| `u8` | vertex count |
| `i16 × 2n` | footprint, alternating x and y in tile-local cells |
| `u8` | height in metres |
| `u8` | minimum height in metres, for future overhangs |
| `u8` | levels |
| `u8` | roof type: 0 flat, 1 gabled, 2 antenna |
| `u8` | category |
| `u8` | facade style |
| `u8` | window style |
| `u8` | colour index |
| `u8` | flags: bit 0 walkable, bit 1 has an interior |

Footprint vertices are signed because a building straddling a tile boundary is
stored in every tile it touches, with coordinates that may fall outside
`0 … 127`. Ownership for counting purposes belongs to the tile containing the
centroid, so a shared building is not double-counted in the world summary.

### Roads

`u16` count, then per road:

| Type | Field |
| --- | --- |
| `u16` | id |
| `u8` | type: 0 street, 1 avenue, 2 path, 3 plaza |
| `u8` | width in decimetres |
| `u8` | surface style |
| `u8` | centreline point count |
| `i16 × 2n` | centreline, alternating x and y in tile-local cells |
| `u8` | name byte length |
| bytes | name, UTF-8, may be empty |

### Props

`u16` count, then 7 bytes each: `u16` id, `u16` x, `u16` y, `u8` kind.

### Spawn points

`u16` count, then 6 bytes each: `u16` x, `u16` y, `u16` heading as a fraction
of a turn.

Spawn points sit on open road cells facing along the road, and the room hands
them out round-robin so two players joining together do not overlap.

## Delivery

`GET /ascii-city/api/world` returns the district descriptor as JSON: id,
version, seed, source, tile counts, cell size and the physics and chat numbers
the client needs before it can simulate anything.

`GET /ascii-city/api/world/tiles/{x}/{y}` returns one encoded tile. Tiles are
immutable within a world version, so the response carries an ETag and
`cache-control: public, max-age=31536000, immutable`, and the gzip variant is
compressed once at startup rather than per request. `x-tile-bytes` reports the
uncompressed size so the client can size a buffer before inflating.

The client fetches tiles inside a Web Worker, decodes them there and transfers
the layer buffers back, so a 160 kB district never blocks the game loop.

## Storage

MongoDB holds encoded tiles keyed by world id, version and tile coordinates,
plus the world descriptor. It is a cache, not a source of truth: the district
is a pure function of its seed, so an empty or unreachable database costs a few
seconds of regeneration at startup and nothing else. `repositories/memory.py`
is the fallback and the test double.

## Adding a format version

Bump `FORMAT_VERSION`, teach `decode_tile` the new shape, and mirror it in the
TypeScript decoder. The decoder rejects an unknown version outright rather than
guessing, and world descriptors carry the version, so old cached tiles are
regenerated instead of misread.
