/**
 * The game session: the one object that owns everything with a lifetime.
 *
 * It loads the district, opens the socket, runs the fixed-step input loop and
 * the variable-step render loop, and publishes a small immutable view of its
 * state for React to render. The UI never reaches into the simulation.
 */

import {
  CHAT_HISTORY_SIZE,
  EYE_HEIGHT_M,
  TICK_SECONDS,
} from '../domain/constants'
import type {
  ChatMessage,
  ConnectionStatus,
  LocalPlayer,
  WorldMetadata,
} from '../domain/types'
import { Connection, now } from '../net/connection'
import { NOTICE_RATE_LIMIT, type InputCommand, type ServerFrame } from '../net/wire'
import { Renderer, type QualityPreset, type RendererStats } from '../render/renderer'
import type { Sprite } from '../render/sprites'
import { InputController } from '../sim/input'
import { InterpolationBuffer } from '../sim/interpolation'
import { Predictor } from '../sim/prediction'
import type { CollisionGrid } from '../world/collisionGrid'
import { WorldClient, type LoadProgress } from '../world/worldClient'

export interface SessionView {
  status: ConnectionStatus
  player: LocalPlayer | null
  population: number
  roster: Array<{ id: number; nickname: string; color: number }>
  messages: ChatMessage[]
  progress: LoadProgress | null
  metadata: WorldMetadata | null
  stats: RendererStats | null
  /** Metres the last reconciliation had to correct. Useful when debugging. */
  correctionM: number
  pointerLocked: boolean
  notice: string | null
}

/** Roughly six HUD refreshes per second: readable, and cheap. */
const HUD_INTERVAL_MS = 160

const EMPTY_VIEW: SessionView = {
  status: { phase: 'idle', detail: '', latencyMs: 0, attempt: 0 },
  player: null,
  population: 0,
  roster: [],
  messages: [],
  progress: null,
  metadata: null,
  stats: null,
  correctionM: 0,
  pointerLocked: false,
  notice: null,
}

export class GameSession {
  private readonly worldClient: WorldClient
  private readonly interpolation = new InterpolationBuffer()
  private readonly roster = new Map<number, { id: number; nickname: string; color: number }>()
  private readonly messages: ChatMessage[] = []

  private renderer: Renderer | null = null
  private input: InputController | null = null
  private connection: Connection | null = null
  private predictor: Predictor | null = null
  private grid: CollisionGrid | null = null

  private frameHandle = 0
  private lastFrameAt = 0
  private lastHudAt = 0
  private accumulator = 0
  private sequence = 1
  private disposed = false
  private resizeObserver: ResizeObserver | null = null
  private noticeTimer: ReturnType<typeof setTimeout> | null = null

  private view: SessionView = EMPTY_VIEW
  private readonly listeners = new Set<(view: SessionView) => void>()

  constructor(private readonly basePath: string) {
    this.worldClient = new WorldClient(basePath)
  }

  subscribe(listener: (view: SessionView) => void): () => void {
    this.listeners.add(listener)
    listener(this.view)
    return () => this.listeners.delete(listener)
  }

  get snapshot(): SessionView {
    return this.view
  }

  async start(canvas: HTMLCanvasElement, surface: HTMLElement): Promise<void> {
    this.patch({ status: { phase: 'loading-world', detail: '', latencyMs: 0, attempt: 0 } })

    const loaded = await this.worldClient.load((progress) => this.patch({ progress }))
    if (this.disposed) return

    this.grid = loaded.grid
    this.patch({ metadata: loaded.metadata })

    this.renderer = new Renderer(canvas)
    this.input = new InputController(surface)
    this.input.onPointerLockChange = (pointerLocked) => this.patch({ pointerLocked })
    this.input.attach()

    this.observe(surface)

    this.predictor = new Predictor({
      x: loaded.grid.widthM / 2,
      y: loaded.grid.heightM / 2,
      yaw: 0,
      pitch: 0,
      animation: 0,
    })

    this.connection = new Connection(this.socketUrl(), {
      onFrame: (frame) => this.onFrame(frame),
      onStatus: (status) => this.patch({ status }),
    })
    this.connection.connect()

    this.lastFrameAt = performance.now()
    this.frameHandle = requestAnimationFrame(this.tick)
  }

  dispose(): void {
    this.disposed = true
    cancelAnimationFrame(this.frameHandle)
    if (this.noticeTimer !== null) clearTimeout(this.noticeTimer)
    this.resizeObserver?.disconnect()
    this.connection?.close()
    this.input?.dispose()
    this.renderer?.dispose()
    this.worldClient.dispose()
    this.listeners.clear()
  }

  // --- commands from the UI ----------------------------------------------

  sendChat(scope: 'global' | 'proximity', text: string): void {
    const trimmed = text.trim()
    if (!trimmed) return
    this.connection?.sendChat(scope, trimmed)
  }

  setChatFocused(focused: boolean): void {
    this.input?.setSuspended(focused)
  }

  requestPointerLock(): void {
    this.input?.requestPointerLock()
  }

  setQuality(preset: QualityPreset): void {
    this.renderer?.setPreset(preset)
  }

  setFieldOfView(degrees: number): void {
    this.renderer?.setFieldOfView(degrees)
  }

  // --- loops ---------------------------------------------------------------

  private readonly tick = (timestamp: number) => {
    if (this.disposed) return
    this.frameHandle = requestAnimationFrame(this.tick)

    const dt = Math.min(0.25, (timestamp - this.lastFrameAt) / 1000)
    this.lastFrameAt = timestamp

    const grid = this.grid
    const predictor = this.predictor
    const renderer = this.renderer
    const input = this.input
    if (!grid || !predictor || !renderer || !input) return

    // Fixed step: the client simulates exactly what the server will simulate.
    this.accumulator += dt
    let steps = 0
    while (this.accumulator >= TICK_SECONDS && steps < 5) {
      this.accumulator -= TICK_SECONDS
      steps += 1
      const intent = input.read()
      const command: InputCommand = {
        sequence: this.sequence,
        forward: intent.forward,
        strafe: intent.strafe,
        yaw: intent.yaw,
        pitch: intent.pitch,
        sprint: intent.sprint,
        clientTime: now(),
      }
      this.sequence = (this.sequence + 1) >>> 0
      predictor.push(command, grid, TICK_SECONDS)
      this.connection?.sendInput(command)
    }

    const intent = input.read()
    const position = predictor.view(dt)
    const camera = {
      x: position.x,
      y: position.y,
      z: EYE_HEIGHT_M,
      yaw: intent.yaw,
      pitch: intent.pitch,
    }

    const sprites: Sprite[] = []
    for (const other of this.interpolation.sample(performance.now())) {
      const member = this.roster.get(other.id)
      sprites.push({
        id: other.id,
        x: other.x,
        y: other.y,
        animation: other.animation,
        nickname: member?.nickname ?? '',
        color: member?.color ?? 0,
      })
    }

    renderer.render(grid, camera, sprites, dt)

    // The HUD only needs a handful of updates per second. Pushing every frame
    // would make React, not the raycaster, the most expensive thing here.
    if (timestamp - this.lastHudAt > HUD_INTERVAL_MS) {
      this.lastHudAt = timestamp
      this.patch({
        player: {
          id: this.view.player?.id ?? 0,
          nickname: this.view.player?.nickname ?? '',
          color: this.view.player?.color ?? 0,
          x: camera.x,
          y: camera.y,
          z: camera.z,
          yaw: camera.yaw,
          pitch: camera.pitch,
          animation: predictor.state.animation,
        },
        population: this.roster.size,
        stats: renderer.stats,
        correctionM: predictor.lastCorrectionM,
      })
    }
  }

  private onFrame(frame: ServerFrame): void {
    switch (frame.kind) {
      case 'welcome': {
        this.roster.set(frame.playerId, {
          id: frame.playerId,
          nickname: frame.nickname,
          color: frame.color,
        })
        this.predictor?.reset(frame.x, frame.y)
        this.input?.setOrientation(frame.yaw, 0)
        this.interpolation.clear()
        this.patch({
          player: {
            id: frame.playerId,
            nickname: frame.nickname,
            color: frame.color,
            x: frame.x,
            y: frame.y,
            z: frame.z,
            yaw: frame.yaw,
            pitch: 0,
            animation: 0,
          },
          roster: [...this.roster.values()],
        })
        return
      }
      case 'snapshot': {
        if (this.grid && this.predictor) {
          this.predictor.reconcile(frame, frame.ackSequence, this.grid, TICK_SECONDS)
        }
        // The viewer is excluded from the entry list by the server.
        this.interpolation.ingest(frame.entries, performance.now())
        return
      }
      case 'chat': {
        this.messages.push(frame.message)
        if (this.messages.length > CHAT_HISTORY_SIZE * 2) this.messages.shift()
        this.patch({ messages: [...this.messages] })
        return
      }
      case 'notice': {
        const prefix = frame.code === NOTICE_RATE_LIMIT ? 'Slow down: ' : ''
        this.showNotice(`${prefix}${frame.text}`)
        return
      }
      case 'roster-sync': {
        this.roster.clear()
        for (const member of frame.members) this.roster.set(member.id, member)
        this.patch({ roster: [...this.roster.values()], population: this.roster.size })
        return
      }
      case 'roster-add': {
        this.roster.set(frame.member.id, frame.member)
        this.patch({ roster: [...this.roster.values()], population: this.roster.size })
        return
      }
      case 'roster-remove': {
        this.roster.delete(frame.id)
        this.interpolation.forget(frame.id)
        this.patch({ roster: [...this.roster.values()], population: this.roster.size })
        return
      }
      default:
        return
    }
  }

  // --- plumbing ------------------------------------------------------------

  private socketUrl(): string {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    return `${protocol}//${window.location.host}${this.basePath}/ws`
  }

  private observe(surface: HTMLElement): void {
    const apply = () => {
      const rect = surface.getBoundingClientRect()
      this.renderer?.resize(rect.width, rect.height)
    }
    apply()
    if (typeof ResizeObserver !== 'undefined') {
      this.resizeObserver = new ResizeObserver(apply)
      this.resizeObserver.observe(surface)
    } else {
      window.addEventListener('resize', apply)
    }
  }

  private showNotice(text: string): void {
    if (this.noticeTimer !== null) clearTimeout(this.noticeTimer)
    this.patch({ notice: text })
    this.noticeTimer = setTimeout(() => this.patch({ notice: null }), 4000)
  }

  private patch(changes: Partial<SessionView>): void {
    this.view = { ...this.view, ...changes }
    for (const listener of this.listeners) listener(this.view)
  }
}
