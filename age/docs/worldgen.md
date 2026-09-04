# World generation

Terrain is never transmitted. The server sends a 64-bit seed in `WELCOME`, and
the browser generates the same tiles the server did. Only player edits travel,
as `TILES` deltas.

That saves the whole terrain bandwidth budget, and it costs one hard
requirement: `age/infrastructure/generator.py` and
`age/frontend/src/world/generator.ts` must produce **bit-identical** output.
`tests/test_age_client_parity.py` and `frontend/src/world/parity.test.ts` hold
that line together.

## Determinism across two languages

Python floats and JavaScript numbers are both IEEE 754 doubles, so arithmetic
agrees exactly — as long as you stay inside the operations the standard pins
down.

**Used:** `+`, `-`, `*`, `/`, `math.floor`, and comparisons. Every one of these
is exactly specified for doubles and gives identical results in both languages.

**Avoided:** `sin`, `cos`, `exp`, `pow`, `sqrt` in field code. These come from
libm and are not guaranteed identical across platforms, let alone across
languages. Gradient constants that would otherwise be `cos(22.5°)` are written
as decimal literals — `0.9238795325112867` — because a decimal literal parses
to the same double in both languages while a trig call might not.

**Rounding:** never the built-in. Python's `round` is half-to-even, JavaScript's
`Math.round` is half-up-toward-positive-infinity. Both sides use an explicit
`floor(x + 0.5)` form.

**Integer hashing:** masked to 64 bits. JavaScript numbers cannot hold 64-bit
integers, so the TypeScript mirror uses `BigInt` for the hash chain and converts
to a double only at the end, through the top 53 bits — exactly the mantissa
width, so `unit_float` produces the same float from the same hash.

## Hashing

The naive `world_seed * x * y` derivation is symmetric about the axes: mirrored
coordinates generate identical terrain, and lane −1 becomes a mirror of lane 1.
The Accordion Spec calls this out, and the fix is a real avalanche mixer.

`domain/hashing.py` uses SplitMix64's finaliser: stateless, one
multiply-xorshift chain, cheap enough to call per tile. `combine` mixes each
value *before* folding, so `combine(1, 0)` and `combine(0, 1)` diverge, and
negative inputs are two's-complement masked so lane −1 and lane 1 are unrelated.

Identifiers such as edge ids are hashed with FNV-1a rather than Python's `hash`,
which is salted per process and would generate a different world on every
restart.

### Chunk seeds

```python
chunk_seed(world_seed, edge_id, segment_index, lane_offset, tier_min)
hub_chunk_seed(world_seed, hub_id, chunk_x, chunk_y)
```

`tier_min` — the lowest tier at which the chunk exists — is part of the corridor
seed, and the *current* tier deliberately is not. A lane that only appears at
tier 1 gets terrain of its own, and an existing chunk never regenerates when the
world expands. That distinction is the whole point of a topological accordion.

There is a matching pair of key functions that exclude the world seed, so
persistence rows stay addressable across a reseed.

## Noise

Gradient noise with a quintic fade and domain rotation, in
`infrastructure/noise.py`.

Sixteen gradients, selected by masking rather than modulo. The quintic fade
`6t⁵ − 15t⁴ + 10t³` has zero first and second derivatives at both ends, so
adjacent lattice cells join without the visible creasing a cubic fade leaves.

The input domain is rotated by about 31.7° before sampling. An axis-aligned
lattice leaves visible horizontal and vertical streaks in the output; rotating
by an angle with no rational relationship to the grid removes them, and costs
one multiply-add rather than a second noise call.

Fractal sums (fBm and ridged) stack octaves at doubling frequency and halving
amplitude. Gradients are memoised, which matters because a chunk samples the
same lattice corners repeatedly.

## The four layers

### Layer 1 — macro path

A spine down the corridor, curved by a low-frequency wander so it does not read
as a ruler line. It is a function of the along-coordinate alone, so it is
continuous by construction: two adjacent chunks computing the same boundary tile
get the same road position without either knowing the other exists.

The road is what makes the world navigable — it tells a player which way the
next hub is. So it gets a verge: a clear strip either side where scatter is
suppressed. Without it, trees grow hard against the paving and the spine stops
being legible from any distance.

### Layer 2 — biome fields

Three independent fractal fields, sampled in **global** coordinates:

| Field | Frequency (cycles/tile) | Wavelength |
| --- | --- | --- |
| Elevation | 0.006 | ~167 tiles |
| Temperature | 0.0035 | ~285 tiles |
| Moisture | 0.009 | ~111 tiles |

Elevation varies slowest, so mountains are regional. Moisture varies fastest, so
a forest can end without the altitude changing. These three numbers decide
whether the world reads as landscape or as noise, and they are the first thing
to tune.

The triple classifies into one of eight biomes — meadow, forest, deep forest,
wetland, heath, desert, highland, ashland — each with a profile that sets the
ground carpet and the scatter weights.

Rivers are a threshold on a ridged field. A ridged field has sharp valleys where
a smooth one has zero crossings, which is what makes a river read as a river.

### Layer 3 — tile layout

The ground carpet comes from the biome profile; scatter is threshold-based
selection against per-tile hashes, weighted by the profile.

The TDD names Wave Function Collapse as the ideal here and threshold selection
as the sanctioned fallback. This takes the fallback and then adds a coherence
pass: a second sweep that reads a one-tile apron beyond the chunk's own edges
and adjusts tiles whose neighbours make them implausible — a lone tree in open
meadow becomes a bush, a gap in a treeline closes.

That buys most of what WFC buys, at a fraction of the cost, and — crucially —
without WFC's global constraint propagation, which is hostile to generating one
chunk at a time in an unpredictable order.

### Layer 4 — points of interest

Camps, ruins and resource nodes, placed deterministically from the chunk seed
and spaced by rule so two camps never land adjacent. The generator also emits
decor placements as a side effect, which the client uses for lantern and
campfire props and their light sources.

## Seam stitching

Structural, not corrective. Every field is a function of global coordinates, so
two adjacent chunks computing the same boundary tile agree without
communicating. There is no blending pass and no post-hoc edge fix-up, because
there is no seam to fix.

The one place this needs care is the coarse-grid optimisation below.

## Coarse sampling

The climate fields have wavelengths of 110 to 285 tiles. Evaluating them per
tile computes very nearly the same value 16 times over.

So they are sampled on a grid — every 4 tiles for climate, every 2 for rivers —
and interpolated bilinearly between samples. Visually identical; more than an
order of magnitude cheaper. This is what makes generation affordable in pure
Python at all: **712 ms per chunk before, ~24 ms after.**

Two constraints:

1. **The stride must divide `CHUNK_TILES`.** Chunk origins are multiples of 32,
   so any power of two up to 32 works.
2. **The grid must be aligned in global coordinates, not chunk-local ones.**
   Otherwise two neighbouring chunks interpolate between different sample
   points and the seam reappears — the exact thing layer-2 global sampling
   exists to prevent.

Rivers get the finer stride because they are a *threshold* on a field whose top
octave has a 31-tile wavelength, and a threshold is far more sensitive to
interpolation error than a classification is. A classification that is one
sample off picks the same biome; a threshold that is one sample off leaves a
gap in a river.

## Hub zones

Hubs are 8×8 chunks — 256 tiles a side. They are pushed into a distant region of
the same global coordinate frame, keyed by hub id, so no hub generates the same
terrain as another or as the corridor. The offsets start at `(hub_id + 1) × 4096`
rather than `hub_id × 4096`, because hub 0 at offset 0 would coincide with
corridor segment 0.

A hub has a paved plaza at its centre with a street grid, walls at its rim, and
a band of wilderness between. Road generation is suppressed in the rim
wilderness — the corridor road would otherwise appear to run straight through
the hub wall.

Generation is lazy, so the nominal 8×8 costs nothing until somebody walks there.

## The MVP world

Two hubs, **Emberhold** and **Rookmarch**, joined by one edge of eight corridor
segments. Tier 0 activates the centre lane; tier 1 adds the two flanking lanes.

The client derives this layout from `edgeId` and `segments` in the world
descriptor rather than hardcoding it, mirroring `build_default_world`. An early
version did hardcode it, and the two drifted immediately.

## Caching and cost

The generator caches recent chunks with a bounded map. Generation is pure, so
the cache is a pure performance concern and can be dropped at any moment
without changing a tile.

On the server, chunk building happens between ticks: one chunk on alternate
ticks, only while the simulation is inside its budget, and allowed to overrun
because 24 ms does not fit in a 33 ms tick's leftover slack. A `PREPARING` chunk
has 2 seconds before it may go `ACTIVE`, so an expanding lane has its terrain
ready by the time it becomes visible. See
[Architecture](architecture.md#where-the-budget-goes) for the trade.

## Verifying parity

```bash
python -m age.tools.make_fixtures        # regenerate frozen payloads
python -m pytest tests/test_age_client_parity.py
cd age && npm test -- parity
```

`make_fixtures.py` writes `frontend/src/__fixtures__/parity.json`: encoded wire
payloads and full generated chunks from the Python side. The vitest suite
decodes and regenerates them and compares tile for tile. A pytest check
regenerates the file and fails if it differs from what is committed, so a
fixture cannot go stale without somebody noticing.
