import { useEffect, useState } from 'react'

import type { GameSession } from '../game/session'
import type { RosterMember } from '../net/wire'
import { avatarFace } from '../render/charset'
import { PLAYER_COLORS } from '../render/palette'

interface Props {
  roster: RosterMember[]
  selfId: number
  session: GameSession | null
}

function css(color: readonly [number, number, number]): string {
  return `rgb(${Math.round(color[0])},${Math.round(color[1])},${Math.round(color[2])})`
}

/**
 * Who else is in the district, held open with Tab.
 *
 * Distances are sampled on a timer rather than every frame: the list is for
 * orientation, and a number that changes sixty times a second is unreadable.
 */
export function Roster({ roster, selfId, session }: Props) {
  const [open, setOpen] = useState(false)
  const [distances, setDistances] = useState<Map<number, number>>(new Map())

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.code !== 'Tab') return
      const tag = (event.target as HTMLElement | null)?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA') return
      event.preventDefault()
      setOpen(true)
    }
    const onKeyUp = (event: KeyboardEvent) => {
      if (event.code === 'Tab') setOpen(false)
    }
    // Alt-tabbing away never delivers the keyup, so the panel would stick.
    const onBlur = () => setOpen(false)

    window.addEventListener('keydown', onKeyDown)
    window.addEventListener('keyup', onKeyUp)
    window.addEventListener('blur', onBlur)
    return () => {
      window.removeEventListener('keydown', onKeyDown)
      window.removeEventListener('keyup', onKeyUp)
      window.removeEventListener('blur', onBlur)
    }
  }, [])

  useEffect(() => {
    if (!open || !session) return
    const sample = () => {
      const { camera, others } = session.liveState
      const next = new Map<number, number>()
      for (const other of others) {
        next.set(other.id, Math.hypot(other.x - camera.x, other.y - camera.y))
      }
      setDistances(next)
    }
    sample()
    const timer = setInterval(sample, 250)
    return () => clearInterval(timer)
  }, [open, session])

  if (!open) return null

  const ordered = [...roster].sort((a, b) => {
    if (a.id === selfId) return -1
    if (b.id === selfId) return 1
    return a.nickname.localeCompare(b.nickname)
  })

  return (
    <div className="roster">
      <header>
        <span>district</span>
        <span className="muted">{roster.length} online</span>
      </header>
      <ul>
        {ordered.map((member) => {
          const colour = css(PLAYER_COLORS[member.color % PLAYER_COLORS.length])
          const distance = distances.get(member.id)
          return (
            <li key={member.id} className={member.id === selfId ? 'self' : undefined}>
              <span className="face" style={{ color: colour }}>
                {avatarFace(member.avatar)}
              </span>
              <span className="who" style={{ color: colour }}>
                {member.nickname}
              </span>
              <span className="where muted">
                {member.id === selfId
                  ? 'you'
                  : distance === undefined
                    ? 'far'
                    : `${Math.round(distance)} m`}
              </span>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
