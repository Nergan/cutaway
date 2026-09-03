import { useState } from 'react'

import type { QualityPreset, RendererStats } from '../render/renderer'

interface Props {
  stats: RendererStats | null
  onClose: () => void
  onQuality: (preset: QualityPreset) => void
  onFieldOfView: (degrees: number) => void
}

const PRESETS: QualityPreset[] = ['auto', 'high', 'balanced', 'low']

export function Settings({ stats, onClose, onQuality, onFieldOfView }: Props) {
  const [preset, setPreset] = useState<QualityPreset>('auto')
  const [fov, setFov] = useState(78)

  return (
    <div className="settings">
      <header>
        <h2>settings</h2>
        <button type="button" onClick={onClose}>
          close
        </button>
      </header>

      <label>
        <span>resolution</span>
        <div className="choices">
          {PRESETS.map((option) => (
            <button
              key={option}
              type="button"
              className={option === preset ? 'active' : ''}
              onClick={() => {
                setPreset(option)
                onQuality(option)
              }}
            >
              {option}
            </button>
          ))}
        </div>
      </label>

      <label>
        <span>field of view: {fov}&deg;</span>
        <input
          type="range"
          min={60}
          max={105}
          value={fov}
          onChange={(event) => {
            const value = Number(event.target.value)
            setFov(value)
            onFieldOfView(value)
          }}
        />
      </label>

      {stats ? (
        <dl className="diagnostics">
          <dt>backend</dt>
          <dd>{stats.backend}</dd>
          <dt>grid</dt>
          <dd>
            {stats.columns} x {stats.rows}
          </dd>
          <dt>frame</dt>
          <dd>{stats.frameMs.toFixed(1)} ms</dd>
        </dl>
      ) : null}

      <p className="muted">
        WASD or arrows to walk. Shift to run. Mouse to look. Enter to talk, Escape to stop
        talking. On a phone, the left half of the screen is a stick and the right half looks
        around.
      </p>
    </div>
  )
}
