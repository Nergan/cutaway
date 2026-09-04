/**
 * The recipe library, grouped by what each entry is for.
 *
 * Grouped by role rather than alphabetically because the grouping carries information the name
 * does not: whether a recipe is bound to a tile, and which. An unbound ground tile is either
 * decoration or a mistake, and this is the only place that distinction is visible.
 */

import { useMemo, useState } from 'react'

import type { Catalogue, Recipe } from './types'

export interface RecipeListProps {
  recipes: readonly Recipe[]
  selected: string | undefined
  onChoose: (key: string) => void
  bindings: Catalogue | undefined
}

export function RecipeList({ recipes, selected, onChoose, bindings }: RecipeListProps) {
  const [filter, setFilter] = useState('')

  /** Which tiles, if any, each recipe draws. Reversed from the catalogue's tile-keyed maps. */
  const usage = useMemo(() => {
    const found = new Map<string, string[]>()
    if (bindings === undefined) return found

    for (const [tile, key] of Object.entries(bindings.tileGround)) {
      const list = found.get(key) ?? []
      list.push(`ground of tile ${tile}`)
      found.set(key, list)
    }
    for (const [tile, key] of Object.entries(bindings.tileProp)) {
      const list = found.get(key) ?? []
      list.push(`prop on tile ${tile}`)
      found.set(key, list)
    }
    for (const key of bindings.decor) {
      const list = found.get(key) ?? []
      list.push('hand-placed decor')
      found.set(key, list)
    }
    return found
  }, [bindings])

  const groups = useMemo(() => {
    const needle = filter.trim().toLowerCase()
    const matching = recipes.filter(
      (recipe) =>
        needle.length === 0 ||
        recipe.key.includes(needle) ||
        recipe.label.toLowerCase().includes(needle),
    )
    return [
      { title: 'Ground', entries: matching.filter((recipe) => recipe.kind === 'ground') },
      { title: 'Props and decor', entries: matching.filter((recipe) => recipe.kind === 'prop') },
    ]
  }, [recipes, filter])

  return (
    <section className="panel atelier-list" aria-label="Recipes">
      <input
        className="atelier-filter"
        value={filter}
        placeholder="Filter…"
        aria-label="Filter recipes"
        onChange={(event) => setFilter(event.target.value)}
      />

      {groups.map((group) => (
        <div key={group.title} className="atelier-group">
          <div className="panel-title">
            {group.title} <span className="muted">({group.entries.length})</span>
          </div>
          <ul>
            {group.entries.map((recipe) => (
              <li key={recipe.key}>
                <button
                  type="button"
                  className={`atelier-entry${recipe.key === selected ? ' on' : ''}`}
                  onClick={() => onChoose(recipe.key)}
                >
                  <span className="name">{recipe.label || recipe.key}</span>
                  <span className="meta">
                    {recipe.width}×{recipe.height}
                    {recipe.frames > 1 && ` · ${recipe.frames}f`}
                  </span>
                  {usage.get(recipe.key) === undefined && (
                    <span className="unbound" title="No tile draws this recipe">
                      unused
                    </span>
                  )}
                </button>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </section>
  )
}
