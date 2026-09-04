/** Health, resource, level, and who you are. The one panel that must never be wrong. */

export interface VitalsProps {
  name: string
  className: string
  level: number
  /** A ratio from 0 to 1, which is how the client carries vitals once decoded. */
  health: number
  resource: number
  /** The pools those ratios are of, as the server derives them from class, level and gear. */
  maxHealth: number
  maxResource: number
  /** Experience into the current level, and what it takes to leave it. */
  experience: number
  nextLevelAt: number
  /** Set when the level-up class choice is waiting (GDD 6.3). */
  onCompose?: () => void
}

/**
 * The wire sends vitals as a byte of percent rather than as absolute values.
 *
 * That is a deliberate protocol choice — it costs one byte instead of four and no client needs
 * to know an NPC's exact hit points. The totals come separately, on the private inventory
 * packet, so the reconstruction below is accurate to within the rounding of that byte rather
 * than to within whatever the client guessed the maximum was.
 */
function scale(ratio: number, maximum: number): number {
  return Math.round(ratio * maximum)
}

export function Vitals({
  name,
  className,
  level,
  health,
  resource,
  maxHealth,
  maxResource,
  experience,
  nextLevelAt,
  onCompose,
}: VitalsProps) {
  const healthPercent = health * 100
  const resourcePercent = resource * 100
  const experiencePercent =
    nextLevelAt > 0 ? Math.min(100, (experience / nextLevelAt) * 100) : 0

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
          {scale(health, maxHealth)} / {maxHealth}
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
          {scale(resource, maxResource)} / {maxResource}
        </span>
      </div>

      <div
        className="bar experience"
        role="meter"
        aria-label="Experience"
        aria-valuenow={Math.round(experiencePercent)}
        aria-valuemin={0}
        aria-valuemax={100}
        title={`${experience} / ${nextLevelAt} experience`}
      >
        <div className="bar-fill experience" style={{ width: `${experiencePercent}%` }} />
      </div>

      {onCompose !== undefined && (
        <button type="button" className="vitals-compose" onClick={onCompose}>
          Choose a second discipline
        </button>
      )}
    </section>
  )
}
