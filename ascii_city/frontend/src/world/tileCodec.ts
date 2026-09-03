/**
 * Decoder for the binary tile container produced by
 * `ascii_city/infrastructure/tile_codec.py`. `docs/world-format.md` is the
 * normative byte layout; this file must not diverge from it.
 *
 * Decoding runs inside a Web Worker, so it returns plain typed arrays that
 * transfer to the main thread without a copy.
 */

import type { Building, Prop, Road, SpawnPoint, WorldTile } from '../domain/types'
import { TAU } from '../domain/constants'

export const MAGIC = 0x31544341 // "ACT1" read as a little-endian u32
export const FORMAT_VERSION = 1

const ANGLE_UNITS = 65536

export class TileFormatError extends Error {}

class Reader {
  private offset = 0
  private readonly view: DataView
  private readonly text = new TextDecoder()

  constructor(private readonly bytes: Uint8Array) {
    this.view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength)
  }

  private require(size: number): number {
    const at = this.offset
    if (at + size > this.bytes.byteLength) {
      throw new TileFormatError('Tile payload is truncated.')
    }
    this.offset = at + size
    return at
  }

  u8(): number {
    return this.view.getUint8(this.require(1))
  }

  u16(): number {
    return this.view.getUint16(this.require(2), true)
  }

  i16(): number {
    return this.view.getInt16(this.require(2), true)
  }

  i32(): number {
    return this.view.getInt32(this.require(4), true)
  }

  u32(): number {
    return this.view.getUint32(this.require(4), true)
  }

  f32(): number {
    return this.view.getFloat32(this.require(4), true)
  }

  /** A copy, because the caller keeps it after the source buffer is released. */
  layer(size: number): Uint8Array {
    const at = this.require(size)
    return this.bytes.slice(at, at + size)
  }

  string(length: number): string {
    const at = this.require(length)
    return this.text.decode(this.bytes.subarray(at, at + length))
  }

  i16Array(count: number): Int16Array {
    const values = new Int16Array(count)
    for (let index = 0; index < count; index += 1) values[index] = this.i16()
    return values
  }
}

export function decodeTile(payload: ArrayBuffer | Uint8Array): WorldTile {
  const bytes = payload instanceof Uint8Array ? payload : new Uint8Array(payload)
  const reader = new Reader(bytes)

  if (reader.u32() !== MAGIC) throw new TileFormatError('Not an ASCII City tile payload.')
  const version = reader.u16()
  if (version !== FORMAT_VERSION) {
    throw new TileFormatError(`Unsupported tile format version ${version}.`)
  }
  reader.u16() // flags, reserved
  const tileX = reader.i32()
  const tileY = reader.i32()
  const cells = reader.u16()
  const cellSize = reader.f32()
  const worldVersion = reader.u32()
  const id = reader.string(reader.u16())

  const area = cells * cells
  const collision = reader.layer(area)
  const heights = reader.layer(area)
  const styles = reader.layer(area)

  const buildings: Building[] = []
  for (let index = reader.u16(); index > 0; index -= 1) {
    const buildingId = reader.u16()
    const vertexCount = reader.u8()
    const footprint = reader.i16Array(vertexCount * 2)
    const height = reader.u8()
    const minHeight = reader.u8()
    const levels = reader.u8()
    const roofType = reader.u8()
    const category = reader.u8()
    const facadeStyle = reader.u8()
    const windowStyle = reader.u8()
    const color = reader.u8()
    const flags = reader.u8()
    buildings.push({
      id: buildingId,
      footprint,
      height,
      minHeight,
      levels,
      roofType,
      category,
      facadeStyle,
      windowStyle,
      color,
      walkable: (flags & 1) !== 0,
      hasInterior: (flags & 2) !== 0,
    })
  }

  const roads: Road[] = []
  for (let index = reader.u16(); index > 0; index -= 1) {
    const roadId = reader.u16()
    const type = reader.u8()
    const width = reader.u8() / 10
    const surfaceStyle = reader.u8()
    const centerline = reader.i16Array(reader.u8() * 2)
    const nameLength = reader.u8()
    const name = nameLength > 0 ? reader.string(nameLength) : null
    roads.push({ id: roadId, centerline, width, type, surfaceStyle, name })
  }

  const props: Prop[] = []
  for (let index = reader.u16(); index > 0; index -= 1) {
    props.push({ id: reader.u16(), x: reader.u16(), y: reader.u16(), kind: reader.u8() })
  }

  const spawnPoints: SpawnPoint[] = []
  for (let index = reader.u16(); index > 0; index -= 1) {
    spawnPoints.push({
      x: reader.u16(),
      y: reader.u16(),
      heading: (reader.u16() / ANGLE_UNITS) * TAU,
    })
  }

  return {
    id,
    version: worldVersion,
    tileX,
    tileY,
    cells,
    cellSize,
    collision,
    heights,
    styles,
    buildings,
    roads,
    props,
    spawnPoints,
  }
}
