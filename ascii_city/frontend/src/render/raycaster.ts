/**
 * The ASCII raycaster.
 *
 * A DDA walk per screen column produces the skyline; the walk continues past
 * the first wall so towers behind the street still cut their silhouette into
 * the sky, which is what makes the city read as vertical. Everything lands in
 * a character grid, and the GPU pass afterwards only turns that grid into
 * pixels.
 */

import { CELL_ROAD, CELL_SIDEWALK, CELL_WATER, unpackStyle } from '../domain/constants'
import type { CollisionGrid } from '../world/collisionGrid'
import {
  RAMP,
  ROAD_GLYPHS,
  ROOF_GLYPHS,
  SHADES,
  SKY_GLYPHS,
  STRUCTURE,
  WINDOWS,
  WINDOW_DARK,
  G_SPACE,
} from './charset'
import { CellBuffer, EFFECT_GLOW, EFFECT_NONE } from './cellBuffer'
import { hash2, hash3 } from './hash'
import {
  FACADE,
  FOG,
  GROUND_ASPHALT,
  GROUND_MARKING,
  GROUND_SIDEWALK,
  GROUND_WET,
  NEON,
  SKY_GLOW,
  SKY_HIGH,
  SKY_LOW,
  STAR,
  VOID,
  fade,
  mix,
  scale,
  type Rgb,
} from './palette'

export interface Camera {
  x: number
  y: number
  z: number
  yaw: number
  pitch: number
}

export interface RaycastQuality {
  /** Horizontal field of view in radians. */
  fov: number
  /** How far a ray travels before it is given up on, in metres. */
  viewDistance: number
  /** Silhouette layers behind the nearest wall. One means no silhouettes. */
  layers: number
  /** Floor casting is the cheapest thing to drop on a weak device. */
  groundDetail: boolean
}

export const DEFAULT_QUALITY: RaycastQuality = {
  fov: (78 * Math.PI) / 180,
  viewDistance: 220,
  layers: 6,
  groundDetail: true,
}

/** Distance at which fog has swallowed most of the contrast. */
const FOG_DISTANCE_M = 90
const FLOOR_HEIGHT_M = 3
const WINDOW_PITCH_M = 1.6

interface Hit {
  distance: number
  height: number
  style: number
  side: number
  /** World coordinate along the wall face; keeps the facade from swimming. */
  along: number
  cellX: number
  cellY: number
}

const HITS: Hit[] = Array.from({ length: 16 }, () => ({
  distance: 0,
  height: 0,
  style: 0,
  side: 0,
  along: 0,
  cellX: 0,
  cellY: 0,
}))

export class Raycaster {
  /** Seconds since the world loaded; drives beacons and signage flicker. */
  time = 0

  constructor(public quality: RaycastQuality = { ...DEFAULT_QUALITY }) {}

  render(buffer: CellBuffer, grid: CollisionGrid, camera: Camera): void {
    const { columns, rows } = buffer
    const half = columns / 2
    const tanHalfFov = Math.tan(this.quality.fov / 2)
    const projColumns = half / tanHalfFov
    // Character cells are twice as tall as they are wide, so the vertical
    // projection has to be halved or the world looks stretched.
    const projRows = projColumns * 0.5
    const horizon = rows * 0.5 + Math.tan(camera.pitch) * projRows

    const dirX = Math.cos(camera.yaw)
    const dirY = Math.sin(camera.yaw)
    // Right-hand vector, matching the strafe convention in movement.ts.
    const planeX = dirY * tanHalfFov
    const planeY = -dirX * tanHalfFov

    buffer.depth.fill(Infinity)

    for (let column = 0; column < columns; column += 1) {
      const cameraX = (2 * column) / columns - 1
      const rayX = dirX + planeX * cameraX
      const rayY = dirY + planeY * cameraX

      const hitCount = this.cast(grid, camera, rayX, rayY)
      this.paintBackdrop(buffer, grid, camera, column, rayX, rayY, horizon, projRows)

      // Far to near, so nearer geometry overwrites the silhouettes behind it.
      for (let index = hitCount - 1; index >= 0; index -= 1) {
        this.paintWall(buffer, column, HITS[index], horizon, projRows, camera.z)
      }
      if (hitCount > 0) buffer.depth[column] = HITS[0].distance
    }
  }

  /** Walk the grid, recording up to `layers` solid cells along the ray. */
  private cast(grid: CollisionGrid, camera: Camera, rayX: number, rayY: number): number {
    const cellSize = grid.cellSize
    const posX = camera.x / cellSize
    const posY = camera.y / cellSize
    let mapX = Math.floor(posX)
    let mapY = Math.floor(posY)

    const deltaX = rayX === 0 ? Infinity : Math.abs(1 / rayX)
    const deltaY = rayY === 0 ? Infinity : Math.abs(1 / rayY)
    const stepX = rayX < 0 ? -1 : 1
    const stepY = rayY < 0 ? -1 : 1
    let sideX = rayX < 0 ? (posX - mapX) * deltaX : (mapX + 1 - posX) * deltaX
    let sideY = rayY < 0 ? (posY - mapY) * deltaY : (mapY + 1 - posY) * deltaY

    const maxCells = this.quality.viewDistance / cellSize
    const layers = this.quality.layers
    let found = 0
    let side = 0

    for (let steps = 0; steps < 2048; steps += 1) {
      if (sideX < sideY) {
        sideX += deltaX
        mapX += stepX
        side = 0
      } else {
        sideY += deltaY
        mapY += stepY
        side = 1
      }

      const travelled = side === 0 ? sideX - deltaX : sideY - deltaY
      if (travelled > maxCells) break
      if (mapX < -1 || mapY < -1 || mapX > grid.width || mapY > grid.height) break
      if (!grid.isSolidCell(mapX, mapY)) continue

      const distance = travelled * cellSize
      const hit = HITS[found]
      hit.distance = distance < 0.01 ? 0.01 : distance
      hit.height = Math.max(1, grid.heightAt(mapX, mapY))
      hit.style = grid.styleAt(mapX, mapY)
      hit.side = side
      hit.cellX = mapX
      hit.cellY = mapY
      hit.along =
        side === 0 ? camera.y + rayY * hit.distance : camera.x + rayX * hit.distance
      found += 1

      // Once a wall reaches over the camera by a wide margin nothing behind it
      // can appear, and there is no point spending steps on it.
      if (found >= layers) break
      if (hit.height > 200 && hit.distance < 6) break
    }
    return found
  }

  /** Sky above the horizon, floor below it. Walls paint over this. */
  private paintBackdrop(
    buffer: CellBuffer,
    grid: CollisionGrid,
    camera: Camera,
    column: number,
    rayX: number,
    rayY: number,
    horizon: number,
    projRows: number,
  ): void {
    const rows = buffer.rows
    const skyBottom = Math.min(rows, Math.ceil(horizon))

    for (let row = 0; row < skyBottom; row += 1) {
      const altitude = (horizon - row) / Math.max(1, horizon)
      const base = mix(SKY_LOW, SKY_HIGH, Math.min(1, altitude * 1.35))
      // The city bleeds light into the smog just above the rooftops.
      const glow = Math.max(0, 1 - altitude * 3.2)
      const color = mix(base, SKY_GLOW, glow * 0.55)

      let glyphIndex = SKY_GLYPHS.empty
      let foreground: Rgb = color
      // Stars are keyed to the ray direction, so they hold still while walking.
      const starKey = hash3(Math.round(rayX * 64), Math.round(rayY * 64), row)
      if (altitude > 0.35 && starKey > 0.988) {
        glyphIndex = SKY_GLYPHS.star[Math.floor(starKey * 4000) % SKY_GLYPHS.star.length]
        foreground = scale(STAR, 0.5 + altitude * 0.6)
      }
      buffer.set(
        column,
        row,
        glyphIndex,
        foreground[0],
        foreground[1],
        foreground[2],
        color[0],
        color[1],
        color[2],
      )
    }

    const groundTop = Math.max(0, Math.ceil(horizon))
    if (!this.quality.groundDetail) {
      for (let row = groundTop; row < rows; row += 1) {
        buffer.set(column, row, G_SPACE, 0, 0, 0, VOID[0], VOID[1], VOID[2])
      }
      return
    }

    for (let row = groundTop; row < rows; row += 1) {
      const offset = row - horizon
      if (offset <= 0.001) {
        buffer.set(column, row, G_SPACE, 0, 0, 0, VOID[0], VOID[1], VOID[2])
        continue
      }
      const distance = (projRows * camera.z) / offset
      if (distance > this.quality.viewDistance) {
        buffer.set(column, row, G_SPACE, 0, 0, 0, FOG[0], FOG[1], FOG[2])
        continue
      }
      const worldX = camera.x + rayX * distance
      const worldY = camera.y + rayY * distance
      const cellX = Math.floor(worldX / grid.cellSize)
      const cellY = Math.floor(worldY / grid.cellSize)
      const code = grid.codeAt(cellX, cellY)
      const fogAmount = 1 - Math.exp(-distance / FOG_DISTANCE_M)

      let background: Rgb
      let foreground: Rgb
      let glyphIndex: number
      const grain = hash2(Math.floor(worldX * 2), Math.floor(worldY * 2))

      if (code === CELL_ROAD) {
        background = GROUND_ASPHALT
        // Lane dashes follow the world grid, so they stay put as you walk.
        const marking = hash2(cellX, cellY) > 0.86
        glyphIndex = marking ? ROAD_GLYPHS.dash : ROAD_GLYPHS.asphalt[grain > 0.7 ? 1 : 0]
        foreground = marking ? GROUND_MARKING : scale(GROUND_ASPHALT, 1.6)
        if (grain > 0.94) {
          // Standing water catches the neon overhead.
          background = mix(background, GROUND_WET, 0.6)
          foreground = mix(foreground, NEON[4], 0.35)
        }
      } else if (code === CELL_SIDEWALK) {
        background = GROUND_SIDEWALK
        glyphIndex = ROAD_GLYPHS.sidewalk[Math.floor(grain * 3) % 3]
        foreground = scale(GROUND_SIDEWALK, 1.9)
      } else if (code === CELL_WATER) {
        background = mix(GROUND_WET, VOID, 0.3)
        glyphIndex = ROAD_GLYPHS.marking
        foreground = scale(GROUND_WET, 1.7)
      } else {
        background = VOID
        glyphIndex = grain > 0.8 ? RAMP[1] : G_SPACE
        foreground = scale(GROUND_SIDEWALK, 1.3)
      }

      const litBackground = fade(background, fogAmount)
      const litForeground = fade(foreground, fogAmount)
      buffer.set(
        column,
        row,
        glyphIndex,
        litForeground[0],
        litForeground[1],
        litForeground[2],
        litBackground[0],
        litBackground[1],
        litBackground[2],
      )
    }
  }

  private paintWall(
    buffer: CellBuffer,
    column: number,
    hit: Hit,
    horizon: number,
    projRows: number,
    eyeZ: number,
  ): void {
    const distance = hit.distance
    const scaleRows = projRows / distance
    const bottom = horizon + scaleRows * eyeZ
    const top = horizon - scaleRows * (hit.height - eyeZ)
    const first = Math.max(0, Math.floor(top))
    const last = Math.min(buffer.rows - 1, Math.ceil(bottom))
    if (last < 0 || first >= buffer.rows) return

    const style = unpackStyle(hit.style)
    const facade = FACADE[style.category]
    const neon = NEON[style.category]
    const fogAmount = 1 - Math.exp(-distance / FOG_DISTANCE_M)
    // A cheap two-sided light so corners read without any real shading.
    const sideShade = hit.side === 0 ? 0.78 : 1.0
    // A facade alternates glazed bands with structural ones. Which is which
    // depends on world position, so the pattern holds still as you walk past.
    const bandIndex = Math.floor(hit.along / WINDOW_PITCH_M)
    const glazed = hash3(hit.cellX, hit.cellY, bandIndex) > 0.28
    const windowChance = 0.34 + style.window * 0.14

    for (let row = first; row <= last; row += 1) {
      // Height in metres of the world point this row looks at.
      const worldZ = eyeZ + (horizon - row) / scaleRows
      if (worldZ < -0.05 || worldZ > hit.height + 0.05) continue

      const floorIndex = Math.floor(worldZ / FLOOR_HEIGHT_M)
      const withinFloor = worldZ - floorIndex * FLOOR_HEIGHT_M
      const lit = hash3(hit.cellX * 31 + bandIndex, hit.cellY, floorIndex)

      let glyphIndex: number
      let foreground: Rgb
      let background = scale(facade, sideShade)
      let effect = EFFECT_NONE

      const isTopRow = row === first && top > 0
      if (isTopRow) {
        // The roof line is the silhouette. Give it the brightest edge.
        glyphIndex =
          hit.height > 45 ? ROOF_GLYPHS.antenna : style.facade & 1 ? ROOF_GLYPHS.gabled : ROOF_GLYPHS.flat
        foreground = scale(neon, 1.1)
        effect = EFFECT_GLOW
        if (hit.height > 60 && Math.sin(this.time * 2.2 + hit.cellX) > 0.7) {
          glyphIndex = ROOF_GLYPHS.beacon
          foreground = [255, 90, 90]
        }
      } else if (withinFloor < 0.42) {
        // Slab between floors.
        glyphIndex = STRUCTURE.ledge
        foreground = scale(facade, 1.9 * sideShade)
      } else if (glazed && withinFloor > 0.8 && withinFloor < 2.5 && worldZ > 1.0) {
        if (lit < windowChance) {
          const strength = Math.floor(lit * 1000) % WINDOWS.length
          glyphIndex = WINDOWS[strength]
          foreground = scale(neon, 1.0 + strength * 0.08)
          background = mix(background, neon, 0.16)
          effect = EFFECT_GLOW
        } else {
          glyphIndex = WINDOW_DARK[Math.floor(lit * 7) % WINDOW_DARK.length]
          foreground = scale(facade, 1.45 * sideShade)
        }
      } else {
        // Structural band: ribs every other band, grainy concrete between.
        // Colour carries the distance, so the glyph is free to carry material.
        glyphIndex = bandIndex & 1 ? STRUCTURE.pillar : SHADES[1 + (Math.floor(lit * 5) % 2)]
        foreground = scale(facade, 1.25 * sideShade)
      }

      const litForeground = fade(foreground, fogAmount)
      const litBackground = fade(background, fogAmount)
      buffer.set(
        column,
        row,
        glyphIndex,
        litForeground[0],
        litForeground[1],
        litForeground[2],
        litBackground[0],
        litBackground[1],
        litBackground[2],
        effect,
      )
    }
  }
}
