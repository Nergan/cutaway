# Importing a real city

The procedural generator is not the only world source. `infrastructure/osm.py`
implements the same `WorldGeneratorPort` from OpenStreetMap geometry, and
everything downstream — the tile codec, the collision grid, the room, the
renderer — cannot tell the two apart, because both hand back a `WorldTile`.

Try it:

```bash
python -m ascii_city.tools.import_osm ascii_city/docs/samples/osm-district.geojson
```

That prints a top-down map of the imported district and the height each
building resolved to, next to the tag it came from.

## The pipeline

```
.osm.pbf regional extract
    │  osmium extract --bbox / --polygon
    ▼
district-sized .osm.pbf
    │  osmium export -f geojson
    ▼
GeoJSON FeatureCollection with OSM tags   ◀── where this project starts
    │  OsmDistrictImporter
    ├─ project WGS84 → local metres
    ├─ classify: building tag → category, highway tag → road type
    ├─ resolve heights by the ladder below
    ├─ rasterise: polygons scanline-filled, roads stroked
    ├─ derive sidewalks and spawn points
    ▼
Canvas → slice_into_tiles → WorldTile[]
    │  encode_tile
    ▼
binary tiles, cached in MongoDB, served immutable
```

The `.osm.pbf` half deliberately lives outside this project. Parsing PBF means
pulling in `osmium` or `pyosmium` — a compiled dependency — to do a conversion
that runs once per district and that every OSM toolchain already does well.
Starting from GeoJSON means `osmium export`, an Overpass query, or a QGIS save
all work as input.

## Why not a 3D tileset

Cesium OSM Buildings is a global 3D layer covering more than 350 million
buildings, and it is available as a 3D Tileset. It is the wrong shape for this
renderer twice over: it is a mesh format, and the renderer wants a height grid;
and it is global, while the client needs one district. Loading a global model
into a browser is explicitly out of scope. If a mesh source were ever needed,
the conversion would happen offline and land in the same tile format.

## Coordinates

The runtime never sees latitude or longitude. `GeoOrigin.project` converts to
local metres — x east, y north — with an equirectangular projection around the
origin's latitude:

```
x = radians(lon − origin.lon) × R × cos(radians(origin.lat))
y = radians(lat − origin.lat) × R
```

Over a district a few hundred metres across the error against a proper
projection is well under a centimetre, which is a twentieth of a cell. The
cosine term matters though: without it, a district at 60° north comes out
stretched by a factor of two east to west.

The origin defaults to the south-west corner of the feature collection's
bounds, so an extract lands with its corner at world zero.

## The height ladder

OSM tags height inconsistently, so the importer tries in order and documents
which rung it landed on:

1. **`height`** — the only tag that states the answer. Parsed in metres unless
   it says otherwise; `40 ft`, `40'` and `12'6"` are all understood, because
   all three occur in the database.
2. **`building:levels` × 3 m**, plus `roof:height` when present. Levels count
   storeys, which stop at the eaves, so a separately tagged roof is added.
3. **A per-category default** from `CATEGORY_DEFAULT_HEIGHT_M`: 8 m for a
   house, 18 for an apartment block, 24 for an office, 80 for a skyscraper.
   A building with no height tags still has to stand somewhere sensible.

`min_height` is honoured and clamped below the roof, and heights are clamped to
255 m because a tile stores height in one byte. A tag that parses to nonsense
is treated as absent rather than raising — one malformed value in a city-sized
extract must not stop the import.

Level counts are kept even when the height came from a tag, so the renderer can
band a facade by storey.

## Classification

| Tag | Becomes |
| --- | --- |
| `building=house`, `detached`, `bungalow`, `terrace` … | small house |
| `building=apartments`, `residential`, `dormitory`, `hotel` | apartment block |
| `building=retail`, `commercial`, `shop`, `supermarket` | shop |
| `building=office`, `government`, `civic`, `university` | office |
| `building=skyscraper`, `tower` | skyscraper |
| `building=warehouse`, `industrial`, `hangar` | warehouse |
| `building=train_station`, `transportation` | station |
| anything else | other |

Anything taller than 60 m is promoted to skyscraper regardless of its tag,
because that is what it reads as from street level.

| Tag | Becomes | Default width |
| --- | --- | --- |
| `highway=motorway`, `trunk`, `primary`, `secondary` | avenue | 14 m |
| `highway=tertiary`, `residential`, `service`, `unclassified` | street | 8 m |
| `highway=footway`, `path`, `steps`, `cycleway` | path | 3 m |
| `highway=pedestrian` | plaza | 12 m |

Width comes from the `width` tag if present, otherwise `lanes` × 3.5 m,
otherwise the default above.

## Rasterisation

Polygons are filled with an even-odd scanline pass over cell centres, which
keeps a shared wall between two terraced houses one cell thick instead of two,
and leaves the notch of an L-shaped building empty. Roads are stroked by
sampling along each segment at half-cell steps — a road is a handful of cells
wide, so polygon offsetting would resolve detail the grid throws away.

Roads are painted before buildings, so a footprint overlapping a mis-tagged
verge wins. Sidewalks are derived afterwards: one cell of pavement wherever
open ground meets a road. Spawn points are placed on open tarmac near the
middle of each road, never within three cells of the district boundary.

Footprints are decimated to at most 64 vertices. A traced building can carry
hundreds of nodes, the tile format counts vertices in one byte, and a two-metre
grid cannot show that detail anyway.

Geometry outside the district is clipped by the canvas rather than resizing the
world, so one extract can be rendered at whatever tile count a deployment
allows.

## Wiring it into the runtime

`presentation/container.py` constructs `DistrictGenerator()` directly. Swapping
in an import is a two-line change there:

```python
payload = json.loads(Path(settings.world_source).read_text(encoding="utf-8"))
generator = OsmDistrictImporter(payload)
```

Nothing else moves. `WorldService` caches whatever the port produces, the
descriptor records `source: "osm"`, and the client reads that field without
caring what it says.

What is deliberately still missing before this is a production path:

- **A district larger than 512 m.** The wire encodes a position as unsigned
  centimetres, so the world cannot exceed 655.35 m per axis today. A real
  neighbourhood wants more, which means widening the position field — a
  protocol version, not a configuration change. See
  [protocol.md](protocol.md).
- **Water and green space.** `natural=water`, `waterway`, `leisure=park` and
  `landuse` are not read yet, though the cell codes for them exist.
- **Relations.** Multipolygon buildings with courtyards are imported as their
  largest outer ring; holes are dropped.
- **Named streets on screen.** Road names are imported and stored, and nothing
  displays them.

## Licensing and attribution

OpenStreetMap data is published under the **Open Database License 1.0**. Using
it here has consequences that are not optional:

- Any district derived from OSM must credit **© OpenStreetMap contributors**
  visibly wherever the district is shown. `OsmDistrictImporter.attribution`
  carries the string, and it should be surfaced in the UI, not just in a file.
- ODbL is share-alike on the *database*. Publishing a derived tile set means
  publishing it under ODbL too. The project's own MIT licence covers the code;
  it does not and cannot relicense the data.
- Do not point a production deployment at the public OSM tile servers or the
  public Overpass instances. They are donated infrastructure with an explicit
  usage policy. Use a regional extract, processed once, served from here.
- **Cesium OSM Buildings** is OSM-derived but distributed through Cesium ion
  under its own terms, requiring both OSM attribution and Cesium attribution.
  Anything from it needs those terms checked before it ships.
- Overture Maps, Microsoft building footprints, CityGML sets and LiDAR each
  carry their own licence. None of them are wired in, and none should be
  without recording the licence next to the data.

The sample in `docs/samples/osm-district.geojson` is invented, not extracted,
precisely so the repository carries no ODbL data and the question does not
arise for the tests.
