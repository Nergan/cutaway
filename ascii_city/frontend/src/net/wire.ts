/**
 * Mirror of `ascii_city/infrastructure/wire_codec.py`.
 *
 * The client encodes input, chat and ping; it decodes everything the server
 * sends. Every field is little-endian. `docs/protocol.md` is normative.
 */

import { ANGLE_SCALE, PITCH_SCALE, POSITION_SCALE, TAU } from '../domain/constants'
import type { ChatMessage, ChatScope } from '../domain/types'

// Client to server.
export const MSG_INPUT = 0x01
export const MSG_CHAT = 0x02
export const MSG_PING = 0x03
export const MSG_RENAME = 0x04

export const INPUT_FLAG_SPRINT = 0x01
export const INPUT_FLAG_JUMP = 0x02

// Server to client.
export const MSG_WELCOME = 0x81
export const MSG_SNAPSHOT = 0x82
export const MSG_CHAT_OUT = 0x83
export const MSG_NOTICE = 0x84
export const MSG_ROSTER_SYNC = 0x85
export const MSG_ROSTER_ADD = 0x86
export const MSG_ROSTER_REMOVE = 0x87
export const MSG_PONG = 0x88
export const MSG_ROSTER_UPDATE = 0x89

export const NOTICE_INFO = 0
export const NOTICE_WARNING = 1
export const NOTICE_ERROR = 2
export const NOTICE_RATE_LIMIT = 3

export const MAX_FRAME_BYTES = 4096

export const SNAPSHOT_FLAG_SIMPLIFIED = 0x04

const INPUT_FRAME_BYTES = 1 + 14
const SNAPSHOT_ENTRY_BYTES = 10

const encoder = new TextEncoder()
const decoder = new TextDecoder()

const SCOPES: ChatScope[] = ['global', 'proximity', 'system']

export class WireError extends Error {}

// --- scalars ---------------------------------------------------------------

export function encodePosition(value: number): number {
  const scaled = Math.round(value * POSITION_SCALE)
  return scaled < 0 ? 0 : scaled > 65535 ? 65535 : scaled
}

export function decodePosition(value: number): number {
  return value / POSITION_SCALE
}

export function encodeYaw(value: number): number {
  return Math.round((((value % TAU) + TAU) % TAU / TAU) * ANGLE_SCALE) & 0xffff
}

export function decodeYaw(value: number): number {
  return (value / ANGLE_SCALE) * TAU
}

export function encodePitch(value: number): number {
  const scaled = Math.round(value * PITCH_SCALE)
  return scaled < -127 ? -127 : scaled > 127 ? 127 : scaled
}

export function decodePitch(value: number): number {
  return value / PITCH_SCALE
}

// --- outbound --------------------------------------------------------------

export interface InputCommand {
  sequence: number
  /** -1..1, positive is forward. */
  forward: number
  /** -1..1, positive is right. */
  strafe: number
  yaw: number
  pitch: number
  sprint: boolean
  jump: boolean
  clientTime: number
}

function clampAxis(value: number): number {
  if (!Number.isFinite(value)) return 0
  const scaled = Math.round(value * 100)
  return scaled < -100 ? -100 : scaled > 100 ? 100 : scaled
}

export function encodeInput(command: InputCommand): Uint8Array {
  const frame = new Uint8Array(INPUT_FRAME_BYTES)
  const view = new DataView(frame.buffer)
  view.setUint8(0, MSG_INPUT)
  view.setUint32(1, command.sequence >>> 0, true)
  view.setInt8(5, clampAxis(command.forward))
  view.setInt8(6, clampAxis(command.strafe))
  view.setUint16(7, encodeYaw(command.yaw), true)
  view.setInt8(9, encodePitch(command.pitch))
  let flags = 0
  if (command.sprint) flags |= INPUT_FLAG_SPRINT
  if (command.jump) flags |= INPUT_FLAG_JUMP
  view.setUint8(10, flags)
  view.setUint32(11, command.clientTime >>> 0, true)
  return frame
}

export function encodeChat(scope: 'global' | 'proximity', text: string): Uint8Array {
  const payload = encoder.encode(text)
  if (payload.byteLength > MAX_FRAME_BYTES - 4) {
    throw new WireError('Chat message is too long to send.')
  }
  const frame = new Uint8Array(4 + payload.byteLength)
  const view = new DataView(frame.buffer)
  view.setUint8(0, MSG_CHAT)
  view.setUint8(1, scope === 'proximity' ? 1 : 0)
  view.setUint16(2, payload.byteLength, true)
  frame.set(payload, 4)
  return frame
}

export function encodePing(clientTime: number): Uint8Array {
  const frame = new Uint8Array(5)
  const view = new DataView(frame.buffer)
  view.setUint8(0, MSG_PING)
  view.setUint32(1, clientTime >>> 0, true)
  return frame
}

export function encodeRename(nickname: string): Uint8Array {
  const payload = encoder.encode(nickname)
  const frame = new Uint8Array(3 + payload.byteLength)
  const view = new DataView(frame.buffer)
  view.setUint8(0, MSG_RENAME)
  view.setUint16(1, payload.byteLength, true)
  frame.set(payload, 3)
  return frame
}

// --- inbound ---------------------------------------------------------------

export interface WelcomeFrame {
  kind: 'welcome'
  playerId: number
  color: number
  nickname: string
  x: number
  y: number
  z: number
  yaw: number
  simulationHz: number
  snapshotHz: number
  serverTimeMs: number
  tilesX: number
  tilesY: number
  tileCells: number
  cellSize: number
  worldVersion: number
  worldId: string
}

export interface SnapshotEntry {
  id: number
  x: number
  y: number
  yaw: number
  pitch: number
  animation: number
  simplified: boolean
}

export interface SnapshotFrame {
  kind: 'snapshot'
  tick: number
  ackSequence: number
  x: number
  y: number
  z: number
  entries: SnapshotEntry[]
}

export interface ChatFrame {
  kind: 'chat'
  message: ChatMessage
}

export interface NoticeFrame {
  kind: 'notice'
  code: number
  text: string
}

export interface RosterMember {
  id: number
  nickname: string
  color: number
}

export interface RosterSyncFrame {
  kind: 'roster-sync'
  members: RosterMember[]
}

export interface RosterAddFrame {
  kind: 'roster-add'
  member: RosterMember
}

export interface RosterRemoveFrame {
  kind: 'roster-remove'
  id: number
}

export interface RosterUpdateFrame {
  kind: 'roster-update'
  member: RosterMember
}

export interface PongFrame {
  kind: 'pong'
  clientTime: number
  serverTimeMs: number
}

export type ServerFrame =
  | WelcomeFrame
  | SnapshotFrame
  | ChatFrame
  | NoticeFrame
  | RosterSyncFrame
  | RosterAddFrame
  | RosterRemoveFrame
  | RosterUpdateFrame
  | PongFrame

function readString(bytes: Uint8Array, at: number, length: number): string {
  if (at + length > bytes.byteLength) throw new WireError('Frame is truncated.')
  return decoder.decode(bytes.subarray(at, at + length))
}

export function decodeServerFrame(payload: ArrayBuffer | Uint8Array): ServerFrame {
  const bytes = payload instanceof Uint8Array ? payload : new Uint8Array(payload)
  if (bytes.byteLength === 0) throw new WireError('Empty frame.')
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength)

  switch (bytes[0]) {
    case MSG_WELCOME:
      return decodeWelcome(bytes, view)
    case MSG_SNAPSHOT:
      return decodeSnapshot(bytes, view)
    case MSG_CHAT_OUT:
      return decodeChat(bytes, view)
    case MSG_NOTICE:
      return {
        kind: 'notice',
        code: view.getUint8(1),
        text: readString(bytes, 4, view.getUint16(2, true)),
      }
    case MSG_ROSTER_SYNC:
      return decodeRosterSync(bytes, view)
    case MSG_ROSTER_ADD:
      return { kind: 'roster-add', member: readRosterEntry(bytes, view, 1).member }
    case MSG_ROSTER_UPDATE:
      return { kind: 'roster-update', member: readRosterEntry(bytes, view, 1).member }
    case MSG_ROSTER_REMOVE:
      return { kind: 'roster-remove', id: view.getUint16(1, true) }
    case MSG_PONG:
      return {
        kind: 'pong',
        clientTime: view.getUint32(1, true),
        serverTimeMs: view.getUint32(5, true),
      }
    default:
      throw new WireError(`Unknown frame type 0x${bytes[0].toString(16)}.`)
  }
}

function decodeWelcome(bytes: Uint8Array, view: DataView): WelcomeFrame {
  const playerId = view.getUint16(1, true)
  const color = view.getUint8(3)
  const nickLength = view.getUint8(4)
  const nickname = readString(bytes, 5, nickLength)
  let at = 5 + nickLength
  const x = decodePosition(view.getUint16(at, true))
  const y = decodePosition(view.getUint16(at + 2, true))
  const z = decodePosition(view.getUint16(at + 4, true))
  const yaw = decodeYaw(view.getUint16(at + 6, true))
  const simulationHz = view.getUint8(at + 8)
  const snapshotHz = view.getUint8(at + 9)
  const serverTimeMs = view.getUint32(at + 10, true)
  const tilesX = view.getUint8(at + 14)
  const tilesY = view.getUint8(at + 15)
  const tileCells = view.getUint16(at + 16, true)
  const cellSize = view.getFloat32(at + 18, true)
  const worldVersion = view.getUint32(at + 22, true)
  at += 26
  const worldId = readString(bytes, at + 1, view.getUint8(at))
  return {
    kind: 'welcome',
    playerId,
    color,
    nickname,
    x,
    y,
    z,
    yaw,
    simulationHz,
    snapshotHz,
    serverTimeMs,
    tilesX,
    tilesY,
    tileCells,
    cellSize,
    worldVersion,
    worldId,
  }
}

function decodeSnapshot(bytes: Uint8Array, view: DataView): SnapshotFrame {
  const tick = view.getUint32(1, true)
  const ackSequence = view.getUint32(5, true)
  const x = decodePosition(view.getUint16(9, true))
  const y = decodePosition(view.getUint16(11, true))
  const z = decodePosition(view.getUint16(13, true))
  const count = view.getUint8(15)
  const entries: SnapshotEntry[] = []
  for (let index = 0; index < count; index += 1) {
    const at = 16 + index * SNAPSHOT_ENTRY_BYTES
    if (at + SNAPSHOT_ENTRY_BYTES > bytes.byteLength) {
      throw new WireError('Snapshot is truncated.')
    }
    const flags = view.getUint8(at + 9)
    entries.push({
      id: view.getUint16(at, true),
      x: decodePosition(view.getUint16(at + 2, true)),
      y: decodePosition(view.getUint16(at + 4, true)),
      yaw: decodeYaw(view.getUint16(at + 6, true)),
      pitch: decodePitch(view.getInt8(at + 8)),
      animation: flags & 0x03,
      simplified: (flags & SNAPSHOT_FLAG_SIMPLIFIED) !== 0,
    })
  }
  return { kind: 'snapshot', tick, ackSequence, x, y, z, entries }
}

function decodeChat(bytes: Uint8Array, view: DataView): ChatFrame {
  const id = view.getUint32(1, true)
  const senderId = view.getUint16(5, true)
  const scope = SCOPES[view.getUint8(7)] ?? 'system'
  const createdAt = view.getFloat64(8, true)
  const nickLength = view.getUint8(16)
  const nickname = readString(bytes, 17, nickLength)
  const at = 17 + nickLength
  const textLength = view.getUint16(at, true)
  const text = readString(bytes, at + 2, textLength)
  return { kind: 'chat', message: { id, senderId, nickname, scope, text, createdAt } }
}

function readRosterEntry(
  bytes: Uint8Array,
  view: DataView,
  at: number,
): { member: RosterMember; next: number } {
  const id = view.getUint16(at, true)
  const color = view.getUint8(at + 2)
  const length = view.getUint8(at + 3)
  const nickname = readString(bytes, at + 4, length)
  return { member: { id, nickname, color }, next: at + 4 + length }
}

function decodeRosterSync(bytes: Uint8Array, view: DataView): RosterSyncFrame {
  const count = view.getUint16(1, true)
  const members: RosterMember[] = []
  let at = 3
  for (let index = 0; index < count; index += 1) {
    const entry = readRosterEntry(bytes, view, at)
    members.push(entry.member)
    at = entry.next
  }
  return { kind: 'roster-sync', members }
}
