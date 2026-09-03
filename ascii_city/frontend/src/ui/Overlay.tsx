import type { SessionView } from '../game/session'

interface Props {
  view: SessionView | null
  fatal: string | null
  onEnter: () => void
}

/** Loading, reconnecting and refusal all share one full-screen panel. */
export function Overlay({ view, fatal, onEnter }: Props) {
  const phase = view?.status.phase ?? 'idle'
  const progress = view?.progress

  let title = 'ASCII CITY'
  let body = 'Waking the district up.'
  let action: { label: string; run: () => void } | null = null

  if (fatal) {
    title = 'THE CITY DID NOT LOAD'
    body = fatal
    action = { label: 'Reload', run: () => window.location.reload() }
  } else if (phase === 'loading-world') {
    body = progress
      ? `Streaming district tiles ${progress.loaded} of ${progress.total}.`
      : 'Fetching the district plan.'
  } else if (phase === 'connecting') {
    body = 'Opening the socket.'
  } else if (phase === 'reconnecting') {
    title = 'RECONNECTING'
    body = view?.status.detail || 'The connection dropped. Trying again.'
  } else if (phase === 'refused') {
    title = 'THE DISTRICT IS FULL'
    body = view?.status.detail || 'Every slot is taken. Try again in a moment.'
    action = { label: 'Try again', run: () => window.location.reload() }
  } else if (phase === 'failed') {
    title = 'DISCONNECTED'
    body = view?.status.detail || 'The server closed the connection.'
    action = { label: 'Reload', run: () => window.location.reload() }
  } else if (phase === 'online') {
    title = 'ASCII CITY'
    body = 'Click to look around. WASD to walk, Shift to run, Enter to talk.'
    action = { label: 'Enter the street', run: onEnter }
  }

  const percentage = progress && progress.total > 0 ? progress.loaded / progress.total : null

  return (
    <div className="overlay">
      <div className="overlay-panel">
        <h1>{title}</h1>
        <p>{body}</p>
        {percentage !== null && phase === 'loading-world' ? (
          <div className="progress">
            <div className="progress-bar" style={{ width: `${Math.round(percentage * 100)}%` }} />
          </div>
        ) : null}
        {action ? (
          <button type="button" onClick={action.run}>
            {action.label}
          </button>
        ) : null}
      </div>
    </div>
  )
}
