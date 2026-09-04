/**
 * The other people in the street.
 *
 * Avatars are billboarded glyph stamps depth-tested against the wall pass, so
 * someone standing behind a tower is correctly hidden by it. Nameplates only
 * appear once a player is close enough for the text to be readable.
 */

import { ANIMATION_IDLE, ANIMATION_RUN, EYE_HEIGHT_M } from '../domain/constants'
import {
  AVATAR_FACE_COLUMN,
  AVATAR_FACE_ROW,
  AVATAR_ROWS,
  CHARSET,
  G_SPACE,
  avatarGlyph,
} from './charset'
import { CellBuffer, EFFECT_GLOW } from './cellBuffer'
import { fade, mix, playerColor, scale, type Rgb } from './palette'
import type { Camera } from './raycaster'

export interface Sprite {
  id: number
  x: number
  y: number
  /** Eye height above the world floor, so a jump lifts the figure. */
  z: number
  animation: number
  nickname: string
  color: number
  avatar: number
}

const AVATAR_HEIGHT_M = 1.8
const AVATAR_WIDTH_M = 0.9
const NAMEPLATE_DISTANCE_M = 42

/** At most three screen cells per stamp cell. Beyond that a glyph is a slab. */
const MAX_STAMP_ROWS = 7 * 3

/**
 * How far a name still carries once its owner is behind something. Names do
 * punch through walls, the way they do in Minecraft, but only close enough
 * that the information is about the room you are in rather than the district.
 */
const OCCLUDED_NAMEPLATE_DISTANCE_M = 16

const FOG_DISTANCE_M = 90

/** What a body's own shadow leaves of whatever it stands in front of. */
const SHADOW: Rgb = [6, 9, 14]

export function renderSprites(
  buffer: CellBuffer,
  camera: Camera,
  sprites: Sprite[],
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

  // Farthest first, so a nearer avatar stamps over one behind it.
  const ordered = sprites
    .map((sprite) => {
      const dx = sprite.x - camera.x
      const dy = sprite.y - camera.y
      return { sprite, depth: dx * dirX + dy * dirY, lateral: dx * rightX + dy * rightY }
    })
    .filter((entry) => entry.depth > 0.5)
    .sort((a, b) => b.depth - a.depth)

  for (const { sprite, depth, lateral } of ordered) {
    const centre = half * (1 + lateral / (depth * tanHalfFov))
    const scaleRows = projRows / depth
    // A jumping player leaves the ground, and their figure has to leave it too.
    const standingOn = sprite.z - EYE_HEIGHT_M
    const feet = horizon + scaleRows * (camera.z - standingOn)
    const head = feet - scaleRows * AVATAR_HEIGHT_M
    let heightRows = feet - head
    if (heightRows < 1.2) continue

    // Past a few metres the stamp is stretched over so many cells that each of
    // its glyphs becomes a slab and the face stops being a face. Capping the
    // magnification keeps the figure crisp, and the chosen face readable.
    let shrink = 1
    if (heightRows > MAX_STAMP_ROWS) {
      shrink = MAX_STAMP_ROWS / heightRows
      heightRows = MAX_STAMP_ROWS
    }

    const widthColumns = Math.max(1, ((projColumns * AVATAR_WIDTH_M) / depth) * shrink)
    const left = Math.round(centre - widthColumns / 2)
    const right = Math.round(centre + widthColumns / 2)
    const fogAmount = 1 - Math.exp(-depth / FOG_DISTANCE_M)
    const base = playerColor(sprite.color)
    // A subtle bob so a walking figure is distinguishable from a standing one.
    const bob =
      sprite.animation === ANIMATION_IDLE
        ? 0
        : Math.sin(time * (sprite.animation === ANIMATION_RUN ? 11 : 7) + sprite.id) * 0.35

    for (let column = left; column <= right; column += 1) {
      if (column < 0 || column >= columns) continue
      if (depth > buffer.depth[column]) continue
      const withinX = widthColumns <= 1 ? 0.5 : (column - left) / (right - left || 1)
      const lastColumn = AVATAR_ROWS[0].length - 1
      const glyphColumn = Math.min(lastColumn, Math.max(0, Math.round(withinX * lastColumn)))

      for (let row = Math.floor(head + bob); row <= Math.ceil(head + bob + heightRows); row += 1) {
        if (row < 0 || row >= rows) continue
        const withinY = (row - (head + bob)) / Math.max(1, heightRows)
        if (withinY < 0 || withinY > 1) continue
        const glyphRow = Math.min(
          AVATAR_ROWS.length - 1,
          Math.floor(withinY * AVATAR_ROWS.length),
        )
        const stamp = AVATAR_ROWS[glyphRow]
        // One cell of the stamp is the head, and that is where the chosen face
        // goes. Everything else is the body.
        const glyphIndex =
          glyphRow === AVATAR_FACE_ROW && glyphColumn === AVATAR_FACE_COLUMN
            ? avatarGlyph(sprite.avatar)
            : stamp[Math.min(stamp.length - 1, glyphColumn)]
        if (glyphIndex === G_SPACE) continue

        const foreground = fade(scale(base, 1.15), fogAmount * 0.7)
        const at = (row * columns + column) * 8
        // A body blocks the light behind it. Without this the figure vanishes
        // the moment it crosses a lit shopfront, which is most of the street.
        const behind = mix(
          [buffer.data[at + 5], buffer.data[at + 6], buffer.data[at + 7]],
          SHADOW,
          0.72,
        )
        buffer.set(
          column,
          row,
          glyphIndex,
          foreground[0],
          foreground[1],
          foreground[2],
          behind[0],
          behind[1],
          behind[2],
          EFFECT_GLOW,
        )
      }
    }

    const centreColumn = Math.round(centre)
    const occluded =
      centreColumn < 0 || centreColumn >= columns || depth > buffer.depth[centreColumn]
    const reach = occluded ? OCCLUDED_NAMEPLATE_DISTANCE_M : NAMEPLATE_DISTANCE_M
    if (depth < reach) {
      drawNameplate(
        buffer,
        sprite.nickname,
        centreColumn,
        Math.floor(head + bob) - 1,
        base,
        occluded,
      )
    }
  }
}

function drawNameplate(
  buffer: CellBuffer,
  nickname: string,
  centre: number,
  row: number,
  color: Rgb,
  occluded: boolean,
): void {
  if (row < 0 || row >= buffer.rows) return
  const text = nickname.length > 18 ? `${nickname.slice(0, 17)}\u2026` : nickname
  const start = centre - Math.floor(text.length / 2)
  // Seen through a wall a name is dimmer and loses its bloom, so the two cases
  // stay distinguishable at a glance.
  const ink = occluded ? mix(color, [10, 16, 22], 0.55) : color
  const effect = occluded ? 0 : EFFECT_GLOW
  for (let index = 0; index < text.length; index += 1) {
    const column = start + index
    if (column < 0 || column >= buffer.columns) continue
    buffer.set(column, row, asciiGlyph(text[index]), ink[0], ink[1], ink[2], 4, 7, 12, effect)
  }
}

const ASCII_TABLE = buildAsciiTable()

function buildAsciiTable(): Int16Array {
  const table = new Int16Array(128).fill(-1)
  CHARSET.forEach((character, index) => {
    const code = character.charCodeAt(0)
    if (code < 128) table[code] = index
  })
  return table
}

/** Nicknames are ASCII by construction; anything else becomes a dot. */
function asciiGlyph(character: string): number {
  const code = character.charCodeAt(0)
  const found = code < 128 ? ASCII_TABLE[code] : -1
  return found >= 0 ? found : 1
}
