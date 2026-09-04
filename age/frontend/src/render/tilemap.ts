/**
 * Chunk terrain as one mesh per chunk.
 *
 * A 32x32 chunk is 1024 tiles, and around twenty chunks are on screen at once. Drawing that
 * as individual sprites is twenty thousand objects for Pixi to sort and batch every frame,
 * which it can do but at a cost that scales with the view. Baking each chunk into a single
 * mesh makes it about twenty draw calls regardless of resolution, and the geometry only
 * changes when a tile does.
 *
 * The mesh is built twice per chunk — once against the colour page, once against the normal
 * page — because the deferred lighting pass needs the same geometry rendered into two
 * buffers. They share vertex data, so the second costs a draw call and nothing else.
 */

import { Container, Geometry, Mesh, Shader, type Texture } from 'pixi.js'

import { CHUNK_TILES, TILE_SIZE_PX } from '../domain/constants'
import type { Atlas } from './atlas'
import type { ChunkStore } from '../world/chunkStore'
import { chunkKey, type ChunkAddress } from '../world/generator'

const VERTEX = `
in vec2 aPosition;
in vec2 aUV;
out vec2 vUV;

uniform mat3 uProjectionMatrix;
uniform mat3 uWorldTransformMatrix;
uniform mat3 uTransformMatrix;

void main(void) {
    mat3 mvp = uProjectionMatrix * uWorldTransformMatrix * uTransformMatrix;
    gl_Position = vec4((mvp * vec3(aPosition, 1.0)).xy, 0.0, 1.0);
    vUV = aUV;
}
`

const FRAGMENT = `
precision mediump float;

in vec2 vUV;
out vec4 finalColor;

uniform sampler2D uPage;

void main(void) {
    finalColor = texture(uPage, vUV);
}
`

/** Reused across every tile of every rebuild; the alternative is a thousand tiny arrays. */
const SCRATCH_UV = new Float32Array(4)

/**
 * One chunk's geometry, and the two meshes that draw it.
 *
 * Vertex data is rebuilt on demand rather than on a timer: a chunk changes when a player
 * edits a tile or when its water frame advances, both of which are events.
 */
class ChunkMesh {
  readonly colour: Mesh<Geometry, Shader>
  readonly normal: Mesh<Geometry, Shader>

  private readonly positions: Float32Array
  private readonly uvs: Float32Array
  private readonly geometry: Geometry
  private readonly tiles = new Uint8Array(CHUNK_TILES * CHUNK_TILES)

  revision = -1
  animationFrame = -1
  /** Whether this chunk has any animated tile, so the scene can skip static ones. */
  animated = false

  constructor(
    readonly key: string,
    readonly address: ChunkAddress,
    private readonly atlas: Atlas,
    colourPage: Texture,
    normalPage: Texture,
  ) {
    const quads = CHUNK_TILES * CHUNK_TILES
    this.positions = new Float32Array(quads * 8)
    this.uvs = new Float32Array(quads * 8)

    // Indices never change: quad n always uses vertices 4n..4n+3, whatever they hold.
    const indices = new Uint16Array(quads * 6)
    for (let quad = 0; quad < quads; quad += 1) {
      const vertex = quad * 4
      const at = quad * 6
      indices[at] = vertex
      indices[at + 1] = vertex + 1
      indices[at + 2] = vertex + 2
      indices[at + 3] = vertex
      indices[at + 4] = vertex + 2
      indices[at + 5] = vertex + 3
    }

    // Positions are fixed too: tile (x, y) is always the same rectangle in chunk space, so
    // only the UVs change when terrain changes.
    for (let ty = 0; ty < CHUNK_TILES; ty += 1) {
      for (let tx = 0; tx < CHUNK_TILES; tx += 1) {
        const at = (ty * CHUNK_TILES + tx) * 8
        const left = tx * TILE_SIZE_PX
        const top = ty * TILE_SIZE_PX
        const right = left + TILE_SIZE_PX
        const bottom = top + TILE_SIZE_PX
        this.positions[at] = left
        this.positions[at + 1] = top
        this.positions[at + 2] = right
        this.positions[at + 3] = top
        this.positions[at + 4] = right
        this.positions[at + 5] = bottom
        this.positions[at + 6] = left
        this.positions[at + 7] = bottom
      }
    }

    this.geometry = new Geometry({
      attributes: { aPosition: this.positions, aUV: this.uvs },
      indexBuffer: indices,
    })

    this.colour = new Mesh({
      geometry: this.geometry,
      shader: Shader.from({
        gl: { vertex: VERTEX, fragment: FRAGMENT },
        resources: { uPage: colourPage.source },
      }),
    })
    this.normal = new Mesh({
      geometry: this.geometry,
      shader: Shader.from({
        gl: { vertex: VERTEX, fragment: FRAGMENT },
        resources: { uPage: normalPage.source },
      }),
    })
  }

  /** Rewrite the UVs from the store's current tiles. */
  rebuild(store: ChunkStore, frame: number): void {
    const revision = store.readInto(this.address, this.tiles)
    this.revision = revision
    this.animationFrame = frame
    this.animated = false

    const rect = SCRATCH_UV
    for (let index = 0; index < this.tiles.length; index += 1) {
      const tile = this.tiles[index]
      const key = this.atlas.groundFor(tile)

      let spriteFrame = 0
      if (this.atlas.animationRate(tile) > 0) {
        this.animated = true
        spriteFrame = frame
      }

      if (
        !this.atlas.writeUv(key, spriteFrame, rect, 0) &&
        !this.atlas.writeUv(this.atlas.index.fallbackGround, 0, rect, 0)
      ) {
        continue
      }

      const u = rect[0]
      const v = rect[1]
      const right = u + rect[2]
      const bottom = v + rect[3]
      const at = index * 8
      this.uvs[at] = u
      this.uvs[at + 1] = v
      this.uvs[at + 2] = right
      this.uvs[at + 3] = v
      this.uvs[at + 4] = right
      this.uvs[at + 5] = bottom
      this.uvs[at + 6] = u
      this.uvs[at + 7] = bottom
    }

    this.geometry.getBuffer('aUV').update()
  }

  /** The tiles as last read, for the prop layer to walk without re-reading the store. */
  get currentTiles(): Uint8Array {
    return this.tiles
  }

  place(x: number, y: number): void {
    this.colour.position.set(x, y)
    this.normal.position.set(x, y)
  }

  destroy(): void {
    this.colour.destroy()
    this.normal.destroy()
    this.geometry.destroy()
  }
}

/**
 * The terrain layer: a pool of chunk meshes, recycled as the player walks.
 *
 * Meshes are pooled rather than created and destroyed. Each one owns three typed arrays and
 * two shaders, and churning them at a walking pace is how a smooth game develops a stutter
 * every time it crosses a chunk boundary.
 */
export class TileLayer {
  readonly colourRoot = new Container()
  readonly normalRoot = new Container()

  private readonly live = new Map<string, ChunkMesh>()
  private readonly pool: ChunkMesh[] = []

  constructor(
    private readonly atlas: Atlas,
    private readonly colourPage: Texture,
    private readonly normalPage: Texture,
  ) {}

  /**
   * Sync the layer to a set of chunk addresses.
   *
   * `frame` drives tile animation; only chunks that contain an animated tile are rebuilt
   * when it changes, which keeps a still landscape free.
   */
  update(
    store: ChunkStore,
    addresses: readonly ChunkAddress[],
    frame: number,
    origin: (address: ChunkAddress) => { x: number; y: number },
  ): void {
    const wanted = new Set<string>()

    for (const address of addresses) {
      const key = chunkKey(address)
      wanted.add(key)

      let mesh = this.live.get(key)
      if (mesh === undefined) {
        mesh = this.acquire(key, address)
        this.live.set(key, mesh)
        mesh.rebuild(store, frame)
      } else {
        const view = store.peek(key)
        const revision = view?.revision ?? mesh.revision
        if (revision !== mesh.revision || (mesh.animated && frame !== mesh.animationFrame)) {
          mesh.rebuild(store, frame)
        }
      }

      const at = origin(address)
      mesh.place(at.x, at.y)
    }

    for (const [key, mesh] of [...this.live]) {
      if (!wanted.has(key)) {
        this.release(key, mesh)
      }
    }
  }

  /** The tiles of a live chunk, for the prop layer. */
  tilesOf(key: string): Uint8Array | undefined {
    return this.live.get(key)?.currentTiles
  }

  get liveCount(): number {
    return this.live.size
  }

  private acquire(key: string, address: ChunkAddress): ChunkMesh {
    const recycled = this.pool.pop()
    if (recycled !== undefined) {
      // A pooled mesh keeps its buffers; only its identity and contents change. The cast
      // is safe because key and address are the only mutable identity it has.
      const mesh = recycled as ChunkMesh & { key: string; address: ChunkAddress }
      mesh.key = key
      mesh.address = address
      mesh.revision = -1
      this.colourRoot.addChild(mesh.colour)
      this.normalRoot.addChild(mesh.normal)
      return mesh
    }

    const mesh = new ChunkMesh(key, address, this.atlas, this.colourPage, this.normalPage)
    this.colourRoot.addChild(mesh.colour)
    this.normalRoot.addChild(mesh.normal)
    return mesh
  }

  private release(key: string, mesh: ChunkMesh): void {
    this.live.delete(key)
    this.colourRoot.removeChild(mesh.colour)
    this.normalRoot.removeChild(mesh.normal)

    // Cap the pool: a player who has crossed the whole world should not hold a mesh for
    // every chunk they have seen.
    if (this.pool.length < 48) this.pool.push(mesh)
    else mesh.destroy()
  }

  destroy(): void {
    for (const mesh of this.live.values()) mesh.destroy()
    for (const mesh of this.pool) mesh.destroy()
    this.live.clear()
    this.pool.length = 0
  }
}
