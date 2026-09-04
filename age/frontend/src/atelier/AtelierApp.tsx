/**
 * The Atelier: the art tool, in the browser, at `/age/atelier`.
 *
 * The premise is that the art is *described* rather than drawn. A tile is a short list of
 * operations — fill this ramp, scatter that one, dither between two levels, ring the silhouette
 * — and baking that list produces the pixels. That is a real constraint on what the art can look
 * like, and it buys three things nothing else does:
 *
 *  - A tile is a few hundred bytes of JSON, so a whole tileset is diffable and reviewable.
 *  - Changing a palette ramp re-tints every sprite that uses it, consistently, at once.
 *  - The height channel comes out of the same operations, so the normal map is free rather than
 *    being a second thing to author and keep in step.
 *
 * The editor is a thin front end over the server's baker. Every preview here is the real bake,
 * fetched from `/api/atelier/bake` — not a reimplementation. There was a version of this that
 * baked locally in TypeScript for latency, and it drifted from the Python within a day: the
 * preview and the export disagreed, which is the one failure an art tool must not have.
 */

import { useCallback, useEffect, useMemo, useState } from 'react'

import { apiBase } from '../ui/api'
import { Inspector } from './Inspector'
import { RecipeList } from './RecipeList'
import { Importers } from './Importers'
import type { Catalogue, Recipe } from './types'

type Tab = 'recipes' | 'import' | 'atlas'

export function AtelierApp() {
  const [catalogue, setCatalogue] = useState<Catalogue | undefined>(undefined)
  const [error, setError] = useState<string | undefined>(undefined)
  const [selected, setSelected] = useState<string | undefined>(undefined)
  const [tab, setTab] = useState<Tab>('recipes')

  /** The recipe being edited, which starts as a copy of the catalogue's and diverges. */
  const [draft, setDraft] = useState<Recipe | undefined>(undefined)

  useEffect(() => {
    let cancelled = false

    fetch(`${apiBase()}/atelier/catalogue`)
      .then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`)
        return response.json() as Promise<Catalogue>
      })
      .then((loaded) => {
        if (cancelled) return
        setCatalogue(loaded)
        const first = loaded.recipes[0]
        if (first !== undefined) {
          setSelected(first.key)
          setDraft(structuredClone(first))
        }
      })
      .catch((cause: unknown) => {
        if (!cancelled) {
          setError(
            cause instanceof Error
              ? `The recipe library did not load: ${cause.message}`
              : 'The recipe library did not load.',
          )
        }
      })

    return () => {
      cancelled = true
    }
  }, [])

  const choose = useCallback(
    (key: string) => {
      const found = catalogue?.recipes.find((recipe) => recipe.key === key)
      if (found === undefined) return
      setSelected(key)
      // Cloned so edits do not mutate the catalogue: the list is what "unmodified" means, and
      // the Revert button needs something to revert to.
      setDraft(structuredClone(found))
    },
    [catalogue],
  )

  const original = useMemo(
    () => catalogue?.recipes.find((recipe) => recipe.key === selected),
    [catalogue, selected],
  )

  const dirty = useMemo(
    () =>
      draft !== undefined &&
      original !== undefined &&
      JSON.stringify(draft) !== JSON.stringify(original),
    [draft, original],
  )

  return (
    <div className="atelier">
      <header className="atelier-bar">
        <div className="atelier-brand">
          <strong>Atelier</strong>
          <span className="muted">Age · procedural pixel art</span>
        </div>
        <nav className="atelier-tabs">
          <button
            type="button"
            className={tab === 'recipes' ? 'on' : ''}
            onClick={() => setTab('recipes')}
          >
            Recipes
          </button>
          <button
            type="button"
            className={tab === 'atlas' ? 'on' : ''}
            onClick={() => setTab('atlas')}
          >
            Atlas
          </button>
          <button
            type="button"
            className={tab === 'import' ? 'on' : ''}
            onClick={() => setTab('import')}
          >
            Import
          </button>
        </nav>
        <a className="atelier-exit" href="../">
          Back to the world
        </a>
      </header>

      {error !== undefined && (
        <div className="panel banner error" role="alert" style={{ position: 'static', margin: 12 }}>
          {error}
        </div>
      )}

      {tab === 'recipes' && (
        <div className="atelier-body">
          <RecipeList
            recipes={catalogue?.recipes ?? []}
            selected={selected}
            onChoose={choose}
            bindings={catalogue}
          />
          {draft !== undefined ? (
            <Inspector
              recipe={draft}
              dirty={dirty}
              catalogue={catalogue}
              onChange={setDraft}
              onRevert={() => original !== undefined && setDraft(structuredClone(original))}
            />
          ) : (
            <section className="panel atelier-empty">
              <p className="muted">
                {catalogue === undefined ? 'Loading the library…' : 'Pick a recipe to edit it.'}
              </p>
            </section>
          )}
        </div>
      )}

      {tab === 'atlas' && <AtlasView />}
      {tab === 'import' && <Importers />}
    </div>
  )
}

/**
 * The packed atlas, both pages, as the game receives them.
 *
 * Worth a tab of its own because packing problems are invisible in a per-recipe preview: a
 * sprite that overflows its cell, or a normal map that does not line up with its colour twin,
 * only shows here.
 */
function AtlasView() {
  const [showNormals, setShowNormals] = useState(false)
  const [zoom, setZoom] = useState(1)
  const [cacheBust] = useState(() => Date.now())

  const source = `${apiBase()}/atelier/${showNormals ? 'atlas-normal.png' : 'atlas.png'}?t=${cacheBust}`

  return (
    <div className="atelier-body">
      <section className="panel atelier-atlas-controls">
        <div className="panel-title">Atlas</div>
        <label className="atelier-check">
          <input
            type="checkbox"
            checked={showNormals}
            onChange={(event) => setShowNormals(event.target.checked)}
          />
          Show normal map
        </label>
        <div className="atelier-field">
          <span>Zoom</span>
          <input
            type="range"
            min={1}
            max={4}
            step={1}
            value={zoom}
            onChange={(event) => setZoom(Number(event.target.value))}
          />
          <output>{zoom}×</output>
        </div>
        <p className="muted" style={{ fontSize: '8pt', marginTop: 8 }}>
          Both pages use the same packing, so a frame's rectangle addresses colour and normals
          alike. If a sprite is lit wrongly in game, compare the two here first.
        </p>
        <a className="atelier-link" href={source} download>
          Download this page
        </a>
      </section>

      <section className="panel atelier-atlas-view">
        <img
          src={source}
          alt={showNormals ? 'Packed normal-map page' : 'Packed colour page'}
          style={{ width: 1024 * zoom, imageRendering: 'pixelated' }}
        />
      </section>
    </div>
  )
}
