"""Deterministic hashing for chunk identity and procedural seeds.

The naive ``world_seed * x * y`` derivation is symmetric about the axes, so
mirrored coordinates generate identical terrain. Accordion Spec 2.5 calls this
out explicitly; the fix is a real avalanche mixer. SplitMix64's finaliser is the
one used here: stateless, one multiply-xorshift chain, and cheap enough to call
per tile.

Every function is pure and every result is masked to 64 bits so the Python and
TypeScript implementations agree bit for bit. The TypeScript mirror uses BigInt
for exactly this reason.
"""

from __future__ import annotations

MASK64 = 0xFFFFFFFFFFFFFFFF

# SplitMix64 finaliser constants.
_GOLDEN_GAMMA = 0x9E3779B97F4A7C15
_MIX_A = 0xBF58476D1CE4E5B9
_MIX_B = 0x94D049BB133111EB


def mix64(value: int) -> int:
    """Avalanche a 64-bit integer so neighbouring inputs land far apart."""
    z = (value + _GOLDEN_GAMMA) & MASK64
    z = ((z ^ (z >> 30)) * _MIX_A) & MASK64
    z = ((z ^ (z >> 27)) * _MIX_B) & MASK64
    return (z ^ (z >> 31)) & MASK64


def combine(*values: int) -> int:
    """Fold several signed integers into one well-mixed 64-bit hash.

    Each value is mixed before folding, so ``combine(1, 0)`` and ``combine(0, 1)``
    diverge. Negative inputs are two's-complement masked, which keeps lane -1 and
    lane 1 unrelated instead of mirrored.
    """
    accumulator = _GOLDEN_GAMMA
    for value in values:
        accumulator = mix64(accumulator ^ (value & MASK64))
    return accumulator


def hash_string(text: str) -> int:
    """Hash an identifier such as an edge id into 64 bits.

    FNV-1a over UTF-8 bytes, then avalanched. Python's own ``hash`` is salted per
    process and would produce a different world on every restart.
    """
    accumulator = 0xCBF29CE484222325
    for byte in text.encode("utf-8"):
        accumulator = ((accumulator ^ byte) * 0x100000001B3) & MASK64
    return mix64(accumulator)


def chunk_key(edge_id: str, segment_index: int, lane_offset: int, tier_min: int) -> int:
    """Identity of a corridor chunk, independent of the world seed.

    Two worlds with different seeds still address the same chunk by the same key,
    which is what lets persistence rows be portable across reseeds.
    """
    return combine(hash_string(edge_id), segment_index, lane_offset, tier_min)


def chunk_seed(
    world_seed: int,
    edge_id: str,
    segment_index: int,
    lane_offset: int,
    tier_min: int,
) -> int:
    """Generation seed for a corridor chunk.

    Includes ``tier_min`` so a lane that only exists at tier 1 has terrain of its
    own, and excludes the *current* tier so an existing chunk never regenerates
    when the world expands. That distinction is the whole point of a topological
    accordion (Accordion Spec 3.3).
    """
    return combine(world_seed, hash_string(edge_id), segment_index, lane_offset, tier_min)


def hub_chunk_key(hub_id: int, chunk_x: int, chunk_y: int) -> int:
    """Identity of a chunk inside a hub zone, in hub-local chunk coordinates."""
    return combine(0x48554200, hub_id, chunk_x, chunk_y)


def hub_chunk_seed(world_seed: int, hub_id: int, chunk_x: int, chunk_y: int) -> int:
    """Generation seed for a hub-zone chunk."""
    return combine(world_seed, 0x48554200, hub_id, chunk_x, chunk_y)


def tile_hash(seed: int, tile_x: int, tile_y: int, salt: int = 0) -> int:
    """Per-tile hash for scatter decisions inside a chunk."""
    return combine(seed, tile_x, tile_y, salt)


def unit_float(hashed: int) -> float:
    """Map a 64-bit hash onto ``[0, 1)``.

    Uses the top 53 bits, which is exactly the mantissa width of an IEEE double,
    so Python and JavaScript produce the same float from the same hash.
    """
    return (hashed >> 11) / 9007199254740992.0


def ranged_int(hashed: int, upper: int) -> int:
    """Map a hash onto ``[0, upper)``. ``upper`` must be positive."""
    if upper <= 0:
        raise ValueError("upper bound must be positive")
    return hashed % upper
