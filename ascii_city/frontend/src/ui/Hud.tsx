import type { SessionView } from '../game/session'
import { PLAYER_COLORS } from '../render/palette'

interface Props {
  view: SessionView
  onOpenSettings: () => void
}

function css(color: readonly [number, number, number]): string {
  return `rgb(${Math.round(color[0])},${Math.round(color[1])},${Math.round(color[2])})`
}

/** Compass letter for a yaw, matching the world axes: +x east, +y north. */
function heading(yaw: number): string {
  const points = ['E', 'NE', 'N', 'NW', 'W', 'SW', 'S', 'SE']
  const index = Math.round((yaw / (Math.PI * 2)) * 8) % 8
  return points[(index + 8) % 8]
}

export function Hud({ view, onOpenSettings }: Props) {
  const player = view.player
  if (!player) return null
  const color = PLAYER_COLORS[player.color % PLAYER_COLORS.length]

  return (
    <div className="hud">
      <div className="hud-block hud-identity">
        <span className="dot" style={{ background: css(color) }} />
        <strong style={{ color: css(color) }}>{player.nickname}</strong>
      </div>

      <div className="hud-block hud-readout">
        <span>
          {Math.round(player.x)}, {Math.round(player.y)}
        </span>
        <span>{heading(player.yaw)}</span>
        <span>{view.population} online</span>
        <span>{view.status.latencyMs} ms</span>
      </div>

      <div className="hud-block hud-tools">
        {view.stats ? (
          <span className="muted">
            {view.stats.columns}x{view.stats.rows} {view.stats.backend === 'webgl2' ? 'GL' : '2D'}{' '}
            {Math.round(view.stats.fps)} fps
          </span>
        ) : null}
        <button type="button" onClick={onOpenSettings}>
          settings
        </button>
      </div>
    </div>
  )
}
