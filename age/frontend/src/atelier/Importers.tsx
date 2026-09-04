/**
 * Import from LDtk and Aseprite.
 *
 * The reason these exist: the procedural recipes are good at texture and terrible at intent. A
 * seamless gravel tile is a five-line recipe; a town square that feels like somewhere is not
 * something you describe with scatter densities. So the pipeline has two mouths — recipes for
 * material, and real editors for layout and hand-drawn frames.
 *
 * Both importers *convert and report*. Nothing here writes into the live world. An upload that
 * applied itself would be a way to overwrite whatever players had built, from a file, with no
 * review; the author reads the conversion and applies it deliberately.
 */

import { useCallback, useState } from 'react'

import { apiBase } from '../ui/api'

interface LdtkLevel {
  identifier: string
  chunks: Array<{ key: string; tiles: number }>
  props: Array<{ key: string; x: number; y: number }>
}

interface AsepriteSprite {
  name: string
  width: number
  height: number
  frames: number
  tags: Array<{ name: string; first: number; last: number; direction: string }>
}

type Result =
  | { kind: 'ldtk'; levels: LdtkLevel[] }
  | { kind: 'aseprite'; sprites: AsepriteSprite[] }
  | { kind: 'error'; message: string }

export function Importers() {
  const [result, setResult] = useState<Result | undefined>(undefined)
  const [busy, setBusy] = useState(false)

  const upload = useCallback(async (file: File, endpoint: 'ldtk' | 'aseprite') => {
    setBusy(true)
    setResult(undefined)
    try {
      const text = await file.text()
      const response = await fetch(`${apiBase()}/atelier/import/${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: text,
      })

      const payload = (await response.json()) as Record<string, unknown>
      if (!response.ok) {
        setResult({
          kind: 'error',
          message: String(payload.detail ?? `The server refused the file (HTTP ${response.status}).`),
        })
        return
      }

      if (endpoint === 'ldtk') {
        setResult({ kind: 'ldtk', levels: (payload.levels ?? []) as LdtkLevel[] })
      } else {
        setResult({ kind: 'aseprite', sprites: (payload.sprites ?? []) as AsepriteSprite[] })
      }
    } catch (cause) {
      setResult({
        kind: 'error',
        message:
          cause instanceof SyntaxError
            ? 'That file is not JSON. LDtk projects need "Save as separate JSON" off, and Aseprite needs the json-array export.'
            : cause instanceof Error
              ? cause.message
              : 'The import failed.',
      })
    } finally {
      setBusy(false)
    }
  }, [])

  return (
    <div className="atelier-body">
      <section className="panel atelier-import">
        <div className="panel-title">LDtk level</div>
        <p className="muted atelier-hint">
          A <code>.ldtk</code> project. Each level becomes a set of chunk overlays plus a list of
          prop placements, addressed by the same chunk keys the server uses. Layers named for a
          tile kind map onto it; anything else is reported and skipped.
        </p>
        <FilePicker accept=".ldtk,application/json" busy={busy} onPick={(file) => void upload(file, 'ldtk')} />

        <div className="panel-title" style={{ marginTop: 20 }}>
          Aseprite sprite
        </div>
        <p className="muted atelier-hint">
          An Aseprite <code>json-array</code> export. Frames and tags come across, so an
          animation authored by hand can be indexed the same way a baked one is. Export the sheet
          alongside it and drop the PNG in the CDN.
        </p>
        <FilePicker
          accept=".json,application/json"
          busy={busy}
          onPick={(file) => void upload(file, 'aseprite')}
        />
      </section>

      <section className="panel atelier-import-result">
        <div className="panel-title">Conversion</div>
        {result === undefined && (
          <p className="muted">
            Nothing imported yet. Results are shown here rather than applied — this tool reads
            files, it does not write to the world.
          </p>
        )}

        {result?.kind === 'error' && <p className="atelier-bake-error">{result.message}</p>}

        {result?.kind === 'ldtk' && (
          <>
            <p className="muted">
              {result.levels.length} level{result.levels.length === 1 ? '' : 's'}.
            </p>
            {result.levels.map((level) => (
              <details key={level.identifier} open={result.levels.length === 1}>
                <summary>
                  {level.identifier} — {level.chunks.length} chunks, {level.props.length} props
                </summary>
                <ul className="atelier-result-list">
                  {level.chunks.map((chunk) => (
                    <li key={chunk.key}>
                      <code>{chunk.key}</code> · {chunk.tiles} tiles
                    </li>
                  ))}
                </ul>
              </details>
            ))}
          </>
        )}

        {result?.kind === 'aseprite' && (
          <>
            <p className="muted">
              {result.sprites.length} sprite{result.sprites.length === 1 ? '' : 's'}.
            </p>
            <ul className="atelier-result-list">
              {result.sprites.map((sprite) => (
                <li key={sprite.name}>
                  <code>{sprite.name}</code> · {sprite.width}×{sprite.height} · {sprite.frames}{' '}
                  frames
                  {sprite.tags.length > 0 && (
                    <> · tags: {sprite.tags.map((tag) => tag.name).join(', ')}</>
                  )}
                </li>
              ))}
            </ul>
          </>
        )}
      </section>
    </div>
  )
}

function FilePicker({
  accept,
  busy,
  onPick,
}: {
  accept: string
  busy: boolean
  onPick: (file: File) => void
}) {
  const [dragging, setDragging] = useState(false)

  return (
    <label
      className={`atelier-drop${dragging ? ' over' : ''}`}
      onDragOver={(event) => {
        event.preventDefault()
        setDragging(true)
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(event) => {
        event.preventDefault()
        setDragging(false)
        const file = event.dataTransfer.files[0]
        if (file !== undefined) onPick(file)
      }}
    >
      <input
        type="file"
        accept={accept}
        disabled={busy}
        onChange={(event) => {
          const file = event.target.files?.[0]
          if (file !== undefined) onPick(file)
          // Cleared so choosing the same file twice fires again, which matters when the file
          // has changed on disk between attempts.
          event.target.value = ''
        }}
      />
      <span>{busy ? 'Reading…' : 'Choose a file, or drop one here'}</span>
    </label>
  )
}
