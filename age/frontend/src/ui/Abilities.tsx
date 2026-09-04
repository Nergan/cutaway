/**
 * The ability bar.
 *
 * Cooldowns are tracked client-side from the moment an ability is sent, not from a server
 * acknowledgement. That is a display lie of about half a round trip, and it is the right lie:
 * a button that stays lit for 60 ms after you press it invites a second press, which the server
 * refuses, which reads as the game ignoring you.
 */

import { useEffect, useState } from 'react'

import type { AbilityInfo } from './api'

export interface AbilitiesProps {
  abilities: readonly AbilityInfo[]
  /** Millisecond timestamps of the last use, by ability id. */
  lastUsed: Readonly<Record<number, number>>
  /** Current resource as a byte of percent, to grey out what cannot be paid for. */
  resource: number
  onUse: (abilityId: number) => void
}

export function Abilities({ abilities, lastUsed, resource, onUse }: AbilitiesProps) {
  // A ticking clock rather than a CSS transition per button: the bar has three entries and one
  // shared 20 Hz tick is cheaper, stays in step across them, and does not need to be restarted
  // whenever a cooldown is refreshed mid-flight.
  const [now, setNow] = useState(() => performance.now())
  useEffect(() => {
    const timer = window.setInterval(() => setNow(performance.now()), 50)
    return () => window.clearInterval(timer)
  }, [])

  return (
    <section className="panel abilities hud-abilities" aria-label="Abilities">
      {abilities.map((ability, index) => {
        const elapsed = now - (lastUsed[ability.abilityId] ?? -Infinity)
        const remaining = Math.max(0, ability.cooldownMs - elapsed)
        const fraction = ability.cooldownMs > 0 ? remaining / ability.cooldownMs : 0
        // Resource is a percent byte and costs are absolute, so this compares against the
        // nominal maximum. Approximate on purpose: the server is the authority on whether a
        // cast can be paid for, and this only decides whether the button looks available.
        const affordable = (resource / 255) * 100 >= ability.resourceCost
        const ready = remaining <= 0 && affordable

        return (
          <button
            type="button"
            key={ability.abilityId}
            className={`ability${ready ? ' ready' : ''}`}
            title={`${ability.name} — ${ability.cooldownMs / 1000}s, ${ability.resourceCost} resource`}
            aria-label={ability.name}
            onClick={() => onUse(ability.abilityId)}
          >
            <span className="key">{index + 1}</span>
            <span className="label">{ability.name}</span>
            {fraction > 0 && <span className="cooldown" style={{ height: `${fraction * 100}%` }} />}
          </button>
        )
      })}
    </section>
  )
}
