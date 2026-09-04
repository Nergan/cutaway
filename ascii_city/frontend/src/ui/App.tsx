import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { GameSession, type SessionView } from '../game/session'
import { Chat } from './Chat'
import { Hud } from './Hud'
import { Minimap } from './Minimap'
import { Overlay } from './Overlay'
import { Roster } from './Roster'
import { Settings } from './Settings'

const BASE_PATH = resolveBasePath()

/** Matches the raycaster's default, and the range its clamp allows. */
const DEFAULT_FOV_DEGREES = 78
const MIN_FOV_DEGREES = 55
const MAX_FOV_DEGREES = 110
/** Degrees per wheel notch. A notch is 100 units in every browser worth caring about. */
const FOV_PER_NOTCH = 4

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
  const [chatOpen, setChatOpen] = useState(false)
  const [fieldOfView, setFieldOfView] = useState(DEFAULT_FOV_DEGREES)
  const [mapExpanded, setMapExpanded] = useState(false)
  // Mounting the session is an effect, so a plain ref would not re-render the
  // children that need it. This state hands it over exactly once.
  const [session, setSession] = useState<GameSession | null>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    const surface = surfaceRef.current
    if (!canvas || !surface) return

    const game = new GameSession(BASE_PATH)
    sessionRef.current = game
    setSession(game)
    const unsubscribe = game.subscribe(setView)
    game.start(canvas, surface).catch((error: unknown) => {
      setFatal(error instanceof Error ? error.message : String(error))
    })

    return () => {
      unsubscribe()
      game.dispose()
      sessionRef.current = null
      setSession(null)
    }
  }, [])

  const sendChat = useCallback((scope: 'global' | 'proximity', text: string) => {
    sessionRef.current?.sendChat(scope, text)
  }, [])

  const sendRename = useCallback((nickname: string) => {
    sessionRef.current?.sendRename(nickname)
  }, [])

  const sendAvatar = useCallback((index: number) => {
    sessionRef.current?.sendAvatar(index)
  }, [])

  const rosterColors = useMemo(() => {
    const map = new Map<number, number>()
    for (const member of view?.roster ?? []) map.set(member.id, member.color)
    return map
  }, [view?.roster])

  const setChatFocused = useCallback((focused: boolean) => {
    setChatOpen(focused)
    sessionRef.current?.setChatFocused(focused)
  }, [])

  const grabPointer = useCallback(() => {
    sessionRef.current?.requestPointerLock()
  }, [])

  // Clicking the world is how you get back to playing: it dismisses whatever
  // panel is holding the mouse, and only then re-captures the pointer.
  const onViewportClick = useCallback(() => {
    if (chatOpen) setChatFocused(false)
    if (settingsOpen) setSettingsOpen(false)
    if (!chatOpen && !settingsOpen) grabPointer()
  }, [chatOpen, settingsOpen, setChatFocused, grabPointer])

  const online = view?.status.phase === 'online'

  // Anything the player is meant to click needs a visible mouse, and a locked
  // pointer has none. Releasing it here is what makes the chat and the
  // settings panel usable without leaving the game.
  const uiWantsMouse = chatOpen || settingsOpen
  const hadMouseUi = useRef(false)
  useEffect(() => {
    if (uiWantsMouse) sessionRef.current?.releasePointerLock()
    else if (hadMouseUi.current && online) sessionRef.current?.requestPointerLock()
    hadMouseUi.current = uiWantsMouse
  }, [uiWantsMouse, online])

  const applyFieldOfView = useCallback((degrees: number) => {
    const clamped = Math.min(MAX_FOV_DEGREES, Math.max(MIN_FOV_DEGREES, Math.round(degrees)))
    setFieldOfView(clamped)
    sessionRef.current?.setFieldOfView(clamped)
  }, [])

  useEffect(() => {
    if (!online) return
    const onKeyDown = (event: KeyboardEvent) => {
      const tag = (event.target as HTMLElement | null)?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA') return
      if (event.code === 'KeyE') {
        event.preventDefault()
        setSettingsOpen((open) => !open)
      } else if (event.code === 'Escape') {
        // Escape only ever backs out. Chat owns it while it is open, so by the
        // time it reaches here it can mean nothing but "close the menu".
        if (chatOpen) return
        event.preventDefault()
        setSettingsOpen(false)
      } else if (event.code === 'KeyZ') {
        if (event.repeat) return
        event.preventDefault()
        setMapExpanded(true)
      } else if (event.code === 'Digit5' || event.code === 'Numpad5' || event.key === '5') {
        event.preventDefault()
        sessionRef.current?.toggleCamera()
      }
    }
    const onKeyUp = (event: KeyboardEvent) => {
      if (event.code === 'KeyZ') setMapExpanded(false)
    }
    // Losing focus mid-hold would otherwise leave the map stuck open.
    const onBlur = () => setMapExpanded(false)
    window.addEventListener('keydown', onKeyDown)
    window.addEventListener('keyup', onKeyUp)
    window.addEventListener('blur', onBlur)
    return () => {
      window.removeEventListener('keydown', onKeyDown)
      window.removeEventListener('keyup', onKeyUp)
      window.removeEventListener('blur', onBlur)
    }
  }, [online, chatOpen])

  // Zooming is a look control, so it belongs to the wheel whenever the mouse
  // is not busy driving a panel.
  useEffect(() => {
    if (!online || uiWantsMouse) return
    const onWheel = (event: WheelEvent) => {
      event.preventDefault()
      applyFieldOfView(fieldOfView + (event.deltaY / 100) * FOV_PER_NOTCH)
    }
    window.addEventListener('wheel', onWheel, { passive: false })
    return () => window.removeEventListener('wheel', onWheel)
  }, [online, uiWantsMouse, fieldOfView, applyFieldOfView])

  const showOverlay = useMemo(() => {
    if (fatal) return true
    if (!view) return true
    return view.status.phase !== 'online' || !view.player
  }, [fatal, view])

  return (
    <div className={`app${uiWantsMouse ? ' app-cursor' : ''}`}>
      <div className="viewport" ref={surfaceRef} onClick={online ? onViewportClick : undefined}>
        <canvas ref={canvasRef} className="screen" />
        {online && view?.player ? <div className="reticle">+</div> : null}
      </div>

      {view && online ? (
        <>
          <Hud view={view} onOpenSettings={() => setSettingsOpen((open) => !open)} />
          <Minimap
            session={session}
            roster={view.roster}
            selfId={view.player?.id ?? 0}
            expanded={mapExpanded}
          />
          <Roster roster={view.roster} selfId={view.player?.id ?? 0} session={session} />
          <Chat
            messages={view.messages}
            selfId={view.player?.id ?? 0}
            rosterColors={rosterColors}
            open={chatOpen}
            onSend={sendChat}
            onOpenChange={setChatFocused}
          />
        </>
      ) : null}

      {view?.notice ? <div className="notice">{view.notice}</div> : null}

      {settingsOpen && view ? (
        <Settings
          nickname={view.player?.nickname ?? ''}
          avatar={view.player?.avatar ?? 0}
          color={view.player?.color ?? 0}
          onClose={() => setSettingsOpen(false)}
          onQuality={(preset) => sessionRef.current?.setQuality(preset)}
          fieldOfView={fieldOfView}
          onFieldOfView={applyFieldOfView}
          onRename={sendRename}
          onAvatar={sendAvatar}
          stats={view.stats}
        />
      ) : null}

      {showOverlay ? <Overlay view={view} fatal={fatal} onEnter={grabPointer} /> : null}
    </div>
  )
}
