/**
 * The three-layer coordinate system, browser side.
 *
 * Mirror of `age/domain/coordinates.py`. Layers 1 and 2 (hub-local and edge-local) are
 * stable frames that survive a topology change; layer 3 is the continuous plane the
 * renderer draws on, derived on demand and never stored.
 *
 * The client only needs the projections, not the persistence types: it receives positions
 * already resolved onto the plane and has to turn a plane point back into a chunk address
 * to know which tiles to read.
 */

import { CHUNK_TILES, HUB_RADIUS_TILES } from '../domain/constants'
import { SpaceType, type ChunkAddress } from './generator'

export interface Point {
  x: number
  y: number
}

export interface HubDefinition {
  hubId: number
  name: string
  angleRadians: number
  distanceTiles: number
  radiusTiles: number
}

export interface EdgeDefinition {
  edgeId: string
  hubA: HubDefinition
  hubB: HubDefinition
  segments: number
}

export function hubCentre(hub: HubDefinition): Point {
  return {
    x: Math.cos(hub.angleRadians) * hub.distanceTiles,
    y: Math.sin(hub.angleRadians) * hub.distanceTiles,
  }
}

/** Unit vector from hub A to hub B: the corridor's `+x`. */
export function edgeDirection(edge: EdgeDefinition): Point {
  const a = hubCentre(edge.hubA)
  const b = hubCentre(edge.hubB)
  const dx = b.x - a.x
  const dy = b.y - a.y
  const length = Math.hypot(dx, dy) || 1
  return { x: dx / length, y: dy / length }
}

/** Where segment 0 begins: the far rim of hub A's zone. */
export function edgeStart(edge: EdgeDefinition): Point {
  const direction = edgeDirection(edge)
  const a = hubCentre(edge.hubA)
  return {
    x: a.x + direction.x * edge.hubA.radiusTiles,
    y: a.y + direction.y * edge.hubA.radiusTiles,
  }
}

export function hubToWorld(hub: HubDefinition, tileX: number, tileY: number): Point {
  const centre = hubCentre(hub)
  return { x: centre.x + tileX, y: centre.y + tileY }
}

/**
 * Layer 2 to layer 3.
 *
 * Walks `segmentIndex` chunks along the corridor and `laneOffset` chunks across it, then
 * adds the tile offset inside that chunk. Affine and tier-free: activating lane 1 does not
 * move anything in lane 0, which is the property the whole accordion rests on.
 */
export function edgeToWorld(
  edge: EdgeDefinition,
  segmentIndex: number,
  laneOffset: number,
  tileX: number,
  tileY: number,
): Point {
  const direction = edgeDirection(edge)
  // Left-hand normal, so positive lanes are consistently on one side.
  const nx = -direction.y
  const ny = direction.x
  const origin = edgeStart(edge)

  const along = segmentIndex * CHUNK_TILES + tileX
  const across = laneOffset * CHUNK_TILES + tileY

  return {
    x: origin.x + direction.x * along + nx * across,
    y: origin.y + direction.y * along + ny * across,
  }
}

export interface EdgeLocal {
  segmentIndex: number
  laneOffset: number
  tileX: number
  tileY: number
}

/**
 * How close to a whole tile counts as being on it. Mirror of `SEAM_TOLERANCE_TILES`.
 *
 * A corridor's direction is a normalised vector, and normalising rounds: an edge running due
 * east has a y component of -6.1e-17 rather than zero. Projecting a point back through it
 * lands a hair off the value it was projected out from, and on a lane boundary a hair decides
 * the whole answer — `Math.floor` sends -8e-19 to lane -1 instead of lane 0. Lane -1 does not
 * exist until the accordion widens, so the point reads as outside the world, which the
 * predictor treats as a wall: an invisible barrier one float wide down the corridor's centre
 * line, over ground that draws as open.
 *
 * This has to match the server's tolerance exactly. A client that snaps where the server does
 * not disagrees about which tile a player stands on, and the disagreement is a correction
 * every frame the player walks the centre line.
 */
const SEAM_TOLERANCE_TILES = 1e-9

/** Pull a value already within rounding error of a whole tile onto it. */
function snapToTile(value: number): number {
  const nearest = Math.round(value)
  return Math.abs(value - nearest) < SEAM_TOLERANCE_TILES ? nearest : value
}

/**
 * Layer 3 to layer 2, the inverse of {@link edgeToWorld}.
 *
 * Tile coordinates come back normalised into `[0, CHUNK_TILES)` using floor division, so a
 * negative lane lands on the correct chunk instead of rounding towards zero. Both projections
 * are snapped first; see {@link SEAM_TOLERANCE_TILES} for what goes wrong without it.
 */
export function worldToEdge(edge: EdgeDefinition, point: Point): EdgeLocal {
  const direction = edgeDirection(edge)
  const nx = -direction.y
  const ny = direction.x
  const origin = edgeStart(edge)

  const dx = point.x - origin.x
  const dy = point.y - origin.y
  const along = snapToTile(dx * direction.x + dy * direction.y)
  const across = snapToTile(dx * nx + dy * ny)

  const segmentIndex = Math.floor(along / CHUNK_TILES)
  const laneOffset = Math.floor(across / CHUNK_TILES)
  return {
    segmentIndex,
    laneOffset,
    tileX: along - segmentIndex * CHUNK_TILES,
    tileY: across - laneOffset * CHUNK_TILES,
  }
}

export function worldToHub(hub: HubDefinition, point: Point): Point {
  const centre = hubCentre(hub)
  return { x: point.x - centre.x, y: point.y - centre.y }
}

/**
 * The tier at which a lane first appears. Mirror of `tier_min_for_lane`.
 *
 * A lane's `tierMin` is part of its chunk key and is hashed into its chunk seed, so it is
 * not a detail the client may default: addressing a flanking lane as tier 0 produces a key
 * the server's topology never names, which the store reads as "outside the world" and the
 * predictor reads as a wall. The symptom is a lane that is solid and unrendered for its
 * whole length the moment the accordion widens.
 */
export function tierMinForLane(laneOffset: number): number {
  return laneOffset === 0 ? 0 : 1
}

/**
 * Split a hub-local tile coordinate into `[chunk, offset]`. Mirror of `_split_hub_tile`.
 *
 * One floor, then an exact integer split, rather than deriving the chunk and the offset
 * from the float independently. Doing them separately lets rounding at a chunk boundary
 * produce an offset of exactly `CHUNK_TILES`, one past the end of the chunk — and a hub
 * plaza sits on the origin, where those boundaries are.
 */
function splitHubTile(value: number): readonly [number, number] {
  const tile = Math.floor(value)
  const chunk = Math.floor(tile / CHUNK_TILES)
  return [chunk, tile - chunk * CHUNK_TILES]
}

/**
 * A corridor tile offset, forced inside its chunk. Mirror of the clamp in `_tile_index`.
 *
 * `worldToEdge` normalises into `[0, CHUNK_TILES)` by subtracting the chunk origin back
 * off, and on a lane boundary that cancellation can land a hair outside the range it
 * promises. The server clamps before it indexes, so the client has to clamp the same way:
 * the failure is not symmetric. An out-of-range index there is a tile of the neighbouring
 * row, but here it reads `undefined` from the tile array, and no terrain is what the
 * predictor treats as a wall.
 */
function clampToChunk(offset: number): number {
  const tile = Math.floor(offset)
  if (tile < 0) return 0
  return tile >= CHUNK_TILES ? CHUNK_TILES - 1 : tile
}

export interface Located {
  address: ChunkAddress
  /** Tile index within the chunk, row-major. */
  index: number
}

/**
 * Which chunk and tile a plane point falls in.
 *
 * Hub zones win over corridors where they overlap, matching the server: a player on the
 * rim is inside the safe zone, and the safe-zone rules are the stricter of the two. Getting
 * this precedence backwards would let the client think it was in a PvP corridor while the
 * server refused every attack.
 */
export function locate(
  point: Point,
  hubs: readonly HubDefinition[],
  edges: readonly EdgeDefinition[],
): Located | undefined {
  for (const hub of hubs) {
    const local = worldToHub(hub, point)
    if (Math.max(Math.abs(local.x), Math.abs(local.y)) <= hub.radiusTiles) {
      const [chunkX, tileX] = splitHubTile(local.x)
      const [chunkY, tileY] = splitHubTile(local.y)
      return {
        address: { spaceType: SpaceType.HUB, hubId: hub.hubId, chunkX, chunkY },
        index: tileY * CHUNK_TILES + tileX,
      }
    }
  }

  let best: Located | undefined
  let bestAcross = Number.POSITIVE_INFINITY
  for (const edge of edges) {
    const local = worldToEdge(edge, point)
    const across = Math.abs(local.laneOffset * CHUNK_TILES + local.tileY)
    if (across < bestAcross) {
      bestAcross = across
      best = {
        address: {
          spaceType: SpaceType.EDGE,
          edgeId: edge.edgeId,
          segmentIndex: local.segmentIndex,
          laneOffset: local.laneOffset,
          tierMin: tierMinForLane(local.laneOffset),
        },
        index: clampToChunk(local.tileY) * CHUNK_TILES + clampToChunk(local.tileX),
      }
    }
  }
  return best
}

export interface WorldLayout {
  hubs: HubDefinition[]
  edges: EdgeDefinition[]
}

export const HUB_NAMES = ['Emberhold', 'Rookmarch'] as const

/**
 * The MVP world: two hubs facing each other across one corridor.
 *
 * Mirror of `build_default_world`. The `edgeId` comes from the welcome packet rather than
 * being hardcoded, and that is not a stylistic choice: the edge id is hashed into every
 * corridor chunk seed, so a client that guessed it wrong would generate an entirely
 * different corridor and only discover it by walking into terrain nobody else can see.
 *
 * The geometry is derived from the same constants as the server for the same reason —
 * hub angles are opposite so the corridor runs through the origin, which keeps the minimap
 * readable and the coordinates easy to reason about while debugging.
 */
export function buildWorld(edgeId: string, segments: number): WorldLayout {
  const separation = HUB_RADIUS_TILES * 2 + segments * CHUNK_TILES

  const hubA: HubDefinition = {
    hubId: 0,
    name: HUB_NAMES[0],
    angleRadians: Math.PI,
    distanceTiles: separation / 2,
    radiusTiles: HUB_RADIUS_TILES,
  }
  const hubB: HubDefinition = {
    hubId: 1,
    name: HUB_NAMES[1],
    angleRadians: 0,
    distanceTiles: separation / 2,
    radiusTiles: HUB_RADIUS_TILES,
  }

  return { hubs: [hubA, hubB], edges: [{ edgeId, hubA, hubB, segments }] }
}
