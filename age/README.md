# Age

[Читать на русском (README.ru.md)](README.ru.md)

A browser MMO slice. Two towns joined by a road; the road gets wider when more
people walk it, and narrows again when they leave. Everyone who opens the page
stands in the same world, sees the same terrain, and can fight, build, harvest
and talk in it.

The world is procedurally generated and **never transmitted**. The server sends
a 64-bit seed, and the browser generates exactly the tiles the server did — the
same noise, the same hashes, the same bits. Only what players change travels
over the wire.

The art is procedurally generated too, and there is an editor for it at
`/age/atelier`.

## Running it

Registered in `orchestrator.toml` and served by the hub at `/age`. Nothing
beyond the repository's own setup:

```bash
./build.sh          # installs Python deps and runs the client build
python main.py      # the hub, with Age on /age
```

Standalone, without the hub:

```bash
cd age && npm install && npm run build
cd .. && python -m age.main --port 8140
# then open http://127.0.0.1:8140/age/
```

For client work, `npm run dev` starts Vite with a proxy to a server on port
8140, so terrain and the socket come from the real backend while the UI
hot-reloads.

## Controls

| Input | Action |
| --- | --- |
| `W` `A` `S` `D` or arrows | Walk |
| `Shift` | Run |
| Mouse | Aim — your character faces the cursor |
| `1` … `5` | Abilities, aimed at the cursor |
| `F` | Harvest the tile under the cursor |
| `B` | Build a wooden wall on the tile under the cursor |
| `C` | Character sheet — level, derived stats, equipment slots |
| `I` | Pack — the inventory grid |
| `Enter` | Chat; `Enter` again sends, `Escape` cancels |
| `Tab` | Diagnostics — latency, tick, topology, chunk counts |
| `+` `-` | Zoom |

A base class has three abilities and a composed one has five, which is why the
bar goes to `5`.

Chat has two ranges: **global** reaches everyone, **local** reaches 24 tiles.

Harvesting and building work within 4 tiles. Fell a tree and you get wood; a
cleared tile climbs back up the regrowth ladder — bare ground, grass, sapling,
bush, tree — one stage a minute, unless somebody keeps cutting it.

## Equipment

Twenty-five items in a hand-authored catalogue: eight materials, two
consumables, and fifteen pieces of equipment across seven slots — head, chest,
hands, legs, feet, weapon and trinket. Materials come from the ground, the rest
from things that die.

The pack holds 24 stacks and nothing more, which is what makes a slot a
decision. Click a stack to wear it or eat it, drag it onto a slot on the sheet,
right-click to throw it away.

Wearing something is not cosmetic. A helm raises the pool the health bar is
drawn from, a blade raises the number that reaches `apply_damage`, and boots
raise the metres per second the movement integrator uses — and the better pieces
trade one against another. A stone-plated vest is thirty-two health and a third
of a tile per second slower. All of it is persisted, so a character logs back in
wearing what it took off.

## The accordion

This is the idea the project is built around, and it is topological rather than
geometric. The world does not stretch; it **gains and loses lanes**.

The corridor between the two towns is eight segments long. At tier 0 only the
centre lane exists. When population crosses ten players the world expands to
tier 1 and two flanking lanes come into being — new terrain, new resource nodes,
new NPCs, three times the room. When it falls below five, the flanks retire and
anybody standing on one is walked back to a hub first.

Two thresholds rather than one, because a single threshold at eight players
would flip the world back and forth every time somebody logged in. And a
fifteen-minute cooldown between changes, so the world cannot churn.

Every chunk moves through a state machine — `DORMANT → PREPARING → ACTIVE →
RETIRING → DORMANT` — and illegal transitions raise rather than being quietly
corrected. A chunk cannot go active before its terrain exists, and cannot retire
while a player stands in it.

Each topology change bumps `topology_version`, and every client frame carries
it. Input aimed at a world that no longer exists is rejected instead of being
applied to the wrong lane.

The demo can force a tier change from the diagnostics panel, because the
production cadence is fifteen minutes and nobody is going to sit through that.

## Classes

Fourteen classes from four halves. Each of Warrior, Healer, Mage and Rogue
contributes an ability, and each pair contributes a signature ability on top —
so 4 + 4 + 6 = 14 kits come out of 14 ability definitions instead of the
forty-plus that writing each kit by hand would need.

| | Warrior | Healer | Mage | Rogue |
| --- | --- | --- | --- | --- |
| **Warrior** | Warrior → Warmaster | Paladin | Spellblade | Mercenary |
| **Healer** | | Healer → Archcleric | Shaman | Pathfinder |
| **Mage** | | | Mage → Archmage | Trickster |
| **Rogue** | | | | Rogue → Shadowmaster |

Doubling a half reaches a pure specialisation; mixing gives a hybrid that holds
both halves plus its own signature.

## How it works

- **Server-authoritative.** Clients send intent — "up and left, running, facing
  here, and I think I ended up at this position". The server integrates the
  movement itself and rubber-bands anything more than 1.5 tiles out. Lying about
  your position gains nothing, and lying about your frame time gets clamped.
- **Predicted locally.** The client runs the same movement code, so walking is
  instant. On each snapshot it rewinds to the acknowledged position, replays
  unacknowledged input, and blends away the residual error over a few frames.
- **Deterministic terrain.** Four layers — a road spine, three climate fields
  classifying into eight biomes, threshold scatter with a coherence pass, then
  points of interest. Every field is a function of global coordinates, so
  adjacent chunks agree on their shared boundary without communicating. There
  is no seam-stitching pass because there is no seam.
- **Delta snapshots.** 30 Hz simulation, 15 Hz snapshots. Per entity: a 4-byte
  id, a 1-byte field mask, and only the fields that changed. A walking player
  costs 13 bytes.
- **Normal-mapped lighting.** Every sprite is baked with a height channel, which
  is differentiated into a normal map. The renderer draws a colour pass and a
  normal pass and composites them, so a lantern at dusk lights the side of a
  wall rather than tinting a flat rectangle.

The layering is hexagonal: `domain` holds the rules, `application` orchestrates
them, `infrastructure` speaks bytes and databases, `presentation` speaks HTTP
and WebSocket. Everything the simulation needs from outside is a Protocol in
`domain/ports.py`.

That matters here specifically. The specification asks for a Go world server;
the monorepo starts Python workers. So this runs a Python core at 30 Hz and says
so — and because the core sits behind ports and the wire format is
language-agnostic and rate-agnostic, a Go or Rust core can be introduced later
without touching the protocol, the client, or the rules.

## The Atelier

Making hundreds of sprites through an AI service is neither reproducible nor
sustainable, so the art is **procedural**: a tile is a recipe of parameterised
operations rather than a hand-placed grid of pixels.

That is not a compromise for a demo. Change one base colour and a whole biome
recolours; change one parameter and every cobble in the world gets rougher. A
frame index is just another parameter, so water ripples and a campfire flickers
without anyone drawing four versions of anything.

Colour discipline is where the pixel-art look actually comes from. Shading moves
along a generated five-step ramp with hue shifts — shadows towards blue,
highlights towards yellow — and saturation *rising* into shadow, because a dark
area in shade is more colourful than a lit one, not less. Getting that backwards
is what makes generated art look like a brightness slider.

The browser editor at **`/age/atelier`** lists every recipe, edits its steps, and
shows the colour bake and the normal bake side by side.

For anyone who would rather draw in a real pixel-art tool, there are importers
for **LDtk** levels and **Aseprite** sheets. The LDtk path needs no tileset
image at all: paint terrain classes as an IntGrid and the numbers *are* the tile
ids, and an LDtk entity named `lantern` places the `lantern` recipe.

See [Art pipeline](docs/art-pipeline.md).

## Storage

MongoDB when it is reachable, skipped when it is not. It keeps characters —
class, appearance, level, inventory, last position — and the terrain overlay per
chunk, flushed on an interval rather than per edit.

Losing the database costs saved characters and player edits, nothing else: the
world is a pure function of its seed. Running with `AGE_USE_MONGO=0` is a
legitimate configuration and a visitor cannot tell.

No Cloudinary. Game art is public and cached by jsDelivr like the rest of the
monorepo's assets, so there is nothing to mask; that adapter stays behind a port
for user-generated content later.

## Configuration

Every variable is declared in `orchestrator.toml`'s allowlist. Defaults run with
no configuration at all.

| Variable | Default | Effect |
| --- | --- | --- |
| `AGE_WORLD_SEED` | `0x0A6E5EED` | The world. Fixed by default so two people describing the demo describe the same place |
| `AGE_CORRIDOR_SEGMENTS` | 8 | Corridor length, clamped 2–16 |
| `AGE_MAX_CLIENTS` | 50 | Room size |
| `AGE_USE_MONGO` | on | Persistence |
| `AGE_TIER_COOLDOWN_SECONDS` | 900 | Lower it to watch the accordion in a sitting |
| `AGE_ALLOW_DEV_CONTROLS` | on | Lets the diagnostics panel force a tier |
| `AGE_WORLD_ID` | `demo` | Database namespace |

## Documentation

- [Architecture](docs/architecture.md) — the layers, the tick loop, where the
  budget goes, and which seams a rewrite is meant to use.
- [Protocol](docs/protocol.md) — every byte on the WebSocket.
- [World generation](docs/worldgen.md) — the four layers, and what it takes to
  make Python and JavaScript agree bit for bit.
- [Art pipeline](docs/art-pipeline.md) — recipes, ramps, normal maps, importers.
- [Roadmap](docs/roadmap.md) — what is deliberately missing and what each piece
  would take.

## Tests

```bash
python -m pytest tests -k age    # 349 server, atelier and parity tests
cd age && npm test               # 126 client tests
```

The parity suites are the load-bearing ones. `age/tools/make_fixtures.py`
freezes payloads and whole generated chunks produced by the Python side into
`frontend/src/__fixtures__/parity.json`; the client suite decodes and
regenerates them and compares tile for tile, and a pytest check regenerates the
file to prove it is current. A constants parity test reads
`frontend/src/domain/constants.ts` and compares every shared number with
`domain/constants.py`.

Changing a constant or the protocol on one side only fails the build instead of
desynchronising a player mid-session. This is not theoretical: the suites caught
two real bugs while being written, both in hub tile lookup, and both of which
made the default spawn town impassable.

To look at things without a browser:

```bash
python scripts/probe_age.py         # boot the world headless, report loop health
python scripts/probe_atelier.py     # bake every recipe to contact sheets
python scripts/probe_character.py   # character frames at 10x
```

`probe_age.py` drives a real event loop at the real tick rate, so its numbers
mean something — it is how the 712 ms chunk generation was found and the 24 ms
replacement was confirmed. The art probes are how the props were reviewed, and
they caught a cliff that read as a radiator and a campfire that did not animate.

## License

MIT. See [LICENSE](LICENSE).
