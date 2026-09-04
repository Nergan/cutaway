/**
 * Render one frame of the real city to the terminal.
 *
 * The raycaster has no browser dependencies, so it can run under Node against
 * tiles pulled from a live server. This is the fastest way to see whether a
 * change to the renderer improved the city or ruined it — and, unlike a
 * screenshot, it is a text answer to "is there a sign on that building".
 *
 *   python -m ascii_city.main --port 8130      # in one shell
 *   npx vite-node tools/preview-frame.ts       # in another
 *
 * `scripts/probe_district.py` prints coordinates worth pointing this at.
 *
 * Options: --url, --x, --y, --yaw (degrees), --pitch, --columns, --rows,
 * --auto (face the longest clear view), --avatar N (stand a figure in front),
 * --plain (no colour).
 */

import { CellBuffer, CELL_STRIDE } from '../frontend/src/render/cellBuffer'
import { CHARSET } from '../frontend/src/render/charset'
import { bakeLightMap, collectProps, renderProps } from '../frontend/src/render/props'
import { Raycaster, DEFAULT_QUALITY } from '../frontend/src/render/raycaster'
import { renderSprites, type Sprite } from '../frontend/src/render/sprites'
import { CollisionGrid, blitTile } from '../frontend/src/world/collisionGrid'
import { decodeTile } from '../frontend/src/world/tileCodec'
import { EYE_HEIGHT_M, PLAYER_RADIUS_M } from '../frontend/src/domain/constants'
import type { WorldMetadata, WorldTile } from '../frontend/src/domain/types'

function option(name: string, fallback: string): string {
  const index = process.argv.indexOf(`--${name}`)
  return index >= 0 && process.argv[index + 1] ? process.argv[index + 1] : fallback
}

const BASE = option('url', 'http://127.0.0.1:8130/ascii-city')
const COLUMNS = Number(option('columns', '150'))
const ROWS = Number(option('rows', '44'))
const AVATAR = Number(option('avatar', '-1'))

/** `--plain` drops the escape codes for terminals and logs that cannot show them. */
const PLAIN = process.argv.includes('--plain')

/** 24-bit colour, because a modern terminal can show the palette as designed. */
function paint(fg: number[], bg: number[], character: string): string {
  if (PLAIN) return character
  return `\u001b[38;2;${fg[0]};${fg[1]};${fg[2]}m\u001b[48;2;${bg[0]};${bg[1]};${bg[2]}m${character}`
}

async function main(): Promise<void> {
  const metadata = (await (await fetch(`${BASE}/api/world`)).json()) as WorldMetadata
  const { tilesX, tilesY, tileCells, cellSize } = metadata.world
  const grid = new CollisionGrid(tilesX * tileCells, tilesY * tileCells, cellSize)

  let bytes = 0
  const tiles: WorldTile[] = []
  for (let y = 0; y < tilesY; y += 1) {
    for (let x = 0; x < tilesX; x += 1) {
      const payload = await (await fetch(`${BASE}/api/world/tiles/${x}/${y}`)).arrayBuffer()
      bytes += payload.byteLength
      const tile = decodeTile(payload)
      blitTile(grid, tile)
      tiles.push(tile)
    }
  }

  const stand = standable(
    grid,
    Number(option('x', String(grid.widthM / 2))),
    Number(option('y', String(grid.heightM / 2))),
  )
  const yaw = process.argv.includes('--auto')
    ? clearestYaw(grid, stand)
    : (Number(option('yaw', '35')) * Math.PI) / 180
  const camera = {
    x: stand.x,
    y: stand.y,
    // Standing on a terrace puts the eye above street level, and a frame shot
    // from street level through a plateau is not what the player would see.
    z: EYE_HEIGHT_M + grid.groundAt(stand.x, stand.y, PLAYER_RADIUS_M),
    yaw,
    pitch: (Number(option('pitch', '0')) * Math.PI) / 180,
  }

  const buffer = new CellBuffer(COLUMNS, ROWS)
  const raycaster = new Raycaster({ ...DEFAULT_QUALITY })
  raycaster.time = 3.2
  const props = collectProps(tiles, cellSize)
  raycaster.light = bakeLightMap(props, grid.width, grid.height, cellSize)

  const started = performance.now()
  raycaster.render(buffer, grid, camera)
  renderProps(buffer, camera, props, raycaster.quality.fov, raycaster.time)
  const sprites: Sprite[] = []
  if (AVATAR >= 0) {
    // Where the chase camera would frame the player, so `--avatar` shows what
    // pressing 5 shows.
    sprites.push({
      id: 2,
      x: camera.x + Math.cos(yaw) * 4.2,
      y: camera.y + Math.sin(yaw) * 4.2,
      z: camera.z,
      animation: 1,
      nickname: 'violet-conduit',
      color: 2,
      avatar: AVATAR,
    })
  }
  renderSprites(buffer, camera, sprites, raycaster.quality.fov, raycaster.time)
  const elapsed = performance.now() - started

  const lines: string[] = []
  for (let row = 0; row < ROWS; row += 1) {
    let line = ''
    for (let column = 0; column < COLUMNS; column += 1) {
      const at = (row * COLUMNS + column) * CELL_STRIDE
      const character = CHARSET[buffer.data[at]] ?? ' '
      line += paint(
        [buffer.data[at + 2], buffer.data[at + 3], buffer.data[at + 4]],
        [buffer.data[at + 5], buffer.data[at + 6], buffer.data[at + 7]],
        character,
      )
    }
    lines.push(PLAIN ? line : `${line}\u001b[0m`)
  }

  console.log(lines.join('\n'))
  console.log(
    `\n${metadata.world.id} v${metadata.world.version} | ${tilesX}x${tilesY} tiles, ` +
      `${(bytes / 1024).toFixed(1)} KiB | ${props.length} props | camera ` +
      `${camera.x.toFixed(1)}, ${camera.y.toFixed(1)}, z ${camera.z.toFixed(2)} facing ` +
      `${((yaw * 180) / Math.PI).toFixed(0)} deg | ${COLUMNS}x${ROWS} cells in ` +
      `${elapsed.toFixed(1)} ms`,
  )
}

/** The asked-for spot, or the nearest one a player could actually stand on. */
function standable(grid: CollisionGrid, x: number, y: number): { x: number; y: number } {
  if (grid.isFreeCircle(x, y, PLAYER_RADIUS_M)) return { x, y }
  for (let radius = 1; radius < 60; radius += 1) {
    for (let step = 0; step < 32; step += 1) {
      const angle = (step / 32) * Math.PI * 2
      const probeX = x + Math.cos(angle) * radius
      const probeY = y + Math.sin(angle) * radius
      if (grid.isFreeCircle(probeX, probeY, PLAYER_RADIUS_M)) return { x: probeX, y: probeY }
    }
  }
  return { x, y }
}

/** Whichever way has the most city in front of it, in five-degree steps. */
function clearestYaw(grid: CollisionGrid, at: { x: number; y: number }): number {
  let best = 0
  let furthest = -1
  for (let step = 0; step < 72; step += 1) {
    const angle = (step / 72) * Math.PI * 2
    const dx = Math.cos(angle)
    const dy = Math.sin(angle)
    let reach = 0
    while (reach < 90 && grid.isFreeCircle(at.x + dx * reach, at.y + dy * reach, PLAYER_RADIUS_M)) {
      reach += 1
    }
    if (reach > furthest) {
      furthest = reach
      best = angle
    }
  }
  return best
}

main().catch((error: unknown) => {
  console.error(error instanceof Error ? error.message : error)
  process.exitCode = 1
})
