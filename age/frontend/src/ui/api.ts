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
  /** One half only: the four a character may be created as (GDD 6.3). */
  isBase: boolean
  /** The half chosen at creation. */
  origin: number
  /** The half added at level-up, or null while the class is still a base class. */
  chosen: number | null
  abilities: AbilityInfo[]
}

/**
 * One entry of the item catalogue.
 *
 * Static, so it arrives here once rather than riding on every inventory packet. The
 * packet carries ids and counts; everything a slot needs to draw itself is looked up
 * against this.
 */
export interface ItemInfo {
  itemId: number
  key: string
  name: string
  /** 0 material, 1 consumable, 2 equipment. */
  kind: number
  /** 0 for anything that cannot be worn. */
  slot: number
  /** 0 common through 3 epic. Tinting only; the stats carry the weight. */
  rarity: number
  stackLimit: number
  description: string
  bonusHealth: number
  bonusResource: number
  bonusDamage: number
  bonusSpeed: number
  restoresHealth: number
  restoresResource: number
}

/** Values of {@link ItemInfo.kind}, mirroring the server's `ItemKind`. */
export const ITEM_MATERIAL = 0
export const ITEM_CONSUMABLE = 1
export const ITEM_EQUIPMENT = 2

export interface EquipmentSlotInfo {
  slot: number
  name: string
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
  /**
   * Distinct looks per appearance byte, for the creation sliders.
   *
   * From the server because the counts are not derivable from anything the client holds:
   * one byte feeds two separate tables in the baker, and a copy maintained here drifted
   * from them the moment either changed.
   */
  appearanceRanges: Record<string, number>
  /** How many stacks the pack holds, so the grid can be drawn before the first packet. */
  inventorySlots: number
  equipmentSlots: EquipmentSlotInfo[]
  items: ItemInfo[]
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
