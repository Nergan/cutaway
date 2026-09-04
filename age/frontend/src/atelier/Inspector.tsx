/**
 * The recipe inspector: the step list, the parameters, and the live bake.
 *
 * The preview is a debounced POST to `/api/atelier/bake`, which is the server's real baker. That
 * costs a round trip per edit, which for a slider is the wrong feel — hence the debounce — but
 * it is the only arrangement where what you see is what ships. A local TypeScript baker was
 * tried and abandoned: it drifted from the Python within a day, and a preview that disagrees
 * with the export is worse than a slow one.
 *
 * Tiles are previewed tiled 3×3 as well as alone, because seamlessness is the property that
 * matters most for ground art and is completely invisible in a single cell.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { apiBase } from '../ui/api'
import { OPS, OPS_BY_NAME, type Catalogue, type FieldSpec, type Recipe, type Step } from './types'

export interface InspectorProps {
  recipe: Recipe
  dirty: boolean
  catalogue: Catalogue | undefined
  onChange: (recipe: Recipe) => void
  onRevert: () => void
}

/** How long to wait after the last edit before re-baking. One frame of a slider drag is not one bake. */
const DEBOUNCE_MS = 220

export function Inspector({ recipe, dirty, catalogue, onChange, onRevert }: InspectorProps) {
  const [showNormals, setShowNormals] = useState(false)
  const [zoom, setZoom] = useState(4)
  const [seed, setSeed] = useState(0)
  const [selectedStep, setSelectedStep] = useState(0)

  const { url, error, baking } = useBake(recipe, seed, showNormals)

  const step = recipe.steps[selectedStep]
  const spec = step === undefined ? undefined : OPS_BY_NAME.get(step.op)

  const update = useCallback(
    (mutate: (draft: Recipe) => void) => {
      const next = structuredClone(recipe)
      mutate(next)
      onChange(next)
    },
    [recipe, onChange],
  )

  const setStepField = useCallback(
    (name: string, value: unknown) => {
      update((draft) => {
        const target = draft.steps[selectedStep]
        if (target !== undefined) target[name] = value
      })
    },
    [update, selectedStep],
  )

  return (
    <section className="panel atelier-inspector" aria-label="Inspector">
      <header className="atelier-inspector-head">
        <div>
          <strong>{recipe.label || recipe.key}</strong>
          <span className="muted">
            {' '}
            · {recipe.kind} · {recipe.width}×{recipe.height} · {recipe.frames} frame
            {recipe.frames === 1 ? '' : 's'}
          </span>
        </div>
        <div className="atelier-inspector-actions">
          {dirty && <span className="pill warn">unsaved</span>}
          <button type="button" disabled={!dirty} onClick={onRevert}>
            Revert
          </button>
          <button type="button" onClick={() => void download(recipe, seed, showNormals)}>
            Export PNG
          </button>
          <button type="button" onClick={() => void copyJson(recipe)}>
            Copy JSON
          </button>
        </div>
      </header>

      <div className="atelier-preview">
        <div className="atelier-preview-strip">
          {error !== undefined ? (
            <p className="atelier-bake-error">{error}</p>
          ) : url === undefined ? (
            <p className="muted">Baking…</p>
          ) : (
            <img
              src={url}
              alt={`${recipe.key} frames`}
              style={{
                width: recipe.width * recipe.frames * zoom,
                height: recipe.height * zoom,
                imageRendering: 'pixelated',
                opacity: baking ? 0.6 : 1,
              }}
            />
          )}
        </div>

        {recipe.kind === 'ground' && url !== undefined && error === undefined && (
          <div className="atelier-preview-tiled">
            <div className="panel-title">Tiled</div>
            <div
              style={{
                width: recipe.width * 3 * 2,
                height: recipe.height * 3 * 2,
                // The strip holds every frame side by side, so tiling it directly would repeat
                // the whole animation. Scaled so one background tile is one frame.
                backgroundImage: `url("${url}")`,
                backgroundSize: `${recipe.width * recipe.frames * 2}px ${recipe.height * 2}px`,
                imageRendering: 'pixelated',
              }}
            />
            <p className="muted" style={{ fontSize: '8pt' }}>
              A visible grid here means the tile is not seamless.
            </p>
          </div>
        )}
      </div>

      <div className="atelier-preview-controls">
        <label className="atelier-check">
          <input
            type="checkbox"
            checked={showNormals}
            onChange={(event) => setShowNormals(event.target.checked)}
          />
          Normal map
        </label>
        <div className="atelier-field">
          <span>Zoom</span>
          <input
            type="range"
            min={1}
            max={8}
            step={1}
            value={zoom}
            onChange={(event) => setZoom(Number(event.target.value))}
          />
          <output>{zoom}×</output>
        </div>
        <div className="atelier-field">
          <span>Seed</span>
          <input
            type="number"
            value={seed}
            style={{ width: 72 }}
            onChange={(event) => setSeed(Number(event.target.value) | 0)}
          />
          <button type="button" onClick={() => setSeed((current) => current + 1)}>
            Next
          </button>
        </div>
        <div className="atelier-field">
          <span>Frames</span>
          <input
            type="number"
            min={1}
            max={8}
            value={recipe.frames}
            style={{ width: 56 }}
            onChange={(event) =>
              update((draft) => {
                draft.frames = Math.max(1, Math.min(8, Number(event.target.value) | 0))
              })
            }
          />
        </div>
      </div>

      <div className="atelier-steps">
        <div className="atelier-step-list">
          <div className="panel-title">Steps</div>
          <ol>
            {recipe.steps.map((entry, index) => (
              <li key={index}>
                <button
                  type="button"
                  className={`atelier-step${index === selectedStep ? ' on' : ''}`}
                  onClick={() => setSelectedStep(index)}
                >
                  <span className="op">{OPS_BY_NAME.get(entry.op)?.label ?? entry.op}</span>
                  {typeof entry.ramp === 'string' && (
                    <span
                      className="swatch"
                      style={{ background: swatch(catalogue, entry) }}
                      title={`${entry.ramp} shade ${entry.level ?? 2}`}
                    />
                  )}
                </button>
              </li>
            ))}
          </ol>

          <div className="atelier-step-buttons">
            <select
              value=""
              aria-label="Add a step"
              onChange={(event) => {
                const chosen = event.target.value
                if (chosen === '') return
                update((draft) => {
                  // Inserted after the selection rather than appended: order is what makes a
                  // recipe work — an outline before a fill is painted over by it — and adding a
                  // step at the end when you meant to add it here is the commonest mistake.
                  draft.steps.splice(selectedStep + 1, 0, { op: chosen })
                })
                setSelectedStep((current) => current + 1)
              }}
            >
              <option value="">Add step…</option>
              {OPS.map((entry) => (
                <option key={entry.op} value={entry.op}>
                  {entry.label}
                </option>
              ))}
            </select>
            <button
              type="button"
              disabled={selectedStep <= 0}
              title="Move earlier: drawn under what follows"
              onClick={() =>
                update((draft) => {
                  const [moved] = draft.steps.splice(selectedStep, 1)
                  draft.steps.splice(selectedStep - 1, 0, moved)
                  setSelectedStep(selectedStep - 1)
                })
              }
            >
              ↑
            </button>
            <button
              type="button"
              disabled={selectedStep >= recipe.steps.length - 1}
              title="Move later: drawn over what precedes"
              onClick={() =>
                update((draft) => {
                  const [moved] = draft.steps.splice(selectedStep, 1)
                  draft.steps.splice(selectedStep + 1, 0, moved)
                  setSelectedStep(selectedStep + 1)
                })
              }
            >
              ↓
            </button>
            <button
              type="button"
              disabled={recipe.steps.length <= 1}
              onClick={() =>
                update((draft) => {
                  draft.steps.splice(selectedStep, 1)
                  setSelectedStep(Math.max(0, selectedStep - 1))
                })
              }
            >
              Remove
            </button>
          </div>
        </div>

        <div className="atelier-step-fields">
          <div className="panel-title">
            {spec?.label ?? step?.op ?? 'No step'}
            {spec === undefined && step !== undefined && (
              <span className="muted"> · no editor for this operation</span>
            )}
          </div>
          {spec !== undefined && <p className="muted atelier-hint">{spec.hint}</p>}

          {spec?.fields.map((field) => (
            <Field
              key={field.name}
              field={field}
              value={step?.[field.name]}
              catalogue={catalogue}
              onChange={(value) => setStepField(field.name, value)}
            />
          ))}

          {spec !== undefined && spec.fields.length === 0 && (
            <p className="muted">This operation takes no parameters.</p>
          )}
        </div>
      </div>
    </section>
  )
}

/** One parameter control, chosen by the field's declared kind. */
function Field({
  field,
  value,
  catalogue,
  onChange,
}: {
  field: FieldSpec
  value: unknown
  catalogue: Catalogue | undefined
  onChange: (value: unknown) => void
}) {
  if (field.kind === 'ramp') {
    const names = Object.keys(catalogue?.ramps ?? {})
    return (
      <div className="atelier-field">
        <span>{field.label}</span>
        <select value={String(value ?? '')} onChange={(event) => onChange(event.target.value)}>
          <option value="">(default)</option>
          {names.map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
        </select>
      </div>
    )
  }

  if (field.kind === 'level') {
    const steps = catalogue?.rampSteps ?? 5
    return (
      <div className="atelier-field">
        <span>{field.label}</span>
        <input
          type="range"
          min={0}
          max={steps - 1}
          step={1}
          value={Number(value ?? 2)}
          onChange={(event) => onChange(Number(event.target.value))}
        />
        <output>{Number(value ?? 2)}</output>
      </div>
    )
  }

  if (field.kind === 'boolean') {
    return (
      <label className="atelier-check">
        <input
          type="checkbox"
          checked={Boolean(value)}
          onChange={(event) => onChange(event.target.checked)}
        />
        {field.label}
      </label>
    )
  }

  if (field.kind === 'rect') {
    const rect = Array.isArray(value) ? (value as number[]) : [0, 0, 32, 32]
    const labels = ['left', 'top', 'right', 'bottom']
    return (
      <div className="atelier-field atelier-rect">
        <span>{field.label}</span>
        {rect.map((component, index) => (
          <input
            key={index}
            type="number"
            value={component}
            aria-label={labels[index]}
            title={labels[index]}
            onChange={(event) => {
              const next = [...rect]
              next[index] = Number(event.target.value) | 0
              onChange(next)
            }}
          />
        ))}
      </div>
    )
  }

  if (field.kind === 'seed') {
    return (
      <div className="atelier-field">
        <span>{field.label}</span>
        <input
          type="number"
          value={Number(value ?? 0)}
          onChange={(event) => onChange(Number(event.target.value) | 0)}
        />
        <button type="button" onClick={() => onChange(Math.floor(Math.random() * 4096))}>
          Roll
        </button>
      </div>
    )
  }

  return (
    <div className="atelier-field">
      <span>{field.label}</span>
      <input
        type="range"
        min={field.min ?? 0}
        max={field.max ?? 100}
        step={field.step ?? 1}
        value={Number(value ?? field.min ?? 0)}
        onChange={(event) => onChange(Number(event.target.value))}
      />
      <output>{Number(value ?? field.min ?? 0)}</output>
    </div>
  )
}

/**
 * Bake a recipe, debounced, and hand back an object URL.
 *
 * Object URLs are revoked when they are replaced. Without that, dragging a slider for a minute
 * leaks a few hundred blobs, which the browser keeps alive because nothing told it not to.
 */
function useBake(
  recipe: Recipe,
  seed: number,
  normals: boolean,
): { url: string | undefined; error: string | undefined; baking: boolean } {
  const [url, setUrl] = useState<string | undefined>(undefined)
  const [error, setError] = useState<string | undefined>(undefined)
  const [baking, setBaking] = useState(false)
  const current = useRef<string | undefined>(undefined)

  // Serialised so the effect re-runs on a value change rather than on every render: `recipe` is
  // a fresh object each edit, and depending on it directly would bake on unrelated re-renders.
  const payload = useMemo(() => JSON.stringify({ ...recipe, seed, normals }), [recipe, seed, normals])

  useEffect(() => {
    let cancelled = false
    setBaking(true)

    const timer = window.setTimeout(() => {
      fetch(`${apiBase()}/atelier/bake`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: payload,
      })
        .then(async (response) => {
          if (!response.ok) {
            // The server's message is the useful one — it names the operation that failed —
            // so it is surfaced verbatim rather than replaced with "bake failed".
            const detail = await response.json().catch(() => undefined)
            throw new Error(detail?.detail ?? `HTTP ${response.status}`)
          }
          return response.blob()
        })
        .then((blob) => {
          if (cancelled) return
          const next = URL.createObjectURL(blob)
          if (current.current !== undefined) URL.revokeObjectURL(current.current)
          current.current = next
          setUrl(next)
          setError(undefined)
        })
        .catch((cause: unknown) => {
          if (!cancelled) setError(cause instanceof Error ? cause.message : 'The bake failed.')
        })
        .finally(() => {
          if (!cancelled) setBaking(false)
        })
    }, DEBOUNCE_MS)

    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [payload])

  useEffect(
    () => () => {
      if (current.current !== undefined) URL.revokeObjectURL(current.current)
    },
    [],
  )

  return { url, error, baking }
}

/** The swatch shown next to a step in the list: its ramp at its shade. */
function swatch(catalogue: Catalogue | undefined, step: Step): string {
  const ramp = catalogue?.ramps[String(step.ramp)]
  if (ramp === undefined) return 'transparent'
  const level = Math.max(0, Math.min(ramp.length - 1, Number(step.level ?? 2)))
  return ramp[level]
}

async function download(recipe: Recipe, seed: number, normals: boolean): Promise<void> {
  const response = await fetch(`${apiBase()}/atelier/bake`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...recipe, seed, normals }),
  })
  if (!response.ok) return

  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `${recipe.key}${normals ? '-normal' : ''}.png`
  link.click()
  URL.revokeObjectURL(url)
}

/**
 * Copy the recipe as JSON.
 *
 * The export path, deliberately. The editor does not write to the server: a recipe is source
 * code, it lives in `age/atelier/recipes.py`, and it goes through review like everything else.
 * An editor that could save straight into the running world would be a way to change the art
 * without anyone seeing the diff.
 */
async function copyJson(recipe: Recipe): Promise<void> {
  const text = JSON.stringify(recipe, null, 2)
  try {
    await navigator.clipboard.writeText(text)
  } catch {
    // Clipboard access needs a secure context and a user gesture, and this is called from one,
    // but a denied permission is still possible. A prompt is a poor fallback that works.
    window.prompt('Copy this recipe:', text)
  }
}
