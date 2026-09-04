/** Health, resource, and who you are. The one panel that must never be wrong. */

import { BASE_MAX_HEALTH, BASE_MAX_RESOURCE } from '../domain/constants'

export interface VitalsProps {
  name: string
  className: string
  level: number
  /** A ratio from 0 to 1, which is how the client carries vitals once decoded. */
  health: number
  resource: number
}

/**
 * The wire sends vitals as a byte of percent rather than as absolute values.
 *
 * That is a deliberate protocol choice — it costs one byte instead of four and no client needs
 * to know an NPC's exact hit points — but it means the numbers here are reconstructed, so they
 * are shown as percentages of a nominal maximum rather than as authoritative totals.
 */
function scale(ratio: number, maximum: number): number {
  return Math.round(ratio * maximum)
}

export function Vitals({ name, className, level, health, resource }: VitalsProps) {
  const healthPercent = health * 100
  const resourcePercent = resource * 100

  return (
    <section className="panel hud-vitals" aria-label="Vitals">
      <div className="vitals-name">
        <strong>{name}</strong>
        <span className="muted">
          {className} · {level}
        </span>
      </div>

      <div
        className="bar"
        role="meter"
        aria-label="Health"
        aria-valuenow={Math.round(healthPercent)}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div className="bar-fill health" style={{ width: `${healthPercent}%` }} />
        <span className="bar-text">
          {scale(health, BASE_MAX_HEALTH)} / {BASE_MAX_HEALTH}
        </span>
      </div>

      <div
        className="bar"
        role="meter"
        aria-label="Resource"
        aria-valuenow={Math.round(resourcePercent)}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div className="bar-fill resource" style={{ width: `${resourcePercent}%` }} />
        <span className="bar-text">
          {scale(resource, BASE_MAX_RESOURCE)} / {BASE_MAX_RESOURCE}
        </span>
      </div>
    </section>
  )
}
