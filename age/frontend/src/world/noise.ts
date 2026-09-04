/**
 * Deterministic gradient noise, browser side.
 *
 * Mirror of `age/infrastructure/noise.py`, and the reason that file avoids `sin`, `cos`,
 * `exp` and `pow` entirely: those come from libm and are not guaranteed to agree across
 * platforms, let alone across languages. Everything here is `+`, `-`, `*`, `/` and
 * `Math.floor`, all of which are IEEE 754 operations with identical results in both.
 *
 * The gradient constants are written as the decimal expansion of the relevant irrational
 * so that both languages parse the same double from the same characters.
 */

import { combine, unitFloat } from './hashing'

const D = 0.7071067811865476 // sqrt(2)/2
const A = 0.9238795325112867 // cos(22.5 degrees)
const B = 0.3826834323650898 // sin(22.5 degrees)

const GRADIENTS: ReadonlyArray<readonly [number, number]> = [
  [1.0, 0.0], [A, B], [D, D], [B, A],
  [0.0, 1.0], [-B, A], [-D, D], [-A, B],
  [-1.0, 0.0], [-A, -B], [-D, -D], [-B, -A],
  [0.0, -1.0], [B, -A], [D, -D], [A, -B],
]
const GRADIENT_MASK = 15n

// Domain rotation. Sampling an axis-aligned lattice leaves visible horizontal and
// vertical streaks; rotating the input by an angle with no rational relationship to the
// grid removes them without costing a second noise call. Decimal expansions of cos/sin
// of roughly 31.7 degrees.
const ROT_COS = 0.8507035
const ROT_SIN = 0.5257311

/**
 * Memoised lattice corners, keyed by seed and integer position.
 *
 * The same optimisation the server makes, and for the same reason: the climate fields
 * have wavelengths of over a hundred tiles, so a whole chunk of samples sits inside a
 * handful of cells and asks for the same four corners thousands of times. It matters
 * more here, because each miss costs three BigInt multiplies.
 *
 * The cap is a plain size check with a full clear rather than a least-recently-used
 * eviction. Access here is spatially local — a chunk touches a small set of corners and
 * then moves on — so the working set is tiny and tracking recency would cost more than
 * it saves.
 */
const GRADIENT_CACHE = new Map<string, readonly [number, number]>()
const GRADIENT_CACHE_LIMIT = 1 << 16

function gradientAt(seed: bigint, x: number, y: number): readonly [number, number] {
  const key = `${seed}:${x}:${y}`
  const cached = GRADIENT_CACHE.get(key)
  if (cached !== undefined) return cached

  const gradient = GRADIENTS[Number(combine(seed, x, y) & GRADIENT_MASK)]
  if (GRADIENT_CACHE.size >= GRADIENT_CACHE_LIMIT) GRADIENT_CACHE.clear()
  GRADIENT_CACHE.set(key, gradient)
  return gradient
}

/**
 * Quintic ease, `6t^5 - 15t^4 + 10t^3`.
 *
 * Zero first and second derivatives at both ends, so adjacent lattice cells join without
 * the visible creasing a cubic fade leaves behind.
 */
function fade(t: number): number {
  return t * t * t * (t * (t * 6.0 - 15.0) + 10.0)
}

/**
 * Single-octave gradient noise in roughly `[-1, 1]`.
 *
 * Values slightly exceed the nominal range at lattice diagonals, which is normal for
 * gradient noise and is why callers normalise through {@link fractal} rather than
 * trusting the bound.
 */
export function gradientNoise(seed: bigint, x: number, y: number): number {
  const rx = x * ROT_COS - y * ROT_SIN
  const ry = x * ROT_SIN + y * ROT_COS

  const x0 = Math.floor(rx)
  const y0 = Math.floor(ry)
  const fx = rx - x0
  const fy = ry - y0

  const g00 = gradientAt(seed, x0, y0)
  const g10 = gradientAt(seed, x0 + 1, y0)
  const g01 = gradientAt(seed, x0, y0 + 1)
  const g11 = gradientAt(seed, x0 + 1, y0 + 1)

  const n00 = g00[0] * fx + g00[1] * fy
  const n10 = g10[0] * (fx - 1.0) + g10[1] * fy
  const n01 = g01[0] * fx + g01[1] * (fy - 1.0)
  const n11 = g11[0] * (fx - 1.0) + g11[1] * (fy - 1.0)

  const u = fade(fx)
  const v = fade(fy)

  const bottom = n00 + (n10 - n00) * u
  const top = n01 + (n11 - n01) * u
  return bottom + (top - bottom) * v
}

const OCTAVE_SALT = 0x9e37n
const RIDGE_SALT = 0x85ebn

/**
 * Fractal summation, normalised to `[0, 1]`.
 *
 * Each octave gets a different seed rather than a different offset, so the octaves are
 * genuinely independent instead of being correlated copies of one field.
 */
export function fractal(
  seed: bigint,
  x: number,
  y: number,
  octaves = 4,
  frequency = 1.0,
  persistence = 0.5,
  lacunarity = 2.0,
): number {
  let total = 0.0
  let amplitude = 1.0
  let totalAmplitude = 0.0
  let current = frequency

  for (let octave = 0; octave < octaves; octave += 1) {
    total += gradientNoise(seed + BigInt(octave) * OCTAVE_SALT, x * current, y * current) * amplitude
    totalAmplitude += amplitude
    amplitude *= persistence
    current *= lacunarity
  }

  if (totalAmplitude === 0.0) return 0.5
  const normalised = (total / totalAmplitude) * 0.5 + 0.5
  // Clamp because gradient noise overshoots slightly at the diagonals.
  if (normalised < 0.0) return 0.0
  if (normalised > 1.0) return 1.0
  return normalised
}

/**
 * Ridged noise in `[0, 1]`, for cliff lines and river channels.
 *
 * Folding the absolute value produces creases where the underlying field crosses zero,
 * which reads as a ridge or a valley depending on which way it is used.
 */
export function ridged(seed: bigint, x: number, y: number, octaves = 3, frequency = 1.0): number {
  let total = 0.0
  let amplitude = 1.0
  let totalAmplitude = 0.0
  let current = frequency

  for (let octave = 0; octave < octaves; octave += 1) {
    const value = gradientNoise(seed + BigInt(octave) * RIDGE_SALT, x * current, y * current)
    const folded = 1.0 - (value >= 0.0 ? value : -value)
    total += folded * folded * amplitude
    totalAmplitude += amplitude
    amplitude *= 0.5
    current *= 2.0
  }

  if (totalAmplitude === 0.0) return 0.0
  const result = total / totalAmplitude
  if (result < 0.0) return 0.0
  if (result > 1.0) return 1.0
  return result
}

/**
 * A stable per-tile random number in `[0, 1)`.
 *
 * Used for scatter decisions, which want no spatial correlation at all: a tree should not
 * know that its neighbour is a tree.
 */
export function scatterValue(seed: bigint, tileX: number, tileY: number, salt = 0): number {
  return unitFloat(combine(seed, tileX, tileY, salt))
}
