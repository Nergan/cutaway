"""Deterministic 32-bit PRNG.

Mulberry32 is used because it is small, fast and reproduces bit-for-bit in any
language with 32-bit integer arithmetic. That matters for regression tests that
pin a district digest, and it keeps the door open for a client-side generator.
"""

from __future__ import annotations

MASK32 = 0xFFFFFFFF


class Mulberry32:
    __slots__ = ("_state",)

    def __init__(self, seed: int) -> None:
        self._state = seed & MASK32

    def next_u32(self) -> int:
        self._state = (self._state + 0x6D2B79F5) & MASK32
        t = self._state
        t = ((t ^ (t >> 15)) * (t | 1)) & MASK32
        t = (t ^ (t + ((t ^ (t >> 7)) * (t | 61)))) & MASK32
        return (t ^ (t >> 14)) & MASK32

    def next_float(self) -> float:
        """Uniform in [0, 1)."""
        return self.next_u32() / 4294967296.0

    def below(self, bound: int) -> int:
        """Uniform integer in [0, bound). Modulo bias is irrelevant at our scale."""
        if bound <= 0:
            return 0
        return self.next_u32() % bound

    def between(self, low: int, high: int) -> int:
        """Uniform integer in [low, high]."""
        if high <= low:
            return low
        return low + self.below(high - low + 1)

    def chance(self, probability: float) -> bool:
        return self.next_float() < probability

    def pick(self, options):
        return options[self.below(len(options))]

    def fork(self, salt: int) -> "Mulberry32":
        """Derive an independent stream so one subsystem cannot shift another."""
        return Mulberry32((self.next_u32() ^ (salt * 0x9E3779B1)) & MASK32)


def hash_seed(*parts: int | str) -> int:
    """FNV-1a over the parts, used to turn names and coordinates into seeds."""
    value = 0x811C9DC5
    for part in parts:
        data = part.encode("utf-8") if isinstance(part, str) else part.to_bytes(8, "little", signed=True)
        for byte in data:
            value = ((value ^ byte) * 0x01000193) & MASK32
    return value


def digest_bytes(*buffers: bytes | bytearray) -> int:
    """FNV-1a digest used to detect world-format drift in tests."""
    value = 0x811C9DC5
    for buffer in buffers:
        for byte in buffer:
            value = ((value ^ byte) * 0x01000193) & MASK32
    return value
