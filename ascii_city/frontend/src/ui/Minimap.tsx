import { useEffect, useRef } from 'react'

import type { GameSession } from '../game/session'
import type { RosterMember } from '../net/wire'
import { avatarFace } from '../render/charset'
import { PLAYER_COLORS } from '../render/palette'

interface Props {
  session: GameSession | null
  roster: RosterMember[]
  selfId: number
  /** Held-open map: bigger widget, and enough district to plan a route on. */
  expanded?: boolean
}

const SIZE_PX = 148
const EXPANDED_SIZE_PX = 460
const DEFAULT_SPAN_M = 130
const EXPANDED_SPAN_M = 340

function css(color: readonly [number, number, number]): string {
  return `rgb(${Math.round(color[0])},${Math.round(color[1])},${Math.round(color[2])})`
}

/**
 * A north-up crop of the district around the player.
 *
 * It runs its own animation frame and reads positions straight off the
 * session, because the React view only refreshes a few times a second and a
 * map that steps like that reads as broken rather than economical.
 */
export function Minimap({ session, roster, selfId, expanded = false }: Props) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const size = expanded ? EXPANDED_SIZE_PX : SIZE_PX
  const span = expanded ? EXPANDED_SPAN_M : DEFAULT_SPAN_M
  // The draw loop must not restart every time somebody joins or renames.
  const rosterRef = useRef(new Map<number, RosterMember>())

  useEffect(() => {
    rosterRef.current = new Map(roster.map((member) => [member.id, member]))
  }, [roster])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas || !session) return

    const context = canvas.getContext('2d')
    if (!context) return

    const ratio = Math.min(2, window.devicePixelRatio || 1)
    canvas.width = size * ratio
    canvas.height = size * ratio

    let handle = 0
    const draw = () => {
      handle = requestAnimationFrame(draw)
      const source = session.minimap
      if (!source) return

      const { camera, others } = session.liveState
      const members = rosterRef.current
      const cells = span / source.cellSize
      const pixelsPerCell = (size * ratio) / cells
      const originCellX = camera.x / source.cellSize - cells / 2
      const originCellY = camera.y / source.cellSize - cells / 2

      context.setTransform(1, 0, 0, 1, 0, 0)
      context.fillStyle = '#04070a'
      context.fillRect(0, 0, canvas.width, canvas.height)

      // World +y is north, so the crop is flipped vertically to put north up.
      context.imageSmoothingEnabled = false
      context.save()
      context.translate(0, canvas.height)
      context.scale(1, -1)
      context.drawImage(
        source.canvas,
        originCellX,
        originCellY,
        cells,
        cells,
        0,
        0,
        canvas.width,
        canvas.height,
      )
      context.restore()

      const toScreen = (worldX: number, worldY: number): [number, number] => [
        (worldX / source.cellSize - originCellX) * pixelsPerCell,
        canvas.height - (worldY / source.cellSize - originCellY) * pixelsPerCell,
      ]

      context.textAlign = 'center'
      context.textBaseline = 'middle'
      context.font = `${Math.round(11 * ratio)}px ${getComputedStyle(canvas).fontFamily}`

      for (const other of others) {
        const member = members.get(other.id)
        const [px, py] = toScreen(other.x, other.y)
        context.fillStyle = css(PLAYER_COLORS[(member?.color ?? 0) % PLAYER_COLORS.length])
        context.fillText(avatarFace(member?.avatar ?? 0), px, py)
      }

      // The player sits dead centre; the wedge is the direction they face.
      const self = members.get(selfId)
      const ink = css(PLAYER_COLORS[(self?.color ?? 0) % PLAYER_COLORS.length])
      const [cx, cy] = toScreen(camera.x, camera.y)
      context.fillStyle = ink
      context.globalAlpha = 0.25
      context.beginPath()
      context.moveTo(cx, cy)
      context.arc(cx, cy, 13 * ratio, -camera.yaw - 0.42, -camera.yaw + 0.42)
      context.closePath()
      context.fill()
      context.globalAlpha = 1
      context.font = `${Math.round(13 * ratio)}px ${getComputedStyle(canvas).fontFamily}`
      context.fillText(avatarFace(self?.avatar ?? 0), cx, cy)
    }

    handle = requestAnimationFrame(draw)
    return () => cancelAnimationFrame(handle)
  }, [session, selfId, span, size])

  return (
    <div
      className={`minimap${expanded ? ' minimap-expanded' : ''}`}
      style={{ width: size, height: size }}
    >
      <canvas ref={canvasRef} style={{ width: size, height: size }} />
      <span className="minimap-north">N</span>
      {expanded ? <span className="minimap-scale">{EXPANDED_SPAN_M} m</span> : null}
    </div>
  )
}
