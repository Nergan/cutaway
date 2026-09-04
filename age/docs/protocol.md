# Protocol

Every byte on the WebSocket at `/age/ws`. The codec is
`age/infrastructure/wire.py` on the server and
`age/frontend/src/net/wire.ts` in the browser; both are pinned by
`tests/test_age_client_parity.py` against frozen fixtures.

`PROTOCOL_VERSION` is **2**. A client whose version does not match is closed
with `ERROR_VERSION_MISMATCH` and told to reload, because a stale bundle that
keeps parsing produces nonsense rather than an error.

The version moved from 1 to 2 with `INVENTORY`. Adding a server frame is
normally free — a client that does not know a type byte ignores it — but this
one is sent unconditionally during the handshake and carries the pools the
vitals panel divides by, so a client that ignored it would draw every bar
against the wrong maximum rather than simply missing a feature.

## Framing

Binary frames only. A text frame is answered with an error and the socket
closes — the alternative is a codec that has to guess.

Every frame is a one-byte message type followed by a payload. All multi-byte
integers are **little-endian**. Strings are a `u16` byte length followed by
UTF-8; every string field has a byte limit, and exceeding it is a protocol
error rather than a truncation.

| Type | Reader |
| --- | --- |
| `u8` `u16` `u32` `u64` | unsigned, little-endian |
| `i32` | signed, little-endian |
| `f64` | IEEE 754 double, little-endian |
| `text` | `u16` length, then that many UTF-8 bytes |

## Quantisation

Floats do not travel as floats except for timestamps.

| Quantity | Encoding | Resolution |
| --- | --- | --- |
| Position (tiles) | `i32`, scaled by `POSITION_SCALE` = 64 | 1/64 tile ≈ 0.5 px, range ±33.5 M tiles |
| Facing (radians) | `u16` across a full turn | ~0.0055° |
| Health, resource | `u8` percentage of maximum | 1/255 |
| Day phase | `u16` across one day | 1/65535 of the cycle |
| Frame time | `u16` in 1/10000 s | 0.1 ms |

Rounding is half-up in both languages. Python's `round` is half-to-even and
JavaScript's `Math.round` is half-up-toward-positive-infinity, so neither is
used directly: `round_half_up` in `wire.py` and its twin in `wire.ts` are
`floor(value + 0.5)` for positives and the mirrored form for negatives. A
half-tile position encoding to a different integer on the two sides would put
a player a pixel out of place forever.

## Client to server

### `0x01 HELLO`

The first frame. Anything else before it closes the socket.

| Field | Type | Notes |
| --- | --- | --- |
| protocol version | `u16` | Must equal 1 |
| character name | `text` | ≤ 96 bytes; normalised and clamped to 24 characters |
| class id | `u8` | 0–13; out of range falls back to Warrior |
| appearance | `u8` × 5 | Skin, hair, hair colour, cloth colour, accent |

### `0x02 READY`

The client has its atlas and its first chunks and wants snapshots. Sent once.
Snapshots do not flow before it, so a slow first paint does not accumulate a
backlog the client will have to fast-forward through.

### `0x03 INPUT`

Sent at `INPUT_HZ` (30) while anything is held, and once on release.

| Field | Type | Notes |
| --- | --- | --- |
| sequence | `u32` | The client's own counter |
| topology version | `u32` | Stale input is rejected, not applied to the wrong world |
| buttons | `u8` | Bit 0 up, 1 down, 2 left, 3 right, 4 run |
| facing | `u16` | Where the character is aiming |
| predicted x, y | `i32` × 2 | Where the client thinks it ended up |
| delta time | `u16` | Frame time in 1/10000 s, clamped server-side |

The predicted position is **not** authority. The server integrates the input
itself and compares; a difference beyond `POSITION_TOLERANCE_TILES` (1.5)
rubber-bands the client. A client that lies about its position gains nothing,
and a client that lies about `delta_time` is clamped to a plausible frame.

Diagonals are normalised from the button bits, so holding two keys is not
faster than one.

### `0x04 ACTION`

| Field | Type |
| --- | --- |
| sequence | `u32` |
| topology version | `u32` |
| ability id | `u16` |
| target x, y | `i32` × 2 |
| target entity | `u32` (0 for none) |

Actions are not predicted. The client shows a cast animation and a cooldown
sweep; the outcome arrives as `COMBAT`. Validation is entirely server-side:
class ownership of the ability, cooldown, the global
`ABILITY_MIN_INTERVAL_MS` floor, resource cost, range, line of sight, and the
hub-zone PvP ban.

### `0x05 CHAT`

`u8` channel, then `text` (≤ 960 bytes, clamped to `CHAT_MAX_LENGTH` = 240
characters). Channels: 0 local, 1 global. Rate-limited to
`CHAT_RATE_LIMIT` (5) messages per `CHAT_RATE_WINDOW_S` (10 s).

### `0x06 BUILD`

| Field | Type | Notes |
| --- | --- | --- |
| topology version | `u32` | |
| action | `u8` | 0 place, 1 harvest |
| tile x, y | `i32` × 2 | World tile coordinates |
| material | `text` | ≤ 32 bytes; the build recipe key |

Range is checked against `BUILD_RANGE_TILES` (4). Placing into a tile occupied
by a player is refused.

### `0x07 PING`

`f64` client timestamp. Answered immediately rather than at the next tick, so
the round trip measures the network and not the tick phase.

### `0x08 DEV_TIER`

`u8` target tier. Gated behind `AGE_ALLOW_DEV_CONTROLS`. The accordion's
production cadence is fifteen minutes; a demo that cannot show it on demand
cannot show it at all.

### `0x09 COMPOSE`

`u8` the second half (GDD 6.3). Refused unless the character is at
`COMPOSE_LEVEL` and still on a base class; the pairing it produces is derived
server-side, so the client cannot name a hybrid it has not earned.

### `0x0A INVENTORY`

| Field | Type | Notes |
| --- | --- | --- |
| action | `u8` | 0 equip, 1 unequip, 2 use, 3 drop |
| slot | `u8` | Pack index, except for unequip, where it is an equipment slot |
| count | `u16` | Drop only; ignored by the rest |

One byte does two jobs because the two indexings are never both in play: three
of the four actions name a stack in the pack, and `unequip` names a place on
the body. Everything here is refused silently rather than with an error, and
answered with a fresh `0x8C INVENTORY` either way — the snapshot is the
correction, so a client that asked for something impossible re-renders the
truth instead of having to reason about a rejection.

## Server to client

### `0x81 WELCOME`

| Field | Type |
| --- | --- |
| protocol version | `u16` |
| entity id | `u32` |
| world seed | `u64` |
| topology version | `u32` |
| current tier | `u8` |
| edge id | `text` (≤ 64) |
| spawn x, y | `i32` × 2 |
| server time | `f64` |

The world seed is the important field. With it the client reproduces terrain
locally, which is why no chunk of tiles is ever transmitted.

### `0x82 SNAPSHOT`

The bandwidth-critical frame, at `SNAPSHOT_HZ` (15).

Header:

| Field | Type |
| --- | --- |
| tick | `u32` |
| server time | `f64` |
| acknowledged input | `u32` |
| topology version | `u32` |
| day phase | `u16` |
| weather | `u8` |
| entity count | `u16` |

Then per entity a `u32` id, a `u8` field mask, and only the flagged fields:

| Bit | Field | Bytes |
| --- | --- | --- |
| 0 | position | 8 |
| 1 | velocity | 8 |
| 2 | facing | 2 |
| 3 | health | 1 |
| 4 | resource | 1 |
| 5 | state | 1 |
| 6 | appearance | 5 |

A walking player is 4 + 1 + 8 = **13 bytes**. Fifty players at 15 Hz is under
600 kB/min of entity data, an order of magnitude inside the traffic budget the
orchestrator grants the project.

`acknowledged_input` is what makes reconciliation work: it is the highest input
sequence the server has processed, so the client knows exactly which
predictions are confirmed and which to replay.

The state byte packs liveness in bit 0 and the NPC AI state as a 3-bit enum in
bits 1–3. It is an enum, not a set of flags — a state machine is in exactly one
state.

### `0x83 SPAWN`

A full introduction, sent once when an entity enters the area of interest:
`u32` id, `u8` kind, `u8` class or archetype, `text` name, position, facing,
`u8` health percent, `u16` level, `u8` state, appearance. Afterwards the entity
is delta-encoded in snapshots.

Every field a snapshot delta can carry is here, and the word to hold onto is
*every*. An entity is introduced once and thereafter described only by the
fields that changed, so anything the introduction omits is not a value the
client waits for — it is a value the client invents, indefinitely. The state
byte was omitted for a while and clients defaulted it to zero, whose bit 0
means *dead*: every entity in the world arrived reading as a corpse, was drawn
in the single-frame hurt pose, greyed and half-faded, and nothing in the game
ever animated. A zero that looks like data is worse than a missing field,
because a missing field throws.

### `0x84 DESPAWN`

`u32` id, `u8` reason: 0 out of range, 1 died, 2 disconnected, 3 chunk retired.
The reason drives the visual — a death plays an animation, a range eviction
just stops drawing.

### `0x85 TOPOLOGY`

`u32` version, `u8` tier, then two lists of chunk keys (`u16` count, then
`text` each): activating and retiring.

Chunk keys, not tiles. The client can generate any chunk it can name, so
activating a whole lane costs a few dozen bytes. Every subsequent client frame
carries the version, so input aimed at a world that no longer exists is
rejected instead of applied to the wrong lane.

### `0x86 COMBAT`

`u32` attacker, `u32` target, `u16` ability, `u16` damage, `u16` healing,
`u8` killed, impact `i32` × 2. One frame per resolved hit; the client turns it
into numbers, a flash and a sound.

### `0x87 CHAT`

`u32` sender, `u8` channel, `text` name, `text` body. Channel 2 is system.

### `0x88 TILES`

`text` chunk key, `u16` count, then per change a `u16` index into the chunk's
1024 tiles and a `u8` tile id.

Index-and-value pairs, not a chunk: one felled tree is three bytes rather than
a kilobyte. This frame is the *only* terrain that travels, and it exists
because player edits are the one thing a seed cannot reproduce.

### `0x89 PONG`

`f64` echoed client time, `f64` server time. The client derives both latency
and a clock offset, and the offset is what lets interpolation place remote
entities on the right timeline.

### `0x8A ERROR`

`u8` code, `text` detail (≤ 160 bytes).

| Code | Meaning |
| --- | --- |
| 1 | Stale topology version |
| 2 | Refused inside a safe zone |
| 3 | Out of range |
| 4 | On cooldown |
| 5 | Not enough resource |
| 6 | Not enough material |
| 7 | Invalid request |
| 8 | Rate limited |
| 9 | You are dead |
| 10 | Protocol version mismatch — reload |

Codes 2 through 9 are informational; the session continues. A garbled frame is
answered with code 7 rather than dropping the connection, because one bad frame
from a buggy client should not cost a player their session. Code 10 closes.

### `0x8B PROGRESS`

`u16` level, `u32` experience, `u32` next level at, `u8` class id, `u8` compose
available, `u8` ability count, then a `u16` per ability id.

Private to its owner and sent on join and on every change, which is a handful
of times a session. The ability ids travel with the class rather than being
derived client-side, so the bar cannot offer something the server will refuse.

### `0x8C INVENTORY`

| Field | Type | Notes |
| --- | --- | --- |
| capacity | `u8` | `INVENTORY_SLOTS` = 24 |
| stack count | `u8` | |
| per stack | `u16` item id, `u16` count | In pack order; the index is the slot |
| equipped count | `u8` | |
| per equipped | `u8` slot, `u16` item id | Slots as in `EquipmentSlot` |
| max health | `u16` | |
| max resource | `u16` | |
| damage bonus | `u16` | |
| move speed | `u16` | Hundredths of a tile per second |

Also private to its owner, and the largest per-player frame in the protocol,
which is why it is never broadcast: another player's bag is not something the
client has anywhere to put.

Only ids travel. Names, slots, rarities and stat modifiers are static and
arrive once on `/api/world`, so a stack costs four bytes rather than a name.
The derived stats ride along because vitals travel as a fraction of a maximum
the client otherwise never sees — without them a helm worth twelve health
would move the bar by nothing visible and the sheet could not print a number.

## Handshake

```
client                                server
  |-- HELLO ------------------------->|  validate version, load or create character
  |<-------------------- WELCOME -----|  seed, spawn, entity id
  |<------------------- TOPOLOGY -----|  active chunks, before anything is drawn
  |<------------------- PROGRESS -----|  level, experience, ability kit
  |<------------------ INVENTORY -----|  pack, loadout, derived stats
  |  (generate terrain, bake atlas)   |
  |-- READY ------------------------->|  begin snapshots
  |<------------------- SNAPSHOT -----|  15 Hz from here
  |-- INPUT (30 Hz) ----------------->|
```

`TOPOLOGY` arrives before `READY` deliberately: the client needs to know which
chunks exist before it can decide what to generate, and generating a chunk that
is about to be retired wastes the first second of a session.

## Limits

| Limit | Value |
| --- | --- |
| Max clients | `MAX_CLIENTS` = 50 |
| Queued inputs per connection | `MAX_QUEUED_INPUTS` = 32 |
| Entities per snapshot | `MAX_ENTITIES_PER_SNAPSHOT` = 64 |
| Name length | 24 characters |
| Chat length | 240 characters |
| Heartbeat | every 5 s, timeout 15 s |

An oversized frame closes the socket. A client that fills its input queue has
the oldest entries dropped, which is the right failure: stale movement is worth
less than current movement.
