/**
 * The renderer: camera, layers, lighting pass, weather.
 *
 * The frame is drawn in two passes. First the world is drawn twice — once with colour art and
 * once with normal-map art, into an offscreen texture — then the colour buffer is put through
 * a filter that samples both and shades every pixel by the lights near it. Drawing twice
 * sounds expensive and is not: both passes are the same geometry with a different page bound,
 * and the alternative for 2D normal-mapped lighting is a custom render pipeline.
 *
 * Camera positions are snapped to whole screen pixels. Pixel art at a fractional offset
 * shimmers, because each tile rounds differently and the rounding changes as you walk.
 */

import { Application, Container, Graphics, RenderTexture, Texture } from 'pixi.js'

import {
  AOI_ACTIVE_RADIUS_CHUNKS,
  DAY_LENGTH_SECONDS,
  TILE_SIZE_PX,
} from '../domain/constants'
import type { RemoteEntity } from '../net/session'
import type { ChunkStore } from '../world/chunkStore'
import { chunkKey, type ChunkAddress } from '../world/generator'
import { Atlas } from './atlas'
import {
  ambientFor,
  isDark,
  lanternStrength,
  lightningAt,
  particlesFor,
  tintFromBytes,
  type Rgb,
} from './atmosphere'
import { CharacterCache, type CharacterLayout } from './characters'
import { DecorCache, type Placement } from './decor'
import { LightingFilter, type Light } from './lighting'
import { PropLayer, poseFor } from './props'
import { TileLayer } from './tilemap'
import { WeatherLayer } from './weather'

export interface CameraTarget {
  /** Tile coordinates. */
  x: number
  y: number
}

export interface FrameInput {
  /** Where the camera looks: the local player's predicted position, in tiles. */
  camera: CameraTarget
  /** The local player, drawn from the predicted position rather than an interpolated one. */
  local:
    | {
        appearance: Parameters<CharacterCache['get']>[0]
        facing: number
        state: number
        speed: number
      }
    | undefined
  entities: Iterable<RemoteEntity>
  /** Chunk addresses to draw. Usually the AOI around the camera. */
  chunks: readonly ChunkAddress[]
  /** Server day phase in `[0, 1)`. */
  dayPhase: number
  weather: number
  /** Ambient tint of the biome under the camera, as three bytes. */
  biomeTint: readonly [number, number, number]
  /** Seconds since the session started. Drives animation and lightning. */
  elapsed: number
  /** Tiles the local player has walked. Drives their walk cycle. */
  distance: number
}

export interface SceneStats {
  chunks: number
  sprites: number
  lights: number
  fps: number
}

/** How zoomed in the world is. Two device pixels per art pixel: legible without being huge. */
const DEFAULT_ZOOM = 2

export class Scene {
  readonly app: Application

  private readonly world = new Container()
  private readonly normalWorld = new Container()
  private readonly overlay = new Container()

  private tiles!: TileLayer
  private props!: PropLayer
  private weatherLayer!: WeatherLayer
  private lighting!: LightingFilter
  private normalBuffer!: RenderTexture

  /** The full-screen rectangle the weather and lightning tints are painted onto. */
  private readonly tint = new Graphics()

  private zoom = DEFAULT_ZOOM
  private stats: SceneStats = { chunks: 0, sprites: 0, lights: 0, fps: 0 }
  private readonly lights: Light[] = []

  /** This frame's decor, kept so the lighting pass can walk it without deriving it again. */
  private readonly decor: Placement[] = []
  private readonly decorCache = new DecorCache()

  private atlas!: Atlas
  private characters!: CharacterCache

  private constructor() {
    this.app = new Application()
  }

  /**
   * Boot the renderer against a canvas parent.
   *
   * `api` is the API root, not the mount prefix: the atlas and the character sheets come from
   * `<mount>/api/atelier/...`, so passing the mount alone silently 404s the whole renderer.
   *
   * Async because the WebGL context, the atlas, and the character layout all have to be in
   * hand before a single frame can be drawn.
   */
  static async create(parent: HTMLElement, api: string): Promise<Scene> {
    const scene = new Scene()

    await scene.app.init({
      resizeTo: parent,
      antialias: false,
      // The scene is opaque and covers the canvas, so there is nothing to blend with.
      backgroundAlpha: 1,
      background: 0x0b0d12,
      // Pixel art wants one device pixel per art pixel at integer zoom. Letting Pixi use the
      // device ratio on top of the zoom gives fractional scales on any HiDPI screen, which
      // is the one thing that makes hand-placed pixels blur.
      resolution: 1,
      autoDensity: true,
      preference: 'webgl',
    })
    parent.appendChild(scene.app.canvas)

    scene.atlas = await Atlas.load(api)
    // The index is fetched, so it may be from an older server than this bundle. A missing
    // layout falls back rather than throwing: the fallback is only wrong if the sprite size
    // changed, and a wrong-looking character beats a blank screen.
    scene.characters = new CharacterCache(
      api,
      scene.atlas.index.character ?? FALLBACK_CHARACTER_LAYOUT,
    )

    scene.build()
    return scene
  }

  private build(): void {
    const colourPage = new Texture({ source: this.atlas.colourSource })
    const normalPage = new Texture({ source: this.atlas.normalSource })

    this.tiles = new TileLayer(this.atlas, colourPage, normalPage)
    this.props = new PropLayer(this.atlas, this.characters, neutralNormalTexture())
    this.weatherLayer = new WeatherLayer()

    // Terrain under props on both layers, and the two layers in lockstep: the lighting pass
    // matches them pixel for pixel, so anything drawn in one and not the other would be lit
    // by its neighbour's normals.
    this.world.addChild(this.tiles.colourRoot, this.props.colourRoot)
    this.normalWorld.addChild(this.tiles.normalRoot, this.props.normalRoot)

    this.normalBuffer = RenderTexture.create({
      width: Math.max(1, this.app.screen.width),
      height: Math.max(1, this.app.screen.height),
      scaleMode: 'nearest',
    })

    this.lighting = new LightingFilter(this.normalBuffer)
    this.world.filters = [this.lighting]

    this.overlay.addChild(this.tint, this.weatherLayer.root)
    this.app.stage.addChild(this.world, this.overlay)

    this.app.renderer.on('resize', () => this.onResize())
    this.onResize()
  }

  private onResize(): void {
    const { width, height } = this.app.screen
    this.normalBuffer.resize(Math.max(1, width), Math.max(1, height))
    this.lighting.setNormalSource(this.normalBuffer.source)
    this.lighting.setResolution(width, height)
    this.weatherLayer.resize(width, height)
  }

  setZoom(zoom: number): void {
    // Integers only. A zoom of 1.5 puts every other art pixel across two screen pixels, and
    // the seams move as the camera does.
    this.zoom = Math.max(1, Math.min(4, Math.round(zoom)))
  }

  get currentZoom(): number {
    return this.zoom
  }

  /** How many tiles fit on screen, for the chunk streamer to size its window. */
  get viewportTiles(): { width: number; height: number } {
    return {
      width: this.app.screen.width / (TILE_SIZE_PX * this.zoom),
      height: this.app.screen.height / (TILE_SIZE_PX * this.zoom),
    }
  }

  /**
   * Draw one frame.
   *
   * Called from the caller's own loop rather than from Pixi's ticker, because the order of
   * simulation, interpolation, and drawing matters and the caller owns it.
   */
  render(store: ChunkStore, input: FrameInput, deltaSeconds: number): void {
    const { width, height } = this.app.screen
    const scale = this.zoom

    // The camera, in world pixels, then snapped so the world lands on whole device pixels.
    const centreX = input.camera.x * TILE_SIZE_PX
    const centreY = input.camera.y * TILE_SIZE_PX
    const offsetX = Math.round(width / 2 - centreX * scale)
    const offsetY = Math.round(height / 2 - centreY * scale)

    for (const layer of [this.world, this.normalWorld]) {
      layer.scale.set(scale)
      layer.position.set(offsetX, offsetY)
    }

    // Terrain. Water advances on its own clock so every chunk of it stays in step.
    const waterFrame = Math.floor(input.elapsed * 6)
    this.tiles.update(store, input.chunks, waterFrame, (address) => originOf(address, store))

    // Props and characters, all queued then depth-sorted in one pass.
    this.props.begin()
    this.decor.length = 0

    for (const address of input.chunks) {
      const tiles = this.tiles.tilesOf(chunkKey(address))
      if (tiles === undefined) continue

      const originTiles = store.chunkOriginTiles(address)
      this.props.addChunkProps(
        tiles,
        originTiles.x * TILE_SIZE_PX,
        originTiles.y * TILE_SIZE_PX,
        waterFrame,
      )

      for (const placement of this.decorCache.forChunk(address, originTiles.x, originTiles.y)) {
        this.decor.push(placement)
        this.props.addDecor(
          placement.key,
          placement.x * TILE_SIZE_PX,
          placement.y * TILE_SIZE_PX,
          waterFrame,
        )
      }
    }

    for (const entity of input.entities) {
      this.props.addEntity(entity, input.elapsed, entity.pose.speed * input.elapsed)
    }

    if (input.local !== undefined) {
      this.props.addCharacter(
        input.local.appearance,
        centreX,
        centreY,
        input.local.facing,
        poseFor(input.local.state, input.local.speed),
        input.elapsed,
        input.distance,
      )
    }

    this.props.flush()

    // Lighting. Ambient first, then the point lights the scene contains.
    const ambient = ambientFor(input.dayPhase, input.weather, tintFromBytes(input.biomeTint))
    const flash = lightningAt(input.weather, input.elapsed)
    this.lighting.setAmbient(
      flash > 0
        ? ([
            ambient.colour[0] + flash * 0.9,
            ambient.colour[1] + flash * 0.9,
            ambient.colour[2] + flash,
          ] as Rgb)
        : ambient.colour,
      ambient.saturationFloor,
    )

    this.collectLights(input, offsetX, offsetY, scale)
    this.lighting.setLights(this.lights, width / 2, height / 2)

    // Weather overlay and particles, both in screen space: rain is between the camera and
    // the world, not part of it.
    this.paintTint(width, height, ambient.overlay, flash)
    this.weatherLayer.update(particlesFor(input.weather), deltaSeconds)

    // The normal pass goes to its own buffer, which the filter then samples. Rendered before
    // the visible frame so the filter reads this frame's normals rather than last frame's.
    this.app.renderer.render({
      container: this.normalWorld,
      target: this.normalBuffer,
      clear: true,
    })
    this.app.renderer.render(this.app.stage)

    this.stats = {
      chunks: this.tiles.liveCount,
      sprites: this.props.drawn,
      lights: this.lights.length,
      fps: deltaSeconds > 0 ? 1 / deltaSeconds : 0,
    }
  }

  /**
   * Gather the lights for this frame.
   *
   * Lanterns and campfires from the decor pass become point lights, and after dark the player
   * carries a faint one so night is atmospheric rather than unplayable. Positions are in screen
   * space because the filter works on the screen buffer, not on the world.
   */
  private collectLights(input: FrameInput, offsetX: number, offsetY: number, scale: number): void {
    this.lights.length = 0

    const strength = lanternStrength(input.dayPhase)
    if (strength > 0.01) {
      for (const placement of this.decor) {
        if (placement.light === undefined) continue
        const emitter = EMITTERS[placement.light]

        // Flicker per source, phased by position, so two nearby fires are not in lockstep.
        const jitter =
          1 +
          Math.sin(input.elapsed * emitter.flickerHz + placement.x * 1.7 + placement.y * 2.3) *
            emitter.flicker

        this.lights.push({
          x: offsetX + placement.x * TILE_SIZE_PX * scale,
          // Lifted to where the flame is rather than where the base is, or a lantern would
          // light the ground under its own post and nothing else.
          y: offsetY + (placement.y * TILE_SIZE_PX - emitter.lift) * scale,
          radius: emitter.radius * scale,
          colour: emitter.colour,
          intensity: emitter.intensity * strength * jitter,
          height: emitter.height * scale,
        })
      }
    }

    if (isDark(input.dayPhase)) {
      const { width, height } = this.app.screen
      this.lights.push({
        x: width / 2,
        y: height / 2,
        radius: 190 * scale,
        colour: [1, 0.94, 0.82],
        intensity: 0.55 * strength,
        height: 26 * scale,
      })
    }
  }

  /** The flat colour laid over the scene: fog, storm gloom, and the lightning flash. */
  private paintTint(
    width: number,
    height: number,
    overlay: readonly [number, number, number, number],
    flash: number,
  ): void {
    this.tint.clear()
    const alpha = overlay[3] + flash * 0.35
    if (alpha <= 0.001) return

    const colour =
      (Math.round(Math.min(1, overlay[0] + flash) * 255) << 16) |
      (Math.round(Math.min(1, overlay[1] + flash) * 255) << 8) |
      Math.round(Math.min(1, overlay[2] + flash) * 255)
    this.tint.rect(0, 0, width, height).fill({ color: colour, alpha: Math.min(0.85, alpha) })
  }

  /** Convert a screen point to tile coordinates: for click-to-aim and click-to-build. */
  screenToTile(screenX: number, screenY: number, camera: CameraTarget): CameraTarget {
    const { width, height } = this.app.screen
    return {
      x: camera.x + (screenX - width / 2) / (TILE_SIZE_PX * this.zoom),
      y: camera.y + (screenY - height / 2) / (TILE_SIZE_PX * this.zoom),
    }
  }

  get diagnostics(): SceneStats {
    return this.stats
  }

  destroy(): void {
    this.tiles.destroy()
    this.props.destroy()
    this.weatherLayer.destroy()
    this.normalBuffer.destroy(true)
    this.app.destroy(true, { children: true })
  }
}

/**
 * What each kind of light source looks like.
 *
 * `height` is what makes a light read as a lamp above the ground rather than a glow painted
 * onto it: at height zero the direction to the light lies in the same plane as the surface
 * normals, so almost nothing gets shaded and the normal map is wasted. `lift` moves the source
 * up the sprite to where the flame actually is.
 */
interface Emitter {
  radius: number
  colour: Rgb
  intensity: number
  height: number
  /** Pixels above the sprite's base that the light originates from. */
  lift: number
  /** How much the intensity wavers, as a fraction, and how fast. */
  flicker: number
  flickerHz: number
}

const EMITTERS: Record<'lantern' | 'campfire', Emitter> = {
  // A lantern is steady, cool-warm, and high up. A campfire is hotter, closer to the ground,
  // and visibly unsteady — the difference between the two is most of what sells either.
  lantern: {
    radius: 170,
    colour: [1, 0.87, 0.62],
    intensity: 1.15,
    height: 46,
    lift: 34,
    flicker: 0.045,
    flickerHz: 2.1,
  },
  campfire: {
    radius: 140,
    colour: [1, 0.68, 0.34],
    intensity: 1.4,
    height: 18,
    lift: 10,
    flicker: 0.17,
    flickerHz: 8.7,
  },
}

/** Used if the server ever serves an index without a character layout. */
const FALLBACK_CHARACTER_LAYOUT: CharacterLayout = {
  width: 32,
  height: 48,
  facings: 3,
  poseFrames: [2, 4, 3, 1],
  columns: 4,
}

/** A single opaque pixel of "surface facing the viewer", for sprites with no normal map. */
function neutralNormalTexture(): Texture {
  const canvas = document.createElement('canvas')
  canvas.width = 1
  canvas.height = 1
  const context = canvas.getContext('2d')
  if (context !== null) {
    // (0.5, 0.5, 1.0) unpacks to a normal of (0, 0, 1): straight out of the screen.
    context.fillStyle = 'rgb(128, 128, 255)'
    context.fillRect(0, 0, 1, 1)
  }
  return Texture.from(canvas)
}

/** Where a chunk's top-left corner sits, in world pixels. */
function originOf(address: ChunkAddress, store: ChunkStore): { x: number; y: number } {
  const tile = store.chunkOriginTiles(address)
  return { x: tile.x * TILE_SIZE_PX, y: tile.y * TILE_SIZE_PX }
}

/** The chunk window to draw around a camera: the AOI radius, in chunks. */
export function visibleChunks(
  store: ChunkStore,
  camera: CameraTarget,
  radiusChunks = AOI_ACTIVE_RADIUS_CHUNKS,
): ChunkAddress[] {
  return store.chunksAround(camera.x, camera.y, radiusChunks)
}

/** Server day phase from a server timestamp, matching `age.application.weather`. */
export function dayPhaseAt(serverTime: number): number {
  return (((serverTime / DAY_LENGTH_SECONDS) % 1) + 1) % 1
}
