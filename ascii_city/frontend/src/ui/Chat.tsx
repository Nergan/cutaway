import { useEffect, useRef, useState } from 'react'

import { CHAT_MAX_LENGTH } from '../domain/constants'
import type { ChatMessage } from '../domain/types'
import { PLAYER_COLORS } from '../render/palette'

interface Props {
  messages: ChatMessage[]
  selfId: number
  rosterColors: ReadonlyMap<number, number>
  open: boolean
  onSend: (scope: 'global' | 'proximity', text: string) => void
  onOpenChange: (open: boolean) => void
}

/**
 * Chat is rendered into text nodes, never into markup, so the angle brackets
 * the sanitiser deliberately preserves stay harmless.
 *
 * Whether the chat is open is owned by the app, because that single flag also
 * decides who holds the mouse: the game or the interface.
 */
export function Chat({ messages, selfId, rosterColors, open, onSend, onOpenChange }: Props) {
  const [draft, setDraft] = useState('')
  const [scope, setScope] = useState<'global' | 'proximity'>('global')
  const inputRef = useRef<HTMLInputElement | null>(null)
  const logRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    const log = logRef.current
    if (log) log.scrollTop = log.scrollHeight
  }, [messages])

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const tag = (event.target as HTMLElement | null)?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA') return
      if ((event.code === 'Enter' || event.code === 'KeyT') && !open) {
        event.preventDefault()
        onOpenChange(true)
      } else if (event.code === 'Escape' && open) {
        onOpenChange(false)
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [open, onOpenChange])

  // The caret follows the panel. Waiting a frame lets the input exist first,
  // and lets the pointer unlock settle before focus lands.
  useEffect(() => {
    if (!open) {
      inputRef.current?.blur()
      return
    }
    const handle = requestAnimationFrame(() => inputRef.current?.focus())
    return () => cancelAnimationFrame(handle)
  }, [open])

  const submit = (event: React.FormEvent) => {
    event.preventDefault()
    const text = draft.trim()
    if (text) onSend(scope, text)
    setDraft('')
    onOpenChange(false)
  }

  return (
    <div className={`chat${open ? ' chat-open' : ''}`}>
      <div className="chat-log" ref={logRef}>
        {messages.slice(-40).map((message) => (
          <div key={`${message.id}-${message.createdAt}`} className={`line line-${message.scope}`}>
            {message.scope === 'system' ? (
              <span className="system">{message.text}</span>
            ) : (
              <>
                <span
                  className="who"
                  style={{ color: colorFor(message.senderId, message.senderId === selfId, rosterColors) }}
                >
                  {message.nickname}
                </span>
                <span className="says">{message.text}</span>
              </>
            )}
          </div>
        ))}
      </div>

      {open ? (
        <form className="chat-input" onSubmit={submit}>
          <button
            type="button"
            className="scope"
            // Without this the button steals focus, the input blurs, and the
            // blur handler below closes the chat mid-sentence.
            onMouseDown={(event) => event.preventDefault()}
            onClick={() => setScope(scope === 'global' ? 'proximity' : 'global')}
            title="Global reaches the district, nearby reaches thirty metres."
          >
            {scope === 'global' ? 'district' : 'nearby'}
          </button>
          <input
            ref={inputRef}
            value={draft}
            maxLength={CHAT_MAX_LENGTH}
            placeholder="say something"
            onChange={(event) => setDraft(event.target.value)}
          />
        </form>
      ) : (
        <div className="chat-hint">T or Enter to talk</div>
      )}
    </div>
  )
}

function colorFor(
  senderId: number,
  isSelf: boolean,
  rosterColors: ReadonlyMap<number, number>,
): string {
  if (isSelf) return '#ffffff'
  const rosterColor = rosterColors.get(senderId)
  const index = rosterColor ?? senderId
  const color = PLAYER_COLORS[index % PLAYER_COLORS.length]
  return `rgb(${color[0]},${color[1]},${color[2]})`
}
