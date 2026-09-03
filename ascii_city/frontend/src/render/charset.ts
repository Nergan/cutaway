/**
 * The glyph vocabulary of the city.
 *
 * Order matters only in that an index is what travels to the GPU; the sets
 * below exist so the raycaster can pick a character by intent ("a lit window",
 * "wet asphalt") instead of by magic number.
 */

export const CHARSET = [
  ' ', '.', ',', ':', ';', "'", '"', '`', '^', '~', '-', '_', '=', '+',
  '*', '#', '%', '&', '$', '@', '|', '/', '\\', '(', ')', '[', ']', '{',
  '}', '<', '>', '!', '?',
  // The full printable alphabet: nameplates carry player nicknames, and a
  // missing letter shows up as a dot in someone's name.
  '0', '1', '2', '3', '4', '5', '6', '7', '8', '9',
  'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M',
  'N', 'O', 'P', 'Q', 'R', 'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z',
  'a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l', 'm',
  'n', 'o', 'p', 'q', 'r', 's', 't', 'u', 'v', 'w', 'x', 'y', 'z',
  '\u2591', '\u2592', '\u2593', '\u2588', // light, medium, dark shade, full block
  '\u2584', '\u2580', '\u258c', '\u2590', // lower, upper, left, right half
  '\u25a0', '\u25a1', '\u25aa', '\u25ab', // squares
  '\u2500', '\u2502', '\u250c', '\u2510', // box drawing
  '\u2514', '\u2518', '\u251c', '\u2524',
  '\u252c', '\u2534', '\u253c', '\u2550',
  '\u2551', '\u2554', '\u2557', '\u255a',
  '\u255d', '\u2571', '\u2572', '\u2573',
  '\u00b7', '\u2022', '\u25cf', '\u25cb',
] as const

export const GLYPH_COUNT = CHARSET.length

const INDEX = new Map<string, number>(CHARSET.map((glyph, index) => [glyph, index]))

export function glyph(character: string): number {
  return INDEX.get(character) ?? 0
}

export const G_SPACE = glyph(' ')

/** Density ramp, darkest to brightest. Distance shading walks this. */
export const RAMP = [' ', '.', ':', '-', '=', '+', '*', '#', '%', '@'].map(glyph)

/** Shade blocks, lightest to solid. Used for facades and fog. */
export const SHADES = ['\u2591', '\u2592', '\u2593', '\u2588'].map(glyph)

/** Lit window glyphs, dimmest to brightest. */
export const WINDOWS = ['\u25ab', '\u25aa', '\u25a1', '\u25a0', '\u2588'].map(glyph)

/** Unlit window frames. */
export const WINDOW_DARK = ['\u00b7', '\u25ab', '\u2591'].map(glyph)

/** Vertical structure of a facade: pillars, ledges, corners. */
export const STRUCTURE = {
  pillar: glyph('\u2502'),
  ledge: glyph('\u2500'),
  cross: glyph('\u253c'),
  cornerLeft: glyph('\u250c'),
  cornerRight: glyph('\u2510'),
  double: glyph('\u2551'),
  slashLeft: glyph('\u2571'),
  slashRight: glyph('\u2572'),
}

/** Road surface, from centre line to kerb. */
export const ROAD_GLYPHS = {
  asphalt: [glyph(' '), glyph('.'), glyph(':')],
  marking: glyph('\u2500'),
  dash: glyph('-'),
  kerb: glyph('_'),
  sidewalk: [glyph('.'), glyph(':'), glyph(';')],
  grate: glyph('#'),
}

export const SKY_GLYPHS = {
  empty: G_SPACE,
  star: [glyph('.'), glyph('\u00b7'), glyph('*'), glyph('+')],
  haze: glyph('\u2591'),
}

/** The standing figure other players are drawn as, top row first. */
export const AVATAR_ROWS = [
  ['\u25cf'],
  ['/', '|', '\\'],
  [' ', '|', ' '],
  ['/', ' ', '\\'],
].map((row) => row.map(glyph))

export const ROOF_GLYPHS = {
  flat: glyph('\u2500'),
  gabled: glyph('^'),
  antenna: glyph('|'),
  beacon: glyph('\u25cf'),
}
