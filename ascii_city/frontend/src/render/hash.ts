/**
 * Cheap deterministic hashes for visual detail.
 *
 * Window lights, star fields and pavement grain must not shimmer when the
 * camera moves, so every detail is a pure function of its world coordinates
 * rather than of frame time or draw order.
 */

/** 32-bit integer hash of three coordinates, returned as 0..1. */
export function hash3(a: number, b: number, c: number): number {
  let h = (a | 0) * 0x27d4eb2d
  h = (h ^ ((b | 0) * 0x165667b1)) >>> 0
  h = (h ^ ((c | 0) * 0x9e3779b1)) >>> 0
  h = Math.imul(h ^ (h >>> 15), 0x2c1b3c6d) >>> 0
  h = Math.imul(h ^ (h >>> 12), 0x297a2d39) >>> 0
  h = (h ^ (h >>> 15)) >>> 0
  return h / 0x100000000
}

export function hash2(a: number, b: number): number {
  return hash3(a, b, 0x5bf0)
}
