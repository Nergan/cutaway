/**
 * The minimap: terrain around the player, plus the players in it.
 *
 * Drawn straight to a small canvas from the chunk store, one pixel per tile, from a palette
 * keyed by tile. Not a scaled-down copy of the world render: the map wants a flat readable
 * plan, and the lit, shaded, weather-graded scene is the opposite of that.
 *
 * Redrawn on a timer rather than every frame. The map's job is orientation, and orientation
 * does not need 60 Hz — 8 is plenty, and it keeps a second full-tile scan off the frame budget.
 */

import { useEffect, useRef } from 'react'

import { ENTITY_PLAYER } from '../domain/constants'
import { Tile } from '../domain/tiles'
import type { RemoteEntity } from '../net/session'
import type { ChunkStore } from '../world/chunkStore'

export interface MinimapProps {
  store: ChunkStore | null
  /** Local player position, in tiles. Read through a ref so this does not re-render. */
  position: () => { x: number; y: number }
  entities: () => Iterable<RemoteEntity>
  /** Hub name or corridor label for the caption. */
  place: string
}

/** Tiles across the map. Odd, so the player sits on an exact centre pixel. */
const SPAN = 97
const SCALE = 2

/**
 * One colour per tile, as a packed RGB string.
 *
 * Deliberately flatter and cooler than the sprite art. A minimap that reproduced the terrain
 * palette would be a blurry thumbnail of the screen; one that abstracts it reads at a glance.
 */
const COLOURS: Record<number, string> = {
  [Tile.BARE_GROUND]: '#5b4f42',
  [Tile.GRASS]: '#4e6b41',
  [Tile.TALL_GRASS]: '#425c37',
  [Tile.BUSH]: '#38512f',
  [Tile.SAPLING]: '#3d5a34',
  [Tile.SAND]: '#a8935f',
  [Tile.GRAVEL]: '#6b6560',
  [Tile.DIRT_ROAD]: '#8a6f4e',
  [Tile.COBBLE_ROAD]: '#95908a',
  [Tile.FLOOR_WOOD]: '#8a6a44',
  [Tile.FLOOR_STONE]: '#a09a92',
  [Tile.SNOW]: '#d6dde2',
  [Tile.ASH]: '#4a4642',
  [Tile.WATER]: '#3f6d8f',
  [Tile.DEEP_WATER]: '#2b4f6b',
  [Tile.TREE]: '#28401f',
  [Tile.DEAD_TREE]: '#4a3f33',
  [Tile.ROCK]: '#797369',
  [Tile.CLIFF]: '#5f5a53',
  [Tile.WALL_WOOD]: '#6f5334',
  [Tile.WALL_STONE]: '#87817a',
  [Tile.FENCE]: '#7a5f3c',
  [Tile.CACTUS]: '#3f5c38',
}

const UNKNOWN = '#23201d'

export function Minimap({ store, position, entities, place }: MinimapProps) {
  const canvas = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const element = canvas.current
    if (element === null) return

    const context = element.getContext('2d')
    if (context === null) return
    context.imageSmoothingEnabled = false

    let timer = 0

    // Bound so `draw` closes over a non-null context rather than re-narrowing it each call.
    const paint = context

    function draw(): void {
      const centre = position()
      const half = Math.floor(SPAN / 2)

      paint.fillStyle = UNKNOWN
      paint.fillRect(0, 0, SPAN, SPAN)

      if (store !== null) {
        for (let dy = -half; dy <= half; dy += 1) {
          for (let dx = -half; dx <= half; dx += 1) {
            const tile = store.tileAtPoint({
              x: Math.floor(centre.x) + dx,
              y: Math.floor(centre.y) + dy,
            })
            if (tile === undefined) continue
            paint.fillStyle = COLOURS[tile] ?? UNKNOWN
            paint.fillRect(dx + half, dy + half, 1, 1)
          }
        }

        for (const entity of entities()) {
          const dx = Math.round(entity.pose.x - centre.x)
          const dy = Math.round(entity.pose.y - centre.y)
          if (Math.abs(dx) > half || Math.abs(dy) > half) continue
          // Players in tan, everything else in red: on a map, "someone" and "something that
          // will attack me" are the only two categories that matter.
          paint.fillStyle = entity.kind === ENTITY_PLAYER ? '#d4a373' : '#c1584f'
          paint.fillRect(dx + half, dy + half, 1, 1)
        }
      }

      paint.fillStyle = '#f4ece0'
      paint.fillRect(half, half, 1, 1)

      timer = window.setTimeout(draw, 125)
    }

    draw()
    return () => window.clearTimeout(timer)
  }, [store, position, entities])

  return (
    <section className="panel minimap hud-minimap" aria-label="Map">
      <canvas
        ref={canvas}
        width={SPAN}
        height={SPAN}
        style={{ width: SPAN * SCALE, height: SPAN * SCALE }}
      />
      <div className="minimap-legend">
        <span>{place}</span>
        <span>{SPAN} tiles</span>
      </div>
    </section>
  )
}
