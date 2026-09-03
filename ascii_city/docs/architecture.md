# Architecture

## The one rule

The server owns every position. A client sends *intent* — "forward, slightly
right, sprinting, facing this way" — and receives positions back twenty times a
second. It never sends a position, and the server never trusts one.

Everything else in this document follows from that. Client prediction exists so
the game does not feel like it is on a leash; interest management exists so a
crowded room does not cost bandwidth linearly per pair; the binary protocol
exists so twenty snapshots a second stay affordable. None of them are allowed
to weaken the rule.

## Layers

```
presentation/     FastAPI routes, the WebSocket endpoint, the DI container
      │           depends on ↓
application/      the room, movement, chat, interest, world service
      │           depends on ↓
domain/           constants, entities, ports — no imports outward
      ↑
infrastructure/   generator, codecs, MongoDB and in-memory repositories
```

`domain` is the vocabulary: what a cell code means, how fast a player walks,
what a building is. It imports nothing from the layers above it, which is what
makes it safe for both a MongoDB adapter and a test double to speak it.

`domain/ports.py` declares the four things the application needs from the
outside world: a generator, a tile repository, a world registry, a chat
archive, and a clock. Each has a memory implementation and a MongoDB one, and
the application cannot tell the difference. This is the seam that makes an
OpenStreetMap importer a drop-in replacement for the procedural generator
rather than a rewrite.

`application` is where the rules run. `CityRoom` is the only stateful thing in
the project: it owns the member list, the input queues, the tick loop and the
broadcast fan-out.

`presentation` is thin on purpose. The WebSocket route wraps a socket in a
`WebSocketPlayerConnection`, hands it to the room, and forwards frames. The
HTTP routes serve metadata, tiles and the SPA shell.

## The tick

```
                 ┌── input frames ──────────────┐
   client ───────┤  0x01, up to 8 per tick      ├──────▶ CityRoom.handle_frame
                 └──────────────────────────────┘             │
                                                              ▼
                                                       per-player queue
                                                              │
   every 50 ms ──▶ CityRoom.step ──▶ apply inputs ──▶ move_player + collision
                                          │
                                          ├─▶ evict silent connections
                                          └─▶ per-viewer snapshot ──▶ clients
```

`step` runs at `SIMULATION_HZ = 20`. It drains at most `MAX_QUEUED_INPUTS = 8`
inputs per player, refilling a token bucket at the tick rate, so a client that
floods input gains no distance — it just loses the excess. Movement and
collision are `application/movement.py`, and the client runs a line-for-line
copy of that function in `frontend/src/sim/movement.ts`.

Snapshots go out on the same tick. Each is built per viewer, because interest
management is per viewer: everyone inside 80 m in full, everyone out to 150 m
flagged simplified, everyone beyond omitted. The viewer's own authoritative
position rides in the snapshot header next to the sequence number of the last
input applied to them — the two facts they need to reconcile.

## Prediction and reconciliation

The client applies input the moment it is generated, then keeps it in a pending
list. When a snapshot arrives it takes the acknowledged position, replays every
input after the acknowledged sequence, and compares the result with what it had
been showing. A small difference is blended away over a few frames; a large one
snaps, because a hundred-metre correction smoothed over time reads as a player
sliding through a wall.

Remote players get the other treatment: their samples are buffered and played
back on a short delay, interpolating between the last two, so packet timing
jitter does not become visible stutter. Angles blend the short way around the
circle.

## Rendering

The renderer is a raycaster, not a rasteriser. Per screen column it walks the
collision grid with DDA, and it does not stop at the first wall — it keeps
going so a tower behind a low wall still cuts its silhouette into the sky.
Each hit paints a run of rows: roof line, floor slabs, window bands, structural
ribs, with distance fog folded into the colour rather than the glyph.

The output is a `CellBuffer`: a flat byte array of glyph index, foreground RGB,
background RGB and an effect flag per character cell. That buffer goes to the
GPU as one instanced draw call against a glyph atlas built at startup on a
Canvas2D surface. The atlas stores each character twice — crisp in the red
channel, blurred in the green — and the shader mixes them, which is where the
neon bleed comes from without a post-processing pass.

`render/canvasRenderer.ts` is a Canvas2D fallback that draws runs of characters
with `fillText` when WebGL2 is unavailable. It is slower and has no glow, but
it keeps the project working on a machine that cannot give us a GL context.

Quality is adaptive: the renderer watches its own frame time and steps the cell
resolution up or down between presets, so a phone and a desktop converge on the
same frame rate at different densities.

## Composition and lifecycle

`presentation/container.py` is the composition root. `startup` picks the
adapters — MongoDB when reachable, memory when not — and kicks off world
preparation as a *background task* rather than awaiting it, so an isolated
worker answers its readiness probe immediately instead of timing out while it
generates a district. Endpoints `await container.ready()`, and the client shows
its loading overlay until that resolves.

`main.py` exposes `asgi_app` plus `startup_clients` and `shutdown_clients`,
which is the contract the orchestrator's loader expects. The project runs
identically embedded in the hub process and isolated behind the proxy; nothing
in the code knows which mode it is in, except that `ASCII_CITY_BASE_PATH` tells
the client where to find its own API.

## Failure behaviour

| What breaks | What happens |
| --- | --- |
| MongoDB unreachable at startup | Falls back to in-memory storage. The district regenerates from its seed; chat history starts empty. |
| MongoDB fails mid-flight | Individual operations log and return empty. The room does not notice. |
| A client stops reading | Its send fails or its queue backs up; the room evicts it rather than blocking the tick. |
| A client sends garbage | `ProtocolError`, a notice frame, and the connection stays. Repeated garbage closes it. |
| The world fails to generate | `container.ready()` re-raises, `/api/world` returns the error, and the client shows it instead of a blank screen. |
| A socket task is cancelled mid-leave | The departure broadcast runs shielded in a room-owned task, so nobody is left with a ghost in their roster. |

## Testing strategy

The two suites are welded together rather than merely coexisting.

- `tools/make_fixtures.py` freezes payloads produced by the Python codecs into
  `frontend/src/__fixtures__/protocol.json`. The Vitest suites decode those
  fixtures, and a pytest check regenerates them and fails if the committed file
  is stale.
- `test_ascii_city_client_parity.py` parses `frontend/src/domain/constants.ts`
  and compares every shared number with `domain/constants.py`.
- `frontend/src/sim/movement.test.ts` mirrors the server's movement tests case
  for case, so prediction cannot quietly diverge from authority.
- `frontend/src/render/raycaster.test.ts` renders headless into a `CellBuffer`
  and asserts structure: sky above ground, walls where buildings are, depth
  ordering between a near wall and a far tower, sprites and nameplates
  occluded by geometry.

Changing the protocol on one side only fails the build. That is the point.

## What was deliberately not built

- **No client-side generation.** The client could run the same seeded generator
  and skip the download entirely, but then two implementations of the same
  algorithm would have to agree forever. Tiles are cheap; divergence is not.
- **No CDN.** A district is tens of kilobytes of immutable, cacheable bytes.
  Adding Cloudinary or a GitHub-hosted CDN would add a failure mode and an
  upload step to save nothing measurable.
- **No entity-component system, no physics engine.** Players are circles on a
  grid. A capsule solver would be more general and would not change what a
  player can do.
- **No room sharding.** One district, one room, capped at 50. Sharding matters
  when the cap is reached, and the cap is a constant.
