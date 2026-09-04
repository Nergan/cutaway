/**
 * The ASCII raycaster.
 *
 * A DDA walk per screen column produces the skyline; the walk continues past
 * the first wall so towers behind the street still cut their silhouette into
 * the sky, which is what makes the city read as vertical. Everything lands in
 * a character grid, and the GPU pass afterwards only turns that grid into
 * pixels.
 */

import {
  CATEGORY_APARTMENT,
  CATEGORY_OFFICE,
  CATEGORY_SHOP,
  CATEGORY_STATION,
  CELL_INTERACTIVE,
  CELL_ROAD,
  CELL_SIDEWALK,
  CELL_WATER,
  unpackStyle,
} from '../domain/constants'
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
  signWord,
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
  rgb,
  scale,
  type Rgb,
} from './palette'

/** The colour a sodium street lamp throws onto the pavement. */
const LAMP_POOL: Rgb = rgb(0xffc879)
/** Indoors: a low ceiling and the boards under it. */
const CEILING: Rgb = rgb(0x0d1016)
const CEILING_LIT: Rgb = rgb(0x1c222c)
const INTERIOR_FLOOR: Rgb = rgb(0x232830)

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

/** Width of a window frame member, in metres of facade. */
const MULLION_M = 0.22
/** Spacing of the horizontal courses scored into a blank wall. */
const COURSE_M = 0.75

/** Metres of facade each character of a vertical signboard occupies. */
const SIGN_CELL_M = 1.5
const EMPTY_WORD: number[] = []
/** Premises that put their name on the outside wall. */
const SIGNED_CATEGORIES = new Set([
  CATEGORY_SHOP,
  CATEGORY_APARTMENT,
  CATEGORY_OFFICE,
  CATEGORY_STATION,
])
const SIGN_INKS: readonly Rgb[] = [
  rgb(0xff5fa2),
  rgb(0x35e0ff),
  rgb(0xffd479),
  rgb(0x9fe86b),
  rgb(0xff8a3d),
]

interface Hit {
  distance: number
  height: number
  style: number
  side: number
  /** World coordinate along the wall face; keeps the facade from swimming. */
  along: number
  cellX: number
  cellY: number
  /** A walkable surface stepping up, not a wall: drawn as a riser. */
  ledge: boolean
}

const HITS: Hit[] = Array.from({ length: 16 }, () => ({
  distance: 0,
  height: 0,
  style: 0,
  side: 0,
  along: 0,
  cellX: 0,
  cellY: 0,
  ledge: false,
}))

export class Raycaster {
  /** Seconds since the world loaded; drives beacons and signage flicker. */
  time = 0

  /**
   * Per-cell pavement light baked from the street furniture, or null before a
   * world is loaded. Lamps that light nothing are just poles.
   */
  light: Float32Array | null = null

  /** Whether the camera is standing inside a carved interior this frame. */
  private indoors = false

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

    // Standing in a shop, what is overhead is a ceiling, not the night sky.
    // One lookup per frame buys the difference between a room and a courtyard.
    this.indoors =
      grid.codeAt(
        Math.floor(camera.x / grid.cellSize),
        Math.floor(camera.y / grid.cellSize),
      ) === CELL_INTERACTIVE

    for (let column = 0; column < columns; column += 1) {
      const cameraX = (2 * column) / columns - 1
      const rayX = dirX + planeX * cameraX
      const rayY = dirY + planeY * cameraX

      const hitCount = this.cast(grid, camera, rayX, rayY)
      this.paintBackdrop(buffer, grid, camera, column, rayX, rayY, horizon, projRows)

      // Far to near, so nearer geometry overwrites the silhouettes behind it.
      for (let index = hitCount - 1; index >= 0; index -= 1) {
        const hit = HITS[index]
        if (hit.ledge) this.paintLedge(buffer, column, hit, horizon, projRows, camera.z)
        else this.paintWall(buffer, column, hit, horizon, projRows, camera.z)
      }
      // Only a wall hides what stands behind it. A knee-high step does not,
      // so the depth the sprite pass tests against skips the risers.
      for (let index = 0; index < hitCount; index += 1) {
        if (HITS[index].ledge) continue
        buffer.depth[column] = HITS[index].distance
        break
      }
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
    // The ground the ray is currently flying over. Every time it climbs, the
    // riser it climbed is a surface the eye can see, so it gets a hit of its
    // own; going back down is just floor, and the floor pass handles that.
    let groundAlong = grid.floorAt(mapX, mapY)

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

      const solid = grid.isSolidCell(mapX, mapY)
      let ledgeTop = 0
      if (!solid) {
        const floor = grid.floorAt(mapX, mapY)
        if (floor <= groundAlong + 0.01) {
          groundAlong = floor
          continue
        }
        ledgeTop = floor
        groundAlong = floor
      }

      const distance = travelled * cellSize
      const hit = HITS[found]
      hit.distance = distance < 0.01 ? 0.01 : distance
      hit.height = solid ? Math.max(1, grid.heightAt(mapX, mapY)) : ledgeTop
      hit.style = grid.styleAt(mapX, mapY)
      hit.side = side
      hit.cellX = mapX
      hit.cellY = mapY
      hit.ledge = !solid
      hit.along =
        side === 0 ? camera.y + rayY * hit.distance : camera.x + rayX * hit.distance
      found += 1

      // Once a wall reaches over the camera by a wide margin nothing behind it
      // can appear, and there is no point spending steps on it.
      if (found >= layers) break
      if (!solid) continue
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

    if (this.indoors) {
      for (let row = 0; row < skyBottom; row += 1) {
        // Nearer the horizon the ceiling is further away and catches less of
        // the room's light, which is what gives it depth.
        const altitude = (horizon - row) / Math.max(1, horizon)
        const panel = hash3(Math.round(rayX * 24), Math.round(rayY * 24), row) > 0.86
        const color = mix(CEILING, CEILING_LIT, altitude * 0.8)
        const ink = panel ? scale(CEILING_LIT, 1.6) : scale(color, 1.4)
        buffer.set(
          column,
          row,
          panel ? ROAD_GLYPHS.marking : SKY_GLYPHS.empty,
          ink[0],
          ink[1],
          ink[2],
          color[0],
          color[1],
          color[2],
        )
      }
    } else {
      this.paintSky(buffer, column, rayX, rayY, horizon, skyBottom)
    }

    const groundTop = Math.max(0, Math.ceil(horizon))
    if (!this.quality.groundDetail) {
      for (let row = groundTop; row < rows; row += 1) {
        buffer.set(column, row, G_SPACE, 0, 0, 0, VOID[0], VOID[1], VOID[2])
      }
      return
    }

    this.paintFloor(buffer, grid, camera, column, rayX, rayY, horizon, projRows, groundTop)
  }

  private paintSky(
    buffer: CellBuffer,
    column: number,
    rayX: number,
    rayY: number,
    horizon: number,
    skyBottom: number,
  ): void {
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
  }

  /** Floor casting: one world sample per row below the horizon. */
  private paintFloor(
    buffer: CellBuffer,
    grid: CollisionGrid,
    camera: Camera,
    column: number,
    rayX: number,
    rayY: number,
    horizon: number,
    projRows: number,
    groundTop: number,
  ): void {
    const rows = buffer.rows
    for (let row = groundTop; row < rows; row += 1) {
      const offset = row - horizon
      if (offset <= 0.001) {
        buffer.set(column, row, G_SPACE, 0, 0, 0, VOID[0], VOID[1], VOID[2])
        continue
      }
      // Where the ground is a plane at zero, one division answers the whole
      // question. Where it is not, the surface under this row sits closer than
      // the plane did, so the sample is walked in: two or three passes settle
      // it, and over flat ground the first pass finds nothing to settle.
      let distance = (projRows * camera.z) / offset
      let worldX = 0
      let worldY = 0
      let cellX = 0
      let cellY = 0
      let elevation = 0
      let beyond = false
      let hidden = false
      for (let pass = 0; pass < 3; pass += 1) {
        if (distance > this.quality.viewDistance) {
          beyond = true
          break
        }
        worldX = camera.x + rayX * distance
        worldY = camera.y + rayY * distance
        cellX = Math.floor(worldX / grid.cellSize)
        cellY = Math.floor(worldY / grid.cellSize)
        const floor = grid.floorAt(cellX, cellY)
        if (Math.abs(floor - elevation) < 0.01) break
        elevation = floor
        const drop = camera.z - elevation
        // Standing below a terrace, its top is over the eye and this row is
        // looking at the face of it, which the ledge pass has already drawn.
        if (drop <= 0.05) {
          hidden = true
          break
        }
        distance = (projRows * drop) / offset
      }
      if (hidden) continue
      if (beyond) {
        buffer.set(column, row, G_SPACE, 0, 0, 0, FOG[0], FOG[1], FOG[2])
        continue
      }

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
      } else if (code === CELL_INTERACTIVE) {
        // A shop floor: tiled, and tinted by whatever the place is.
        const accent = NEON[unpackStyle(grid.styleAt(cellX, cellY)).category]
        background = mix(INTERIOR_FLOOR, accent, 0.12)
        const tile = (cellX + cellY) & 1
        glyphIndex = tile ? ROAD_GLYPHS.sidewalk[1] : ROAD_GLYPHS.marking
        foreground = mix(scale(INTERIOR_FLOOR, 2.4), accent, 0.35)
      } else if (code === CELL_WATER) {
        background = mix(GROUND_WET, VOID, 0.3)
        glyphIndex = ROAD_GLYPHS.marking
        foreground = scale(GROUND_WET, 1.7)
      } else {
        background = VOID
        glyphIndex = grain > 0.8 ? RAMP[1] : G_SPACE
        foreground = scale(GROUND_SIDEWALK, 1.3)
      }

      // A pool of lamplight on wet asphalt is most of what sells a night
      // street, and the map that produces it was baked at load time.
      const lamp = this.lightAt(grid, cellX, cellY)
      if (lamp > 0.01) {
        background = mix(scale(background, 1 + lamp * 0.9), LAMP_POOL, lamp * 0.22)
        foreground = mix(scale(foreground, 1 + lamp * 1.1), LAMP_POOL, lamp * 0.3)
        if (glyphIndex === G_SPACE && lamp > 0.5) glyphIndex = RAMP[1]
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

  private lightAt(grid: CollisionGrid, cellX: number, cellY: number): number {
    const map = this.light
    if (!map) return 0
    if (cellX < 0 || cellY < 0 || cellX >= grid.width || cellY >= grid.height) return 0
    return map[cellY * grid.width + cellX]
  }

  /**
   * The vertical face of a step or terrace.
   *
   * Short enough that a facade's worth of windows and signage would be
   * nonsense on it, so it gets its own treatment: a bright nosing along the
   * top edge and stone below, which is what makes a flight of stairs read as
   * stairs from the bottom.
   */
  private paintLedge(
    buffer: CellBuffer,
    column: number,
    hit: Hit,
    horizon: number,
    projRows: number,
    eyeZ: number,
  ): void {
    const scaleRows = projRows / hit.distance
    const top = horizon - scaleRows * (hit.height - eyeZ)
    const bottom = horizon + scaleRows * eyeZ
    const first = Math.max(0, Math.floor(top))
    const last = Math.min(buffer.rows - 1, Math.ceil(bottom))
    if (last < 0 || first >= buffer.rows) return

    const fogAmount = 1 - Math.exp(-hit.distance / FOG_DISTANCE_M)
    const sideShade = hit.side === 0 ? 0.7 : 1.15
    const stone = scale(GROUND_SIDEWALK, 0.55 * sideShade)
    const nosing = scale(GROUND_SIDEWALK, 2.1)

    for (let row = first; row <= last; row += 1) {
      const worldZ = eyeZ + (horizon - row) / scaleRows
      if (worldZ < -0.05 || worldZ > hit.height + 0.02) continue
      const edge = row === first && top > 0
      const foreground = fade(edge ? nosing : scale(stone, 1.7), fogAmount)
      const background = fade(edge ? mix(stone, nosing, 0.3) : stone, fogAmount)
      buffer.set(
        column,
        row,
        edge ? STRUCTURE.ledge : SHADES[1],
        foreground[0],
        foreground[1],
        foreground[2],
        background[0],
        background[1],
        background[2],
        EFFECT_NONE,
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
    // Stronger side contrast and a little distance falloff read as volume.
    const sideShade = hit.side === 0 ? 0.58 : 1.12
    const depthShade = 0.72 + 0.28 * Math.exp(-distance / 90)
    // A facade alternates glazed bands with structural ones. Which is which
    // depends on world position, so the pattern holds still as you walk past.
    const bandIndex = Math.floor(hit.along / WINDOW_PITCH_M)
    const glazed = hash3(hit.cellX, hit.cellY, bandIndex) > 0.28
    const windowChance = 0.34 + style.window * 0.14
    // Where this column sits inside its band. Close up a band is dozens of
    // screen columns wide, so without this the whole thing is one flat slab.
    const acrossBand = hit.along - bandIndex * WINDOW_PITCH_M
    const mullion = acrossBand < MULLION_M || acrossBand > WINDOW_PITCH_M - MULLION_M

    // The one thing a Tokyo street has more of than windows: signboards bolted
    // up the front of the building, read top to bottom. One band in four
    // carries one, on the kinds of premises that have something to advertise.
    const boardKey = hash3(hit.cellX * 7 + bandIndex * 3, hit.cellY * 13 + 5, 91)
    const board = SIGNED_CATEGORIES.has(style.category) && boardKey > 0.74 && hit.height > 6
    const boardWord = board ? signWord(Math.floor(boardKey * 9973)) : EMPTY_WORD
    const boardBottom = 2.6
    const boardTop = Math.min(hit.height - 1.2, boardBottom + boardWord.length * SIGN_CELL_M)
    const boardInk = SIGN_INKS[Math.floor(boardKey * 977) % SIGN_INKS.length]

    for (let row = first; row <= last; row += 1) {
      // Height in metres of the world point this row looks at.
      const worldZ = eyeZ + (horizon - row) / scaleRows
      if (worldZ < -0.05 || worldZ > hit.height + 0.05) continue

      const floorIndex = Math.floor(worldZ / FLOOR_HEIGHT_M)
      const withinFloor = worldZ - floorIndex * FLOOR_HEIGHT_M
      const lit = hash3(hit.cellX * 31 + bandIndex, hit.cellY, floorIndex)

      let glyphIndex: number
      let foreground: Rgb
      let background = scale(facade, sideShade * depthShade)
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
      } else if (board && worldZ > boardBottom && worldZ < boardTop) {
        const index = Math.floor((boardTop - worldZ) / SIGN_CELL_M)
        // The board has an edge and its characters sit in cells. Standing under
        // one, that structure is the difference between a sign and a wash of
        // colour across a quarter of the screen.
        const rule = (boardTop - worldZ) % SIGN_CELL_M < 0.16
        glyphIndex = mullion
          ? STRUCTURE.double
          : rule
            ? STRUCTURE.ledge
            : boardWord[Math.min(boardWord.length - 1, Math.max(0, index))]
        foreground = scale(boardInk, mullion || rule ? 1.7 : 1.4)
        background = mix(VOID, boardInk, 0.22)
        effect = EFFECT_GLOW
      } else if (withinFloor < 0.42) {
        // Slab between floors — brighter on sun-facing bands for contour.
        const edge = hash3(hit.cellX, hit.cellY, bandIndex) > 0.82
        glyphIndex = edge ? STRUCTURE.pillar : STRUCTURE.ledge
        foreground = scale(facade, (edge ? 2.2 : 1.9) * sideShade * depthShade)
      } else if (worldZ < 1.2 && bandIndex === 0) {
        // Street-level plinth: darker base anchors the facade to the ground.
        glyphIndex = STRUCTURE.pillar
        foreground = scale(facade, 1.05 * sideShade)
        background = mix(background, VOID, 0.25)
      } else if (glazed && withinFloor > 0.8 && withinFloor < 2.5 && worldZ > 1.0) {
        // A window is a frame with glass in it, not a coloured rectangle. The
        // frame is what survives magnification and gives the wall its relief.
        const sill = withinFloor < 0.8 + MULLION_M
        const head = withinFloor > 2.5 - MULLION_M
        if (mullion || sill || head) {
          glyphIndex = mullion
            ? sill || head
              ? STRUCTURE.cross
              : STRUCTURE.pillar
            : STRUCTURE.ledge
          foreground = scale(facade, 2.1 * sideShade * depthShade)
        } else if (lit < windowChance) {
          const strength = Math.floor(lit * 1000) % WINDOWS.length
          // A pane catches the street diagonally, so the highlight runs across
          // the glass rather than filling it.
          const sheen = (acrossBand * 2.1 + withinFloor) % 1.15 < 0.3
          glyphIndex = sheen ? WINDOWS[WINDOWS.length - 1] : WINDOWS[strength]
          foreground = scale(neon, (sheen ? 1.35 : 1.0) + strength * 0.08)
          background = mix(background, neon, sheen ? 0.28 : 0.16)
          effect = EFFECT_GLOW
        } else {
          glyphIndex = WINDOW_DARK[Math.floor(lit * 7) % WINDOW_DARK.length]
          foreground = scale(facade, 1.45 * sideShade)
        }
      } else {
        // Structural band: ribs every other band, grainy concrete between.
        // Colour carries the distance, so the glyph is free to carry material.
        // The seam and the courses are what stop a close wall reading as one
        // undifferentiated slab.
        const course = withinFloor % COURSE_M < COURSE_M * 0.22
        glyphIndex = course
          ? STRUCTURE.ledge
          : mullion
            ? STRUCTURE.pillar
            : SHADES[1 + (Math.floor(lit * 5) % 2)]
        foreground = scale(facade, (course || mullion ? 1.7 : 1.25) * sideShade)
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
