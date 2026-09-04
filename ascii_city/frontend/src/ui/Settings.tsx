import { useEffect, useState } from 'react'

import { AVATAR_FACES } from '../render/charset'
import { PLAYER_COLORS } from '../render/palette'
import type { QualityPreset, RendererStats } from '../render/renderer'

interface Props {
  stats: RendererStats | null
  nickname: string
  avatar: number
  color: number
  onClose: () => void
  onQuality: (preset: QualityPreset) => void
  onFieldOfView: (degrees: number) => void
  onRename: (nickname: string) => void
  onAvatar: (index: number) => void
}

const PRESETS: QualityPreset[] = ['auto', 'high', 'balanced', 'low']

export function Settings({
  stats,
  nickname,
  avatar,
  color,
  onClose,
  onQuality,
  onFieldOfView,
  onRename,
  onAvatar,
}: Props) {
  const [preset, setPreset] = useState<QualityPreset>('auto')
  const [fov, setFov] = useState(78)
  const [draftNick, setDraftNick] = useState(nickname)
  const swatch = PLAYER_COLORS[color % PLAYER_COLORS.length]
  const ink = `rgb(${swatch[0]},${swatch[1]},${swatch[2]})`

  const submitNick = (event: React.FormEvent) => {
    event.preventDefault()
    const trimmed = draftNick.trim()
    if (trimmed && trimmed !== nickname) onRename(trimmed)
  }

  useEffect(() => {
    setDraftNick(nickname)
  }, [nickname])

  return (
    <div className="settings">
      <header>
        <h2>settings</h2>
        <button type="button" onClick={onClose}>
          close
        </button>
      </header>

      <form className="rename-row" onSubmit={submitNick}>
        <label>
          <span>nickname</span>
          <div className="rename-input">
            <input
              value={draftNick}
              maxLength={32}
              onChange={(event) => setDraftNick(event.target.value)}
              placeholder="your name in the district"
            />
            <button type="submit" disabled={!draftNick.trim() || draftNick.trim() === nickname}>
              save
            </button>
          </div>
        </label>
      </form>

      <label>
        <span>avatar</span>
        <div className="faces">
          {AVATAR_FACES.map((face, index) => (
            <button
              key={face}
              type="button"
              className={index === avatar ? 'face active' : 'face'}
              style={index === avatar ? { color: ink, borderColor: ink } : undefined}
              onClick={() => onAvatar(index)}
              aria-label={`Avatar ${index + 1}`}
            >
              {face}
            </button>
          ))}
        </div>
      </label>

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
        WASD or arrows to walk. Ctrl to run. Space to jump. Mouse to look. T or Enter to talk,
        Escape to stop talking. Escape again for this panel. Hold Tab for the player list. 5
        steps the camera behind you. On a phone, the left half of the screen is a stick and the
        right half looks around.
      </p>
    </div>
  )
}
