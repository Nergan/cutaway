/** Shared shapes for the world, the network layer and the renderer. */

export interface WorldDescriptor {
  id: string
  version: number
  seed: number
  source: string
  tilesX: number
  tilesY: number
  tileCells: number
  cellSize: number
  widthM: number
  heightM: number
  tileFormat: number
}

export interface WorldMetadata {
  world: WorldDescriptor
  physics: {
    playerRadius: number
    eyeHeight: number
    walkSpeed: number
    runSpeed: number
  }
  network: {
    simulationHz: number
    snapshotHz: number
    fullDetailRadius: number
    simplifiedRadius: number
  }
  chat: {
    maxLength: number
    rateLimit: number
    rateWindowSeconds: number
    proximityRadius: number
  }
}

export interface Building {
  id: number
  /** Flat `[x0, y0, x1, y1, ...]` ring in tile-local cell coordinates. */
  footprint: Int16Array
  height: number
  minHeight: number
  levels: number
  roofType: number
  category: number
  facadeStyle: number
  windowStyle: number
  color: number
  walkable: boolean
  hasInterior: boolean
}

export interface Road {
  id: number
  centerline: Int16Array
  width: number
  type: number
  surfaceStyle: number
  name: string | null
}

export interface Prop {
  id: number
  x: number
  y: number
  kind: number
}

export interface SpawnPoint {
  x: number
  y: number
  heading: number
}

export interface WorldTile {
  id: string
  version: number
  tileX: number
  tileY: number
  cells: number
  cellSize: number
  collision: Uint8Array
  heights: Uint8Array
  styles: Uint8Array
  buildings: Building[]
  roads: Road[]
  props: Prop[]
  spawnPoints: SpawnPoint[]
}

/** Local, predicted state for the player this browser controls. */
export interface LocalPlayer {
  id: number
  nickname: string
  color: number
  x: number
  y: number
  z: number
  yaw: number
  pitch: number
  animation: number
}

/** A remote player as last reported by the server. */
export interface RemotePlayer {
  id: number
  nickname: string
  color: number
  x: number
  y: number
  yaw: number
  pitch: number
  animation: number
  simplified: boolean
  /** Client clock, milliseconds, when this sample arrived. */
  receivedAt: number
}

export type ChatScope = 'global' | 'proximity' | 'system'

export interface ChatMessage {
  id: number
  senderId: number
  nickname: string
  scope: ChatScope
  text: string
  createdAt: number
}

export type ConnectionPhase =
  | 'idle'
  | 'loading-world'
  | 'connecting'
  | 'online'
  | 'reconnecting'
  | 'refused'
  | 'failed'

export interface ConnectionStatus {
  phase: ConnectionPhase
  detail: string
  latencyMs: number
  attempt: number
}
