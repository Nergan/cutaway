# Roadmap

What this slice is, what it is deliberately not, and what each of the missing
pieces would take. The point of the layering is that none of the entries below
require touching the layers above them.

## What is in

- The accordion topology: two hubs, one edge of eight segments, two tiers, real
  hysteresis, real chunk lifecycle, players evacuated out of a retiring lane.
- Deterministic four-layer world generation, bit-identical in Python and
  TypeScript, so terrain costs nothing on the wire.
- Movement with client prediction and server reconciliation, and the anti-cheat
  that makes the prediction safe to trust.
- 14 composite classes with an ability catalogue, combat resolution with
  cooldowns, resources, range, line of sight and a hub-zone PvP ban.
- Two NPC archetypes with a state machine, aggro and flee hysteresis, and hub
  guards.
- Terrain that can be harvested and built on, with a regrowth ladder, persisted
  as per-chunk overlays.
- Local and global chat, rate-limited and sanitised.
- Day/night, weather, and normal-mapped dynamic lighting.
- The Atelier: procedural pixel art with animation and derived normal maps, a
  browser editor, and LDtk/Aseprite importers.
- 475 tests, including cross-language parity for every shared constant and for
  generated terrain.

## What is out, and why

### A Go or Rust simulation core

The TDD specifies one. The monorepo's supervisor starts Python workers and
nothing else, so this slice runs the core in Python at 30 Hz and says so.

The path is already cut. Everything the simulation needs from outside is a
Protocol in `domain/ports.py`, and the wire format is language-agnostic and
rate-agnostic. A Go core would implement the same ports across a socket; the
protocol, the client, and the rules stay where they are. `SIMULATION_HZ` can rise
without a protocol change because nothing in the format encodes the tick rate.

**Effort:** substantial, but isolated. The domain rules would have to be ported,
which is where the parity-test approach already used for terrain and constants
would pay for itself again.

### More than two hubs

`build_default_world` builds the MVP world: two hubs, one edge. The coordinate
system, the topology FSM and the seeding scheme are all general — chunk seeds
key on `(edge_id, segment, lane, tier_min)` and hub seeds on `(hub_id, cx, cy)`,
neither of which assumes a count.

**Effort:** small. A graph of hubs and edges instead of a hardcoded pair, and a
routing decision about which edge a player at a hub gate walks onto.

### Instanced dungeons and raids

The GDD's content pillar. Nothing here contradicts it: an instance is another
space type alongside `HUB` and `EDGE`, with its own seed and its own topology
entry, and the accordion already knows how to bring a space up and down.

**Effort:** medium. Mostly content and encounter scripting rather than
architecture.

### Data-driven abilities

Abilities are a hardcoded catalogue composed from four halves, which is how 14
kits come out of 14 definitions instead of 42. The GDD wants abilities as
modifiers loaded from data.

**Effort:** medium. `Ability` is already a flat dataclass with no behaviour, so
the loader is the work, not the model. Ability ids are stable and travel on the
wire, so a migration has to preserve them.

### Economy, crafting, trade

Levels, the pack and the worn slots are persisted and all three now feed the
simulation: kills roll a drop table, equipment moves the pools and the damage.
What is missing is anything to *do* with a coin. There is no crafting, no
vendor, no trade between players, and dropping an item destroys it rather than
leaving it on the ground for somebody else.

**Effort:** medium, and mostly design. The catalogue and the persistence shape
are there; a ground-item entity kind is the only new mechanism a real drop
needs.

### Guilds, territory, sieges

The GDD's social layer. Untouched. Territory is the interesting one, because
claimed land interacts with the regrowth ladder — a claimed tile should not
regrow — and the terrain layer already has the hook for it.

### Cloudinary

Not used. Game art is public and cached by jsDelivr, so it needs none of
Cloudinary's masking. The adapter stays behind a port for user-generated
content later — player portraits, guild banners, screenshots — which is
genuinely what Cloudinary is for.

### Areas of the spec that would need research before building

- **Wave Function Collapse** for tile layout. The generator uses threshold
  selection plus a coherence pass, which the TDD names as the sanctioned
  fallback. WFC's global constraint propagation is hostile to generating one
  chunk at a time in an unpredictable order, so adopting it means solving that
  first, not just swapping an algorithm.
- **Lag compensation for projectiles.** `POSITION_HISTORY_SECONDS` is recorded
  and `LAG_COMPENSATION_WINDOW_MS` is defined, but only instant abilities
  rewind. A travelling projectile needs a decision about whose timeline it
  lives on.
- **Horizontal scaling.** One process owns the world. Sharding by edge is the
  obvious cut, and `topology_version` already gives clients a way to be told
  their world changed underneath them.

## Near-term, in rough order

1. **A second edge and a third hub.** The smallest change that makes the
   accordion's purpose visible — right now there is only one corridor to widen.
2. **Autotiling from the material channel.** The canvas already carries it and
   nothing reads it yet. This is the biggest visual return per hour of work:
   grass would meet sand with a proper transition instead of a hard edge.
3. **Save the Atelier's edits.** The editor bakes and exports, but a recipe
   change lives in the browser. Writing recipes back to disk closes the loop and
   turns the editor into a real tool.
4. **Ability effects on the client.** Combat resolves correctly and is drawn
   minimally. Projectile trails, impact flashes and hit reactions are pure
   presentation and cost nothing on the wire.
5. **Sound.** There is none. The material channel is already the right key for
   footsteps.
