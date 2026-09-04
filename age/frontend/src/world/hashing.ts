/**
 * Deterministic hashing, browser side.
 *
 * Mirror of `age/domain/hashing.py`. Every function is pure and every result is masked
 * to 64 bits, because the whole streaming design rests on this file agreeing with the
 * server bit for bit: the client generates its own terrain from the world seed, so a
 * chunk of tiles never crosses the wire. One wrong bit and two players standing in the
 * same place see different ground.
 *
 * ## Why BigInt
 *
 * SplitMix64 needs 64-bit multiply-and-mask, and a JavaScript number cannot do it: the
 * mantissa is 53 bits, so `a * b` silently loses the low bits of any product wider than
 * that. The alternatives were emulating 64-bit multiplication in 16-bit limbs, or
 * BigInt.
 *
 * BigInt won because it is obviously correct and the cost is contained. It is roughly
 * an order of magnitude slower than number arithmetic, which would matter if this were
 * called per tile — but gradient corners are memoised exactly as they are on the server,
 * so a chunk needs a few hundred hashes rather than tens of thousands, and generation
 * happens in a worker where it competes with nothing.
 *
 * If profiling ever says otherwise, the limb-based version is a drop-in replacement for
 * `mix64` alone: everything else here is defined in terms of it.
 */

export const MASK64 = 0xffffffffffffffffn

const GOLDEN_GAMMA = 0x9e3779b97f4a7c15n
const MIX_A = 0xbf58476d1ce4e5b9n
const MIX_B = 0x94d049bb133111ebn

/** Avalanche a 64-bit integer so neighbouring inputs land far apart. */
export function mix64(value: bigint): bigint {
  let z = (value + GOLDEN_GAMMA) & MASK64
  z = ((z ^ (z >> 30n)) * MIX_A) & MASK64
  z = ((z ^ (z >> 27n)) * MIX_B) & MASK64
  return (z ^ (z >> 31n)) & MASK64
}

/**
 * Fold several signed integers into one well-mixed 64-bit hash.
 *
 * Each value is mixed before folding, so `combine(1, 0)` and `combine(0, 1)` diverge.
 * Negative inputs are two's-complement masked, which keeps lane -1 and lane 1 unrelated
 * instead of mirrored — the axis-symmetry bug Accordion Spec 2.5 calls out.
 */
export function combine(...values: Array<bigint | number>): bigint {
  let accumulator = GOLDEN_GAMMA
  for (const value of values) {
    accumulator = mix64(accumulator ^ (BigInt(value) & MASK64))
  }
  return accumulator
}

/**
 * Hash an identifier such as an edge id into 64 bits.
 *
 * FNV-1a over UTF-8 bytes, then avalanched. Not the platform's string hash, which is
 * salted per process and would produce a different world on every reload.
 */
export function hashString(text: string): bigint {
  let accumulator = 0xcbf29ce484222325n
  const prime = 0x100000001b3n
  for (const byte of new TextEncoder().encode(text)) {
    accumulator = ((accumulator ^ BigInt(byte)) * prime) & MASK64
  }
  return mix64(accumulator)
}

/** Generation seed for a corridor chunk. */
export function chunkSeed(
  worldSeed: bigint,
  edgeId: string,
  segmentIndex: number,
  laneOffset: number,
  tierMin: number,
): bigint {
  return combine(worldSeed, hashString(edgeId), segmentIndex, laneOffset, tierMin)
}

/** Generation seed for a chunk inside a hub zone. */
export function hubChunkSeed(
  worldSeed: bigint,
  hubId: number,
  chunkX: number,
  chunkY: number,
): bigint {
  return combine(worldSeed, 0x48554200, hubId, chunkX, chunkY)
}

/**
 * Map a 64-bit hash onto `[0, 1)`.
 *
 * The top 53 bits, which is exactly a double's mantissa width, so the conversion to a
 * number is lossless and Python's division produces the same float.
 */
export function unitFloat(hashed: bigint): number {
  return Number(hashed >> 11n) / 9007199254740992
}

/** Per-tile hash for scatter decisions inside a chunk. */
export function tileHash(
  seed: bigint,
  tileX: number,
  tileY: number,
  salt: number = 0,
): bigint {
  return combine(seed, tileX, tileY, salt)
}
