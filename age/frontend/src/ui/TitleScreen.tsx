/**
 * The title screen: name, class, and look.
 *
 * The appearance preview is a live bake from the server, which is worth doing rather than
 * showing a generic silhouette: the five appearance bytes are the only part of a character a
 * player controls, and seeing the result is the whole point of choosing.
 */

import { useEffect, useMemo, useState } from 'react'

import { MAX_NAME_LENGTH } from '../domain/constants'
import type { Appearance } from '../net/wire'
import { apiBase, type ClassInfo, type WorldInfo } from './api'

export interface Profile {
  name: string
  classId: number
  appearance: Appearance
}

export interface TitleScreenProps {
  world: WorldInfo | undefined
  error: string | undefined
  busy: boolean
  onEnter: (profile: Profile) => void
}

/** How many distinct values each appearance byte has, matching the Atelier's ramp tables. */
const LOOK_RANGES = { body: 3, hair: 5, palette: 5, outfit: 6, accent: 6 } as const

const LOOK_LABELS: Record<keyof typeof LOOK_RANGES, string> = {
  body: 'Build',
  hair: 'Hair',
  palette: 'Skin',
  outfit: 'Outfit',
  accent: 'Accent',
}

/** A name the player did not pick, so entering the world never blocks on a text field. */
const SUGGESTIONS = [
  'Wren',
  'Ashvane',
  'Corvid',
  'Marrow',
  'Kestrel',
  'Hollis',
  'Bramble',
  'Vesper',
]

function randomAppearance(): Appearance {
  return {
    body: Math.floor(Math.random() * LOOK_RANGES.body),
    hair: Math.floor(Math.random() * LOOK_RANGES.hair),
    palette: Math.floor(Math.random() * LOOK_RANGES.palette),
    outfit: Math.floor(Math.random() * LOOK_RANGES.outfit),
    accent: Math.floor(Math.random() * LOOK_RANGES.accent),
  }
}

export function TitleScreen({ world, error, busy, onEnter }: TitleScreenProps) {
  const [name, setName] = useState(() => SUGGESTIONS[Math.floor(Math.random() * SUGGESTIONS.length)])
  const [classId, setClassId] = useState(0)
  const [appearance, setAppearance] = useState<Appearance>(randomAppearance)

  const classes = world?.classes ?? []
  const chosen = useMemo(
    () => classes.find((entry) => entry.classId === classId) ?? classes[0],
    [classes, classId],
  )

  // The preview is the walk strip: standing still tells you less about a sprite than moving.
  const previewUrl = useMemo(() => {
    const query = new URLSearchParams({
      body: String(appearance.body),
      hair: String(appearance.hair),
      palette: String(appearance.palette),
      outfit: String(appearance.outfit),
      accent: String(appearance.accent),
      facing: '0',
      pose: '1',
    })
    return `${apiBase()}/atelier/character.png?${query.toString()}`
  }, [appearance])

  // Step through the strip so the preview walks on the spot.
  const [previewFrame, setPreviewFrame] = useState(0)
  useEffect(() => {
    const timer = window.setInterval(() => setPreviewFrame((frame) => (frame + 1) % 4), 140)
    return () => window.clearInterval(timer)
  }, [])

  const trimmed = name.trim()
  const ready = world !== undefined && trimmed.length > 0 && !busy

  return (
    <div className="title">
      <div className="panel title-card">
        <header className="title-brand">
          <h1>AGE</h1>
          <p>A living world that folds and unfolds around the people in it.</p>
        </header>

        <div className="field">
          <label htmlFor="character-name">Name</label>
          <input
            id="character-name"
            value={name}
            maxLength={MAX_NAME_LENGTH}
            spellCheck={false}
            autoComplete="off"
            onChange={(event) => setName(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && ready) onEnter({ name: trimmed, classId, appearance })
            }}
          />
        </div>

        <div className="field">
          <label>Class</label>
          <div className="class-grid" role="radiogroup" aria-label="Class">
            {classes.map((entry) => (
              <ClassOption
                key={entry.classId}
                entry={entry}
                chosen={entry.classId === classId}
                onChoose={() => setClassId(entry.classId)}
              />
            ))}
            {classes.length === 0 && <span className="muted">Waiting for the server…</span>}
          </div>
          {chosen !== undefined && (
            <p className="muted" style={{ fontSize: '9pt', marginTop: 6 }}>
              {chosen.fantasy}
            </p>
          )}
        </div>

        <div className="field">
          <label>Appearance</label>
          <div className="look-row">
            <div
              className="look-preview"
              role="img"
              aria-label="Character preview"
              style={{
                backgroundImage: `url("${previewUrl}")`,
                // The strip is four frames wide; showing one means scaling it to four times
                // the box and sliding it. Cheaper and sharper than four separate requests.
                backgroundSize: '400% 100%',
                backgroundPosition: `${-previewFrame * 100}% 0`,
                backgroundRepeat: 'no-repeat',
                imageRendering: 'pixelated',
              }}
            />
            <div className="look-sliders">
              {(Object.keys(LOOK_RANGES) as Array<keyof typeof LOOK_RANGES>).map((part) => (
                <LookSlider
                  key={part}
                  label={LOOK_LABELS[part]}
                  value={appearance[part]}
                  max={LOOK_RANGES[part] - 1}
                  onChange={(value) => setAppearance((current) => ({ ...current, [part]: value }))}
                />
              ))}
            </div>
          </div>
          <button
            type="button"
            style={{ marginTop: 10, alignSelf: 'flex-start' }}
            onClick={() => setAppearance(randomAppearance())}
          >
            Randomise
          </button>
        </div>

        <div className="title-actions">
          <button
            type="button"
            className="primary"
            disabled={!ready}
            onClick={() => onEnter({ name: trimmed, classId, appearance })}
          >
            {busy ? 'Entering…' : 'Enter the world'}
          </button>
          {world !== undefined && (
            <span className="muted" style={{ fontSize: '9pt' }}>
              {world.population} / {world.maxClients} online · tier {world.currentTier}
            </span>
          )}
          {error !== undefined && <span style={{ color: 'var(--danger)', fontSize: '9pt' }}>{error}</span>}
        </div>

        <footer className="title-note">
          <kbd>WASD</kbd> move · <kbd>Shift</kbd> run · <kbd>1</kbd>–<kbd>3</kbd> abilities ·{' '}
          <kbd>F</kbd> harvest · <kbd>B</kbd> build · <kbd>Enter</kbd> chat · <kbd>Tab</kbd>{' '}
          diagnostics
        </footer>
      </div>
    </div>
  )
}

function ClassOption({
  entry,
  chosen,
  onChoose,
}: {
  entry: ClassInfo
  chosen: boolean
  onChoose: () => void
}) {
  const roles = ['Tank', 'Healer', 'Damage', 'Support']
  return (
    <button
      type="button"
      role="radio"
      aria-checked={chosen}
      className={`class-option${chosen ? ' chosen' : ''}`}
      onClick={onChoose}
    >
      <strong>{entry.name}</strong>
      <small>
        {roles[entry.role] ?? 'Unknown'} · {entry.abilities.length} abilities
      </small>
    </button>
  )
}

function LookSlider({
  label,
  value,
  max,
  onChange,
}: {
  label: string
  value: number
  max: number
  onChange: (value: number) => void
}) {
  return (
    <>
      <span>{label}</span>
      <input
        type="range"
        min={0}
        max={max}
        step={1}
        value={value}
        aria-label={label}
        onChange={(event) => onChange(Number(event.target.value))}
      />
    </>
  )
}
