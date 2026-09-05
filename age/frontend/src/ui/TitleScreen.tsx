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

/**
 * How many distinct values each appearance byte has, if the server has not said yet.
 *
 * These used to be the only source, and they were wrong: five stops for hair and five for
 * skin against the baker's twelve and three. A slider that overshoots its table repeats
 * looks and one that undershoots hides them, and neither is visible without counting
 * ramps in Python. The server now publishes the real counts with the world; this is the
 * shape to render before that arrives.
 */
const LOOK_RANGES = { body: 3, hair: 12, palette: 3, outfit: 6, accent: 4 } as const

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

type LookPart = keyof typeof LOOK_RANGES

function randomAppearance(ranges: Record<LookPart, number> = LOOK_RANGES): Appearance {
  return {
    body: Math.floor(Math.random() * ranges.body),
    hair: Math.floor(Math.random() * ranges.hair),
    palette: Math.floor(Math.random() * ranges.palette),
    outfit: Math.floor(Math.random() * ranges.outfit),
    accent: Math.floor(Math.random() * ranges.accent),
  }
}

export function TitleScreen({ world, error, busy, onEnter }: TitleScreenProps) {
  const [name, setName] = useState(() => SUGGESTIONS[Math.floor(Math.random() * SUGGESTIONS.length)])
  const [classId, setClassId] = useState(0)
  const [appearance, setAppearance] = useState<Appearance>(randomAppearance)

  // Only the four base classes. The other ten are reached by choosing a second half at
  // level-up (GDD 6.3), and offering them here would hand out the reward for free.
  const classes = useMemo(
    () => (world?.classes ?? []).filter((entry) => entry.isBase),
    [world?.classes],
  )
  const chosen = useMemo(
    () => classes.find((entry) => entry.classId === classId) ?? classes[0],
    [classes, classId],
  )
  const ranges = useMemo(() => {
    const published = world?.appearanceRanges
    if (published === undefined) return LOOK_RANGES as Record<LookPart, number>
    const merged = { ...LOOK_RANGES } as Record<LookPart, number>
    for (const part of Object.keys(merged) as LookPart[]) {
      // Guard the count rather than trusting it: a zero would give the slider a negative
      // maximum, and this is the screen a visitor sees first.
      if (Number.isInteger(published[part]) && published[part] > 0) merged[part] = published[part]
    }
    return merged
  }, [world?.appearanceRanges])

  // One idle frame, not the walk strip. Cycling four frames of a just-fetched PNG
  // is what made the box strobe: each slider tick swapped the URL, the old image
  // vanished, and the walk cycle then jumped across empty frames until the new
  // strip decoded. Standing still is less charming and the only thing that does
  // not blink on a slow host.
  const previewUrl = useMemo(() => {
    const query = new URLSearchParams({
      body: String(appearance.body),
      hair: String(appearance.hair),
      palette: String(appearance.palette),
      outfit: String(appearance.outfit),
      accent: String(appearance.accent),
      facing: '0',
      pose: '0',
    })
    return `${apiBase()}/atelier/character.png?${query.toString()}`
  }, [appearance])

  // Keep showing the last decoded sprite until the next one is ready. Assigning
  // a new URL to the box itself empties it for the length of the request.
  const [loadedUrl, setLoadedUrl] = useState<string>()
  useEffect(() => {
    let cancelled = false
    const image = new Image()
    image.onload = () => {
      if (!cancelled) setLoadedUrl(previewUrl)
    }
    image.src = previewUrl
    return () => {
      cancelled = true
    }
  }, [previewUrl])

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
          <p className="muted" style={{ fontSize: '8.5pt', marginTop: 4 }}>
            At your first level-up you choose a second discipline. The pair names what you
            become — a Warrior who studies healing is a Paladin; one who doubles down is a
            Warmaster.
          </p>
        </div>

        <div className="field">
          <label>Appearance</label>
          <div className="look-row">
            <div
              className="look-preview"
              role="img"
              aria-label="Character preview"
              style={{
                backgroundImage: loadedUrl === undefined ? undefined : `url("${loadedUrl}")`,
                // Idle is two frames wide; show the first and leave the rest off-screen.
                backgroundSize: '200% 100%',
                backgroundPosition: '0 0',
                backgroundRepeat: 'no-repeat',
                imageRendering: 'pixelated',
              }}
            />
            <div className="look-sliders">
              {(Object.keys(LOOK_RANGES) as LookPart[]).map((part) => (
                <LookSlider
                  key={part}
                  label={LOOK_LABELS[part]}
                  value={appearance[part]}
                  max={ranges[part] - 1}
                  onChange={(value) => setAppearance((current) => ({ ...current, [part]: value }))}
                />
              ))}
            </div>
          </div>
          <button
            type="button"
            style={{ marginTop: 10, alignSelf: 'flex-start' }}
            onClick={() => setAppearance(randomAppearance(ranges))}
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
