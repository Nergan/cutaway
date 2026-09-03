/**
 * Render one frame of the real city to the terminal.
 *
 * The raycaster has no browser dependencies, so it can run under Node against
 * tiles pulled from a live server. This is the fastest way to see whether a
 * change to the renderer improved the city or ruined it.
 *
 *   python -m ascii_city.main --port 8130      # in one shell
 *   npx vite-node tools/preview-frame.ts       # in another
 *
 * Options: --url, --x, --y, --yaw (degrees), --columns, --rows.
 */

import { CellBuffer, CELL_STRIDE } from '../frontend/src/render/cellBuffer'
import { CHARSET } from '../frontend/src/render/charset'
import { Raycaster, DEFAULT_QUALITY } from '../frontend/src/render/raycaster'
import { renderSprites, type Sprite } from '../frontend/src/render/sprites'
import { CollisionGrid, blitTile } from '../frontend/src/world/collisionGrid'
import { decodeTile } from '../frontend/src/world/tileCodec'
import { EYE_HEIGHT_M } from '../frontend/src/domain/constants'
import type { WorldMetadata } from '../frontend/src/domain/types'

function option(name: string, fallback: string): string {
  const index = process.argv.indexOf(`--${name}`)
  return index >= 0 && process.argv[index + 1] ? process.argv[index + 1] : fallback
}

const BASE = option('url', 'http://127.0.0.1:8130/ascii-city')
const COLUMNS = Number(option('columns', '150'))
const ROWS = Number(option('rows', '44'))

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
  for (let y = 0; y < tilesY; y += 1) {
    for (let x = 0; x < tilesX; x += 1) {
      const payload = await (await fetch(`${BASE}/api/world/tiles/${x}/${y}`)).arrayBuffer()
      bytes += payload.byteLength
      blitTile(grid, decodeTile(payload))
    }
  }

  const camera = {
    x: Number(option('x', String(grid.widthM / 2))),
    y: Number(option('y', String(grid.heightM / 2))),
    z: EYE_HEIGHT_M,
    yaw: (Number(option('yaw', '35')) * Math.PI) / 180,
    pitch: (Number(option('pitch', '0')) * Math.PI) / 180,
  }

  const buffer = new CellBuffer(COLUMNS, ROWS)
  const raycaster = new Raycaster({ ...DEFAULT_QUALITY })
  raycaster.time = 3.2

  const started = performance.now()
  raycaster.render(buffer, grid, camera)
  const sprites: Sprite[] = [
    { id: 2, x: camera.x + 6, y: camera.y + 3, animation: 1, nickname: 'violet-conduit', color: 2 },
  ]
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
      `${(bytes / 1024).toFixed(1)} KiB | camera ${camera.x.toFixed(1)}, ${camera.y.toFixed(1)} ` +
      `facing ${option('yaw', '35')} deg | ${COLUMNS}x${ROWS} cells in ${elapsed.toFixed(1)} ms`,
  )
}

main().catch((error: unknown) => {
  console.error(error instanceof Error ? error.message : error)
  process.exitCode = 1
})
