/**
 * The world panel: time of day, weather, population, and the accordion's tier.
 *
 * The tier is the one line here that is not decoration. The accordion is the project's central
 * idea and it is invisible by design — the world quietly grows a lane when a corridor gets busy
 * — so without a readout there is nothing to see, and a demo of an invisible feature is a demo
 * of nothing. When dev controls are on, the tier is also a pair of buttons, because waiting for
 * ten players to turn up is not a demonstration either.
 */

import {
  WEATHER_CLEAR,
  WEATHER_CLOUDY,
  WEATHER_FOG,
  WEATHER_RAIN,
  WEATHER_SNOW,
  WEATHER_STORM,
} from '../domain/constants'

export interface WorldPanelProps {
  place: string
  dayPhase: number
  weather: number
  population: number
  tier: number
  maxTier: number
  latencyMs: number
  devControls: boolean
  onTier: (tier: number) => void
}

const WEATHER_NAMES: Record<number, string> = {
  [WEATHER_CLEAR]: 'Clear',
  [WEATHER_CLOUDY]: 'Overcast',
  [WEATHER_RAIN]: 'Rain',
  [WEATHER_STORM]: 'Storm',
  [WEATHER_FOG]: 'Fog',
  [WEATHER_SNOW]: 'Snow',
}

/**
 * The clock, as a name rather than a number.
 *
 * A day is six minutes here, so "14:37" would be nonsense precision on a clock that runs at
 * ninety times real time. The phase names are what a player actually reads it for.
 */
function timeOfDay(phase: number): string {
  const wrapped = ((phase % 1) + 1) % 1
  if (wrapped < 0.06) return 'Deep night'
  if (wrapped < 0.16) return 'First light'
  if (wrapped < 0.28) return 'Dawn'
  if (wrapped < 0.44) return 'Morning'
  if (wrapped < 0.56) return 'Noon'
  if (wrapped < 0.7) return 'Afternoon'
  if (wrapped < 0.8) return 'Dusk'
  if (wrapped < 0.9) return 'Evening'
  return 'Night'
}

export function WorldPanel({
  place,
  dayPhase,
  weather,
  population,
  tier,
  maxTier,
  latencyMs,
  devControls,
  onTier,
}: WorldPanelProps) {
  return (
    <section className="panel hud-world" aria-label="World">
      <div className="panel-title">{place}</div>
      <dl className="world-rows">
        <dt>Time</dt>
        <dd>{timeOfDay(dayPhase)}</dd>
        <dt>Weather</dt>
        <dd>{WEATHER_NAMES[weather] ?? 'Unknown'}</dd>
        <dt>Online</dt>
        <dd>{population}</dd>
        <dt>Tier</dt>
        <dd>
          {tier} / {maxTier}
        </dd>
        <dt>Ping</dt>
        <dd>{Math.round(latencyMs)} ms</dd>
      </dl>

      {devControls && (
        <div style={{ display: 'flex', gap: 6, marginTop: 8 }}>
          {Array.from({ length: maxTier + 1 }, (_, target) => (
            <button
              key={target}
              type="button"
              className={`pill${target === tier ? ' on' : ''}`}
              style={{ cursor: 'pointer', flex: 1 }}
              onClick={() => onTier(target)}
              title={
                target > tier
                  ? 'Unfold a lane on either side of the corridor'
                  : target < tier
                    ? 'Fold the outer lanes back, evacuating anyone on them'
                    : 'Current tier'
              }
            >
              Tier {target}
            </button>
          ))}
        </div>
      )}
    </section>
  )
}
