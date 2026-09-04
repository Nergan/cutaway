/**
 * The `/api/world` document, and where the client is mounted.
 *
 * One fetch before the socket opens. It carries the world seed the generator needs, the class
 * catalogue the picker shows, and the biome tints the renderer grades by — all things that are
 * server-authoritative and none of which change during a session.
 */

export interface AbilityInfo {
  abilityId: number
  key: string
  name: string
  kind: number
  rangeTiles: number
  radiusTiles: number
  cooldownMs: number
  resourceCost: number
  damage: number
  healing: number
}

export interface ClassInfo {
  classId: number
  key: string
  name: string
  role: number
  fantasy: string
  isPure: boolean
  abilities: AbilityInfo[]
}

export interface HubInfo {
  hubId: number
  name: string
  x: number
  y: number
  radiusTiles: number
}

export interface BiomeInfo {
  biome: number
  name: string
  ambientTint: [number, number, number]
  danger: number
}

export interface WorldInfo {
  worldId: string
  worldSeed: number
  protocol: number
  edgeId: string
  segments: number
  topologyVersion: number
  currentTier: number
  population: number
  maxClients: number
  devControls: boolean
  cdnBase: string
  dayPhase: number
  weather: number
  hubs: HubInfo[]
  classes: ClassInfo[]
  biomes: BiomeInfo[]
}

/**
 * Where this bundle is mounted.
 *
 * Derived from the document's own path rather than hardcoded, because the same build runs at
 * `/age` behind the orchestrator and at `/` under a bare dev server, and the API and WebSocket
 * URLs have to follow whichever it is.
 */
export function mountBase(): string {
  const path = window.location.pathname
  const marker = '/age'
  const at = path.indexOf(marker)
  if (at < 0) return ''
  return path.slice(0, at + marker.length)
}

export function apiBase(): string {
  return `${mountBase()}/api`
}

export function socketUrl(): string {
  const scheme = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${scheme}//${window.location.host}${mountBase()}/ws`
}

export async function fetchWorld(): Promise<WorldInfo> {
  const response = await fetch(`${apiBase()}/world`)
  if (!response.ok) {
    // The orchestrator starts this project lazily, so the first request can arrive while the
    // world is still bootstrapping. The message says which of the two it was.
    throw new Error(
      response.status === 503
        ? 'The world is still waking up. Try again in a moment.'
        : `The server refused to describe the world (HTTP ${response.status}).`,
    )
  }
  return (await response.json()) as WorldInfo
}

/** Ask the server to move the accordion. Only honoured when dev controls are on. */
export async function forceTier(tier: number): Promise<void> {
  await fetch(`${apiBase()}/dev/tier/${tier}`, { method: 'POST' })
}
