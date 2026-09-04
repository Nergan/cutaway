/**
 * The wire codec, checked against frames the Python server actually produced.
 *
 * Every `encoded` string in the fixture came out of `age/infrastructure/wire.py`. Decoding
 * them here proves this mirror reads what the server writes; re-encoding the client frames
 * and comparing bytes proves the server can read what this writes. Both directions matter,
 * because a field width mistake in the delta encoding shifts everything after it and
 * produces plausible garbage rather than an error.
 */

import { describe, expect, it } from 'vitest'

import fixtures from '../__fixtures__/parity.json'
import { PERCENT_SCALE, POSITION_SCALE, PROTOCOL_VERSION } from '../domain/constants'
import {
  BUILD_PLACE,
  FIELD_APPEARANCE,
  FIELD_FACING,
  FIELD_HEALTH,
  FIELD_POSITION,
  FIELD_RESOURCE,
  FIELD_STATE,
  FIELD_VELOCITY,
  INPUT_RIGHT,
  INPUT_RUN,
  INPUT_UP,
  ProtocolError,
  Writer,
  decodeAngle,
  decodePosition,
  decodeServerPacket,
  encodeAction,
  encodeAngle,
  encodeBuild,
  encodeChat,
  encodeHello,
  encodeInput,
  encodeInventory,
  encodePing,
  encodePosition,
  encodeReady,
} from './wire'

/** The fixtures store frames as base64; Node has no atob worth relying on. */
function bytes(encoded: string): Uint8Array {
  return new Uint8Array(Buffer.from(encoded, 'base64'))
}

function hex(payload: Uint8Array): string {
  return Array.from(payload)
    .map((byte) => byte.toString(16).padStart(2, '0'))
    .join(' ')
}

// --- what the client sends --------------------------------------------------

describe('client frames the server has already accepted', () => {
  const packets = fixtures.clientPackets

  it('encodes a hello byte-for-byte', () => {
    const appearance = packets.hello.appearance
    const actual = encodeHello(packets.hello.characterName, packets.hello.classId, {
      body: appearance[0],
      hair: appearance[1],
      palette: appearance[2],
      outfit: appearance[3],
      accent: appearance[4],
    })
    expect(hex(actual)).toBe(hex(bytes(packets.hello.encoded)))
  })

  it('encodes a ready as a single byte', () => {
    const actual = encodeReady()
    expect(hex(actual)).toBe(hex(bytes(packets.ready.encoded)))
    expect(actual.byteLength).toBe(1)
  })

  it('encodes an input frame byte-for-byte', () => {
    // The one sent thirty times a second, so it is the frame most worth pinning.
    const actual = encodeInput({
      sequence: packets.input.sequence,
      topologyVersion: packets.input.topologyVersion,
      buttons: INPUT_UP | INPUT_RIGHT | INPUT_RUN,
      facing: 1.25,
      predictedX: packets.input.predictedX,
      predictedY: packets.input.predictedY,
      deltaTime: 0.0333,
    })
    expect(hex(actual)).toBe(hex(bytes(packets.input.encoded)))
  })

  it('agrees with the server on which bits the movement keys are', () => {
    expect(INPUT_UP | INPUT_RIGHT | INPUT_RUN).toBe(packets.input.buttons)
  })

  it('encodes an action byte-for-byte', () => {
    const actual = encodeAction(
      packets.action.sequence,
      fixtures.clientPackets.input.topologyVersion,
      packets.action.abilityId,
      packets.action.targetX,
      packets.action.targetY,
      packets.action.targetEntity,
    )
    expect(hex(actual)).toBe(hex(bytes(packets.action.encoded)))
  })

  it('encodes non-ASCII chat byte-for-byte', () => {
    // Cyrillic is two bytes per character in UTF-8, so a length prefix counting
    // characters instead of bytes would pass an ASCII test and fail here.
    const actual = encodeChat(packets.chat.channel, packets.chat.text)
    expect(hex(actual)).toBe(hex(bytes(packets.chat.encoded)))
  })

  it('encodes a build request with a negative tile coordinate', () => {
    // Hub-local coordinates are signed; an unsigned field would wrap silently.
    expect(packets.build.tileX).toBeLessThan(0)
    const actual = encodeBuild(
      fixtures.clientPackets.input.topologyVersion,
      BUILD_PLACE,
      packets.build.tileX,
      packets.build.tileY,
      packets.build.material,
    )
    expect(hex(actual)).toBe(hex(bytes(packets.build.encoded)))
  })

  it('encodes a ping byte-for-byte', () => {
    expect(hex(encodePing(packets.ping.clientTime))).toBe(hex(bytes(packets.ping.encoded)))
  })

  it('encodes an inventory command byte-for-byte', () => {
    const actual = encodeInventory(
      packets.inventory.action,
      packets.inventory.slot,
      packets.inventory.count,
    )
    expect(hex(actual)).toBe(hex(bytes(packets.inventory.encoded)))
  })
})

// --- what the server sends -------------------------------------------------

describe('server frames', () => {
  const packets = fixtures.serverPackets

  it('decodes a welcome, keeping the full 64-bit world seed', () => {
    const packet = decodeServerPacket(bytes(packets.welcome.encoded))
    expect(packet.kind).toBe('welcome')
    if (packet.kind !== 'welcome') return

    expect(packet.protocolVersion).toBe(PROTOCOL_VERSION)
    expect(packet.entityId).toBe(packets.welcome.entityId)
    // A Number here would lose the low bits of a large seed and generate a different
    // world from the server's, silently.
    expect(packet.worldSeed).toBe(BigInt(packets.welcome.worldSeed))
    expect(packet.currentTier).toBe(packets.welcome.currentTier)
    expect(packet.edgeId).toBe(packets.welcome.edgeId)
    expect(packet.spawnX).toBeCloseTo(packets.welcome.spawnX, 6)
    expect(packet.spawnY).toBeCloseTo(packets.welcome.spawnY, 6)
    expect(packet.serverTime).toBe(packets.welcome.serverTime)
  })

  it('decodes a delta snapshot, reading only the flagged fields', () => {
    const packet = decodeServerPacket(bytes(packets.snapshot.encoded))
    expect(packet.kind).toBe('snapshot')
    if (packet.kind !== 'snapshot') return

    expect(packet.tick).toBe(packets.snapshot.tick)
    expect(packet.acknowledgedInput).toBe(packets.snapshot.acknowledgedInput)
    expect(packet.topologyVersion).toBe(packets.snapshot.topologyVersion)
    expect(packet.dayPhase).toBeCloseTo(packets.snapshot.dayPhase, 4)
    expect(packet.weather).toBe(packets.snapshot.weather)
    expect(packet.deltas).toHaveLength(packets.snapshot.entities.length)

    const expected = packets.snapshot.entities
    packet.deltas.forEach((delta, index) => {
      // The fixture only carries the fields each delta actually flagged, so the honest type
      // admits `undefined` per key. Without it TypeScript refuses the cast, which is fair:
      // half these properties are genuinely absent.
      const want = expected[index] as Record<string, number | number[] | undefined>
      expect(delta.entityId).toBe(want.entityId)
      expect(delta.fields).toBe(want.fields)

      if (delta.fields & FIELD_POSITION) {
        expect(delta.x).toBeCloseTo(want.x as number, 6)
        expect(delta.y).toBeCloseTo(want.y as number, 6)
      } else {
        // Absence matters as much as presence: a decoder that reads unflagged fields
        // would consume the next entity's bytes.
        expect(delta.x).toBeUndefined()
      }

      if (delta.fields & FIELD_VELOCITY) {
        expect(delta.vx).toBeCloseTo(want.vx as number, 6)
        expect(delta.vy).toBeCloseTo(want.vy as number, 6)
      } else {
        expect(delta.vx).toBeUndefined()
      }

      if (delta.fields & FIELD_FACING) {
        expect(delta.facing).toBeCloseTo(want.facing as number, 4)
      }
      if (delta.fields & FIELD_HEALTH) {
        // Server sends a byte; the client works in a 0..1 ratio.
        expect(delta.health).toBeCloseTo((want.healthPercent as number) / PERCENT_SCALE, 6)
      }
      if (delta.fields & FIELD_RESOURCE) {
        expect(delta.resource).toBeCloseTo((want.resourcePercent as number) / PERCENT_SCALE, 6)
      }
      if (delta.fields & FIELD_STATE) {
        expect(delta.state).toBe(want.state)
      }
      if (delta.fields & FIELD_APPEARANCE) {
        const appearance = want.appearance as number[]
        expect(delta.appearance).toEqual({
          body: appearance[0],
          hair: appearance[1],
          palette: appearance[2],
          outfit: appearance[3],
          accent: appearance[4],
        })
      }
    })
  })

  it('consumes the snapshot exactly, leaving no trailing bytes', () => {
    // The strongest single check on the delta encoding: if any field were read at the
    // wrong width the cursor would end up somewhere else, even when the values happen
    // to look plausible.
    const payload = bytes(packets.snapshot.encoded)
    const packet = decodeServerPacket(payload)
    expect(packet.kind).toBe('snapshot')

    const truncated = payload.subarray(0, payload.byteLength - 1)
    expect(() => decodeServerPacket(truncated)).toThrow(ProtocolError)
  })

  it('decodes a spawn', () => {
    const packet = decodeServerPacket(bytes(packets.spawn.encoded))
    expect(packet.kind).toBe('spawn')
    if (packet.kind !== 'spawn') return

    expect(packet.entityId).toBe(packets.spawn.entityId)
    expect(packet.entityKind).toBe(packets.spawn.kind)
    expect(packet.archetype).toBe(packets.spawn.archetype)
    expect(packet.name).toBe(packets.spawn.name)
    expect(packet.x).toBeCloseTo(packets.spawn.x, 6)
    expect(packet.y).toBeCloseTo(packets.spawn.y, 6)
    expect(packet.level).toBe(packets.spawn.level)
    expect(packet.health).toBeCloseTo(packets.spawn.healthPercent / PERCENT_SCALE, 6)
    // The state byte and the appearance are the tail of the packet, and the tail is where
    // a missing field hides: everything before it still decodes, so the packet looks fine.
    expect(packet.state).toBe(packets.spawn.state)
    // Compared in the packing order rather than by name, so a pair of components swapped
    // on one side of the wire fails here instead of quietly redressing every character.
    const { body, hair, palette, outfit, accent } = packet.appearance
    expect([body, hair, palette, outfit, accent]).toEqual(packets.spawn.appearance)
  })

  it('consumes the spawn exactly, leaving no trailing bytes', () => {
    // The check the spawn packet did not have, and the reason a whole field went missing
    // from it unnoticed. A spawn is the only packet that establishes an entity's baseline,
    // so a field dropped here is one the client substitutes a default for, forever. The
    // state byte was dropped, the default was zero, and zero means dead: every character
    // in the game was drawn as a corpse in a one-frame pose and nothing ever animated.
    const payload = bytes(packets.spawn.encoded)
    expect(decodeServerPacket(payload).kind).toBe('spawn')
    expect(() => decodeServerPacket(payload.subarray(0, payload.byteLength - 1))).toThrow(
      ProtocolError,
    )
  })

  it('decodes a despawn', () => {
    const packet = decodeServerPacket(bytes(packets.despawn.encoded))
    expect(packet.kind).toBe('despawn')
    if (packet.kind !== 'despawn') return
    expect(packet.entityId).toBe(packets.despawn.entityId)
  })

  it('decodes a topology change as chunk keys rather than tiles', () => {
    // The bandwidth argument for client-side generation, visible in one packet: a lane
    // activation costs a few dozen bytes because the client can generate what it names.
    const payload = bytes(packets.topology.encoded)
    const packet = decodeServerPacket(payload)
    expect(packet.kind).toBe('topology')
    if (packet.kind !== 'topology') return

    expect(packet.topologyVersion).toBe(packets.topology.topologyVersion)
    expect(packet.currentTier).toBe(packets.topology.currentTier)
    expect(packet.activeChunks).toEqual(packets.topology.activeChunks)
    expect(packet.retiringChunks).toEqual(packets.topology.retiringChunks)
    expect(payload.byteLength).toBeLessThan(80)
  })

  it('decodes a combat event', () => {
    const packet = decodeServerPacket(bytes(packets.combat.encoded))
    expect(packet.kind).toBe('combat')
    if (packet.kind !== 'combat') return
    expect(packet.attackerId).toBe(packets.combat.attackerId)
    expect(packet.targetId).toBe(packets.combat.targetId)
    expect(packet.damage).toBe(packets.combat.damage)
    expect(packet.killed).toBe(packets.combat.killed)
  })

  it('decodes chat', () => {
    const packet = decodeServerPacket(bytes(packets.chat.encoded))
    expect(packet.kind).toBe('chat')
    if (packet.kind !== 'chat') return
    expect(packet.senderName).toBe(packets.chat.senderName)
    expect(packet.text).toBe(packets.chat.text)
  })

  it('decodes a tile overlay delta', () => {
    const packet = decodeServerPacket(bytes(packets.tiles.encoded))
    expect(packet.kind).toBe('tiles')
    if (packet.kind !== 'tiles') return
    expect(packet.chunkKey).toBe(packets.tiles.chunkKey)
    expect(packet.changes).toEqual(packets.tiles.changes)
  })

  it('decodes a pong with both timestamps intact', () => {
    const packet = decodeServerPacket(bytes(packets.pong.encoded))
    expect(packet.kind).toBe('pong')
    if (packet.kind !== 'pong') return
    // Round-trip timing is the only thing on the wire that is a raw double, because
    // quantising it would quantise the clock offset.
    expect(packet.clientTime).toBe(packets.pong.clientTime)
    expect(packet.serverTime).toBe(packets.pong.serverTime)
  })

  it('decodes an error, including the version mismatch the client must act on', () => {
    const packet = decodeServerPacket(bytes(packets.error.encoded))
    expect(packet.kind).toBe('error')
    if (packet.kind !== 'error') return
    expect(packet.code).toBe(packets.error.code)
    expect(packet.detail).toBe(packets.error.detail)
  })

  it('decodes an inventory snapshot with its stacks, loadout and derived stats', () => {
    const payload = bytes(packets.inventory.encoded)
    const packet = decodeServerPacket(payload)
    expect(packet.kind).toBe('inventory')
    if (packet.kind !== 'inventory') return

    expect(packet.capacity).toBe(packets.inventory.capacity)
    expect(packet.stacks.map((stack) => [stack.itemId, stack.count])).toEqual(
      packets.inventory.stacks,
    )
    expect(packet.equipped.map((worn) => [worn.slot, worn.itemId])).toEqual(
      packets.inventory.equipped,
    )
    expect(packet.maxHealth).toBe(packets.inventory.maxHealth)
    expect(packet.maxResource).toBe(packets.inventory.maxResource)
    expect(packet.bonusDamage).toBe(packets.inventory.bonusDamage)
    expect(packet.moveSpeed).toBeCloseTo(packets.inventory.moveSpeed, 6)
  })

  it('consumes the inventory snapshot exactly, leaving no trailing bytes', () => {
    // Two variable-length runs back to back, so a count read at the wrong width would
    // shift the derived stats into values that still look like plausible numbers.
    const payload = bytes(packets.inventory.encoded)
    expect(() => decodeServerPacket(payload.subarray(0, payload.byteLength - 1))).toThrow(
      ProtocolError,
    )
  })
})

// --- quantisation ----------------------------------------------------------

describe('quantisation', () => {
  it('round-trips positions that land on a quantum exactly', () => {
    for (const value of [12.5, -30.25, 8.5, -4.25, 64, -100.75, 200.5]) {
      expect(decodePosition(encodePosition(value))).toBeCloseTo(value, 10)
    }
  })

  it('never loses more than half a step', () => {
    const halfStep = 0.5 / POSITION_SCALE
    for (const value of [0.001, 1 / 3, -1 / 7, 123.456, -987.654]) {
      expect(Math.abs(decodePosition(encodePosition(value)) - value)).toBeLessThanOrEqual(halfStep)
    }
  })

  it('rounds halves upward, the way the server does', () => {
    // Math.round breaks ties upward; Python's round() breaks them to even. The server
    // has its own round_half_up for this. If they disagreed, a position on an exact half
    // step would differ by one unit forever and reconciliation would never settle.
    expect(encodePosition(0.5 / POSITION_SCALE)).toBe(1)
    expect(encodePosition(1.5 / POSITION_SCALE)).toBe(2)
    expect(encodePosition(2.5 / POSITION_SCALE)).toBe(3)
  })

  it('wraps angles rather than clipping them', () => {
    expect(encodeAngle(0)).toBe(encodeAngle(2 * Math.PI))
    for (const radians of [0, 1.25, 3, -2, Math.PI]) {
      const recovered = decodeAngle(encodeAngle(radians))
      // Compared as a direction, not a number: -2 comes back as +4.28.
      expect(Math.cos(recovered)).toBeCloseTo(Math.cos(radians), 4)
      expect(Math.sin(recovered)).toBeCloseTo(Math.sin(radians), 4)
    }
  })
})

// --- malformed input -------------------------------------------------------

describe('rejecting malformed frames', () => {
  it('refuses an empty packet', () => {
    expect(() => decodeServerPacket(new Uint8Array(0))).toThrow(ProtocolError)
  })

  it('refuses an unknown message type instead of guessing', () => {
    expect(() => decodeServerPacket(new Uint8Array([0xff]))).toThrow(ProtocolError)
  })

  it('refuses a string whose length prefix exceeds the field limit', () => {
    // Otherwise a hostile or corrupt frame could make the client allocate on demand.
    const payload = new Writer(0x87).u32(1).u8(0).u16(0xffff).build()
    expect(() => decodeServerPacket(payload)).toThrow(ProtocolError)
  })

  it('refuses a snapshot claiming more entities than it carries', () => {
    const payload = new Writer(0x82)
      .u32(1)
      .f64(0)
      .u32(0)
      .u32(0)
      .u16(0)
      .u8(0)
      .u16(50) // fifty entities promised, none supplied
      .build()
    expect(() => decodeServerPacket(payload)).toThrow(ProtocolError)
  })

  it('truncates an over-long string on a character boundary', () => {
    // Cutting mid-character would send the server invalid UTF-8, and the limits are in
    // bytes while the input is in characters.
    const payload = new Writer(0x05).u8(0).text('\u041f\u0440\u0438\u0432\u0435\u0442', 5).build()
    const length = new DataView(payload.buffer, payload.byteOffset).getUint16(2, true)
    expect(length % 2).toBe(0)
    expect(length).toBeLessThanOrEqual(5)
  })
})
