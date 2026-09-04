/**
 * Chat, in two states.
 *
 * Closed it is a few lines of text over the world with no background and no pointer capture —
 * readable, ignorable, and not in the way. Open it becomes a panel with an input, and it takes
 * the keyboard, which is the important part: the movement keys are letters, so a chat box that
 * does not claim focus turns "hello" into a walk north-west.
 */

import { useEffect, useLayoutEffect, useRef, useState } from 'react'

import { CHANNEL_GLOBAL, CHANNEL_LOCAL, CHANNEL_SYSTEM, CHAT_MAX_LENGTH } from '../domain/constants'
import type { ChatLine } from '../net/session'

export interface ChatProps {
  lines: readonly ChatLine[]
  open: boolean
  onOpen: () => void
  onClose: () => void
  onSay: (channel: number, text: string) => void
}

/** How many lines the collapsed strip shows. Enough to notice, few enough to skim. */
const COLLAPSED_LINES = 5

const CHANNEL_NAMES: Record<number, string> = {
  [CHANNEL_LOCAL]: 'Local',
  [CHANNEL_GLOBAL]: 'Global',
  [CHANNEL_SYSTEM]: 'System',
}

export function Chat({ lines, open, onOpen, onClose, onSay }: ChatProps) {
  const [draft, setDraft] = useState('')
  const [channel, setChannel] = useState(CHANNEL_LOCAL)
  const input = useRef<HTMLInputElement>(null)
  const log = useRef<HTMLDivElement>(null)

  // Focus on open. Without this the box appears and the next keystroke walks the player.
  useEffect(() => {
    if (open) input.current?.focus()
  }, [open])

  // Pin to the bottom as lines arrive, but only when the reader is already there: yanking
  // someone back down while they are scrolled up reading is worse than a missed line.
  useLayoutEffect(() => {
    const element = log.current
    if (element === null) return
    const atBottom = element.scrollHeight - element.scrollTop - element.clientHeight < 40
    if (atBottom) element.scrollTop = element.scrollHeight
  }, [lines])

  const visible = open ? lines : lines.slice(-COLLAPSED_LINES)

  function submit(): void {
    const text = draft.trim()
    if (text.length > 0) onSay(channel, text)
    setDraft('')
    onClose()
  }

  return (
    <section
      className={`panel chat${open ? '' : ' collapsed'} hud-chat`}
      aria-label="Chat"
      onClick={() => {
        if (!open) onOpen()
      }}
    >
      <div className="chat-log" ref={log} aria-live="polite">
        {visible.map((line, index) => (
          <Line key={`${line.receivedAt}-${index}`} line={line} />
        ))}
        {visible.length === 0 && open && <span className="muted">Nothing said yet.</span>}
      </div>

      {open && (
        <div className="chat-entry">
          <select
            className="channel"
            value={channel}
            aria-label="Channel"
            onChange={(event) => setChannel(Number(event.target.value))}
          >
            <option value={CHANNEL_LOCAL}>Local</option>
            <option value={CHANNEL_GLOBAL}>Global</option>
          </select>
          <input
            ref={input}
            value={draft}
            maxLength={CHAT_MAX_LENGTH}
            placeholder="Say something…"
            aria-label="Message"
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              // Stopped from propagating so the game's key handler never sees these: a
              // capital W in a sentence should not be a step north.
              event.stopPropagation()
              if (event.key === 'Enter') submit()
              else if (event.key === 'Escape') {
                setDraft('')
                onClose()
              }
            }}
          />
          <button type="button" onClick={submit}>
            Send
          </button>
        </div>
      )}
    </section>
  )
}

function Line({ line }: { line: ChatLine }) {
  const channelClass =
    line.channel === CHANNEL_GLOBAL ? 'global' : line.channel === CHANNEL_SYSTEM ? 'system' : 'local'

  if (line.channel === CHANNEL_SYSTEM) {
    return <div className="chat-line system">{line.text}</div>
  }

  return (
    <div className={`chat-line ${channelClass}`}>
      <span className="who">
        {line.channel === CHANNEL_GLOBAL ? `[${CHANNEL_NAMES[CHANNEL_GLOBAL]}] ` : ''}
        {line.senderName}:
      </span>{' '}
      {line.text}
    </div>
  )
}
