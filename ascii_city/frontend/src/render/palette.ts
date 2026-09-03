/**
 * The night palette.
 *
 * Everything is dark and cold except the light people made: windows, signage
 * and street lamps. Colours are packed as 0xRRGGBB and unpacked straight into
 * the cell buffer, so no allocation happens in the render loop.
 */

import {
  CATEGORY_APARTMENT,
  CATEGORY_HOUSE,
  CATEGORY_OFFICE,
  CATEGORY_OTHER,
  CATEGORY_SHOP,
  CATEGORY_SKYSCRAPER,
  CATEGORY_STATION,
  CATEGORY_WAREHOUSE,
  PLAYER_COLOR_COUNT,
} from '../domain/constants'

export type Rgb = readonly [number, number, number]

export function rgb(hex: number): Rgb {
  return [(hex >> 16) & 0xff, (hex >> 8) & 0xff, hex & 0xff]
}

export const VOID: Rgb = rgb(0x04070a)
export const FOG: Rgb = rgb(0x070b14)

export const SKY_HIGH: Rgb = rgb(0x05070f)
export const SKY_LOW: Rgb = rgb(0x141033)
/** The city's own light bouncing off the smog layer. */
export const SKY_GLOW: Rgb = rgb(0x3a1c4a)
export const STAR: Rgb = rgb(0x9fb6d8)

export const GROUND_ASPHALT: Rgb = rgb(0x161c26)
export const GROUND_SIDEWALK: Rgb = rgb(0x1e242e)
export const GROUND_MARKING: Rgb = rgb(0x5c6b7f)
export const GROUND_WET: Rgb = rgb(0x1a3040)

/** Structural colour per building category: the concrete, not the lights. */
export const FACADE: readonly Rgb[] = [
  rgb(0x2a2f33), // house
  rgb(0x33292c), // shop
  rgb(0x2b2f3a), // apartment
  rgb(0x252d38), // office
  rgb(0x1f2a36), // skyscraper
  rgb(0x2c2c28), // warehouse
  rgb(0x33302a), // station
  rgb(0x2a2a2e), // other
]

/** Neon accent per category: signage, window light, edge glow. */
export const NEON: readonly Rgb[] = [
  rgb(0xffcf8a), // house: warm domestic light
  rgb(0xff5fa2), // shop: pink signage
  rgb(0xffb45f), // apartment: sodium lamps
  rgb(0x62b8ff), // office: cold fluorescents
  rgb(0x35e0ff), // skyscraper: cyan
  rgb(0x9fe86b), // warehouse: sickly green
  rgb(0xff8a3d), // station: amber
  rgb(0x7ef7c8), // other: mint
]

export const CATEGORY_ORDER = [
  CATEGORY_HOUSE,
  CATEGORY_SHOP,
  CATEGORY_APARTMENT,
  CATEGORY_OFFICE,
  CATEGORY_SKYSCRAPER,
  CATEGORY_WAREHOUSE,
  CATEGORY_STATION,
  CATEGORY_OTHER,
] as const

/** Player colours, chosen to stay legible against the night. */
export const PLAYER_COLORS: readonly Rgb[] = [
  rgb(0x7ef7c8),
  rgb(0xffd479),
  rgb(0xff7ad9),
  rgb(0x62b8ff),
  rgb(0x9fe86b),
  rgb(0xff8a3d),
  rgb(0x35e0ff),
  rgb(0xf25f5c),
  rgb(0xc792ea),
  rgb(0xffe66d),
  rgb(0x6dd3ce),
  rgb(0xf4a6c0),
]

export function playerColor(index: number): Rgb {
  return PLAYER_COLORS[((index % PLAYER_COLOR_COUNT) + PLAYER_COLOR_COUNT) % PLAYER_COLOR_COUNT]
}

/** Blend towards fog. `amount` of 1 is fully fogged. */
export function fade(color: Rgb, amount: number, target: Rgb = FOG): Rgb {
  const a = amount < 0 ? 0 : amount > 1 ? 1 : amount
  return [
    color[0] + (target[0] - color[0]) * a,
    color[1] + (target[1] - color[1]) * a,
    color[2] + (target[2] - color[2]) * a,
  ]
}

export function scale(color: Rgb, factor: number): Rgb {
  return [
    Math.min(255, color[0] * factor),
    Math.min(255, color[1] * factor),
    Math.min(255, color[2] * factor),
  ]
}

export function mix(a: Rgb, b: Rgb, alpha: number): Rgb {
  return [
    a[0] + (b[0] - a[0]) * alpha,
    a[1] + (b[1] - a[1]) * alpha,
    a[2] + (b[2] - a[2]) * alpha,
  ]
}
