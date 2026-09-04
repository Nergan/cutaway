# Wire protocol

The normative reference for every byte on the game socket. The Python side is
`infrastructure/wire_codec.py`, the TypeScript side is
`frontend/src/net/wire.ts`, and `tests/test_ascii_city_client_parity.py` fails
the build if one of them drifts from the fixtures in
`frontend/src/__fixtures__/protocol.json`.

## Conventions

Every frame is a binary WebSocket message whose first byte is the type. All
multi-byte fields are **little-endian** and there is no padding anywhere: the
Python structs are all declared with the `<` prefix.

Frames are never split or batched. One WebSocket message is exactly one frame.

A client frame larger than **4096 bytes** is dropped before parsing
(`MAX_FRAME_BYTES`). The orchestrator enforces a separate ceiling of its own,
so a hostile client cannot reach the room with a large payload either way.

### Quantisation

| Quantity | Encoding | Scale | Range |
| --- | --- | --- | --- |
| Position | `u16` centimetres | `POSITION_SCALE = 100` | 0 … 655.35 m per axis |
| Yaw | `u16` fraction of a turn | `ANGLE_SCALE = 65536` | full circle, ≈0.0055° per step |
| Pitch | `i8` hundredths of a radian | `PITCH_SCALE = 100` | ±1.27 rad, clamped to ±1.2 |
| Analogue input axis | `i8` hundredths | — | −1.0 … 1.0 |

Positions are clamped into the encodable range rather than wrapping, so a bug
upstream produces a player pinned to a district edge, not one teleported across
the map. The district itself is capped at `MAX_TILES_PER_AXIS` tiles per axis
for the same reason: a world wider than 655.35 m could not name its own far
corner. Enlarging it is a protocol change, not a configuration change.

Rounding is `floor(value + 0.5)` on both sides. Python's built-in `round` uses
banker's rounding and JavaScript's `Math.round` does not, so the Python codecs
call `infrastructure/quantise.py::round_half_up` instead. A value landing
exactly on a half would otherwise encode to two different bytes depending on
which language produced it.

## Client to server

### `0x01` INPUT — 15 bytes

| Offset | Type | Field |
| --- | --- | --- |
| 0 | `u8` | `0x01` |
| 1 | `u32` | sequence number, monotonic per connection |
| 5 | `i8` | forward axis, hundredths |
| 6 | `i8` | strafe axis, hundredths |
| 7 | `u16` | yaw |
| 9 | `i8` | pitch |
| 10 | `u8` | flags: bit 0 = sprint, bit 1 = jump |
| 11 | `u32` | client timestamp in milliseconds, echoed in nothing — it exists for the client's own latency bookkeeping |

The server applies at most `MAX_QUEUED_INPUTS = 8` inputs per player per tick
and refills a token bucket at the simulation rate. Sending input faster than
20 Hz buys a player nothing; the excess is discarded rather than banked.

Non-finite or out-of-range axes are clamped by `InputCommand.sanitised` before
they reach the simulation.

### `0x02` CHAT — 4 + *n* bytes

| Offset | Type | Field |
| --- | --- | --- |
| 0 | `u8` | `0x02` |
| 1 | `u8` | scope: `0` global, `1` proximity |
| 2 | `u16` | UTF-8 byte length |
| 4 | bytes | UTF-8 text |

Scope `2` (system) is server-only; a client that sends it gets a protocol
error. Text is NFC-normalised, stripped of control characters and truncated to
`CHAT_MAX_LENGTH = 240` characters on arrival.

### `0x03` PING — 5 bytes

| Offset | Type | Field |
| --- | --- | --- |
| 0 | `u8` | `0x03` |
| 1 | `u32` | client timestamp in milliseconds |

### `0x04` RENAME — 3 + *n* bytes

| Offset | Type | Field |
| --- | --- | --- |
| 0 | `u8` | `0x04` |
| 1 | `u16` | UTF-8 byte length |
| 3 | bytes | nickname, UTF-8 |

The server validates the nickname the same way it does on join. A successful
rename updates the roster and broadcasts `0x89` ROSTER_UPDATE to everyone in the
room.

### `0x05` SET AVATAR — 2 bytes

| Offset | Type | Field |
| --- | --- | --- |
| 0 | `u8` | `0x05` |
| 1 | `u8` | avatar index, `0 … PLAYER_AVATAR_COUNT - 1` |

The index selects a glyph from `frontend/src/render/charset.ts::AVATAR_FACES`.
Only the index travels, so appending a face to that table is a client change
rather than a protocol change — but the table may only ever grow at the end,
because an index already on the wire must keep meaning the same face. An index
past the end is refused with a notice rather than clamped.

Like a rename, a successful change broadcasts `0x89` ROSTER_UPDATE.

## Server to client

### `0x81` WELCOME

Sent once, immediately after the socket is accepted and the player is seated.

| Type | Field |
| --- | --- |
| `u8` | `0x81` |
| `u16` | your player id |
| `u8` | your colour index, 0 … 11 |
| `u8` | your avatar index, 0 … 23 |
| `u8` | nickname byte length |
| bytes | nickname, UTF-8 |
| `u16` | spawn x |
| `u16` | spawn y |
| `u16` | spawn z |
| `u16` | spawn yaw |
| `u8` | simulation Hz |
| `u8` | snapshot Hz |
| `u32` | server time in milliseconds |
| `u8` | tiles along x |
| `u8` | tiles along y |
| `u16` | cells per tile edge |
| `f32` | cell size in metres |
| `u32` | world version |
| `u8` | world id byte length |
| bytes | world id, UTF-8 |

The client uses the world id and version to decide whether cached tiles are
still valid, and the two rates to size its fixed-step loop and its
interpolation delay.

### `0x82` SNAPSHOT

Sent every tick to every player.

| Type | Field |
| --- | --- |
| `u8` | `0x82` |
| `u32` | tick |
| `u32` | highest input sequence applied for *you* |
| `u16` | your authoritative x |
| `u16` | your authoritative y |
| `u16` | your authoritative z |
| `i16` | your vertical velocity, in centimetres per second |
| `u8` | entry count, capped at 255 |

The vertical velocity is here because the client replays its unacknowledged
input from this state. Without it the replay has to assume zero, which flattens
the arc of a jump twenty times a second.

Then one 12-byte entry per visible player:

| Type | Field |
| --- | --- |
| `u16` | player id |
| `u16` | x |
| `u16` | y |
| `u16` | z |
| `u16` | yaw |
| `i8` | pitch |
| `u8` | flags |

The height is here for the same reason it is in the header: without it a jump
is something you can only see in your own view, and everyone else in the street
stays glued to the pavement.

Entry flags: bits 0–1 carry the animation state (`0` idle, `1` walk, `2` run),
bit 2 marks a *simplified* entry.

The viewer is never in the entry list — their own position is in the header,
next to the acknowledgement they need in order to reconcile.

Interest management decides who appears: everyone within
`FULL_DETAIL_RADIUS_M = 80` is sent in full, everyone between that and
`SIMPLIFIED_RADIUS_M = 150` is sent with the simplified flag so the client can
skip nameplates and animation detail, and everyone beyond is omitted. A player
who disappears this way stays in the roster, so the client keeps their name and
colour and simply stops drawing them.

### `0x83` CHAT

| Type | Field |
| --- | --- |
| `u8` | `0x83` |
| `u32` | message id |
| `u16` | sender id, `0` for system messages |
| `u8` | scope: `0` global, `1` proximity, `2` system |
| `f64` | creation time, unix seconds |
| `u8` | nickname byte length |
| bytes | nickname, UTF-8 |
| `u16` | text byte length |
| bytes | text, UTF-8 |

### `0x84` NOTICE

| Type | Field |
| --- | --- |
| `u8` | `0x84` |
| `u8` | code: `0` info, `1` warning, `2` error, `3` rate limit |
| `u16` | text byte length |
| bytes | text, UTF-8, truncated to 512 bytes |

### `0x85` / `0x86` / `0x87` / `0x89` ROSTER

The roster is the identity directory: name, colour and avatar. It changes only
on join, leave, rename and avatar change, which is why none of those fields are
repeated inside every snapshot.

`0x85` ROSTER SYNC: `u16` count, then that many entries.
`0x86` ROSTER ADD: exactly one entry.
`0x87` ROSTER REMOVE: `u16` player id.
`0x89` ROSTER UPDATE: one entry, when a nickname or avatar changes.

An entry is `u16` player id, `u8` colour index, `u8` avatar index, `u8`
nickname byte length, then the nickname.

### `0x88` PONG

| Type | Field |
| --- | --- |
| `u8` | `0x88` |
| `u32` | the client timestamp from the ping |
| `u32` | server time in milliseconds |

## Bandwidth

A snapshot to a player who can see 49 others is `1 + 16 + 1 + 49 × 12 = 606`
bytes. At 20 Hz that is about 12 kB/s down per player, and a full 50-player
room costs roughly 12 MB per minute in total — an order of magnitude below the
traffic the orchestrator budgets for this project. Upstream is 15 bytes per
input, so 300 B/s per player.

## Changing the protocol

1. Edit `domain/constants.py` and mirror it in `frontend/src/domain/constants.ts`.
2. Edit both codecs.
3. Regenerate fixtures: `python -m ascii_city.tools.make_fixtures`.
4. Run both suites. The parity test regenerates the fixtures itself and
   compares, so a stale file fails rather than silently passing.

There is no version negotiation. Client and server ship together, and the SPA
shell is served by the same process that speaks the protocol, so a mismatch
cannot outlive a deploy.
