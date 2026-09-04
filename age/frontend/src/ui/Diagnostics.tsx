/**
 * The diagnostics overlay, on Tab.
 *
 * Not a debug leftover. Almost everything interesting in this project is invisible when it
 * works — prediction only shows up as a correction, chunk streaming only as a stall, the
 * accordion only as a lane appearing — and the alternative to a readout is a console session.
 */

import type { SceneStats } from '../render/scene'

export interface DiagnosticsProps {
  scene: SceneStats
  chunks: { loaded: number; active: number; overlaid: number; pending: number }
  /** Predictor state: how many inputs are unacknowledged and how far off the last one was. */
  pendingInputs: number
  correctionTiles: number
  latencyMs: number
  clockOffset: number
  topologyVersion: number
  entities: number
  position: { x: number; y: number }
}

export function Diagnostics({
  scene,
  chunks,
  pendingInputs,
  correctionTiles,
  latencyMs,
  clockOffset,
  topologyVersion,
  entities,
  position,
}: DiagnosticsProps) {
  return (
    <aside className="panel diagnostics" aria-label="Diagnostics">
      <div>
        <b>fps</b> {scene.fps.toFixed(0)}
      </div>
      <div>
        <b>at</b> {position.x.toFixed(1)}, {position.y.toFixed(1)}
      </div>
      <div>
        <b>draw</b> {scene.chunks} chunks · {scene.sprites} sprites · {scene.lights} lights
      </div>
      <div>
        <b>chunks</b> {chunks.loaded} loaded / {chunks.active} active
      </div>
      <div>
        <b>edits</b> {chunks.overlaid} tiles · {chunks.pending} deferred
      </div>
      <div>
        <b>net</b> {Math.round(latencyMs)} ms · offset {clockOffset.toFixed(3)}s
      </div>
      <div>
        {/* A correction that stays visibly non-zero means the client and server disagree about
            movement, which is the single most useful number on this panel. */}
        <b>predict</b> {pendingInputs} queued · {correctionTiles.toFixed(3)} tiles off
      </div>
      <div>
        <b>entities</b> {entities}
      </div>
      <div>
        <b>topology</b> v{topologyVersion}
      </div>
    </aside>
  )
}
