# Art pipeline

The problem this solves: a tile-based game needs hundreds of sprites, and
generating each one through an AI service is neither reproducible nor
sustainable. The demo needs art *now*, and the project needs a way to keep
making art *later*.

So there are two paths, and they meet at the same atlas.

1. **The Atelier** — a procedural pixel-art pipeline with a browser editor at
   `/age/atelier`. Art is described as a recipe of parameterised operations, so
   a tile is a few lines of JSON rather than a hand-placed grid of pixels.
2. **External editors** — importers for [LDtk](https://ldtk.io) levels and
   [Aseprite](https://www.aseprite.org) sheets, so anyone who would rather draw
   in a real pixel-art tool can, without rewriting the game.

Both produce the same thing: RGBA frames with a matching normal map, packed into
an atlas, indexed by a JSON manifest the renderer reads.

## Why procedural

A recipe is not a compromise for a demo — it is what makes the art *editable*.
Change one base colour and a whole biome recolours. Change one parameter and
every cobble in the world gets rougher. That is the difference between an
authoring tool and a folder of PNGs, and it is exactly what a project with one
developer and a long roadmap needs.

It also gives animation for free: a frame index is just another parameter, so
water ripples and a campfire flickers without anyone drawing four versions of
anything.

## The canvas

`atelier/canvas.py`. Three channels, and the third is the point:

| Channel | Contents |
| --- | --- |
| `colour` | RGBA, what gets drawn |
| `depth` | 0–255, how far the surface stands out of the ground |
| `material` | An index for the autotiler, and footstep sounds later |

Nothing renders `depth` directly. `atelier/normals.py` differentiates it into a
normal map, which is what lets a torch light a wall from the side. Authoring
height is far easier than authoring normals — "how far does this stick out" is a
question about a shape — and it is the only way a *generated* sprite can get
plausible normals at all.

Every operation is deterministic in the seed it is given, so two bakes of one
recipe are byte-identical. That is what lets the client bake its own atlas at
boot and get exactly the art the server exports.

### Operations

| Operation | What it does |
| --- | --- |
| `fill` | A rectangle, or the whole canvas, in one ramp shade |
| `scatter` | Hash-seeded speckle at a density, for gravel and grass |
| `dither` | An ordered Bayer 4×4 gradient between two shades |
| `blob` | An organic mass, optionally domed, for rocks and foliage |
| `column` | A vertical form with a lit and a shadow face, for trunks and posts |
| `line` | A straight run, for planks, seams and cracks |
| `outline` | A dark rim following the alpha silhouette |
| `contact_shadow` | A soft ellipse under the sprite so it sits on the ground |
| `mirror_horizontal` | Reflects, for symmetry without drawing twice |
| `sway` | Shears above a pivot row — foliage in wind |
| `bob` | Translates vertically — a floating or bouncing frame |
| `ripple` | A sine displacement across rows — water |
| `flicker` | Erodes a silhouette above a row by frame-seeded noise — flame |

Dithering is ordered Bayer rather than error-diffused. Floyd–Steinberg produces
speckle that *crawls* when the sprite moves; pixel art needs a pattern that
stays put.

`flicker` exists because `sway` was the wrong tool for fire. Shearing a flame
produces a flame leaning left and right, which reads as a flag. Eroding its
silhouette by a frame-seeded amount reads as burning.

## Palettes and ramps

`atelier/palette.py`. Pixel art reads as pixel art largely because of colour
discipline: a small palette, and shading that moves along a *ramp* rather than
by multiplying a colour down. Multiplying gives muddy grey shadows.

A ramp is five shades — core, two shadows, two highlights — generated from one
base colour with three rules:

**Hue shifts.** Shadows drift towards blue, highlights towards yellow. This is
the single biggest difference between generated ramps that look flat and ones
that look painted.

The magnitudes are small: 0.022 turns into the shadows, 0.018 into the
highlights. This is a fixed delta rather than a rotation towards a target, and
warm hues have no room — orange sits about twenty degrees from red, so a larger
step walks skin straight through red into magenta. At 0.055 a tan of `bc8a64`
shaded to `a7463b`, which on a face reads as an injury. Cool hues tolerate far
more, but the constant has to suit the tightest case.

**Saturation rises into shadow.** A dark area in shade is *more* colourful than
a lit one, not less. Getting this backwards is what makes a generated ramp look
like a brightness slider.

**The lightness ladder is not linear.** `(-2.0, -1.05, 0.0, 0.90, 1.65)` — the
outer steps are compressed so the top never reaches white and the bottom never
reaches black. A linear ladder blew every highlight on a mid-lightness colour
out to near-white, which flattened the whole tileset into glare.

## Recipes

`atelier/recipes.py`. A recipe is JSON:

```json
{
  "key": "cobble_road",
  "width": 32,
  "height": 32,
  "frames": 1,
  "tileable": true,
  "steps": [
    { "op": "fill", "ramp": "stone", "level": 1 },
    { "op": "dither", "ramp": "stone", "from": 1, "to": 3 },
    { "op": "blob", "ramp": "stone", "level": 3, "count": 14, "radius": 3 }
  ]
}
```

Because it is JSON, a recipe round-trips through the browser editor, through the
`/api/atelier/bake` endpoint, and into a file, with no build step. `catalogue()`
publishes the whole set, which is what the editor lists.

Sizes are clamped on load. A recipe claiming 40000 px square would bake until
the worker died, and this endpoint takes input from a browser.

## Characters

`atelier/character.py` builds a character from an appearance — skin, hair style,
hair colour, cloth colour, build — across 4 facings × 3 poses × 4 frames.

A `Skeleton` derives every joint position from proportion constants, so the head,
neck, shoulders, arms and legs stay consistent across facings and poses. Drawing
order matters: neck before torso, far arm before torso, near arm after, or a
turned character's shoulder ends up in front of their chin.

Facings are handled properly rather than by mirroring one drawing: front shows
two eyes, profile shows one, offset towards the direction of travel, and the back
shows hair only.

Getting this wrong is very visible. An early version had a wide head with no
neck and legs the width of a pencil, which read as a marionette rather than a
person.

## Normal maps

`atelier/normals.py`. A Sobel gradient over the depth channel, packed the way
every 2D engine expects: `x` in red, `y` in green, `z` in blue, `[-1, 1]` mapped
to `[0, 255]`, flat surfaces at `(128, 128, 255)`.

Sobel rather than a central difference because pixel art is full of one-pixel
steps and a two-tap derivative turns every one of them into a hard crease.

Two details that are easy to get wrong and hard to notice:

- **The sign of green.** This uses the OpenGL convention, `+y` up the screen,
  because that is what the PixiJS shader samples with. Inverted lighting looks
  *almost* right, which is much harder to spot than lighting that is obviously
  broken, so a test asserts it.
- **Wrapping.** Seamless ground tiles sample across their own edges instead of
  clamping. Clamping leaves a one-pixel ridge exactly where the tile repeats,
  visible as a grid over the whole world.

Transparent pixels get a flat normal, so an unlit background does not pick up
the relief of whatever was next to it.

## Packing

`atelier/sheet.py` shelf-packs baked frames into a 1024 px page, with 2 px
padding so bilinear sampling cannot bleed a neighbour into a tile. Two pages are
exported per bake — colour and normal — at identical dimensions, so one set of UV
coordinates addresses both.

The index the renderer reads is served as `/api/atelier/atlas.json`, and it
carries more than placements: the tile-to-art bindings, which tiles animate and
at what rate, the decor keys, and the character sheet layout.

That is deliberate. An earlier version duplicated the tile-to-sprite mapping in
`recipes.py` and in the client's `tilemap.ts`, and the two drifted silently — a
new tile rendered as water with no error anywhere. Publishing the bindings from
the server makes it structurally impossible: the client cannot bind a tile the
server did not name, and a pytest guard asserts every published binding points
at art that actually exists.

## HTTP surface

| Endpoint | Returns |
| --- | --- |
| `GET /api/atelier/catalogue` | Every recipe and every ramp, for the editor |
| `GET /api/atelier/atlas.png` | The colour page |
| `GET /api/atelier/atlas-normal.png` | The normal page, same dimensions |
| `GET /api/atelier/atlas.json` | Placements, bindings, animation rates, layout |
| `POST /api/atelier/bake` | One recipe as JSON, back as a PNG |
| `GET /api/atelier/character.png` | One facing and pose strip |
| `GET /api/atelier/character-sheet.png` | Every facing and pose in one grid |
| `POST /api/atelier/import/ldtk` | An LDtk project, converted |
| `POST /api/atelier/import/aseprite` | An Aseprite JSON export, converted |

`character-sheet.png` exists because the per-strip endpoint meant twelve requests
per player appearance. The client's `CharacterCache` fetches one sheet and slices
it using the layout from the atlas index.

The import endpoints convert and return; they never write to the live world.
An import is a preview until somebody saves it.

## Importers

`atelier/importers.py`.

**LDtk.** Reads levels into tile arrays and prop placements. The interesting part
is that it needs no tileset image: paint terrain classes as an **IntGrid** and
the numbers *are* the tile ids. Entity identifiers are recipe keys, so an LDtk
entity called `lantern` places the `lantern` recipe — the naming is the whole
integration, with no mapping table to keep in sync.

An out-of-range tile id falls back to bare ground rather than failing the import.
That makes the mistake visible on the map, and bare ground regrows, so it is not
permanent.

**Aseprite.** Reads the `json-array` export into frames, tags and slices. The
hash format is rejected rather than supported: reconstructing frame order from
hash keys means parsing whatever filename template the author happened to use,
which is not a contract worth depending on.

Slices matter more than they look. The `anchor` slice is how an artist says "the
feet are here", and the renderer needs it — anchoring a tall sprite by its centre
puts the character's waist on the tile instead of their boots.

Both importers shape-check everything, because both take uploads from a browser.
A malformed file comes back as a 400 with a reason, never as a stack trace.

## PNG

`atelier/png.py` encodes and decodes PNG with nothing but `zlib` from the
standard library. Paeth filtering, maximum compression.

No Pillow. The orchestrator gives this project a limited dependency budget and
the whole encoder is a hundred lines; a compiled image library to write RGBA
rectangles is not a trade worth making. The decoder exists so tests can assert
what was produced rather than assert a byte count.

## Working on the art

```bash
python scripts/probe_atelier.py [outdir]     # every recipe as scaled contact sheets
python scripts/probe_character.py [outdir]   # character frames at 10x
```

Both write PNGs to disk without needing a server, which is how the props were
reviewed. It caught real problems: the cliff read as a radiator, the lantern as a
mirror on a stick, and the campfire did not animate at all. None of those are
visible in code review, and all three were obvious in one image.

The browser editor at `/age/atelier` is the same pipeline over HTTP: pick a
recipe, edit its steps, see the colour and normal bake side by side, and copy the
JSON back out.
