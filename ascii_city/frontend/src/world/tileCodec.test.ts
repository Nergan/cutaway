import { describe, expect, it } from 'vitest'

import fixtures from '../__fixtures__/protocol.json'
import { TileFormatError, decodeTile } from './tileCodec'

const PAYLOAD = Uint8Array.from(Buffer.from(fixtures.tile.encoded, 'base64'))
const EXPECTED = fixtures.tile.expected

describe('tile decoding', () => {
  it('reads the header the Python encoder wrote', () => {
    const tile = decodeTile(PAYLOAD)
    expect(tile.id).toBe(EXPECTED.id)
    expect(tile.version).toBe(EXPECTED.version)
    expect(tile.tileX).toBe(EXPECTED.tileX)
    expect(tile.tileY).toBe(EXPECTED.tileY)
    expect(tile.cells).toBe(EXPECTED.cells)
    expect(tile.cellSize).toBeCloseTo(EXPECTED.cellSize, 5)
  })

  it('reads all three cell layers at full length', () => {
    const tile = decodeTile(PAYLOAD)
    const area = EXPECTED.cells * EXPECTED.cells
    expect(tile.collision).toHaveLength(area)
    expect(tile.heights).toHaveLength(area)
    expect(tile.styles).toHaveLength(area)
    expect([...tile.collision.slice(0, 8)]).toEqual(EXPECTED.collisionHead)
    expect([...tile.heights.slice(0, 8)]).toEqual(EXPECTED.heightsHead)
    expect([...tile.styles.slice(0, 8)]).toEqual(EXPECTED.stylesHead)
  })

  it('reads buildings with their footprint and packed flags', () => {
    const tile = decodeTile(PAYLOAD)
    expect(tile.buildings).toHaveLength(EXPECTED.buildingCount)

    const first = tile.buildings[0]
    expect(first.id).toBe(EXPECTED.firstBuilding.id)
    expect(first.height).toBe(EXPECTED.firstBuilding.height)
    expect(first.levels).toBe(EXPECTED.firstBuilding.levels)
    expect(first.roofType).toBe(EXPECTED.firstBuilding.roofType)
    expect(first.category).toBe(EXPECTED.firstBuilding.category)
    expect(first.facadeStyle).toBe(EXPECTED.firstBuilding.facadeStyle)
    expect(first.windowStyle).toBe(EXPECTED.firstBuilding.windowStyle)
    expect(first.color).toBe(EXPECTED.firstBuilding.color)
    expect(first.walkable).toBe(EXPECTED.firstBuilding.walkable)
    expect(first.hasInterior).toBe(EXPECTED.firstBuilding.hasInterior)
    expect([...first.footprint]).toEqual(EXPECTED.firstBuilding.footprint)

    const second = tile.buildings[1]
    expect(second.walkable).toBe(EXPECTED.secondBuilding.walkable)
    expect(second.hasInterior).toBe(EXPECTED.secondBuilding.hasInterior)
  })

  it('reads roads, including the optional name', () => {
    const tile = decodeTile(PAYLOAD)
    expect(tile.roads).toHaveLength(EXPECTED.roadCount)
    expect(tile.roads[0].name).toBe(EXPECTED.firstRoad.name)
    expect(tile.roads[0].width).toBeCloseTo(EXPECTED.firstRoad.width, 5)
    expect(tile.roads[0].type).toBe(EXPECTED.firstRoad.type)
    expect(tile.roads[1].name).toBe(EXPECTED.secondRoadName)
  })

  it('reads props and spawn points, decoding headings back to radians', () => {
    const tile = decodeTile(PAYLOAD)
    expect(tile.props).toHaveLength(EXPECTED.propCount)
    expect(tile.props[0]).toEqual({ id: 1, x: 2, y: 6, kind: 3 })
    expect(tile.spawnPoints).toHaveLength(EXPECTED.spawnCount)
    expect(tile.spawnPoints[0].heading).toBeCloseTo(0, 5)
    expect(tile.spawnPoints[1].heading).toBeCloseTo(Math.PI, 4)
  })
})

describe('malformed tiles', () => {
  it('rejects a payload that is not a tile', () => {
    expect(() => decodeTile(Uint8Array.from([1, 2, 3, 4, 5, 6, 7, 8]))).toThrow(TileFormatError)
  })

  it('rejects a future format version', () => {
    const future = PAYLOAD.slice()
    future[4] = 99
    expect(() => decodeTile(future)).toThrow(/Unsupported tile format version 99/)
  })

  it('rejects a truncated payload instead of reading past the end', () => {
    expect(() => decodeTile(PAYLOAD.slice(0, PAYLOAD.byteLength - 40))).toThrow(TileFormatError)
  })

  it('reads a tile that sits at a non-zero offset in a larger buffer', () => {
    const padded = new Uint8Array(PAYLOAD.byteLength + 7)
    padded.set(PAYLOAD, 7)
    expect(decodeTile(padded.subarray(7)).id).toBe(EXPECTED.id)
  })
})
