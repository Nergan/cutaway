/**
 * WebSocket transport with reconnection and latency tracking.
 *
 * The socket carries binary frames only. A dropped connection reconnects with
 * exponential backoff, and because the server never trusts a client position,
 * reconnecting simply produces a fresh authoritative spawn rather than a
 * chance to teleport.
 */

import type { ConnectionStatus } from '../domain/types'
import {
  decodeServerFrame,
  encodeChat,
  encodeInput,
  encodePing,
  type InputCommand,
  type ServerFrame,
} from './wire'

const PING_INTERVAL_MS = 4000
const BACKOFF_STEPS_MS = [500, 1000, 2000, 4000, 8000]
const MAX_ATTEMPTS = 12

/** Close codes the server uses for refusals that a retry will not fix soon. */
const CLOSE_ROOM_FULL = 4001
const CLOSE_WORLD_UNAVAILABLE = 4002
const CLOSE_BAD_FRAME = 4003

export interface ConnectionHandlers {
  onFrame: (frame: ServerFrame) => void
  onStatus: (status: ConnectionStatus) => void
}

export class Connection {
  private socket: WebSocket | null = null
  private pingTimer: ReturnType<typeof setInterval> | null = null
  private retryTimer: ReturnType<typeof setTimeout> | null = null
  private attempt = 0
  private closedByUs = false
  private latencyMs = 0
  private status: ConnectionStatus = {
    phase: 'idle',
    detail: '',
    latencyMs: 0,
    attempt: 0,
  }

  constructor(
    private readonly url: string,
    private readonly handlers: ConnectionHandlers,
  ) {}

  connect(): void {
    this.closedByUs = false
    this.open()
  }

  close(): void {
    this.closedByUs = true
    this.clearTimers()
    this.socket?.close(1000, 'Client left.')
    this.socket = null
    this.publish('idle', '')
  }

  get isOpen(): boolean {
    return this.socket?.readyState === WebSocket.OPEN
  }

  get latency(): number {
    return this.latencyMs
  }

  sendInput(command: InputCommand): void {
    this.send(encodeInput(command))
  }

  sendChat(scope: 'global' | 'proximity', text: string): void {
    this.send(encodeChat(scope, text))
  }

  private send(payload: Uint8Array): void {
    if (this.socket?.readyState !== WebSocket.OPEN) return
    // Never let an outbound queue grow into seconds of stale intent.
    if (this.socket.bufferedAmount > 64 * 1024) return
    this.socket.send(payload)
  }

  private open(): void {
    this.clearTimers()
    this.publish(this.attempt === 0 ? 'connecting' : 'reconnecting', '')

    let socket: WebSocket
    try {
      socket = new WebSocket(this.url)
    } catch (error) {
      this.scheduleRetry(error instanceof Error ? error.message : 'The socket could not open.')
      return
    }
    socket.binaryType = 'arraybuffer'
    this.socket = socket

    socket.onopen = () => {
      this.attempt = 0
      this.publish('online', '')
      this.pingTimer = setInterval(() => this.send(encodePing(now())), PING_INTERVAL_MS)
      this.send(encodePing(now()))
    }

    socket.onmessage = (event: MessageEvent) => {
      if (!(event.data instanceof ArrayBuffer)) return
      let frame: ServerFrame
      try {
        frame = decodeServerFrame(event.data)
      } catch {
        // A frame this client cannot parse is a version skew, not a fatal error.
        return
      }
      if (frame.kind === 'pong') {
        this.latencyMs = Math.max(0, now() - frame.clientTime)
        this.publish(this.status.phase, this.status.detail)
        return
      }
      this.handlers.onFrame(frame)
    }

    socket.onerror = () => {
      // `onclose` always follows, and it carries the reason worth showing.
    }

    socket.onclose = (event: CloseEvent) => {
      this.clearTimers()
      this.socket = null
      if (this.closedByUs) return

      if (event.code === CLOSE_ROOM_FULL) {
        this.publish('refused', 'The district is full. Try again in a moment.')
        return
      }
      if (event.code === CLOSE_BAD_FRAME) {
        this.publish('failed', 'The server rejected this client as incompatible.')
        return
      }
      const detail =
        event.code === CLOSE_WORLD_UNAVAILABLE
          ? 'The district is still loading.'
          : event.reason || 'The connection dropped.'
      this.scheduleRetry(detail)
    }
  }

  private scheduleRetry(detail: string): void {
    if (this.closedByUs) return
    if (this.attempt >= MAX_ATTEMPTS) {
      this.publish('failed', `${detail} Reload to try again.`)
      return
    }
    const delay = BACKOFF_STEPS_MS[Math.min(this.attempt, BACKOFF_STEPS_MS.length - 1)]
    this.attempt += 1
    this.publish('reconnecting', detail)
    this.retryTimer = setTimeout(() => this.open(), delay)
  }

  private clearTimers(): void {
    if (this.pingTimer !== null) clearInterval(this.pingTimer)
    if (this.retryTimer !== null) clearTimeout(this.retryTimer)
    this.pingTimer = null
    this.retryTimer = null
  }

  private publish(phase: ConnectionStatus['phase'], detail: string): void {
    this.status = { phase, detail, latencyMs: this.latencyMs, attempt: this.attempt }
    this.handlers.onStatus(this.status)
  }
}

/** Milliseconds since page load, truncated to the u32 the protocol carries. */
export function now(): number {
  return Math.round(performance.now()) >>> 0
}
