/**
 * Who owns the mouse.
 *
 * Losing the cursor under an open panel is the kind of bug that makes a game
 * unplayable and leaves no trace in a screenshot, so the handover between the
 * pointer lock and the interface is pinned down here rather than eyeballed.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { InputController } from './input'

interface Harness {
  input: InputController
  surface: HTMLElement
  exit: ReturnType<typeof vi.fn>
  request: ReturnType<typeof vi.fn>
  /** Pretend the browser granted or dropped the lock and told the page. */
  lock(held: boolean): void
}

let harness: Harness

beforeEach(() => {
  const listeners = new Map<string, EventListener[]>()
  const on = (type: string, handler: EventListener) => {
    listeners.set(type, [...(listeners.get(type) ?? []), handler])
  }
  const request = vi.fn()
  const exit = vi.fn()
  const surface = {
    addEventListener: on,
    removeEventListener: () => {},
    requestPointerLock: request,
  } as unknown as HTMLElement

  const documentListeners = new Map<string, EventListener[]>()
  vi.stubGlobal('document', {
    addEventListener: (type: string, handler: EventListener) => {
      documentListeners.set(type, [...(documentListeners.get(type) ?? []), handler])
    },
    removeEventListener: () => {},
    exitPointerLock: exit,
    pointerLockElement: null as unknown,
  })
  vi.stubGlobal('window', {
    addEventListener: () => {},
    removeEventListener: () => {},
    innerWidth: 1000,
  })

  const input = new InputController(surface)
  input.attach()

  harness = {
    input,
    surface,
    exit,
    request,
    lock(held: boolean) {
      ;(globalThis.document as unknown as { pointerLockElement: unknown }).pointerLockElement = held
        ? surface
        : null
      for (const handler of documentListeners.get('pointerlockchange') ?? []) {
        handler(new Event('pointerlockchange'))
      }
    },
  }
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('the pointer lock', () => {
  it('is taken when the player asks for it', () => {
    harness.input.requestPointerLock()
    expect(harness.request).toHaveBeenCalledTimes(1)
  })

  it('is handed back when a panel wants the mouse', () => {
    harness.input.requestPointerLock()
    harness.lock(true)
    expect(harness.input.isPointerLocked).toBe(true)

    harness.input.setPointerLockAllowed(false)
    expect(harness.exit).toHaveBeenCalled()
  })

  it('is handed back even when the page thinks it is already free', () => {
    // The flag only updates on `pointerlockchange`. Trusting a stale one is how
    // a player ends up with no cursor and no way to get it back.
    expect(harness.input.isPointerLocked).toBe(false)
    harness.input.setPointerLockAllowed(false)
    expect(harness.exit).toHaveBeenCalled()
  })

  it('is not retaken by a click while a panel is open', () => {
    harness.input.setPointerLockAllowed(false)
    harness.request.mockClear()
    harness.input.requestPointerLock()
    expect(harness.request).not.toHaveBeenCalled()
  })

  it('is available again once the panel closes', () => {
    harness.input.setPointerLockAllowed(false)
    harness.input.setPointerLockAllowed(true)
    harness.input.requestPointerLock()
    expect(harness.request).toHaveBeenCalledTimes(1)
  })
})
