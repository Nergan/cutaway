/**
 * The level-up class choice (GDD 6.3).
 *
 * A character is created as one of four base disciplines and, on reaching the composition
 * level, takes a second half. Picking the same half again makes the pure specialist; picking a
 * different one makes the hybrid. Fourteen classes out of four choices and one decision.
 *
 * The offer is derived from the class catalogue rather than hardcoded here, so the panel names
 * the actual resulting class and lists the abilities it will grant. Presenting the choice as
 * four abstract halves and letting the player find out afterwards what they became is the kind
 * of thing that reads as a bug.
 */

import type { ClassInfo } from './api'

export interface ComposeProps {
  /** The class the character is now: one of the four base classes. */
  current: ClassInfo
  /** The whole catalogue, used to work out what each choice leads to. */
  classes: readonly ClassInfo[]
  onChoose: (half: number) => void
  onDismiss: () => void
}

export function Compose({ current, classes, onChoose, onDismiss }: ComposeProps) {
  const halves = classes.filter((entry) => entry.isBase)

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="Second discipline">
      <div className="panel compose-card">
        <h2>Choose a second discipline</h2>
        <p className="muted">
          You began as {current.name}. What you add now decides what you become, and it cannot
          be changed later.
        </p>

        <div className="compose-grid">
          {halves.map((half) => {
            const result = resultOf(current, half, classes)
            return (
              <button
                key={half.classId}
                type="button"
                className="compose-option"
                onClick={() => onChoose(half.origin)}
              >
                <strong>{result?.name ?? half.name}</strong>
                <span className="muted compose-half">
                  {current.name} + {half.name}
                  {half.classId === current.classId ? ' · pure' : ''}
                </span>
                <span className="muted compose-fantasy">{result?.fantasy ?? half.fantasy}</span>
                <span className="compose-kit">
                  {(result?.abilities ?? []).map((ability) => ability.name).join(' · ')}
                </span>
              </button>
            )
          })}
        </div>

        <button type="button" className="compose-later" onClick={onDismiss}>
          Decide later
        </button>
      </div>
    </div>
  )
}

/**
 * Which class results from adding ``half`` to ``current``.
 *
 * A pairing is the same class from either side, so the origin and chosen halves are compared
 * as an unordered pair. The pure specialist is the case where both halves are the same, which
 * falls out of the same comparison without a special case.
 */
function resultOf(
  current: ClassInfo,
  half: ClassInfo,
  classes: readonly ClassInfo[],
): ClassInfo | undefined {
  const wanted = [current.origin, half.origin].sort()
  return classes.find((entry) => {
    if (entry.chosen === null) return false
    const pair = [entry.origin, entry.chosen].sort()
    return pair[0] === wanted[0] && pair[1] === wanted[1]
  })
}
