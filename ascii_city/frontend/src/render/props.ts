/**
 * Street furniture.
 *
 * The generator has always emitted lamps, trees, kiosks and signage; this is
 * where they finally become visible. Each kind is a small ASCII stamp drawn as
 * a billboard, depth-tested against the wall pass so a lamp behind a tower
 * stays behind it.
 *
 * Props never affect collision. They are dressing, and dressing that stops you
 * walking is indistinguishable from a bug.
 */

import {
  FLOOR_STEP_M,
  isSolidCode,
  PROP_BANNER,
  PROP_BENCH,
  PROP_BOLLARD,
  PROP_KIOSK,
  PROP_LAMP,
  PROP_NPC,
  PROP_PLANTER,
  PROP_SIGN,
  PROP_STALL,
  PROP_TRAFFIC_LIGHT,
  PROP_TREE,
  PROP_VENDING,
} from '../domain/constants'
import type { WorldTile } from '../domain/types'
import { CellBuffer, EFFECT_GLOW, EFFECT_NONE } from './cellBuffer'
import {
  AVATAR_FACE_COLUMN,
  AVATAR_FACE_ROW,
  AVATAR_GLYPHS,
  AVATAR_ROWS,
  avatarGlyph,
  glyph,
  signWord,
} from './charset'
import { fade, mix, rgb, scale, type Rgb } from './palette'
import type { Camera } from './raycaster'

export interface WorldProp {
  x: number
  y: number
  /** Elevation of the ground it stands on, so it rides the terraces. */
  z: number
  kind: number
  /** Stable per-prop noise, so flicker and variant choice hold still. */
  seed: number
}

const FOG_DISTANCE_M = 90

/** Beyond this a one-metre bench is a single dim cell; not worth the cost. */
const PROP_VIEW_DISTANCE_M = 70

const LAMP_LIGHT: Rgb = rgb(0xffc879)
const SIGN_INK: readonly Rgb[] = [
  rgb(0xff5fa2),
  rgb(0x35e0ff),
  rgb(0xffd479),
  rgb(0x9fe86b),
  rgb(0xc792ea),
]

/**
 * One kind of street furniture.
 *
 * `art` reads top to bottom, and a space means "leave the world showing", so
 * the stamps stay legible as silhouettes rather than as rectangles.
 */
interface PropArt {
  heightM: number
  widthM: number
  art: readonly string[]
  ink: Rgb
  /** Rows at or above this index glow: the lit part of the object. */
  glowFrom: number
  /** Light the object throws onto the pavement, in metres of radius. */
  lightRadiusM: number
  lightInk: Rgb
}

const ART: Record<number, PropArt> = {
  [PROP_LAMP]: {
    heightM: 5.4,
    widthM: 1.1,
    art: [' \u2584 ', '\u2500\u2588\u2500', ' \u2502 ', ' \u2502 ', ' \u2502 ', ' \u2502 '],
    ink: rgb(0x4a4f58),
    glowFrom: 0,
    // Wide enough to reach the kerb, tight enough that neighbouring lamps read
    // as separate pools instead of one flat wash down the street.
    lightRadiusM: 5.5,
    lightInk: LAMP_LIGHT,
  },
  [PROP_TREE]: {
    heightM: 6.2,
    widthM: 3.4,
    art: [
      ' \u2591 ',
      '\u2591\u2592\u2591',
      '\u2592\u2593\u2592',
      '\u2591\u2592\u2591',
      ' \u2502 ',
      ' \u2502 ',
    ],
    ink: rgb(0x2f5540),
    glowFrom: 99,
    lightRadiusM: 0,
    lightInk: LAMP_LIGHT,
  },
  [PROP_KIOSK]: {
    heightM: 3.1,
    widthM: 2.6,
    art: ['\u2550\u2550\u2550', '\u2593\u25a0\u2593', '\u2502\u25aa\u2502'],
    ink: rgb(0x565059),
    glowFrom: 1,
    lightRadiusM: 5,
    lightInk: rgb(0xff8fbe),
  },
  [PROP_SIGN]: {
    heightM: 5.5,
    widthM: 1.4,
    // A lit board with writing down it, not a solid slab: the frame is what
    // keeps it reading as signage once it is scaled up close.
    art: [
      '\u250c\u2500\u2510',
      '\u2502\u00a7\u2502',
      '\u2502\u00b6\u2502',
      '\u2502\u203c\u2502',
      '\u2514\u2500\u2518',
    ],
    ink: rgb(0xff5fa2),
    glowFrom: 0,
    lightRadiusM: 6,
    lightInk: rgb(0xff5fa2),
  },
  [PROP_BENCH]: {
    heightM: 1.0,
    widthM: 2.0,
    art: ['\u2500\u2500\u2500', '\u2584\u2584\u2584', '\u2502 \u2502'],
    ink: rgb(0x4b4238),
    glowFrom: 99,
    lightRadiusM: 0,
    lightInk: LAMP_LIGHT,
  },
  [PROP_VENDING]: {
    heightM: 2.1,
    widthM: 1.3,
    art: ['\u250c\u2500\u2510', '\u2502\u25a0\u2502', '\u2502\u25aa\u2502', '\u2514\u2500\u2518'],
    ink: rgb(0x3c4a5c),
    glowFrom: 1,
    lightRadiusM: 5,
    lightInk: rgb(0x8fd8ff),
  },
  [PROP_TRAFFIC_LIGHT]: {
    heightM: 4.6,
    widthM: 1.2,
    art: [' \u25cf ', ' \u2502 ', ' \u2502 ', ' \u2502 ', ' \u2502 '],
    ink: rgb(0x3f444c),
    glowFrom: 0,
    lightRadiusM: 3,
    lightInk: rgb(0x6bff8f),
  },
  [PROP_BOLLARD]: {
    heightM: 0.9,
    widthM: 0.5,
    art: [' \u25aa ', ' \u2502 '],
    ink: rgb(0x585d66),
    glowFrom: 99,
    lightRadiusM: 0,
    lightInk: LAMP_LIGHT,
  },
  [PROP_PLANTER]: {
    heightM: 1.3,
    widthM: 1.8,
    art: ['\u2663\u2663\u2663', '\u2593\u2593\u2593'],
    ink: rgb(0x3d6247),
    glowFrom: 99,
    lightRadiusM: 0,
    lightInk: LAMP_LIGHT,
  },
  [PROP_STALL]: {
    heightM: 3.0,
    widthM: 3.2,
    art: ['\u2550\u2550\u2550\u2550\u2550', '\u25cf\u2500\u2500\u2500\u25cf', '\u2593\u2588\u2588\u2588\u2593', '\u2502 \u2591 \u2502'],
    ink: rgb(0x6a4038),
    glowFrom: 1,
    lightRadiusM: 7,
    lightInk: rgb(0xff9a5c),
  },
  [PROP_BANNER]: {
    heightM: 3.2,
    widthM: 0.8,
    art: [' \u2500 ', ' \u2593 ', ' \u00a7 ', ' \u2593 ', ' \u2502 '],
    ink: rgb(0xe0e8f0),
    glowFrom: 1,
    lightRadiusM: 2,
    lightInk: rgb(0xffd479),
  },
  [PROP_NPC]: {
    // A street with nobody on it reads as an evacuation. These do not move,
    // but at a distance a still figure is still a person.
    heightM: 1.8,
    widthM: 0.9,
    art: [],
    ink: rgb(0x8f9bb0),
    glowFrom: 99,
    lightRadiusM: 0,
    lightInk: LAMP_LIGHT,
  },
}

const FALLBACK = ART[PROP_BOLLARD]

/** Glyph indices, resolved once so the render loop never touches the map. */
const STAMPS = new Map<number, Int16Array[]>()
for (const [kind, art] of Object.entries(ART)) {
  STAMPS.set(
    Number(kind),
    art.art.map((row) => Int16Array.from([...row], (character) => glyph(character))),
  )
}

const G_BLANK = glyph(' ')
const FRAME = {
  topLeft: glyph('\u250c'),
  top: glyph('\u2500'),
  topRight: glyph('\u2510'),
  side: glyph('\u2502'),
  bottomLeft: glyph('\u2514'),
  bottomRight: glyph('\u2518'),
}

/** Built on demand, then kept: there are only ever a few dozen distinct signs. */
const LETTERED = new Map<string, Int16Array[]>()

/**
 * A sign with a word running down it.
 *
 * Boards get a frame so they read as a box bolted to a pole; banners do not,
 * because a banner is cloth.
 */
function letteredSign(seed: number, framed: boolean): Int16Array[] {
  const word = signWord(Math.floor(seed * 9973))
  const key = `${word.join()}|${framed}`
  const cached = LETTERED.get(key)
  if (cached) return cached

  const edge = framed ? FRAME.side : G_BLANK
  const rows: Int16Array[] = []
  if (framed) rows.push(Int16Array.of(FRAME.topLeft, FRAME.top, FRAME.topRight))
  for (const character of word) rows.push(Int16Array.of(edge, character, edge))
  if (framed) rows.push(Int16Array.of(FRAME.bottomLeft, FRAME.top, FRAME.bottomRight))
  LETTERED.set(key, rows)
  return rows
}

/** A pedestrian: the player figure, wearing whichever face their seed picks. */
function pedestrian(seed: number): Int16Array[] {
  const key = `npc${Math.floor(seed * AVATAR_GLYPHS.length)}`
  const cached = LETTERED.get(key)
  if (cached) return cached

  const face = avatarGlyph(Math.floor(seed * 997))
  const rows = AVATAR_ROWS.map((row, index) =>
    Int16Array.from(row, (character, column) =>
      index === AVATAR_FACE_ROW && column === AVATAR_FACE_COLUMN ? face : character,
    ),
  )
  LETTERED.set(key, rows)
  return rows
}

export function propArt(kind: number): PropArt {
  return ART[kind] ?? FALLBACK
}

/** Flatten every tile's prop list into world-space metres, once at load. */
export function collectProps(tiles: readonly WorldTile[], cellSize: number): WorldProp[] {
  const props: WorldProp[] = []
  for (const tile of tiles) {
    const originX = tile.tileX * tile.cells
    const originY = tile.tileY * tile.cells
    for (const prop of tile.props) {
      const cell = prop.y * tile.cells + prop.x
      const solid = isSolidCode(tile.collision[cell])
      props.push({
        x: (originX + prop.x + 0.5) * cellSize,
        y: (originY + prop.y + 0.5) * cellSize,
        // A bench on a terrace stands on the terrace, not sunk into it.
        z: solid ? 0 : tile.heights[cell] * FLOOR_STEP_M,
        kind: prop.kind,
        seed: ((prop.id * 2654435761) >>> 0) / 0x100000000,
      })
    }
  }
  return props
}

/**
 * Pavement lighting, baked once.
 *
 * A lamp that does not light anything is just a pole, so every emitting prop
 * smears a falloff into a per-cell buffer the floor pass reads. Baking is what
 * keeps it free: the alternative is a distance test per prop per floor cell.
 */
export function bakeLightMap(
  props: readonly WorldProp[],
  width: number,
  height: number,
  cellSize: number,
): Float32Array {
  const light = new Float32Array(width * height)
  for (const prop of props) {
    const art = propArt(prop.kind)
    if (art.lightRadiusM <= 0) continue
    const radius = art.lightRadiusM / cellSize
    const centreX = prop.x / cellSize - 0.5
    const centreY = prop.y / cellSize - 0.5
    const minX = Math.max(0, Math.floor(centreX - radius))
    const maxX = Math.min(width - 1, Math.ceil(centreX + radius))
    const minY = Math.max(0, Math.floor(centreY - radius))
    const maxY = Math.min(height - 1, Math.ceil(centreY + radius))
    for (let cy = minY; cy <= maxY; cy += 1) {
      for (let cx = minX; cx <= maxX; cx += 1) {
        const distance = Math.hypot(cx - centreX, cy - centreY) / radius
        if (distance >= 1) continue
        const falloff = (1 - distance) * (1 - distance)
        const index = cy * width + cx
        // Overlapping pools brighten, but saturate rather than blow out.
        light[index] = Math.min(1.4, light[index] + falloff)
      }
    }
  }
  return light
}

export function renderProps(
  buffer: CellBuffer,
  camera: Camera,
  props: readonly WorldProp[],
  fov: number,
  time: number,
): void {
  const { columns, rows } = buffer
  const half = columns / 2
  const tanHalfFov = Math.tan(fov / 2)
  const projColumns = half / tanHalfFov
  const projRows = projColumns * 0.5
  const horizon = rows * 0.5 + Math.tan(camera.pitch) * projRows

  const dirX = Math.cos(camera.yaw)
  const dirY = Math.sin(camera.yaw)
  const rightX = dirY
  const rightY = -dirX

  // One pass to find what is in front, then farthest first so nearer
  // furniture stamps over what it stands in front of.
  const visible: Array<{ prop: WorldProp; depth: number; lateral: number }> = []
  for (const prop of props) {
    const dx = prop.x - camera.x
    const dy = prop.y - camera.y
    const depth = dx * dirX + dy * dirY
    if (depth <= 0.4 || depth > PROP_VIEW_DISTANCE_M) continue
    const lateral = dx * rightX + dy * rightY
    // Cheap frustum reject before the expensive per-cell work.
    if (Math.abs(lateral) > depth * tanHalfFov * 1.6) continue
    visible.push({ prop, depth, lateral })
  }
  visible.sort((a, b) => b.depth - a.depth)

  for (const { prop, depth, lateral } of visible) {
    const art = propArt(prop.kind)
    const stamp =
      prop.kind === PROP_SIGN
        ? letteredSign(prop.seed, true)
        : prop.kind === PROP_BANNER
          ? letteredSign(prop.seed, false)
          : prop.kind === PROP_NPC
            ? pedestrian(prop.seed)
            : STAMPS.get(prop.kind)
    if (!stamp) continue

    const scaleRows = projRows / depth
    const feet = horizon + scaleRows * (camera.z - prop.z)
    const head = feet - scaleRows * art.heightM
    const heightRows = feet - head
    if (heightRows < 0.9) continue

    const centre = half * (1 + lateral / (depth * tanHalfFov))
    const widthColumns = Math.max(1, (projColumns * art.widthM) / depth)
    const left = Math.round(centre - widthColumns / 2)
    const right = Math.max(left, Math.round(centre + widthColumns / 2) - 1)
    const fogAmount = 1 - Math.exp(-depth / FOG_DISTANCE_M)

    let ink = art.ink
    let flicker = 1
    if (prop.kind === PROP_SIGN || prop.kind === PROP_BANNER) {
      ink = SIGN_INK[Math.floor(prop.seed * SIGN_INK.length) % SIGN_INK.length]
      // A tube that never falters reads as a texture, not as a light.
      flicker = prop.seed > 0.82 ? 0.55 + 0.45 * Math.abs(Math.sin(time * 9 + prop.seed * 20)) : 1
    } else if (prop.kind === PROP_TRAFFIC_LIGHT) {
      const phase = (time * 0.22 + prop.seed) % 1
      ink = phase < 0.55 ? rgb(0x6bff8f) : phase < 0.65 ? rgb(0xffd479) : rgb(0xff5b5b)
    }

    for (let column = left; column <= right; column += 1) {
      if (column < 0 || column >= columns) continue
      if (depth > buffer.depth[column]) continue
      const spanColumns = right - left
      const withinX = spanColumns === 0 ? 0.5 : (column - left) / spanColumns

      for (let row = Math.floor(head); row <= Math.ceil(feet); row += 1) {
        if (row < 0 || row >= rows) continue
        const withinY = (row - head) / Math.max(1e-3, heightRows)
        if (withinY < 0 || withinY > 1) continue

        const artRow = Math.min(stamp.length - 1, Math.floor(withinY * stamp.length))
        const line = stamp[artRow]
        const artColumn = Math.min(line.length - 1, Math.floor(withinX * line.length))
        const glyphIndex = line[artColumn]
        if (glyphIndex === 0) continue

        const emissive = artRow >= art.glowFrom
        const tint = emissive ? scale(ink, 1.25 * flicker) : scale(art.ink, 0.95)
        const foreground = fade(tint, fogAmount * 0.75)
        const at = (row * columns + column) * 8
        const behind: Rgb = [buffer.data[at + 5], buffer.data[at + 6], buffer.data[at + 7]]
        // Emissive parts bleed a little into their own backdrop, which is what
        // makes a sign look lit rather than painted.
        const background = emissive ? mix(behind, fade(ink, fogAmount), 0.22) : behind

        buffer.set(
          column,
          row,
          glyphIndex,
          foreground[0],
          foreground[1],
          foreground[2],
          background[0],
          background[1],
          background[2],
          emissive ? EFFECT_GLOW : EFFECT_NONE,
        )
      }
    }
  }
}
