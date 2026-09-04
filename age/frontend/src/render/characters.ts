/**
 * Character art, fetched per appearance and sliced into frames.
 *
 * Characters are not in the atlas, and cannot be: their look is five bytes of appearance, and
 * baking every combination would produce a page the size of the world. So each distinct
 * appearance is one request for one grid — all three facings by all four poses — which the
 * browser then caches for an hour.
 *
 * The grid's layout comes from the atlas index rather than from a constant here. It is the
 * same `POSE_FRAMES` table the Python generator owns, and a copy in TypeScript would be one
 * more thing to keep in step for no benefit.
 */

import { Assets, Rectangle, Texture, type TextureSource } from 'pixi.js'

import type { Appearance } from '../net/wire'
import type { CharacterGrid } from './atlas'

/** Matches `age.atelier.character.Facing`. `SIDE` is drawn once and mirrored. */
export const Facing = { DOWN: 0, SIDE: 1, UP: 2 } as const

/** Matches `age.atelier.character.Pose`. */
export const Pose = { IDLE: 0, WALK: 1, ATTACK: 2, HURT: 3 } as const

/** The grid description the atlas index publishes. */
export type CharacterLayout = CharacterGrid

/** One appearance's frames, ready to draw. */
export interface CharacterSheet {
  colour: Texture[][]
  normal: Texture[][]
  width: number
  height: number
}

/** The five appearance bytes as a cache key and a query string. */
function appearanceKey(appearance: Appearance): string {
  return `${appearance.body}.${appearance.hair}.${appearance.palette}.${appearance.outfit}.${appearance.accent}`
}

function query(appearance: Appearance, normals: boolean): string {
  const parts = [
    `body=${appearance.body}`,
    `hair=${appearance.hair}`,
    `palette=${appearance.palette}`,
    `outfit=${appearance.outfit}`,
    `accent=${appearance.accent}`,
  ]
  if (normals) parts.push('normals=true')
  return parts.join('&')
}

/**
 * A lazily-filled cache of character sheets.
 *
 * Sheets arrive asynchronously, so a caller that asks for one it has never seen gets
 * `undefined` and is expected to draw something else for a frame or two. The alternative —
 * awaiting art inside the render loop — would stall the whole scene for one newcomer.
 */
export class CharacterCache {
  private readonly sheets = new Map<string, CharacterSheet>()
  private readonly inFlight = new Set<string>()

  /** Appearances that failed to load, so a broken one is not retried every frame. */
  private readonly failed = new Set<string>()

  constructor(
    private readonly base: string,
    private readonly layout: CharacterLayout,
  ) {}

  /**
   * The sheet for an appearance, requesting it if absent.
   *
   * Deliberately not async. The renderer calls this once per visible entity per frame and
   * needs an answer now; the request it kicks off resolves into the cache for a later frame.
   */
  get(appearance: Appearance): CharacterSheet | undefined {
    const key = appearanceKey(appearance)
    const found = this.sheets.get(key)
    if (found !== undefined) return found
    if (!this.inFlight.has(key) && !this.failed.has(key)) void this.fetch(key, appearance)
    return undefined
  }

  /** Await an appearance, for the one case that can afford to: the local player at spawn. */
  async prime(appearance: Appearance): Promise<CharacterSheet | undefined> {
    const key = appearanceKey(appearance)
    const found = this.sheets.get(key)
    if (found !== undefined) return found
    if (this.failed.has(key)) return undefined
    await this.fetch(key, appearance)
    return this.sheets.get(key)
  }

  private async fetch(key: string, appearance: Appearance): Promise<void> {
    this.inFlight.add(key)
    try {
      const [colour, normal] = await Promise.all([
        Assets.load<Texture>({
          src: `${this.base}/atelier/character-sheet.png?${query(appearance, false)}`,
          data: { scaleMode: 'nearest', autoGenerateMipmaps: false },
        }),
        Assets.load<Texture>({
          src: `${this.base}/atelier/character-sheet.png?${query(appearance, true)}`,
          data: { scaleMode: 'nearest', autoGenerateMipmaps: false },
        }),
      ])
      this.sheets.set(key, this.slice(colour.source, normal.source))
    } catch (error) {
      // A missing sheet degrades to whatever the caller draws instead. Logged once, because
      // the same appearance asked for every frame would flood the console.
      console.warn(`Age: character art for ${key} did not load`, error)
      this.failed.add(key)
    } finally {
      this.inFlight.delete(key)
    }
  }

  private slice(colourSource: TextureSource, normalSource: TextureSource): CharacterSheet {
    const { width, height, facings, poseFrames, columns } = this.layout
    const rows = facings * poseFrames.length

    const colour: Texture[][] = []
    const normal: Texture[][] = []

    for (let row = 0; row < rows; row += 1) {
      // Only the frames the pose actually has. Reading the empty tail of a short pose's row
      // would draw a transparent rectangle, which looks exactly like a vanished player.
      const count = poseFrames[row % poseFrames.length] ?? 1
      const colourRow: Texture[] = []
      const normalRow: Texture[] = []
      for (let column = 0; column < Math.min(count, columns); column += 1) {
        const frame = new Rectangle(column * width, row * height, width, height)
        colourRow.push(new Texture({ source: colourSource, frame }))
        normalRow.push(new Texture({ source: normalSource, frame: frame.clone() }))
      }
      colour.push(colourRow)
      normal.push(normalRow)
    }

    return { colour, normal, width, height }
  }

  /** Which grid row holds a facing and pose. */
  row(facing: number, pose: number): number {
    const poses = this.layout.poseFrames.length
    return facing * poses + (pose % poses)
  }

  frameCount(pose: number): number {
    return this.layout.poseFrames[pose % this.layout.poseFrames.length] ?? 1
  }

  get spriteWidth(): number {
    return this.layout.width
  }

  get spriteHeight(): number {
    return this.layout.height
  }
}

/**
 * Which facing to draw, and whether to mirror it, for an angle in radians.
 *
 * Three drawn facings cover four directions because left and right are the same sprite
 * flipped. Screen space here: `+y` is down, so an angle near `+pi/2` is walking towards the
 * camera. The thresholds are at 45 degrees, which makes diagonal movement pick the axis it
 * is closer to rather than favouring one.
 */
export function facingFor(angle: number): { facing: number; mirrored: boolean } {
  const wrapped = ((angle % (Math.PI * 2)) + Math.PI * 2) % (Math.PI * 2)
  const eighth = Math.PI / 4

  if (wrapped < eighth || wrapped >= eighth * 7) return { facing: Facing.SIDE, mirrored: false }
  if (wrapped < eighth * 3) return { facing: Facing.DOWN, mirrored: false }
  if (wrapped < eighth * 5) return { facing: Facing.SIDE, mirrored: true }
  return { facing: Facing.UP, mirrored: false }
}

/**
 * Which animation frame to show.
 *
 * Walk speed drives the cycle so a run does not shuffle: the phase advances with distance
 * covered rather than with time, which is what makes footfalls land where the feet are.
 */
export function animationFrame(
  pose: number,
  frames: number,
  elapsedSeconds: number,
  distanceTiles: number,
): number {
  if (frames <= 1) return 0
  if (pose === Pose.WALK) {
    // One full four-frame cycle per two tiles walked.
    return Math.floor(distanceTiles * (frames / 2)) % frames
  }
  // Idle and the rest run on a clock. 6 fps: slow enough to read as pixel art.
  return Math.floor(elapsedSeconds * 6) % frames
}
