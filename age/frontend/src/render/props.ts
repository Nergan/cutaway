/**
 * Everything that stands up out of the ground: trees, walls, lanterns, players, NPCs.
 *
 * Two problems this layer exists to solve.
 *
 * The first is depth. A tree at the top of the screen is behind a player at the bottom, and a
 * tree at the bottom is in front. That ordering changes as anything moves, so it is resolved
 * per frame by sorting on the world `y` of each sprite's base. Getting it wrong is the
 * difference between a world and a set of decals.
 *
 * The second is churn. The set of visible props changes constantly as the camera moves, and
 * creating a `Sprite` per prop per frame would allocate thousands of objects a second. So
 * sprites are pooled and re-pointed, and the pool is only trimmed when it is clearly too big.
 */

import { Container, Sprite, type Texture } from 'pixi.js'

import { CHUNK_TILES, ENTITY_NPC, ENTITY_PLAYER, TILE_SIZE_PX } from '../domain/constants'
import type { RemoteEntity } from '../net/session'
import type { Atlas } from './atlas'
import { animationFrame, facingFor, Pose, type CharacterCache } from './characters'

/** One drawn thing, in world pixels, with its two textures. */
export interface Billboard {
  colour: Texture
  normal: Texture | undefined
  /** Left edge, world pixels. */
  x: number
  /** Top edge, world pixels. */
  y: number
  /** The row used for depth sorting: where the sprite touches the ground. */
  baseY: number
  mirrored: boolean
  /** Multiplied into the sprite. Used to grey out corpses and flash on hit. */
  tint: number
  alpha: number
}

/**
 * A pooled pair of sprites — one on the colour layer, one on the normal layer.
 *
 * Both layers must draw the same geometry in the same order, or the lighting pass would
 * light pixels using a neighbour's normals. Keeping them in one object is the cheapest way
 * to guarantee it.
 */
class Pair {
  readonly colour = new Sprite()
  readonly normal = new Sprite()

  constructor() {
    this.colour.anchor.set(0, 0)
    this.normal.anchor.set(0, 0)
  }

  apply(billboard: Billboard, neutralNormal: Texture): void {
    this.colour.texture = billboard.colour
    this.normal.texture = billboard.normal ?? neutralNormal

    const width = billboard.colour.width
    for (const sprite of [this.colour, this.normal]) {
      // Mirroring by negative scale keeps one texture doing both sides. The x shift is
      // because a negative scale flips around the anchor, which would otherwise move the
      // sprite a full width to the left.
      sprite.scale.x = billboard.mirrored ? -1 : 1
      sprite.position.set(billboard.mirrored ? billboard.x + width : billboard.x, billboard.y)
      sprite.alpha = billboard.alpha
    }
    this.colour.tint = billboard.tint
  }

  destroy(): void {
    this.colour.destroy()
    this.normal.destroy()
  }
}

/** How many spare pairs to keep. Roughly a screenful of props plus a raid's worth of players. */
const POOL_LIMIT = 512

export class PropLayer {
  readonly colourRoot = new Container()
  readonly normalRoot = new Container()

  private readonly live: Pair[] = []
  private readonly pool: Pair[] = []
  private readonly billboards: Billboard[] = []

  constructor(
    private readonly atlas: Atlas,
    private readonly characters: CharacterCache,
    /** Drawn where a sprite has no normal map: a flat surface facing the viewer. */
    private readonly neutralNormal: Texture,
  ) {}

  /** Start a frame. Cheap: the array keeps its capacity between frames. */
  begin(): void {
    this.billboards.length = 0
  }

  /**
   * Queue the standing props of one chunk.
   *
   * `tiles` is the chunk's tile array as the tilemap last read it, so this walks memory the
   * tilemap has already paid to fetch rather than asking the store again.
   */
  addChunkProps(tiles: Uint8Array, originX: number, originY: number, frame: number): void {
    for (let index = 0; index < tiles.length; index += 1) {
      const key = this.atlas.propFor(tiles[index])
      if (key === undefined) continue

      const sprite = this.atlas.get(key)
      if (sprite === undefined) continue

      const tileX = index % CHUNK_TILES
      const tileY = (index - tileX) / CHUNK_TILES
      const baseY = originY + (tileY + 1) * TILE_SIZE_PX

      this.billboards.push({
        colour: sprite.colour[frame % sprite.colour.length],
        normal: sprite.normal[frame % sprite.normal.length],
        x: originX + tileX * TILE_SIZE_PX,
        // Props hang above the cell they grow from, and `anchorY` is how far below the tile's
        // bottom edge the sprite continues — a fence post that sinks into the ground.
        y: baseY - sprite.height + sprite.anchorY,
        baseY,
        mirrored: false,
        tint: 0xffffff,
        alpha: 1,
      })
    }
  }

  /** Queue a piece of hand-placed decor: a lantern, a campfire, a banner. */
  addDecor(key: string, worldX: number, worldY: number, frame: number): void {
    const sprite = this.atlas.get(key)
    if (sprite === undefined) return

    const baseY = worldY
    this.billboards.push({
      colour: sprite.colour[frame % sprite.colour.length],
      normal: sprite.normal[frame % sprite.normal.length],
      x: worldX - sprite.width / 2,
      y: baseY - sprite.height + sprite.anchorY,
      baseY,
      mirrored: false,
      tint: 0xffffff,
      alpha: 1,
    })
  }

  /**
   * Queue a character.
   *
   * `elapsed` drives clock-based animation and `distance` drives the walk cycle, so a running
   * player's feet move at the speed they are actually travelling.
   */
  addCharacter(
    appearance: Parameters<CharacterCache['get']>[0],
    worldX: number,
    worldY: number,
    facingAngle: number,
    pose: number,
    elapsed: number,
    distance: number,
    tint = 0xffffff,
    alpha = 1,
  ): void {
    const sheet = this.characters.get(appearance)
    if (sheet === undefined) return

    const { facing, mirrored } = facingFor(facingAngle)
    const row = this.characters.row(facing, pose)
    const frames = sheet.colour[row]
    if (frames === undefined || frames.length === 0) return

    const at = animationFrame(pose, frames.length, elapsed, distance)
    const baseY = worldY

    this.billboards.push({
      colour: frames[at],
      normal: sheet.normal[row]?.[at],
      // Characters are positioned by the point between their feet, which is the same point
      // the simulation moves. Anything else and the sprite would drift out of its hitbox.
      x: worldX - sheet.width / 2,
      y: baseY - sheet.height,
      baseY,
      mirrored,
      tint,
      alpha,
    })
  }

  /** Queue a remote entity from its last interpolated pose. */
  addEntity(entity: RemoteEntity, elapsed: number, distance: number): void {
    if (entity.kind !== ENTITY_PLAYER && entity.kind !== ENTITY_NPC) return

    // Dead entities stay drawn for the few seconds before the server despawns them, greyed
    // and half-faded: a body that vanishes the instant it dies makes a kill feel like it did
    // not happen.
    const dead = !isAlive(entity.state) || entity.health <= 0
    this.addCharacter(
      entity.appearance,
      entity.pose.x * TILE_SIZE_PX,
      entity.pose.y * TILE_SIZE_PX,
      entity.pose.facing,
      poseFor(entity.state, entity.pose.speed),
      elapsed,
      distance,
      dead ? 0x707888 : 0xffffff,
      dead ? 0.55 : 1,
    )
  }

  /**
   * Sort by depth and hand the result to the display list.
   *
   * The sort is on base row, with `x` as a tiebreak so two things on the same row do not
   * swap order between frames and flicker.
   */
  flush(): void {
    this.billboards.sort((a, b) => a.baseY - b.baseY || a.x - b.x)

    // Grow to fit, then re-point. Children are added once and reused, so the display list's
    // order matches the sorted order without any per-frame reparenting.
    while (this.live.length < this.billboards.length) {
      const pair = this.pool.pop() ?? new Pair()
      this.colourRoot.addChild(pair.colour)
      this.normalRoot.addChild(pair.normal)
      this.live.push(pair)
    }

    for (let index = 0; index < this.billboards.length; index += 1) {
      this.live[index].apply(this.billboards[index], this.neutralNormal)
      this.live[index].colour.visible = true
      this.live[index].normal.visible = true
    }

    // Surplus pairs are hidden rather than removed: an empty sprite costs a visibility check,
    // and removing and re-adding children is what makes a scene stutter when a crowd
    // disperses. They are only released when the surplus is large and persistent.
    for (let index = this.billboards.length; index < this.live.length; index += 1) {
      this.live[index].colour.visible = false
      this.live[index].normal.visible = false
    }

    const surplus = this.live.length - this.billboards.length
    if (surplus > POOL_LIMIT) {
      for (let index = 0; index < surplus - POOL_LIMIT; index += 1) {
        const pair = this.live.pop()
        if (pair === undefined) break
        this.colourRoot.removeChild(pair.colour)
        this.normalRoot.removeChild(pair.normal)
        pair.destroy()
      }
    }
  }

  /** How many sprites the last frame drew. For the diagnostics overlay. */
  get drawn(): number {
    return this.billboards.length
  }

  destroy(): void {
    for (const pair of this.live) pair.destroy()
    for (const pair of this.pool) pair.destroy()
    this.live.length = 0
    this.pool.length = 0
  }
}

/**
 * The state byte, as `age.application.interest._state_byte` packs it.
 *
 * Bit 0 is alive; bits 1 to 3 hold an `AIState`, not a set of flags. Players get one too —
 * `PATROL` when they are moving, `IDLE` when they are not — so one decoder covers both.
 */
export const AiState = {
  IDLE: 0,
  PATROL: 1,
  AGGRO: 2,
  ATTACK: 3,
  FLEE: 4,
  DEAD: 5,
} as const

export function isAlive(state: number): boolean {
  return (state & 1) !== 0
}

export function aiStateOf(state: number): number {
  return (state >> 1) & 0x07
}

/**
 * Which pose to draw.
 *
 * The state byte decides between attacking and not; speed decides between walking and
 * standing. Speed rather than the `PATROL` bit because speed comes from interpolated
 * positions and so is already smoothed — a player who stops between two snapshots stops
 * animating on the frame they stop, not on the next packet.
 */
export function poseFor(state: number, speed: number): number {
  const ai = aiStateOf(state)
  if (!isAlive(state) || ai === AiState.DEAD) return Pose.HURT
  if (ai === AiState.ATTACK) return Pose.ATTACK
  if (speed > 0.15) return Pose.WALK
  return Pose.IDLE
}
