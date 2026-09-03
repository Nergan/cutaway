# ASCII City

[Читать на русском (README.ru.md)](README.ru.md)

A multiplayer first-person city rendered entirely as glowing ASCII. Everyone
who opens the page walks the same street, sees the same skyline, sees each
other, and can talk. The district is generated procedurally from a seed, and
the server owns every position in it.

```
─▓▓│▪□□□▪▪□□▪░││▓───││││▓░░░░▫▫│││││││▓▓▓▓────│││▪▪▪▪████······▓▓▫▫▫▫▫███████│││
│▪▪▪▪□□□▪▪□▓▓────▓▓▓│▫▫▫·░░░░▫▫│││││││▓▓▓▓▓▓││────▓▓▓████······▓▓▫││││███████···
░▪▪▪│▓───│▓▓▓▫▫▫■■■■▫▫▫▫·░░░░▫▫│││││││▓▓▓▓▓▓···░░□▓▓▓│────────▓▓▓│││││███████···
│▓▓────▓││▓▓▓│▫▫····□□□□□░░░░▪▪│││││││▓▓▓▓▓▓░░░▪▪▓▓▓▓│││───│▓▓▓▓▓│││││███████│││
│▓▓││▓▓▓││▓▓▓│││▓▓▓▓││││▓▫▫▫▫▫▫│││││││▓▓▓▓▓▓│││││▓▓▓▓│││││││▓▓▓violet-conduit███
░██░░□□□▫▫··▪░░░▪▪▪▪■■■■■▫▫▫▫▫▫│││││││▓▓▓▓▓▓■■■█████■■■■■░░░███▓▓●●●●●●●●●●●████
│▓▓││▓▓▓││▓▓▓│││▓▓▓▓││││▓▓▓▓▓│││││││││▓▓▓▓▓▓│││││▓▓▓▓│││││││▓▓▓▓▓///|||||\\\████
.   ...::.::::::...▓│─────────────────────▓▓  .                  ///|||||\\\█│││
      ....   -----------------            :::::::.;;;;;;.........///::───\\\────
```

## Running it

The project is registered in `orchestrator.toml` and served by the hub at
`/ascii-city`. Nothing special is needed beyond the repository's own setup:

```bash
./build.sh          # installs Python deps and runs the client build
python main.py      # the hub, with ASCII City on /ascii-city
```

Standalone, without the hub:

```bash
cd ascii_city && npm install && npm run build
cd .. && python -m ascii_city.main --port 8130
# then open http://127.0.0.1:8130/ascii-city/
```

For client work, `npm run dev` starts Vite with a proxy to a server on port
8130, so the district and the socket come from the real backend while the UI
hot-reloads.

## Controls

| Input | Action |
| --- | --- |
| `W` `A` `S` `D` or arrows | Walk |
| `Shift` | Run |
| Mouse | Look (click the viewport to capture the pointer) |
| `Enter` | Open the chat line; `Enter` again sends, `Escape` cancels |
| Left half of a touchscreen | Virtual stick |
| Right half of a touchscreen | Look |

Chat has two ranges: `district` reaches everyone, `nearby` reaches thirty
metres. The button left of the input switches between them.

## How it works

The server is the only thing that knows where anyone is. Clients send *intent*
— "forward, slightly right, sprinting, facing this way" — and the server
answers with positions twenty times a second. A client that lies about its
input gains nothing, because the step length and the collision test are the
server's to compute.

- **World.** A seeded procedural generator paints avenues, streets, blocks and
  buildings, then slices the result into 256 m tiles. Tiles are immutable for a
  world version, so they are served with a long cache lifetime and gzipped once
  at startup rather than per request.
- **Transport.** A compact binary WebSocket protocol. A snapshot entry is ten
  bytes, so a full fifty-player room costs roughly 10 MB per minute — an order
  of magnitude under the traffic budget the orchestrator grants the project.
- **Prediction.** The client runs a line-for-line copy of the server's movement
  code, so walking feels instant. When a snapshot arrives, the client rewinds
  to the acknowledged position, replays unacknowledged input, and blends any
  leftover error away over a few frames.
- **Rendering.** A DDA raycast per screen column, continued past the first wall
  so towers behind the street still cut their silhouette into the sky. The
  result is a character grid uploaded to the GPU as a single instanced draw
  call; the glyph atlas carries a blurred copy of each character in its green
  channel, which becomes the neon bleed.

Layers are separated the hexagonal way: `domain` knows the rules, `application`
orchestrates them, `infrastructure` speaks bytes and databases, `presentation`
speaks HTTP and WebSocket. The world source is a port, and there are already
two implementations of it: the procedural generator and an OpenStreetMap
importer that turns tagged GeoJSON into the same tiles. Nothing above the port
can tell them apart.

## Storage

MongoDB is used when it is reachable and skipped when it is not. It caches
encoded tiles, records the world descriptor, and keeps a short chat history
with a TTL index. Losing the database costs the chat backlog and a few seconds
of regeneration on startup, nothing else — the district is a pure function of
its seed.

There is no CDN dependency. Tiles are small, immutable and served by the
project itself, which keeps the whole thing self-contained.

## Documentation

- [Architecture](docs/architecture.md) — layers, data flow, why the server is
  authoritative, and where the seams are.
- [Protocol](docs/protocol.md) — every byte on the WebSocket.
- [World format](docs/world-format.md) — the binary tile container.
- [OSM import](docs/osm-import.md) — how a real city would replace the
  procedural one.

## Tests

```bash
python -m pytest tests -k ascii_city   # 249 server, import and parity tests
cd ascii_city && npm test              # 83 client tests
```

The two suites are tied together on purpose. `ascii_city/tools/make_fixtures.py`
freezes payloads produced by the Python codecs; the client suite decodes them,
and a pytest check regenerates them to prove they are current. A constants
parity test reads `frontend/src/domain/constants.ts` and compares every shared
number with `domain/constants.py`. Changing the protocol on one side only will
fail the build rather than desync a player.

To look at the city without a browser:

```bash
python -m ascii_city.main --port 8130
cd ascii_city && npx vite-node tools/preview-frame.ts -- --plain --yaw 120
```

`ascii_city/tools/preview.py` does the same for the generator itself, printing
a top-down map of the district and its statistics, and
`ascii_city/tools/import_osm.py` prints the same map for a district imported
from GeoJSON:

```bash
python -m ascii_city.tools.import_osm ascii_city/docs/samples/osm-district.geojson
```

## License

MIT. See [LICENSE](LICENSE).
