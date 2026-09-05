/**
 * Loading the baked atlas the Atelier produces.
 *
 * The server bakes every tile and prop into one 1024px page pair — colour and normal map —
 * plus a JSON index. The client fetches all three once and never asks again: the art is
 * deterministic from a seed, so the same URL always yields the same page and the browser
 * cache does the rest.
 *
 * Two pages rather than one because the normal map is what makes 2D lighting look like
 * anything. A flat sprite lit by a point light is just a sprite with a gradient on it; the
 * same sprite with per-pixel normals catches the light on its edges and reads as solid.
 */

import { Assets, Rectangle, Texture, type TextureSource } from 'pixi.js'

import { ATLAS_PADDING_PX, TILE_SIZE_PX } from '../domain/constants'

export interface FrameIndex {
  name: string
  frame: number
  x: number
  y: number
  w: number
  h: number
  /**
   * Rows below the tile's bottom edge that this sprite occupies.
   *
   * A 56px tree stands in a 32px cell: 24 rows hang above, and the anchor is what lines its
   * base up with the tile it grows from rather than centring it in the cell.
   */
  anchorY: number
}

export interface AtlasIndex {
  width: number
  height: number
  frames: FrameIndex[]
  /**
   * Tile id (as a string key) to the ground art that draws it.
   *
   * Served by the Atelier rather than declared here on purpose. It is the same mapping the
   * recipe library already owns, and a second copy in TypeScript drifts silently — the
   * symptom is one tile rendering as the wrong art, which no test on either side would
   * catch.
   */
  tileGround: Record<string, string>
  /** Tile id to the standing prop drawn above it, for tiles that have one. */
  tileProp: Record<string, string>
  /** Tile id to frames per second, for tiles whose ground animates. */
  animated: Record<string, number>
  /** What an unmapped tile draws. */
  fallbackGround: string
  /** Recipes with no tile of their own, placed by hand: lanterns, campfires, banners. */
  decor: string[]
  /**
   * How `character-sheet.png` is laid out.
   *
   * Characters are not in the atlas — their art depends on five appearance bytes, and baking
   * every combination would be a page the size of the world — so they are fetched per
   * appearance and sliced against this.
   */
  character: CharacterGrid
}

export interface CharacterGrid {
  width: number
  height: number
  facings: number
  /** Frames per pose, indexed by pose id. */
  poseFrames: number[]
  /** Grid width in cells: the widest pose. Shorter poses leave their tail empty. */
  columns: number
}

/** One sprite's frames, in order, with the normal-map twin of each. */
export interface SpriteFrames {
  key: string
  colour: Texture[]
  normal: Texture[]
  anchorY: number
  width: number
  height: number
  /**
   * Normalised `[u, v, w, h]` per frame, flat, four floats each.
   *
   * Precomputed because the tilemap asks for one per tile per rebuild: a thousand lookups
   * per chunk, and for a chunk of water, a thousand every frame. Searching the frame list
   * for each of those was the whole cost of a water rebuild.
   */
  uvs: Float32Array
}

export class Atlas {
  private readonly sprites = new Map<string, SpriteFrames>()

  private constructor(
    readonly colourSource: TextureSource,
    readonly normalSource: TextureSource,
    readonly index: AtlasIndex,
  ) {
    this.build()
  }

  /**
   * Fetch and slice the atlas.
   *
   * `api` is the API root — `<mount>/api` — so this works both behind the orchestrator at
   * `/age` and against a bare dev server.
   */
  static async load(api: string): Promise<Atlas> {
    // A cold host can 504 the first atlas fetch while the page is still baking.
    // One failure used to abort the whole renderer. Three tries, a second apart,
    // cover a bake that finishes just after the proxy gave up.
    let lastError: unknown
    for (let attempt = 0; attempt < 3; attempt += 1) {
      try {
        return await Atlas.fetch(api, attempt)
      } catch (error) {
        lastError = error
        await new Promise((resolve) => window.setTimeout(resolve, 1000 * (attempt + 1)))
      }
    }
    throw lastError instanceof Error ? lastError : new Error('atlas load failed')
  }

  private static async fetch(api: string, attempt: number): Promise<Atlas> {
    const bust = attempt === 0 ? '' : `?retry=${attempt}`
    const [colour, normal, index] = await Promise.all([
      Assets.load<Texture>({
        src: `${api}/atelier/atlas.png${bust}`,
        // Nearest neighbour, always. Pixel art through a linear filter is the single
        // fastest way to make hand-made art look like a JPEG.
        data: { scaleMode: 'nearest', autoGenerateMipmaps: false },
      }),
      Assets.load<Texture>({
        src: `${api}/atelier/atlas-normal.png${bust}`,
        data: { scaleMode: 'nearest', autoGenerateMipmaps: false },
      }),
      fetch(`${api}/atelier/atlas.json${bust}`).then((response) => {
        if (!response.ok) throw new Error(`atlas index: HTTP ${response.status}`)
        return response.json() as Promise<AtlasIndex>
      }),
    ])

    return new Atlas(colour.source, normal.source, index)
  }

  private build(): void {
    // Grouped by name first so frames can be indexed by number without a sort per lookup.
    const grouped = new Map<string, FrameIndex[]>()
    for (const frame of this.index.frames) {
      const existing = grouped.get(frame.name)
      if (existing === undefined) grouped.set(frame.name, [frame])
      else existing.push(frame)
    }

    for (const [key, frames] of grouped) {
      frames.sort((a, b) => a.frame - b.frame)
      const first = frames[0]

      // Half a texel is trimmed off each edge. Without it, a tile drawn at a fractional
      // camera offset bleeds its neighbour's outermost pixel in as a one-pixel seam, and on
      // a 32px grid that is very visible.
      const inset = 0.5
      const uvs = new Float32Array(frames.length * 4)
      frames.forEach((frame, at) => {
        uvs[at * 4] = (frame.x + inset) / this.index.width
        uvs[at * 4 + 1] = (frame.y + inset) / this.index.height
        uvs[at * 4 + 2] = (frame.w - inset * 2) / this.index.width
        uvs[at * 4 + 3] = (frame.h - inset * 2) / this.index.height
      })

      this.sprites.set(key, {
        key,
        colour: frames.map((frame) => this.slice(this.colourSource, frame)),
        normal: frames.map((frame) => this.slice(this.normalSource, frame)),
        anchorY: first.anchorY,
        width: first.w,
        height: first.h,
        uvs,
      })
    }
  }

  private slice(source: TextureSource, frame: FrameIndex): Texture {
    return new Texture({
      source,
      frame: new Rectangle(frame.x, frame.y, frame.w, frame.h),
    })
  }

  get(key: string): SpriteFrames | undefined {
    return this.sprites.get(key)
  }

  /**
   * A sprite's frame, wrapping the index rather than clamping it.
   *
   * Animations are driven by a monotonically increasing counter, so wrapping is what makes
   * a four-frame idle loop out of `frame % 4` without every caller knowing the count.
   */
  frame(key: string, frame: number): Texture | undefined {
    const sprite = this.sprites.get(key)
    if (sprite === undefined || sprite.colour.length === 0) return undefined
    return sprite.colour[((frame % sprite.colour.length) + sprite.colour.length) % sprite.colour.length]
  }

  normalFrame(key: string, frame: number): Texture | undefined {
    const sprite = this.sprites.get(key)
    if (sprite === undefined || sprite.normal.length === 0) return undefined
    return sprite.normal[((frame % sprite.normal.length) + sprite.normal.length) % sprite.normal.length]
  }

  get keys(): string[] {
    return [...this.sprites.keys()].sort()
  }

  /** The ground art for a tile id, falling back to the page's declared fallback. */
  groundFor(tile: number): string {
    return this.index.tileGround[String(tile)] ?? this.index.fallbackGround
  }

  /** The standing prop for a tile id, or `undefined` when it has none. */
  propFor(tile: number): string | undefined {
    return this.index.tileProp[String(tile)]
  }

  /** Frames per second for an animated tile, or 0 for a still one. */
  animationRate(tile: number): number {
    return this.index.animated[String(tile)] ?? 0
  }

  /**
   * Write a frame's normalised UV rectangle into `out` at `at`, and report whether it exists.
   *
   * The tilemap draws every visible tile in one draw call, so it samples the page directly
   * rather than binding a Texture per tile. Writing into the caller's buffer rather than
   * returning a tuple avoids allocating one array per tile per rebuild, which for a screen
   * of animated water is a few thousand short-lived objects a frame.
   */
  writeUv(key: string, frame: number, out: Float32Array, at: number): boolean {
    const sprite = this.sprites.get(key)
    if (sprite === undefined) return false
    const count = sprite.uvs.length / 4
    const index = ((frame % count) + count) % count
    out[at] = sprite.uvs[index * 4]
    out[at + 1] = sprite.uvs[index * 4 + 1]
    out[at + 2] = sprite.uvs[index * 4 + 2]
    out[at + 3] = sprite.uvs[index * 4 + 3]
    return true
  }

  /** A frame's UV rectangle as a tuple. For tests and one-off callers, not per-tile work. */
  uv(key: string, frame = 0): readonly [number, number, number, number] | undefined {
    const scratch = new Float32Array(4)
    if (!this.writeUv(key, frame, scratch, 0)) return undefined
    return [scratch[0], scratch[1], scratch[2], scratch[3]]
  }

  /** Whether a sprite is a ground tile: exactly one cell, with nothing overhanging. */
  isGround(key: string): boolean {
    const sprite = this.sprites.get(key)
    return (
      sprite !== undefined &&
      sprite.width === TILE_SIZE_PX &&
      sprite.height === TILE_SIZE_PX &&
      sprite.anchorY === 0
    )
  }

  get padding(): number {
    return ATLAS_PADDING_PX
  }
}
