/**
 * The application shell: fetch the world, show the title screen, then hand over to the game.
 *
 * The `Session` is created here and lives for as long as the tab does. It is deliberately not
 * React state: it owns a socket, a send timer, and a prediction buffer, and a component that
 * re-created it on a re-render would drop the player out of the world.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { Session } from '../net/session'
import { fetchWorld, socketUrl, type WorldInfo } from './api'
import { GameView } from './GameView'
import { TitleScreen, type Profile } from './TitleScreen'

export function App() {
  const [world, setWorld] = useState<WorldInfo | undefined>(undefined)
  const [error, setError] = useState<string | undefined>(undefined)
  const [profile, setProfile] = useState<Profile | undefined>(undefined)
  const [connecting, setConnecting] = useState(false)

  const session = useRef<Session | null>(null)

  useEffect(() => {
    let cancelled = false

    fetchWorld()
      .then((info) => {
        if (!cancelled) setWorld(info)
      })
      .catch((cause: unknown) => {
        if (!cancelled) {
          setError(cause instanceof Error ? cause.message : 'The server did not answer.')
        }
      })

    return () => {
      cancelled = true
    }
  }, [])

  // Close the socket on unload rather than leaving the server to time it out. The server
  // handles a dropped connection fine, but a clean close means the player's position is saved
  // on the way out instead of at the last snapshot.
  useEffect(() => {
    const leave = () => session.current?.leave()
    window.addEventListener('pagehide', leave)
    return () => {
      window.removeEventListener('pagehide', leave)
      leave()
    }
  }, [])

  const enter = useCallback((chosen: Profile) => {
    setConnecting(true)
    setError(undefined)

    const created = new Session(socketUrl(), chosen)
    session.current = created

    // The title screen stays up until the welcome packet lands, because the world cannot be
    // generated before the seed arrives and a black screen with a spinner is worse than a
    // title screen with a button that says "Entering".
    const offReady = created.on('ready', () => {
      offReady()
      offFailed()
      setProfile(chosen)
      setConnecting(false)
    })

    const offFailed = created.on('status', (status, detail) => {
      if (status !== 'failed') return
      offReady()
      offFailed()
      setError(detail ?? 'The connection failed.')
      setConnecting(false)
      session.current = null
    })

    created.connect()
  }, [])

  const chosenClass = useMemo(() => {
    if (world === undefined || profile === undefined) return undefined
    return world.classes.find((entry) => entry.classId === profile.classId) ?? world.classes[0]
  }, [world, profile])

  if (
    world !== undefined &&
    profile !== undefined &&
    chosenClass !== undefined &&
    session.current !== null
  ) {
    return (
      <GameView
        session={session.current}
        world={world}
        chosenClass={chosenClass}
        name={profile.name}
      />
    )
  }

  return <TitleScreen world={world} error={error} busy={connecting} onEnter={enter} />
}
