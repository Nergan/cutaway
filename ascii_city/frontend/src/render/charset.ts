/**
 * The glyph vocabulary of the city.
 *
 * Order matters only in that an index is what travels to the GPU; the sets
 * below exist so the raycaster can pick a character by intent ("a lit window",
 * "wet asphalt") instead of by magic number.
 */

/**
 * Kana and kanji for shop signage.
 *
 * Katakana carry most of the load because their strokes survive being squeezed
 * into a half-width atlas cell; the kanji here are the handful the district's
 * vocabulary actually needs.
 */
const KATAKANA = [
  '\u30a2', '\u30ab', '\u30b1', '\u30b3', '\u30b5', '\u30b7', '\u30b9',
  '\u30c6', '\u30c8', '\u30ca', '\u30cb', '\u30d0', '\u30d3', '\u30db',
  '\u30de', '\u30df', '\u30e0', '\u30e1', '\u30e2', '\u30e9', '\u30ea',
  '\u30eb', '\u30ec', '\u30ed', '\u30f3', '\u30fc', '\u30aa', '\u30e4',
] as const

const KANJI = [
  '\u5c45', '\u9152', '\u5c4b', '\u85ac', '\u5c40', '\u9280', '\u884c',
  '\u66f8', '\u5e97', '\u5599', '\u8336', '\u5bff', '\u53f8', '\u6e29',
  '\u6cc9', '\u4ea4', '\u756a', '\u96fb', '\u6c17', '\u53e4', '\u7740',
  '\u713c', '\u8089', '\u9eba', '\u6e6f', '\u672c', '\u6771', '\u4eac',
  '\u65b0', '\u5bbf', '\u6e0b', '\u8c37', '\u79cb', '\u8449', '\u539f',
  '\u51fa', '\u5165', '\u53e3', '\u99c5', '\u5927', '\u4e2d', '\u5c0f',
] as const

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
  // Avatar faces. Every one of these is a CP437 codepoint, so any monospace
  // font that can draw the box-drawing set above can draw these too.
  '\u263a', '\u263b', '\u2665', '\u2666', '\u2663', '\u2660',
  '\u2642', '\u2640', '\u266a', '\u266b', '\u263c', '\u25ba',
  '\u25c4', '\u25b2', '\u25bc', '\u25d8', '\u25d9', '\u2605',
  '\u2606', '\u2302', '\u00a7', '\u00b6', '\u203c', '\u2195',
  // Signage. Every shopfront in the district is lettered from this set, so it
  // covers the words in SIGN_WORDS and nothing else — an unused glyph is an
  // atlas cell and a texture fetch that never pays for itself.
  ...KATAKANA,
  ...KANJI,
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

/**
 * The faces a player can wear. Index into this is what travels on the wire, so
 * the order has to match `PLAYER_AVATAR_COUNT` on the server and may only ever
 * grow at the end.
 */
export const AVATAR_FACES = [
  '\u263a', '\u263b', '\u2665', '\u2666', '\u2663', '\u2660',
  '\u2642', '\u2640', '\u266a', '\u266b', '\u263c', '\u25ba',
  '\u25c4', '\u25b2', '\u25bc', '\u25d8', '\u25d9', '\u2605',
  '\u2606', '\u2302', '\u00a7', '\u00b6', '\u203c', '\u2195',
] as const

export const AVATAR_GLYPHS = AVATAR_FACES.map(glyph)

export function avatarFace(index: number): string {
  const count = AVATAR_FACES.length
  return AVATAR_FACES[((index % count) + count) % count]
}

export function avatarGlyph(index: number): number {
  const count = AVATAR_GLYPHS.length
  return AVATAR_GLYPHS[((index % count) + count) % count]
}

/**
 * The standing figure a player is drawn as.
 *
 * The head is a drawn box with the player's chosen face inside it. Giving the
 * face a frame is what makes the choice legible: a bare glyph floating above a
 * stick figure reads as noise at any distance, whereas a boxed one reads as a
 * head wearing that face.
 *
 * The stamp is mostly blank on purpose. It is stretched over however many
 * screen cells the figure projects onto, and a dense stamp seen from two
 * metres away magnifies into a solid slab.
 */
export const AVATAR_ROWS = [
  ' \u250c\u2500\u2510 ',
  ' \u2502.\u2502 ',
  ' \u2514\u252c\u2518 ',
  ' /|\\ ',
  '  |  ',
  ' / \\ ',
  '/   \\',
].map((row) => [...row].map(glyph))

/** Where in {@link AVATAR_ROWS} the player's chosen face is stamped. */
export const AVATAR_FACE_ROW = 1
export const AVATAR_FACE_COLUMN = 2

/**
 * What the signs say.
 *
 * Written top to bottom, the way a Tokyo shopfront hangs them. Which word a
 * sign gets is a function of its id, so the district reads the same on every
 * machine and the wire carries no text at all.
 */
export const SIGN_WORDS: readonly number[][] = [
  '\u30e9\u30fc\u30e1\u30f3', // ramen
  '\u5c45\u9152\u5c4b', // izakaya
  '\u85ac\u5c40', // pharmacy
  '\u30ab\u30e9\u30aa\u30b1', // karaoke
  '\u9280\u884c', // bank
  '\u66f8\u5e97', // bookshop
  '\u5599\u8336', // tearoom
  '\u5bff\u53f8', // sushi
  '\u6e29\u6cc9', // hot spring
  '\u30db\u30c6\u30eb', // hotel
  '\u30b3\u30f3\u30d3\u30cb', // convenience store
  '\u4ea4\u756a', // police box
  '\u96fb\u6c17', // electrics
  '\u53e4\u7740', // second-hand clothes
  '\u713c\u8089', // grilled meat
  '\u30d0\u30fc', // bar
  '\u9eba', // noodles
  '\u6e6f', // bathhouse
  '\u9152', // sake
  '\u672c', // books
  '\u6771\u4eac', // Tokyo
  '\u65b0\u5bbf', // Shinjuku
  '\u6e0b\u8c37', // Shibuya
  '\u79cb\u8449\u539f', // Akihabara
  '\u51fa\u53e3', // way out
  '\u5165\u53e3', // way in
  '\u99c5', // station
  '\u5927\u30bb\u30fc\u30eb', // big sale
].map((word) => [...word].map(glyph))

/** Deterministic pick, so the same sign says the same thing to everybody. */
export function signWord(seed: number): number[] {
  const count = SIGN_WORDS.length
  return SIGN_WORDS[((seed % count) + count) % count]
}

export const ROOF_GLYPHS = {
  flat: glyph('\u2500'),
  gabled: glyph('^'),
  antenna: glyph('|'),
  beacon: glyph('\u25cf'),
}
