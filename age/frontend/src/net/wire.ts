/**
 * The binary wire protocol, browser side.
 *
 * Mirror of `age/infrastructure/wire.py`. Little-endian throughout, one byte of
 * message type at the front of every packet, and no floats on the wire except the two
 * timestamps: positions are fixed-point integers, angles are normalised uint16s, and
 * health is a percentage byte.
 *
 * Quantising deliberately is what lets both sides round identically. The one trap is
 * `Math.round`, which breaks ties upward, where Python's `round` breaks them to even —
 * so the server has its own `round_half_up` and this file uses `Math.round`. A position
 * landing on exactly half a step would otherwise disagree by one unit forever, and
 * that shows up as a reconciliation error that never settles.
 */

import {
  ANGLE_SCALE,
  CHAT_MAX_LENGTH,
  MAX_NAME_LENGTH,
  PERCENT_SCALE,
  POSITION_SCALE,
  PROTOCOL_VERSION,
} from '../domain/constants'

// --- message types ----------------------------------------------------------
//
// Client-to-server types have the high bit clear, server-to-client set, so a packet
// arriving on the wrong side is rejected by inspection rather than by accident.

export const CLIENT_HELLO = 0x01
export const CLIENT_READY = 0x02
export const CLIENT_INPUT = 0x03
export const CLIENT_ACTION = 0x04
export const CLIENT_CHAT = 0x05
export const CLIENT_BUILD = 0x06
export const CLIENT_PING = 0x07
export const CLIENT_DEV_TIER = 0x08
export const CLIENT_COMPOSE = 0x09
export const CLIENT_INVENTORY = 0x0a

export const SERVER_WELCOME = 0x81
export const SERVER_SNAPSHOT = 0x82
export const SERVER_SPAWN = 0x83
export const SERVER_DESPAWN = 0x84
export const SERVER_TOPOLOGY = 0x85
export const SERVER_COMBAT = 0x86
export const SERVER_CHAT = 0x87
export const SERVER_TILES = 0x88
export const SERVER_PONG = 0x89
export const SERVER_ERROR = 0x8a
export const SERVER_PROGRESS = 0x8b
export const SERVER_INVENTORY = 0x8c

// What to do with a slot. `EQUIP`, `USE` and `DROP` address an inventory index;
// `UNEQUIP` addresses an equipment slot.
export const INVENTORY_EQUIP = 0
export const INVENTORY_UNEQUIP = 1
export const INVENTORY_USE = 2
export const INVENTORY_DROP = 3

export const INPUT_UP = 1 << 0
export const INPUT_DOWN = 1 << 1
export const INPUT_LEFT = 1 << 2
export const INPUT_RIGHT = 1 << 3
export const INPUT_RUN = 1 << 4

// The state byte: bit 0 is liveness, bits 1-3 the AI or movement state. Named here
// because it is a protocol field, and both the session and the renderer decide what to
// draw from it.
export const STATE_ALIVE = 1 << 0

export const DESPAWN_OUT_OF_RANGE = 0
export const DESPAWN_DIED = 1
export const DESPAWN_DISCONNECTED = 2
export const DESPAWN_CHUNK_RETIRED = 3

export const ERROR_STALE_TOPOLOGY = 1
export const ERROR_SAFE_ZONE = 2
export const ERROR_OUT_OF_RANGE = 3
export const ERROR_ON_COOLDOWN = 4
export const ERROR_NO_RESOURCE = 5
export const ERROR_NO_MATERIAL = 6
export const ERROR_INVALID = 7
export const ERROR_RATE_LIMITED = 8
export const ERROR_DEAD = 9
// Distinct from ERROR_INVALID because the client can act on it: a mismatch means a
// stale cached bundle, and the only fix is a hard reload.
export const ERROR_VERSION_MISMATCH = 10

export const BUILD_PLACE = 0
export const BUILD_HARVEST = 1

/** Which fields a snapshot delta carries. Mirrors `DirtyField`. */
export const FIELD_POSITION = 1 << 0
export const FIELD_VELOCITY = 1 << 1
export const FIELD_FACING = 1 << 2
export const FIELD_HEALTH = 1 << 3
export const FIELD_RESOURCE = 1 << 4
export const FIELD_STATE = 1 << 5
export const FIELD_APPEARANCE = 1 << 6

export class ProtocolError extends Error {}

// --- quantisation -----------------------------------------------------------

export function encodePosition(tiles: number): number {
  return Math.round(tiles * POSITION_SCALE)
}

export function decodePosition(raw: number): number {
  return raw / POSITION_SCALE
}

export function encodeAngle(radians: number): number {
  const turn = 2 * Math.PI
  let normalised = radians % turn
  if (normalised < 0) normalised += turn
  return Math.round(normalised * ANGLE_SCALE) & 0xffff
}

export function decodeAngle(raw: number): number {
  return raw / ANGLE_SCALE
}

export function decodePercent(raw: number): number {
  return raw / PERCENT_SCALE
}

// --- writer and reader ------------------------------------------------------

const encoder = new TextEncoder()
const decoder = new TextDecoder('utf-8')

/**
 * Little-endian byte builder.
 *
 * Grows by doubling rather than by allocating per field. Client packets are tens of
 * bytes and one is sent per input tick, so at 30 Hz the allocation churn of the naive
 * version is the kind of thing that shows up as a sawtooth in a memory profile.
 */
export class Writer {
  private view: DataView
  private bytes: Uint8Array
  private offset = 0

  constructor(messageType: number, capacity = 64) {
    this.bytes = new Uint8Array(capacity)
    this.view = new DataView(this.bytes.buffer)
    this.u8(messageType)
  }

  private need(count: number): void {
    if (this.offset + count <= this.bytes.length) return
    let size = this.bytes.length * 2
    while (size < this.offset + count) size *= 2
    const grown = new Uint8Array(size)
    grown.set(this.bytes)
    this.bytes = grown
    this.view = new DataView(grown.buffer)
  }

  u8(value: number): this {
    this.need(1)
    this.view.setUint8(this.offset, value & 0xff)
    this.offset += 1
    return this
  }

  u16(value: number): this {
    this.need(2)
    this.view.setUint16(this.offset, value & 0xffff, true)
    this.offset += 2
    return this
  }

  u32(value: number): this {
    this.need(4)
    this.view.setUint32(this.offset, value >>> 0, true)
    this.offset += 4
    return this
  }

  i32(value: number): this {
    this.need(4)
    this.view.setInt32(this.offset, value | 0, true)
    this.offset += 4
    return this
  }

  f64(value: number): this {
    this.need(8)
    this.view.setFloat64(this.offset, value, true)
    this.offset += 8
    return this
  }

  /**
   * Length-prefixed UTF-8, truncated on encoded bytes but never mid-character.
   *
   * `TextEncoder.encodeInto` reports how many whole characters fitted, which is
   * exactly the boundary-safe truncation the server does by decoding and retrying.
   */
  text(value: string, limit: number): this {
    const scratch = new Uint8Array(limit)
    const { written } = encoder.encodeInto(value, scratch)
    const length = written ?? 0
    this.u16(length)
    this.need(length)
    this.bytes.set(scratch.subarray(0, length), this.offset)
    this.offset += length
    return this
  }

  build(): Uint8Array {
    return this.bytes.subarray(0, this.offset)
  }
}

/** Little-endian byte cursor that refuses to read past the end. */
export class Reader {
  private view: DataView

  constructor(
    private readonly bytes: Uint8Array,
    private offset = 0,
  ) {
    this.view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength)
  }

  get remaining(): number {
    return this.bytes.byteLength - this.offset
  }

  private take(count: number): number {
    if (this.remaining < count) {
      throw new ProtocolError(`packet ended early: wanted ${count}, had ${this.remaining}`)
    }
    const at = this.offset
    this.offset += count
    return at
  }

  u8(): number {
    return this.view.getUint8(this.take(1))
  }

  u16(): number {
    return this.view.getUint16(this.take(2), true)
  }

  u32(): number {
    return this.view.getUint32(this.take(4), true)
  }

  i32(): number {
    return this.view.getInt32(this.take(4), true)
  }

  /**
   * A 64-bit unsigned integer, as a BigInt.
   *
   * The world seed is the only field this wide, and it has to survive intact: it feeds
   * the terrain hash, where losing the low bits to a double's 53-bit mantissa would
   * generate a different world from the server's.
   */
  u64(): bigint {
    return this.view.getBigUint64(this.take(8), true)
  }

  f64(): number {
    return this.view.getFloat64(this.take(8), true)
  }

  text(limit: number): string {
    const length = this.u16()
    if (length > limit) {
      throw new ProtocolError(`string of ${length} bytes exceeds the ${limit} byte limit`)
    }
    const at = this.take(length)
    return decoder.decode(this.bytes.subarray(at, at + length))
  }
}

// --- client to server -------------------------------------------------------

export interface Appearance {
  body: number
  hair: number
  palette: number
  outfit: number
  accent: number
}

export function encodeHello(
  characterName: string,
  classId: number,
  appearance: Appearance,
): Uint8Array {
  return new Writer(CLIENT_HELLO)
    .u16(PROTOCOL_VERSION)
    .text(characterName, MAX_NAME_LENGTH * 4)
    .u8(classId)
    .u8(appearance.body)
    .u8(appearance.hair)
    .u8(appearance.palette)
    .u8(appearance.outfit)
    .u8(appearance.accent)
    .build()
}

export function encodeReady(): Uint8Array {
  return new Writer(CLIENT_READY, 1).build()
}

export interface InputFrame {
  sequence: number
  topologyVersion: number
  buttons: number
  facing: number
  predictedX: number
  predictedY: number
  deltaTime: number
}

export function encodeInput(frame: InputFrame): Uint8Array {
  return new Writer(CLIENT_INPUT, 24)
    .u32(frame.sequence)
    .u32(frame.topologyVersion)
    .u8(frame.buttons)
    .u16(encodeAngle(frame.facing))
    .i32(encodePosition(frame.predictedX))
    .i32(encodePosition(frame.predictedY))
    // Delta time in ten-thousandths of a second. Two bytes covers 6.5 s, far more
    // than any tick the client will admit to, at a resolution finer than one.
    .u16(Math.min(0xffff, Math.round(frame.deltaTime * 10000)))
    .build()
}

export function encodeAction(
  sequence: number,
  topologyVersion: number,
  abilityId: number,
  targetX: number,
  targetY: number,
  targetEntity: number,
): Uint8Array {
  return new Writer(CLIENT_ACTION, 24)
    .u32(sequence)
    .u32(topologyVersion)
    .u16(abilityId)
    .i32(encodePosition(targetX))
    .i32(encodePosition(targetY))
    .u32(targetEntity)
    .build()
}

export function encodeChat(channel: number, text: string): Uint8Array {
  return new Writer(CLIENT_CHAT, 64).u8(channel).text(text, CHAT_MAX_LENGTH * 4).build()
}

export function encodeBuild(
  topologyVersion: number,
  action: number,
  tileX: number,
  tileY: number,
  material: string,
): Uint8Array {
  return new Writer(CLIENT_BUILD, 48)
    .u32(topologyVersion)
    .u8(action)
    .i32(tileX)
    .i32(tileY)
    .text(material, 32)
    .build()
}

export function encodePing(clientTime: number): Uint8Array {
  return new Writer(CLIENT_PING, 16).f64(clientTime).build()
}

export function encodeDevTier(targetTier: number): Uint8Array {
  return new Writer(CLIENT_DEV_TIER, 2).u8(targetTier).build()
}

/** Take a second half at level-up, becoming the pairing's class (GDD 6.3). */
export function encodeCompose(half: number): Uint8Array {
  return new Writer(CLIENT_COMPOSE, 2).u8(half).build()
}

/**
 * Equip, unequip, use, or drop one slot.
 *
 * `count` is only read by a drop. Everything else moves exactly one item, because the
 * equipment map has no way to answer what wearing two of something would mean.
 */
export function encodeInventory(action: number, slot: number, count = 1): Uint8Array {
  return new Writer(CLIENT_INVENTORY, 4).u8(action).u8(slot).u8(count).build()
}

// --- server to client -------------------------------------------------------

export interface Welcome {
  kind: 'welcome'
  protocolVersion: number
  entityId: number
  worldSeed: bigint
  topologyVersion: number
  currentTier: number
  edgeId: string
  spawnX: number
  spawnY: number
  serverTime: number
}

export interface EntityDelta {
  entityId: number
  fields: number
  x?: number
  y?: number
  vx?: number
  vy?: number
  facing?: number
  health?: number
  resource?: number
  state?: number
  appearance?: Appearance
}

export interface Snapshot {
  kind: 'snapshot'
  tick: number
  serverTime: number
  acknowledgedInput: number
  topologyVersion: number
  dayPhase: number
  weather: number
  deltas: EntityDelta[]
}

export interface Spawn {
  kind: 'spawn'
  entityId: number
  entityKind: number
  archetype: number
  name: string
  x: number
  y: number
  facing: number
  health: number
  level: number
  /** Packed liveness and animation state, the same byte a delta carries. */
  state: number
  appearance: Appearance
}

export interface Despawn {
  kind: 'despawn'
  entityId: number
  reason: number
}

export interface Topology {
  kind: 'topology'
  topologyVersion: number
  currentTier: number
  activeChunks: string[]
  retiringChunks: string[]
}

export interface Combat {
  kind: 'combat'
  attackerId: number
  targetId: number
  abilityId: number
  damage: number
  healing: number
  killed: boolean
  x: number
  y: number
}

export interface Chat {
  kind: 'chat'
  senderId: number
  channel: number
  senderName: string
  text: string
}

export interface Tiles {
  kind: 'tiles'
  chunkKey: string
  changes: Array<[number, number]>
}

export interface Pong {
  kind: 'pong'
  clientTime: number
  serverTime: number
}

export interface ServerError {
  kind: 'error'
  code: number
  detail: string
}

export interface Progress {
  kind: 'progress'
  level: number
  experience: number
  /** Experience needed to leave the current level. */
  nextLevelAt: number
  classId: number
  /** Whether the character is owed the level-up class choice. */
  composeAvailable: boolean
  /**
   * The kit, in bar order, starting with the basic attack.
   *
   * Sent by the server rather than derived from the class id so the bar cannot show
   * a button the server would refuse.
   */
  abilityIds: number[]
}

/** One occupied inventory slot. The index in {@link Inventory.stacks} is its address. */
export interface ItemStack {
  itemId: number
  count: number
}

export interface Inventory {
  kind: 'inventory'
  /** How many stacks the pack holds, so the grid can draw its empty slots. */
  capacity: number
  stacks: ItemStack[]
  /** Worn items, by equipment slot. */
  equipped: Array<{ slot: number; itemId: number }>
  /**
   * What the loadout adds up to.
   *
   * The maxima are here rather than derived from the class because the client only
   * ever sees vitals as a fraction: without these it can draw the bar but cannot say
   * what the bar is a fraction of.
   */
  maxHealth: number
  maxResource: number
  bonusDamage: number
  /** Walking speed in tiles per second, after class and equipment. */
  moveSpeed: number
}

export type ServerPacket =
  | Welcome
  | Snapshot
  | Spawn
  | Despawn
  | Topology
  | Combat
  | Chat
  | Tiles
  | Pong
  | ServerError
  | Progress
  | Inventory

function readAppearance(reader: Reader): Appearance {
  return {
    body: reader.u8(),
    hair: reader.u8(),
    palette: reader.u8(),
    outfit: reader.u8(),
    accent: reader.u8(),
  }
}

/** Parse one server frame. Throws {@link ProtocolError} on anything malformed. */
export function decodeServerPacket(bytes: Uint8Array): ServerPacket {
  if (bytes.byteLength === 0) throw new ProtocolError('empty packet')

  const messageType = bytes[0]
  const reader = new Reader(bytes, 1)

  switch (messageType) {
    case SERVER_WELCOME:
      return {
        kind: 'welcome',
        protocolVersion: reader.u16(),
        entityId: reader.u32(),
        worldSeed: reader.u64(),
        topologyVersion: reader.u32(),
        currentTier: reader.u8(),
        edgeId: reader.text(64),
        spawnX: decodePosition(reader.i32()),
        spawnY: decodePosition(reader.i32()),
        serverTime: reader.f64(),
      }

    case SERVER_SNAPSHOT: {
      const tick = reader.u32()
      const serverTime = reader.f64()
      const acknowledgedInput = reader.u32()
      const topologyVersion = reader.u32()
      const dayPhase = reader.u16() / 65535
      const weather = reader.u8()
      const count = reader.u16()

      const deltas: EntityDelta[] = []
      for (let i = 0; i < count; i += 1) {
        const delta: EntityDelta = { entityId: reader.u32(), fields: reader.u8() }
        if (delta.fields & FIELD_POSITION) {
          delta.x = decodePosition(reader.i32())
          delta.y = decodePosition(reader.i32())
        }
        if (delta.fields & FIELD_VELOCITY) {
          delta.vx = decodePosition(reader.i32())
          delta.vy = decodePosition(reader.i32())
        }
        if (delta.fields & FIELD_FACING) delta.facing = decodeAngle(reader.u16())
        if (delta.fields & FIELD_HEALTH) delta.health = decodePercent(reader.u8())
        if (delta.fields & FIELD_RESOURCE) delta.resource = decodePercent(reader.u8())
        if (delta.fields & FIELD_STATE) delta.state = reader.u8()
        if (delta.fields & FIELD_APPEARANCE) delta.appearance = readAppearance(reader)
        deltas.push(delta)
      }

      return {
        kind: 'snapshot',
        tick,
        serverTime,
        acknowledgedInput,
        topologyVersion,
        dayPhase,
        weather,
        deltas,
      }
    }

    case SERVER_SPAWN:
      return {
        kind: 'spawn',
        entityId: reader.u32(),
        entityKind: reader.u8(),
        archetype: reader.u8(),
        name: reader.text(MAX_NAME_LENGTH * 4),
        x: decodePosition(reader.i32()),
        y: decodePosition(reader.i32()),
        facing: decodeAngle(reader.u16()),
        health: decodePercent(reader.u8()),
        level: reader.u16(),
        state: reader.u8(),
        appearance: readAppearance(reader),
      }

    case SERVER_DESPAWN:
      return { kind: 'despawn', entityId: reader.u32(), reason: reader.u8() }

    case SERVER_TOPOLOGY: {
      const topologyVersion = reader.u32()
      const currentTier = reader.u8()
      const activeChunks: string[] = []
      for (let i = reader.u16(); i > 0; i -= 1) activeChunks.push(reader.text(96))
      const retiringChunks: string[] = []
      for (let i = reader.u16(); i > 0; i -= 1) retiringChunks.push(reader.text(96))
      return { kind: 'topology', topologyVersion, currentTier, activeChunks, retiringChunks }
    }

    case SERVER_COMBAT:
      return {
        kind: 'combat',
        attackerId: reader.u32(),
        targetId: reader.u32(),
        abilityId: reader.u16(),
        damage: reader.u16(),
        healing: reader.u16(),
        killed: reader.u8() !== 0,
        x: decodePosition(reader.i32()),
        y: decodePosition(reader.i32()),
      }

    case SERVER_CHAT:
      return {
        kind: 'chat',
        senderId: reader.u32(),
        channel: reader.u8(),
        senderName: reader.text(MAX_NAME_LENGTH * 4),
        text: reader.text(CHAT_MAX_LENGTH * 4),
      }

    case SERVER_TILES: {
      const chunkKey = reader.text(96)
      const changes: Array<[number, number]> = []
      for (let i = reader.u16(); i > 0; i -= 1) changes.push([reader.u16(), reader.u8()])
      return { kind: 'tiles', chunkKey, changes }
    }

    case SERVER_PONG:
      return { kind: 'pong', clientTime: reader.f64(), serverTime: reader.f64() }

    case SERVER_ERROR:
      return { kind: 'error', code: reader.u8(), detail: reader.text(160) }

    case SERVER_PROGRESS: {
      const level = reader.u16()
      const experience = reader.u32()
      const nextLevelAt = reader.u32()
      const classId = reader.u8()
      const composeAvailable = reader.u8() !== 0
      const count = reader.u8()
      const abilityIds: number[] = []
      for (let i = 0; i < count; i += 1) abilityIds.push(reader.u16())
      return {
        kind: 'progress',
        level,
        experience,
        nextLevelAt,
        classId,
        composeAvailable,
        abilityIds,
      }
    }

    case SERVER_INVENTORY: {
      const capacity = reader.u8()
      const stacks: ItemStack[] = []
      for (let i = reader.u8(); i > 0; i -= 1) {
        stacks.push({ itemId: reader.u16(), count: reader.u16() })
      }
      const equipped: Array<{ slot: number; itemId: number }> = []
      for (let i = reader.u8(); i > 0; i -= 1) {
        equipped.push({ slot: reader.u8(), itemId: reader.u16() })
      }
      return {
        kind: 'inventory',
        capacity,
        stacks,
        equipped,
        maxHealth: reader.u16(),
        maxResource: reader.u16(),
        bonusDamage: reader.u16(),
        // Hundredths of a tile per second, which is how the server keeps the only
        // float in the packet off the wire.
        moveSpeed: reader.u16() / 100,
      }
    }

    default:
      throw new ProtocolError(
        `unknown server message type 0x${messageType.toString(16).padStart(2, '0')}`,
      )
  }
}
