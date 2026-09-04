/**
 * Keyboard, mouse and touch collapsed into one intent vector.
 *
 * Nothing here knows about the network. It reports what the human is asking
 * for; the game loop turns that into a numbered command at a fixed rate.
 */

import { MAX_PITCH_RAD, TAU } from '../domain/constants'

export interface Intent {
  forward: number
  strafe: number
  sprint: boolean
  jump: boolean
  yaw: number
  pitch: number
}

const MOUSE_SENSITIVITY = 0.0022
const TOUCH_LOOK_SENSITIVITY = 0.006
const JOYSTICK_RADIUS_PX = 56

type Action = 'forward' | 'back' | 'left' | 'right' | 'sprint' | 'jump'

const KEYS: Record<string, Action> = {
  KeyW: 'forward',
  ArrowUp: 'forward',
  KeyS: 'back',
  ArrowDown: 'back',
  KeyA: 'left',
  ArrowLeft: 'left',
  KeyD: 'right',
  ArrowRight: 'right',
  ControlLeft: 'sprint',
  ControlRight: 'sprint',
  Space: 'jump',
}

export class InputController {
  private readonly held = new Set<string>();
  private yaw = 0
  private pitch = 0
  private sprintKey = false
  private jumpQueued = false
  /** Set while a text field owns the keyboard. */
  private suspended = false
  private pointerLocked = false
  private lookPointer: number | null = null
  private lookLast = { x: 0, y: 0 }
  private stickPointer: number | null = null
  private stickOrigin = { x: 0, y: 0 }
  private stick = { x: 0, y: 0 }
  private detach: Array<() => void> = []

  onPointerLockChange: ((locked: boolean) => void) | null = null

  constructor(private readonly surface: HTMLElement) {}

  attach(): void {
    const target = this.surface
    const listen = (element: EventTarget, type: string, handler: EventListener) => {
      element.addEventListener(type, handler)
      this.detach.push(() => element.removeEventListener(type, handler))
    }

    listen(window, 'keydown', this.onKeyDown as EventListener)
    listen(window, 'keyup', this.onKeyUp as EventListener)
    listen(window, 'blur', this.releaseAll)
    listen(document, 'pointerlockchange', this.onLockChange)
    listen(window, 'mousemove', this.onMouseMove as EventListener)
    listen(target, 'pointerdown', this.onPointerDown as EventListener)
    listen(window, 'pointermove', this.onPointerMove as EventListener)
    listen(window, 'pointerup', this.onPointerUp as EventListener)
    listen(window, 'pointercancel', this.onPointerUp as EventListener)
    listen(target, 'contextmenu', (event) => event.preventDefault())
  }

  dispose(): void {
    for (const off of this.detach) off()
    this.detach = []
    this.releaseAll()
  }

  /** Suspend movement keys while the chat input has focus. */
  setSuspended(value: boolean): void {
    this.suspended = value
    if (value) this.releaseAll()
  }

  requestPointerLock(): void {
    if (this.pointerLocked) return
    // Chrome refuses a re-lock for about a second after Escape released it,
    // and rejects without a gesture. Either way the click handler is still
    // there, so a refusal is not worth an unhandled rejection.
    try {
      const result = this.surface.requestPointerLock?.() as Promise<void> | undefined
      if (result && typeof result.catch === 'function') result.catch(() => {})
    } catch {
      /* the player can always click the viewport */
    }
  }

  /** Give the mouse back to the page so the interface can be clicked. */
  releasePointerLock(): void {
    if (this.pointerLocked) document.exitPointerLock?.()
  }

  get isPointerLocked(): boolean {
    return this.pointerLocked
  }

  /** Virtual joystick offset in pixels, for the on-screen control. */
  get joystick(): { x: number; y: number; active: boolean } {
    return { x: this.stick.x, y: this.stick.y, active: this.stickPointer !== null }
  }

  /**
   * The intent for one simulation step. Edge-triggered actions are consumed,
   * so exactly one command can carry a given key press.
   */
  consume(): Intent {
    const intent = this.peek()
    this.jumpQueued = false
    return intent
  }

  /**
   * The same intent without consuming anything, for the render path.
   *
   * The camera samples orientation every frame while the simulation steps
   * twenty times a second, so most frames read without stepping. Consuming
   * here would throw away roughly two out of three jumps.
   */
  peek(): Intent {
    if (this.suspended) {
      return { forward: 0, strafe: 0, sprint: false, jump: false, yaw: this.yaw, pitch: this.pitch }
    }
    let forward = (this.held.has('forward') ? 1 : 0) - (this.held.has('back') ? 1 : 0)
    let strafe = (this.held.has('right') ? 1 : 0) - (this.held.has('left') ? 1 : 0)
    if (this.stickPointer !== null) {
      forward += -this.stick.y / JOYSTICK_RADIUS_PX
      strafe += this.stick.x / JOYSTICK_RADIUS_PX
    }
    const magnitude = Math.hypot(forward, strafe)
    if (magnitude > 1) {
      forward /= magnitude
      strafe /= magnitude
    }
    return {
      forward,
      strafe,
      sprint: this.sprintKey || magnitude > 0.92,
      jump: this.jumpQueued,
      yaw: this.yaw,
      pitch: this.pitch,
    }
  }

  setOrientation(yaw: number, pitch: number): void {
    this.yaw = ((yaw % TAU) + TAU) % TAU
    this.pitch = clampPitch(pitch)
  }

  private applyLook(dx: number, dy: number, sensitivity: number): void {
    this.yaw = (((this.yaw - dx * sensitivity) % TAU) + TAU) % TAU
    this.pitch = clampPitch(this.pitch - dy * sensitivity)
  }

  private readonly onKeyDown = (event: KeyboardEvent) => {
    const action = KEYS[event.code]
    if (!action) return
    if (this.suspended) return
    event.preventDefault()
    if (action === 'sprint') this.sprintKey = true
    else if (action === 'jump') this.jumpQueued = true
    else this.held.add(action)
  }

  private readonly onKeyUp = (event: KeyboardEvent) => {
    const action = KEYS[event.code]
    if (!action) return
    if (action === 'sprint') this.sprintKey = false
    else this.held.delete(action)
  }

  private readonly releaseAll = () => {
    this.held.clear()
    this.sprintKey = false
    this.jumpQueued = false
    this.stickPointer = null
    this.stick.x = 0
    this.stick.y = 0
    this.lookPointer = null
  }

  private readonly onLockChange = () => {
    this.pointerLocked = document.pointerLockElement === this.surface
    this.onPointerLockChange?.(this.pointerLocked)
  }

  private readonly onMouseMove = (event: MouseEvent) => {
    if (!this.pointerLocked || this.suspended) return
    this.applyLook(event.movementX, event.movementY, MOUSE_SENSITIVITY)
  }

  private readonly onPointerDown = (event: PointerEvent) => {
    if (event.pointerType === 'mouse') {
      this.requestPointerLock()
      return
    }
    // Left half of the viewport drives the stick, right half looks around.
    if (event.clientX < window.innerWidth * 0.45 && this.stickPointer === null) {
      this.stickPointer = event.pointerId
      this.stickOrigin = { x: event.clientX, y: event.clientY }
      this.stick = { x: 0, y: 0 }
    } else if (this.lookPointer === null) {
      this.lookPointer = event.pointerId
      this.lookLast = { x: event.clientX, y: event.clientY }
    }
  }

  private readonly onPointerMove = (event: PointerEvent) => {
    if (event.pointerId === this.stickPointer) {
      const dx = event.clientX - this.stickOrigin.x
      const dy = event.clientY - this.stickOrigin.y
      const distance = Math.hypot(dx, dy) || 1
      const scale = Math.min(1, JOYSTICK_RADIUS_PX / distance)
      this.stick = { x: dx * scale, y: dy * scale }
    } else if (event.pointerId === this.lookPointer) {
      this.applyLook(
        event.clientX - this.lookLast.x,
        event.clientY - this.lookLast.y,
        TOUCH_LOOK_SENSITIVITY,
      )
      this.lookLast = { x: event.clientX, y: event.clientY }
    }
  }

  private readonly onPointerUp = (event: PointerEvent) => {
    if (event.pointerId === this.stickPointer) {
      this.stickPointer = null
      this.stick = { x: 0, y: 0 }
    }
    if (event.pointerId === this.lookPointer) this.lookPointer = null
  }
}

function clampPitch(value: number): number {
  return value < -MAX_PITCH_RAD ? -MAX_PITCH_RAD : value > MAX_PITCH_RAD ? MAX_PITCH_RAD : value
}
