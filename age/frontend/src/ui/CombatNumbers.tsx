/**
 * Floating damage and healing numbers.
 *
 * The gap this closes is the whole of "skills do nothing". The server has always
 * resolved abilities and always sent a combat event saying what happened, and the
 * client has always thrown it away. A health bar two tiles wide dropping by an eighth
 * is not feedback anyone reads as a hit; a number leaving the target is.
 *
 * Positions are captured once, when the event lands, rather than tracked. A number
 * that followed a moving target would be a per-frame React update for something that
 * lives for under a second, and it would read worse: what is being annotated is the
 * moment, not the creature.
 */

import { useEffect, useRef, useState } from 'react'

import type { Combat } from '../net/wire'
import type { Session } from '../net/session'
import type { Scene } from '../render/scene'

/** How long a number stays up. Matches the rise animation in the stylesheet. */
const LIFETIME_MS = 900

export interface CombatNumbersProps {
  session: Session
  /** Read through a ref because the scene is built after the first render. */
  scene: () => Scene | null
}

interface Floater {
  id: number
  text: string
  tone: 'damage' | 'heal' | 'miss'
  x: number
  y: number
}

export function CombatNumbers({ session, scene }: CombatNumbersProps) {
  const [floaters, setFloaters] = useState<Floater[]>([])
  const nextId = useRef(0)

  useEffect(() => {
    const timers: Array<ReturnType<typeof setTimeout>> = []

    const off = session.on('combat', (event: Combat) => {
      const current = scene()
      if (current === null) return

      const at = current.tileToScreen(event.x, event.y, session.position)
      const id = (nextId.current += 1)
      const floater: Floater = {
        id,
        ...toneOf(event),
        x: at.x,
        // Lifted clear of the sprite's feet, which is where the world point is.
        y: at.y - 28,
      }

      setFloaters((live) => [...live.slice(-15), floater])
      timers.push(
        setTimeout(() => {
          setFloaters((live) => live.filter((entry) => entry.id !== id))
        }, LIFETIME_MS),
      )
    })

    return () => {
      off()
      for (const timer of timers) clearTimeout(timer)
    }
  }, [session, scene])

  return (
    <div className="combat-numbers" aria-hidden="true">
      {floaters.map((floater) => (
        <span
          key={floater.id}
          className={`floater ${floater.tone}`}
          style={{ left: floater.x, top: floater.y }}
        >
          {floater.text}
        </span>
      ))}
    </div>
  )
}

function toneOf(event: Combat): { text: string; tone: Floater['tone'] } {
  if (event.damage > 0) return { text: String(event.damage), tone: 'damage' }
  if (event.healing > 0) return { text: `+${event.healing}`, tone: 'heal' }
  // A whiff still needs to say something, or an ability aimed badly is
  // indistinguishable from an ability that is broken.
  return { text: 'miss', tone: 'miss' }
}
