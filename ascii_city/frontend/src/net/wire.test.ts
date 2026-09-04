/**
 * Cross-language protocol tests.
 *
 * Every payload here was produced by the Python reference implementation via
 * `ascii_city/tools/make_fixtures.py`. If the two codecs ever disagree by a
 * single byte, this suite says so before a player ever sees a desync.
 */

import { describe, expect, it } from 'vitest'

import fixtures from '../__fixtures__/protocol.json'
import {
  MAX_FRAME_BYTES,
  MSG_CHAT,
  MSG_INPUT,
  MSG_PING,
  MSG_RENAME,
  MSG_SET_AVATAR,
  WireError,
  decodePitch,
  decodePosition,
  decodeServerFrame,
  decodeYaw,
  encodeChat,
  encodeInput,
  encodePing,
  encodePitch,
  encodePosition,
  encodeRename,
  encodeSetAvatar,
  encodeYaw,
} from './wire'

function bytes(base64: string): Uint8Array {
  return Uint8Array.from(Buffer.from(base64, 'base64'))
}

describe('scalar encodings', () => {
  it('matches the server for every sampled position', () => {
    for (const sample of fixtures.scalars.positions) {
      expect(encodePosition(sample.metres), `${sample.metres} m`).toBe(sample.encoded)
    }
  })

  it('matches the server for every sampled yaw', () => {
    for (const sample of fixtures.scalars.yaw) {
      expect(encodeYaw(sample.radians), `${sample.radians} rad`).toBe(sample.encoded)
    }
  })

  it('matches the server for every sampled pitch', () => {
    for (const sample of fixtures.scalars.pitch) {
      expect(encodePitch(sample.radians), `${sample.radians} rad`).toBe(sample.encoded)
    }
  })

  it('round-trips a position to within a centimetre', () => {
    for (const metres of [0, 1.234, 99.995, 640]) {
      expect(Math.abs(decodePosition(encodePosition(metres)) - metres)).toBeLessThanOrEqual(0.005)
    }
  })

  it('round-trips a yaw to within a thousandth of a radian', () => {
    for (const radians of [0, 0.5, Math.PI, 5.9]) {
      expect(Math.abs(decodeYaw(encodeYaw(radians)) - radians)).toBeLessThan(0.001)
    }
  })

  it('clamps a pitch beyond the legal cone', () => {
    expect(decodePitch(encodePitch(4))).toBeCloseTo(1.27, 5)
    expect(decodePitch(encodePitch(-4))).toBeCloseTo(-1.27, 5)
  })
})

describe('frames this client sends', () => {
  it('encodes input exactly as the server decoder expects', () => {
    const fixture = fixtures.clientFrames.input
    const encoded = encodeInput({
      sequence: fixture.command.sequence,
      forward: fixture.command.forward,
      strafe: fixture.command.strafe,
      yaw: fixture.command.yaw,
      pitch: fixture.command.pitch,
      sprint: fixture.command.sprint,
      jump: fixture.command.jump,
      clientTime: fixture.command.clientTime,
    })
    expect(encoded[0]).toBe(MSG_INPUT)
    expect(encoded).toEqual(bytes(fixture.encoded))
  })

  it('encodes chat exactly as the server decoder expects', () => {
    const fixture = fixtures.clientFrames.chat
    const encoded = encodeChat('proximity', fixture.text)
    expect(encoded[0]).toBe(MSG_CHAT)
    expect(encoded).toEqual(bytes(fixture.encoded))
  })

  it('encodes ping exactly as the server decoder expects', () => {
    const fixture = fixtures.clientFrames.ping
    const encoded = encodePing(fixture.clientTime)
    expect(encoded[0]).toBe(MSG_PING)
    expect(encoded).toEqual(bytes(fixture.encoded))
  })

  it('encodes a rename exactly as the server decoder expects', () => {
    const fixture = fixtures.clientFrames.rename
    const encoded = encodeRename(fixture.nickname)
    expect(encoded[0]).toBe(MSG_RENAME)
    expect(encoded).toEqual(bytes(fixture.encoded))
  })

  it('encodes an avatar change exactly as the server decoder expects', () => {
    const fixture = fixtures.clientFrames.setAvatar
    const encoded = encodeSetAvatar(fixture.avatar)
    expect(encoded[0]).toBe(MSG_SET_AVATAR)
    expect(encoded).toEqual(bytes(fixture.encoded))
  })

  it('keeps an input frame at fifteen bytes whatever the values', () => {
    const frame = encodeInput({
      sequence: 0xffffffff,
      forward: 5,
      strafe: -5,
      yaw: 99,
      pitch: -99,
      sprint: false,
      jump: false,
      clientTime: 0xffffffff,
    })
    expect(frame.byteLength).toBe(15)
  })

  it('normalises a non-finite axis to zero rather than sending garbage', () => {
    const frame = encodeInput({
      sequence: 1,
      forward: Number.NaN,
      strafe: Number.POSITIVE_INFINITY,
      yaw: 0,
      pitch: 0,
      sprint: false,
      jump: false,
      clientTime: 0,
    })
    expect(new DataView(frame.buffer).getInt8(5)).toBe(0)
    expect(new DataView(frame.buffer).getInt8(6)).toBe(0)
  })

  it('refuses a chat message too large for one frame', () => {
    expect(() => encodeChat('global', 'x'.repeat(MAX_FRAME_BYTES))).toThrow(WireError)
  })
})

describe('frames the server sends', () => {
  it('decodes a welcome', () => {
    const fixture = fixtures.serverFrames.welcome
    const frame = decodeServerFrame(bytes(fixture.encoded))
    expect(frame.kind).toBe('welcome')
    if (frame.kind !== 'welcome') return
    expect(frame.playerId).toBe(fixture.expected.playerId)
    expect(frame.nickname).toBe(fixture.expected.nickname)
    expect(frame.color).toBe(fixture.expected.color)
    expect(frame.avatar).toBe(fixture.expected.avatar)
    expect(frame.simulationHz).toBe(fixture.expected.simulationHz)
    expect(frame.serverTimeMs).toBe(fixture.expected.serverTimeMs)
    expect(frame.tilesX).toBe(fixture.expected.tilesX)
    expect(frame.tileCells).toBe(fixture.expected.tileCells)
    expect(frame.cellSize).toBeCloseTo(fixture.expected.cellSize, 5)
    expect(frame.worldVersion).toBe(fixture.expected.worldVersion)
    expect(frame.worldId).toBe(fixture.expected.worldId)
    expect(frame.x).toBeCloseTo(112.5, 2)
    expect(frame.y).toBeCloseTo(64.25, 2)
  })

  it('decodes a snapshot including the simplified flag', () => {
    const fixture = fixtures.serverFrames.snapshot
    const frame = decodeServerFrame(bytes(fixture.encoded))
    expect(frame.kind).toBe('snapshot')
    if (frame.kind !== 'snapshot') return
    expect(frame.tick).toBe(fixture.expected.tick)
    expect(frame.ackSequence).toBe(fixture.expected.ackSequence)
    expect(frame.entries).toHaveLength(fixture.expected.entryCount)
    fixture.expected.entries.forEach((expected, index) => {
      expect(frame.entries[index].id).toBe(expected.id)
      expect(frame.entries[index].simplified).toBe(expected.simplified)
      expect(frame.entries[index].animation).toBe(expected.animation)
    })
    expect(frame.entries[0].x).toBeCloseTo(98.0, 2)
    expect(frame.entries[0].pitch).toBeCloseTo(0.9, 2)
  })

  it('decodes chat without mangling the preserved angle brackets', () => {
    const fixture = fixtures.serverFrames.chat
    const frame = decodeServerFrame(bytes(fixture.encoded))
    expect(frame.kind).toBe('chat')
    if (frame.kind !== 'chat') return
    expect(frame.message.text).toBe(fixture.expected.text)
    expect(frame.message.text).toContain('<grin>')
    expect(frame.message.nickname).toBe(fixture.expected.nickname)
    expect(frame.message.scope).toBe('proximity')
    expect(frame.message.senderId).toBe(fixture.expected.senderId)
    expect(frame.message.createdAt).toBeCloseTo(fixture.expected.createdAt, 6)
  })

  it('decodes a notice', () => {
    const frame = decodeServerFrame(bytes(fixtures.serverFrames.notice.encoded))
    expect(frame).toEqual({
      kind: 'notice',
      code: fixtures.serverFrames.notice.expected.code,
      text: fixtures.serverFrames.notice.expected.text,
    })
  })

  it('decodes the roster frames, avatars included', () => {
    const sync = decodeServerFrame(bytes(fixtures.serverFrames.rosterSync.encoded))
    expect(sync.kind).toBe('roster-sync')
    if (sync.kind === 'roster-sync') {
      expect(sync.members).toEqual(fixtures.serverFrames.rosterSync.expected.members)
    }

    const added = decodeServerFrame(bytes(fixtures.serverFrames.rosterAdd.encoded))
    expect(added.kind).toBe('roster-add')
    if (added.kind === 'roster-add') {
      expect(added.member).toEqual(fixtures.serverFrames.rosterAdd.expected)
    }

    const updated = decodeServerFrame(bytes(fixtures.serverFrames.rosterUpdate.encoded))
    expect(updated.kind).toBe('roster-update')
    if (updated.kind === 'roster-update') {
      expect(updated.member).toEqual(fixtures.serverFrames.rosterUpdate.expected)
    }

    const removed = decodeServerFrame(bytes(fixtures.serverFrames.rosterRemove.encoded))
    expect(removed).toEqual({ kind: 'roster-remove', id: 4242 })
  })

  it('decodes a pong', () => {
    const frame = decodeServerFrame(bytes(fixtures.serverFrames.pong.encoded))
    expect(frame).toEqual({
      kind: 'pong',
      clientTime: fixtures.serverFrames.pong.expected.clientTime,
      serverTimeMs: fixtures.serverFrames.pong.expected.serverTimeMs,
    })
  })
})

describe('hostile input', () => {
  it('rejects an empty frame', () => {
    expect(() => decodeServerFrame(new Uint8Array(0))).toThrow(WireError)
  })

  it('rejects an unknown frame type', () => {
    expect(() => decodeServerFrame(Uint8Array.from([0xf0, 1, 2, 3]))).toThrow(WireError)
  })

  it('rejects a snapshot that promises more entries than it carries', () => {
    const honest = bytes(fixtures.serverFrames.snapshot.encoded)
    const lying = honest.slice()
    lying[15] = 200
    expect(() => decodeServerFrame(lying)).toThrow(WireError)
  })

  it('rejects a truncated notice', () => {
    const frame = Uint8Array.from([0x84, 0, 0xff, 0xff, 65])
    expect(() => decodeServerFrame(frame)).toThrow(WireError)
  })
})
