# Architecture

Age is a server-authoritative multiplayer game served by the monorepo hub at
`/age`. This document explains the layers, what crosses between them, and where
the seams are that a future rewrite is meant to use.

## Why hexagonal here

The specification asks for a Go or Rust world server. The monorepo's supervisor
starts Python workers and nothing else, so the simulation core is Python for
now — and the whole point of the layering is that this is a *choice*, not a
commitment.

Everything the simulation needs from the outside world is a Protocol in
`domain/ports.py`: the clock, the chunk generator, the character store, the
topology store, the broadcaster. Nothing in `domain` or `application` imports
`infrastructure` or `presentation`. So a Go core can be introduced by
implementing the same ports on the other side of a socket without touching a
line of protocol code, UI code, or the rules themselves.

```
presentation/     FastAPI, WebSocket, DI container, tick loop
    |  (depends on application + domain + infrastructure)
    v
application/      world state, movement, combat, AI, accordion, terrain, chat
    |  (depends on domain only)
    v
domain/           rules, constants, coordinates, topology FSM, classes, ports
    ^
infrastructure/   noise, chunk generator, wire codec, clock, Mongo, memory
    |  (depends on domain; implements its ports)
```

`atelier/` sits beside these as a separate bounded context. It is the art
pipeline — it bakes pixel art and reads external editor files — and the game
does not import it. The game consumes its output as PNG and JSON over HTTP,
exactly as a browser does.

## The layers

### domain

Pure rules, no I/O, no async.

| Module | Responsibility |
| --- | --- |
| `constants.py` | Every tunable shared with the client, mirrored in `frontend/src/domain/constants.ts` and compared by a parity test |
| `hashing.py` | The 64-bit mix used by both languages to derive per-chunk and per-tile seeds |
| `coordinates.py` | The three-layer space: logical (hub/edge/segment), world tiles, chunk addresses |
| `tiles.py` | The 23 tiles, what blocks movement, what blocks sight, harvest yields, build recipes, the 8 biome profiles |
| `topology.py` | The accordion state machine: chunk lifecycle, tier, `topology_version` |
| `classes.py` | 4 base classes composing into 14, and their ability catalogue |
| `npc.py` | Archetypes and the AI state machine as a pure `next_state` function |
| `entities.py` | Entity records and the `DirtyField` mask that drives delta snapshots |
| `ports.py` | The Protocols the application depends on |

The topology FSM is worth calling out. A chunk moves
`DORMANT -> PREPARING -> ACTIVE -> RETIRING -> DORMANT`, and illegal
transitions raise rather than silently correcting. The state lives in the
domain because "may this chunk retire while a player stands in it" is a rule,
not a storage detail.

### application

Orchestration. Async where it touches a port, synchronous where it computes.

`World` is the aggregate: entities, the spatial index, tile overlays, the
topology, weather and the day phase. Everything else in the layer is a
function over it — `movement.apply_input`, `combat.resolve_action`,
`ai.tick`, `terrain.harvest`. They return report objects and push events into
an `EventQueue`; they never write to a socket. That is why they are trivially
testable, and why `tests/test_age_world.py` can drive 166 scenarios without a
server.

`accordion.WorldManager` owns the interesting part: evaluating population
against the hysteresis thresholds, expanding and contracting tiers, walking
chunks through the FSM, and evacuating players out of a lane that is about to
retire. It also owns the warm-up queue, which is where the tick budget is
actually spent (see below).

`interest.py` computes what each connection is told about: the chunks in its
area of interest, the entities inside the view radius, capped at
`MAX_ENTITIES_PER_SNAPSHOT`. It is the reason a busy hub does not cost more
bandwidth than a quiet corridor.

### infrastructure

The adapters.

`generator.py` is the terrain generator, and it has a twin in
`frontend/src/world/generator.ts`. The two must agree bit for bit — see
[World generation](worldgen.md).

`wire.py` is the binary codec, with a twin in `frontend/src/net/wire.ts`. See
[Protocol](protocol.md).

`mongo_repositories.py` and `memory_repositories.py` implement the same two
ports. Mongo is used when reachable and skipped when not; the world is a pure
function of its seed, so losing the database costs saved characters and terrain
edits, not the world.

### presentation

`container.py` is the composition root: it reads settings, picks the memory or
Mongo repositories, builds the world, starts the room. `room.py` runs the tick
loop. `connection.py` is one player's socket state — their input queue,
acknowledged sequence, area of interest, and the entities they have been told
about. `http_routes.py` and `ws_routes.py` are thin translations between HTTP
or WebSocket and the application layer.

## The tick loop

30 Hz simulation, 15 Hz snapshots. One tick:

1. Drain queued input per connection, run `movement.apply_input` for each.
2. Resolve queued actions through `combat.resolve_action`.
3. `ai.tick` — NPCs decide every third tick, integrate every tick.
4. `terrain.tick_regrowth`, `weather.tick`.
5. `accordion.WorldManager.tick` — evaluate the topology on its own interval.
6. Every other tick, build snapshots and flush the event queue to sockets.

The loop measures its own overrun. A tick that runs long is logged rather than
silently dropping frames, because an accordion expansion is exactly the moment
you want to know about it.

### Where the budget goes

A tick is 33 ms. Generating one chunk originally took 712 ms, which stalled
the world for two seconds every time a lane activated. Two changes fixed it:

- The generator samples its noise fields on a coarse grid and interpolates
  between samples, rather than evaluating per tile. Terrain features are much
  larger than a tile, so the visible result is unchanged. 712 ms became 24 ms.
- Chunk warm-up moved between ticks. `Room._warm_up` builds at most one chunk,
  on alternate ticks, and only while the simulation itself is comfortably inside
  its budget.

Twenty-four milliseconds still does not fit in a 33 ms tick's leftover slack, so
waiting for enough slack would mean waiting forever. Instead the build is
*allowed* to overrun. The loop keeps an absolute deadline, so an overrun delays
exactly the next tick and then recovers; the visible effect while a queue drains
is the tick rate sagging towards 24 Hz, which the client's interpolation absorbs.
Draining 176 chunks after a forced expansion costs three slow ticks out of 181,
with a peak of 58 ms.

A busy world fails the budget check and stops warming entirely. Chunks it skipped
are generated on first touch instead — one hitch for one player rather than a
sustained sag for everyone. That degradation is the deal, and TDD 2.2 INV-7 asks
for it to be explicit rather than silent, which is why the loop measures and logs
its own overruns.

A worker thread was tried and is worse. The GIL makes it preemption rather than
parallelism, so the same cost reappears as tick jitter, and it puts the chunk
cache under concurrent access for no gain.

`PREPARING` chunks have `CHUNK_PREPARE_SECONDS` (2 s) before they may go
`ACTIVE`, so by the time a lane becomes visible its terrain is in memory and
activation is a flag flip rather than a stall.

Snapshots are the other cost. They are deltas: a 4-byte id, a 1-byte field
mask, and only the fields that changed. A player who is merely walking costs
13 bytes.

## Storage

Two ports, both optional.

`CharacterRepository` keeps a character per name: class, appearance, level,
inventory, last position. `TopologyRepository` keeps the current tier and the
terrain overlay per chunk, flushed on an interval rather than per edit.

Without Mongo both are in-memory and the world resets on restart. That is a
legitimate demo configuration and the default when `AGE_USE_MONGO` is off.

## The client

The browser is not a thin terminal. It runs:

- **A copy of the terrain generator.** Terrain is never transmitted. The server
  sends a seed; the client generates the same tiles. Only player edits travel.
- **A copy of the movement code.** Input is applied locally for instant
  response, then reconciled: on a snapshot the client rewinds to the
  acknowledged position, replays unacknowledged input, and blends away the
  residual error over a few frames.
- **Interpolation for everyone else.** Remote entities are rendered from a
  two-snapshot buffer, so 15 Hz snapshots look like smooth motion.

The renderer is PixiJS v8. Two scene graphs are drawn: a colour pass and a
normal-map pass, composited by a lighting filter that reads the normals to
shade every sprite from the sun, the moon, and nearby point lights. Chunks are
built into a single mesh per chunk with pre-computed UVs, so an animated water
chunk costs a buffer write rather than a rebuild.

## Testing strategy

| Suite | Count | What it pins |
| --- | --- | --- |
| `tests/test_age_world.py` | 166 | Domain and application: topology FSM, accordion, movement, combat, AI, terrain, chat, sessions |
| `tests/test_age_server.py` | 48 | HTTP and WebSocket, including the handshake, error paths and the Atelier API |
| `tests/test_age_atelier.py` | 45 | Canvas operations, recipes, normal maps, PNG encoding, importers |
| `tests/test_age_client_parity.py` | 90 | Every shared constant, and terrain generated by both languages |
| `age` vitest | 126 | Client mirrors: wire codec, prediction, interpolation, chunk store, atmosphere, parity |

The parity suites are the load-bearing ones. `age/tools/make_fixtures.py`
freezes payloads produced by the Python codec into
`frontend/src/__fixtures__/parity.json`; the client suite decodes them, and a
pytest check regenerates the file to prove it is current. Changing the protocol
or a constant on one side only fails the build instead of desynchronising a
player mid-session.
