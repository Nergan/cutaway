import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { GameSession, type SessionView } from '../game/session'
import { Chat } from './Chat'
import { Hud } from './Hud'
import { Overlay } from './Overlay'
import { Settings } from './Settings'

const BASE_PATH = resolveBasePath()

/**
 * The prefix the orchestrator mounted this project at. Reading it from the
 * URL rather than hard-coding it keeps the standalone dev server, the hub and
 * any future prefix change working without a rebuild.
 */
function resolveBasePath(): string {
  const match = window.location.pathname.match(/^(\/[^/]+)/)
  return match && match[1] !== '/static' ? match[1] : '/ascii-city'
}

export function App() {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const surfaceRef = useRef<HTMLDivElement | null>(null)
  const sessionRef = useRef<GameSession | null>(null)

  const [view, setView] = useState<SessionView | null>(null)
  const [fatal, setFatal] = useState<string | null>(null)
  const [settingsOpen, setSettingsOpen] = useState(false)

  useEffect(() => {
    const canvas = canvasRef.current
    const surface = surfaceRef.current
    if (!canvas || !surface) return

    const session = new GameSession(BASE_PATH)
    sessionRef.current = session
    const unsubscribe = session.subscribe(setView)
    session.start(canvas, surface).catch((error: unknown) => {
      setFatal(error instanceof Error ? error.message : String(error))
    })

    return () => {
      unsubscribe()
      session.dispose()
      sessionRef.current = null
    }
  }, [])

  const sendChat = useCallback((scope: 'global' | 'proximity', text: string) => {
    sessionRef.current?.sendChat(scope, text)
  }, [])

  const sendRename = useCallback((nickname: string) => {
    sessionRef.current?.sendRename(nickname)
  }, [])

  const rosterColors = useMemo(() => {
    const map = new Map<number, number>()
    for (const member of view?.roster ?? []) map.set(member.id, member.color)
    return map
  }, [view?.roster])

  const setChatFocused = useCallback((focused: boolean) => {
    sessionRef.current?.setChatFocused(focused)
  }, [])

  const grabPointer = useCallback(() => {
    sessionRef.current?.requestPointerLock()
  }, [])

  const online = view?.status.phase === 'online'
  const showOverlay = useMemo(() => {
    if (fatal) return true
    if (!view) return true
    return view.status.phase !== 'online' || !view.player
  }, [fatal, view])

  return (
    <div className="app">
      <div className="viewport" ref={surfaceRef} onClick={online ? grabPointer : undefined}>
        <canvas ref={canvasRef} className="screen" />
        {online && view?.player ? <div className="reticle">+</div> : null}
      </div>

      {view && online ? (
        <>
          <Hud view={view} onOpenSettings={() => setSettingsOpen((open) => !open)} />
          <Chat
            messages={view.messages}
            selfId={view.player?.id ?? 0}
            rosterColors={rosterColors}
            onSend={sendChat}
            onFocusChange={setChatFocused}
          />
        </>
      ) : null}

      {view?.notice ? <div className="notice">{view.notice}</div> : null}

      {settingsOpen && view ? (
        <Settings
          nickname={view.player?.nickname ?? ''}
          onClose={() => setSettingsOpen(false)}
          onQuality={(preset) => sessionRef.current?.setQuality(preset)}
          onFieldOfView={(degrees) => sessionRef.current?.setFieldOfView(degrees)}
          onRename={sendRename}
          stats={view.stats}
        />
      ) : null}

      {showOverlay ? <Overlay view={view} fatal={fatal} onEnter={grabPointer} /> : null}
    </div>
  )
}
