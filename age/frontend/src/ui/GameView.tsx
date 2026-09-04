/**
 * The game screen: the canvas, the loop that drives it, and the HUD over it.
 *
 * The important structural decision here is that React does not own the frame. The renderer
 * runs from a `requestAnimationFrame` loop that reads the session directly, and React re-renders
 * only when something a panel shows actually changes — vitals, chat, tier — at about 8 Hz. A
 * component that re-rendered per frame would spend more time reconciling a virtual DOM than
 * drawing the world, and none of these panels change 60 times a second.
 *
 * Input is handled on `window` rather than on a focused element, because the game has no focus
 * target: the canvas is not interactive in the DOM sense. Chat takes the keyboard when open, and
 * the handler checks for that first.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { MAX_TIER, RESPAWN_DELAY_SECONDS } from '../domain/constants'
import type { ChatLine, Loadout, Session } from '../net/session'
import { Scene, visibleChunks, type SceneStats } from '../render/scene'
import { Abilities } from './Abilities'
import { CharacterSheet } from './CharacterSheet'
import { Chat } from './Chat'
import { CombatNumbers } from './CombatNumbers'
import { Compose } from './Compose'
import { Diagnostics } from './Diagnostics'
import { InventoryPanel } from './InventoryPanel'
import { Minimap } from './Minimap'
import { apiBase, forceTier, type ClassInfo, type WorldInfo } from './api'
import { Vitals } from './Vitals'
import { WorldPanel } from './WorldPanel'

export interface GameViewProps {
  session: Session
  world: WorldInfo
  chosenClass: ClassInfo
  name: string
}

/** How often the panels refresh. Fast enough to feel live, slow enough to be free. */
const HUD_HZ = 8

interface Toast {
  id: number
  text: string
  bad: boolean
}

export function GameView({ session, world, chosenClass, name }: GameViewProps) {
  const host = useRef<HTMLDivElement>(null)
  const scene = useRef<Scene | null>(null)

  const [ready, setReady] = useState(false)
  const [failure, setFailure] = useState<string | undefined>(undefined)
  const [chatOpen, setChatOpen] = useState(false)
  const [showDiagnostics, setShowDiagnostics] = useState(false)
  const [dead, setDead] = useState(false)
  const [toasts, setToasts] = useState<Toast[]>([])

  /**
   * Held in a ref because it is written from the input handler and read from the render loop,
   * neither of which should trigger a re-render. `lastUsed` also feeds the cooldown display,
   * which is why it is mirrored into state at the HUD's own rate rather than per press.
   */
  const cooldowns = useRef<Record<number, number>>({})
  const [cooldownView, setCooldownView] = useState<Record<number, number>>({})

  /**
   * The ability whose cooldown was started optimistically and not yet confirmed.
   *
   * The bar starts a cooldown the moment a key is pressed, which is the right lie
   * while the cast lands. When the server refuses instead, the lie outlives its
   * purpose: the button sits dark for its full cooldown over a cast that never
   * happened, and the player concludes the skill does nothing.
   */
  const pendingAbility = useRef<number | null>(null)

  /** Tiles walked, for the walk cycle. Distance rather than time, so a run does not shuffle. */
  const distance = useRef(0)

  const [hud, setHud] = useState(() => snapshotHud(session))
  const [stats, setStats] = useState<SceneStats>({ chunks: 0, sprites: 0, lights: 0, fps: 0 })
  const [composing, setComposing] = useState(false)
  const [showSheet, setShowSheet] = useState(false)
  const [showInventory, setShowInventory] = useState(false)

  /** Rebuilt only when the catalogue does, which is never within a session. */
  const itemsById = useMemo(
    () => new Map(world.items.map((item) => [item.itemId, item])),
    [world],
  )

  /**
   * The class the server says the character is, which is not necessarily the one they were
   * created as: composing at level-up replaces it.
   *
   * The HUD used to read `chosenClass` throughout, which is the creation-time pick handed down
   * from the title screen. That is correct for exactly as long as nobody levels up, after
   * which the ability bar still showed the base class's three abilities while the server was
   * refusing anything the composed class had gained.
   */
  const liveClass =
    world.classes.find((entry) => entry.classId === hud.classId) ?? chosenClass

  // --- the renderer ---------------------------------------------------------

  useEffect(() => {
    let cancelled = false
    let frame = 0

    async function boot(): Promise<void> {
      const parent = host.current
      if (parent === null) return

      let built: Scene
      try {
        built = await Scene.create(parent, apiBase())
      } catch (error) {
        if (!cancelled) {
          setFailure(
            error instanceof Error
              ? `The renderer could not start: ${error.message}`
              : 'The renderer could not start.',
          )
        }
        return
      }

      if (cancelled) {
        built.destroy()
        return
      }

      scene.current = built
      setReady(true)

      let previous = performance.now()
      const started = previous
      let lastCamera = session.position

      const loop = (): void => {
        frame = requestAnimationFrame(loop)

        const now = performance.now()
        // Clamped because a backgrounded tab produces a delta of many seconds, and feeding
        // that to the smoother would teleport the player the moment they came back.
        const delta = Math.min(0.25, (now - previous) / 1000)
        previous = now

        const store = session.store
        if (store === null) return

        session.sample(now / 1000, delta)

        const camera = session.position
        const step = Math.hypot(camera.x - lastCamera.x, camera.y - lastCamera.y)
        distance.current += step
        lastCamera = camera

        const chunks = visibleChunks(store, camera)
        // Keep memory bounded as the player walks. The unload ring is wider than the draw
        // ring so a chunk is not dropped and regenerated while pacing a boundary.
        store.pruneAround(camera, 4)

        const local = session.local
        built.render(
          store,
          {
            camera,
            local:
              local === null
                ? undefined
                : {
                    appearance: local.appearance,
                    facing: local.facing,
                    state: local.state,
                    // Measured from the drawn position rather than from held keys, so walking
                    // into a wall stops the animation as well as the movement.
                    speed: delta > 0 ? step / delta : 0,
                  },
            entities: session.entities.values(),
            chunks,
            dayPhase: session.dayPhase,
            weather: session.weather,
            biomeTint: biomeTintAt(store, camera, world),
            elapsed: (now - started) / 1000,
            distance: distance.current,
          },
          delta,
        )
      }

      frame = requestAnimationFrame(loop)
    }

    void boot()

    return () => {
      cancelled = true
      cancelAnimationFrame(frame)
      scene.current?.destroy()
      scene.current = null
    }
  }, [session, world])

  // --- the HUD's own clock --------------------------------------------------

  useEffect(() => {
    const timer = window.setInterval(() => {
      setHud(snapshotHud(session))
      setCooldownView({ ...cooldowns.current })
      const current = scene.current
      if (current !== null) setStats(current.diagnostics)
    }, 1000 / HUD_HZ)
    return () => window.clearInterval(timer)
  }, [session, world])

  // --- session events ------------------------------------------------------

  const toast = useCallback((text: string, bad = false) => {
    const entry = { id: Date.now() + Math.random(), text, bad }
    setToasts((current) => [...current.slice(-4), entry])
    window.setTimeout(() => {
      setToasts((current) => current.filter((candidate) => candidate.id !== entry.id))
    }, 2600)
  }, [])

  const useAbility = useCallback(
    (abilityId: number) => {
      const aim = aimPoint(scene.current, session)
      cooldowns.current[abilityId] = performance.now()
      pendingAbility.current = abilityId
      session.useAbility(abilityId, aim.x, aim.y)
    },
    [session],
  )

  useEffect(() => {
    const offRefused = session.on('refused', (_code, detail) => {
      const refused = pendingAbility.current
      if (refused !== null) {
        delete cooldowns.current[refused]
        pendingAbility.current = null
      }
      toast(detail, true)
    })
    const offCombat = session.on('combat', () => {
      pendingAbility.current = null
    })
    const offDied = session.on('died', () => setDead(true))
    const offRespawned = session.on('respawned', () => setDead(false))
    const offTopology = session.on('topology', (tier) =>
      toast(tier > 0 ? `The corridor widens — tier ${tier}` : 'The corridor narrows — tier 0'),
    )
    const offStatus = session.on('status', (status, detail) => {
      if (status === 'reconnecting') toast('Connection lost — reconnecting…', true)
      else if (status === 'failed') setFailure(detail ?? 'The connection failed.')
    })
    const offProgress = session.on('progress', (progression, levelled) => {
      if (levelled) toast(`Level ${progression.level}`)
      // Opened rather than only offered on the button, because the choice gates the rest of
      // the kit and a player who does not know it is waiting simply never makes it.
      if (progression.composeAvailable) setComposing(true)
    })

    return () => {
      offRefused()
      offCombat()
      offDied()
      offRespawned()
      offTopology()
      offStatus()
      offProgress()
    }
  }, [session, toast])

  // --- input ---------------------------------------------------------------

  const abilities = liveClass.abilities

  useEffect(() => {
    const held = { up: false, down: false, left: false, right: false, run: false }

    function push(): void {
      session.setInput(held)
    }

    function use(index: number): void {
      const ability = abilities[index]
      if (ability === undefined) return

      const elapsed = performance.now() - (cooldowns.current[ability.abilityId] ?? -Infinity)
      if (elapsed < ability.cooldownMs) return

      useAbility(ability.abilityId)
    }

    function onKeyDown(event: KeyboardEvent): void {
      // Chat owns the keyboard when open, and its own handler stops propagation. This is the
      // belt to that braces: a stray key while the box is open must never move the player.
      if (chatOpen) return
      if (event.repeat && event.code !== 'Tab') return

      switch (event.code) {
        case 'KeyW':
        case 'ArrowUp':
          held.up = true
          break
        case 'KeyS':
        case 'ArrowDown':
          held.down = true
          break
        case 'KeyA':
        case 'ArrowLeft':
          held.left = true
          break
        case 'KeyD':
        case 'ArrowRight':
          held.right = true
          break
        case 'ShiftLeft':
        case 'ShiftRight':
          held.run = true
          break
        case 'Digit1':
          use(0)
          return
        case 'Digit2':
          use(1)
          return
        case 'Digit3':
          use(2)
          return
        // A composed class has five abilities and only three were bound, so the two
        // the level-up granted were unreachable from the keyboard.
        case 'Digit4':
          use(3)
          return
        case 'Digit5':
          use(4)
          return
        case 'KeyI':
          setShowInventory((current) => !current)
          return
        case 'KeyC':
          setShowSheet((current) => !current)
          return
        case 'KeyF': {
          const target = targetTile(scene.current, session)
          session.harvest(Math.floor(target.x), Math.floor(target.y))
          return
        }
        case 'KeyB': {
          const target = targetTile(scene.current, session)
          session.build(Math.floor(target.x), Math.floor(target.y), 'wall_wood')
          return
        }
        case 'Enter':
          event.preventDefault()
          setChatOpen(true)
          return
        case 'Tab':
          event.preventDefault()
          setShowDiagnostics((current) => !current)
          return
        case 'Equal':
          scene.current?.setZoom((scene.current?.currentZoom ?? 2) + 1)
          return
        case 'Minus':
          scene.current?.setZoom((scene.current?.currentZoom ?? 2) - 1)
          return
        default:
          return
      }
      push()
    }

    function onKeyUp(event: KeyboardEvent): void {
      switch (event.code) {
        case 'KeyW':
        case 'ArrowUp':
          held.up = false
          break
        case 'KeyS':
        case 'ArrowDown':
          held.down = false
          break
        case 'KeyA':
        case 'ArrowLeft':
          held.left = false
          break
        case 'KeyD':
        case 'ArrowRight':
          held.right = false
          break
        case 'ShiftLeft':
        case 'ShiftRight':
          held.run = false
          break
        default:
          return
      }
      push()
    }

    function onBlur(): void {
      // Losing focus with a key down would leave the player walking into a wall forever.
      held.up = held.down = held.left = held.right = held.run = false
      push()
    }

    function onPointerMove(event: PointerEvent): void {
      pointer.x = event.clientX
      pointer.y = event.clientY
      const current = scene.current
      if (current === null) return
      const target = current.screenToTile(event.clientX, event.clientY, session.position)
      session.setInput({ facing: Math.atan2(target.y - session.position.y, target.x - session.position.x) })
    }

    window.addEventListener('keydown', onKeyDown)
    window.addEventListener('keyup', onKeyUp)
    window.addEventListener('blur', onBlur)
    window.addEventListener('pointermove', onPointerMove)

    return () => {
      window.removeEventListener('keydown', onKeyDown)
      window.removeEventListener('keyup', onKeyUp)
      window.removeEventListener('blur', onBlur)
      window.removeEventListener('pointermove', onPointerMove)
    }
  }, [session, abilities, chatOpen, useAbility])

  // --- reads for the child panels, stable so they do not re-render ----------

  const position = useCallback(() => session.position, [session])
  const entities = useCallback(() => session.entities.values(), [session])

  const place = useMemo(() => describePlace(session, world), [session, world, hud.tier])

  return (
    <div className="game">
      <div className="stage" ref={host} />

      {failure !== undefined && (
        <div className="panel banner error" role="alert">
          {failure}
        </div>
      )}
      {!ready && failure === undefined && (
        <div className="panel banner">Waking the world…</div>
      )}

      <div className="hud">
        <Vitals
          name={name}
          className={liveClass.name}
          level={hud.level}
          health={hud.health}
          resource={hud.resource}
          maxHealth={hud.loadout.maxHealth}
          maxResource={hud.loadout.maxResource}
          experience={hud.experience}
          nextLevelAt={hud.nextLevelAt}
          onCompose={hud.composeAvailable ? () => setComposing(true) : undefined}
        />

        <WorldPanel
          place={place}
          dayPhase={hud.dayPhase}
          weather={hud.weather}
          population={hud.population}
          tier={hud.tier}
          maxTier={MAX_TIER}
          latencyMs={hud.latencyMs}
          devControls={world.devControls}
          onTier={(tier) => {
            // Both paths exist because the WebSocket route only works while connected and the
            // HTTP one works even before the first snapshot lands.
            session.requestTier(tier)
            void forceTier(tier)
          }}
        />

        <Chat
          lines={hud.chat}
          open={chatOpen}
          onOpen={() => setChatOpen(true)}
          onClose={() => setChatOpen(false)}
          onSay={(channel, text) => session.say(channel, text)}
        />

        <Abilities
          abilities={abilities}
          lastUsed={cooldownView}
          resource={hud.resource}
          maxResource={hud.loadout.maxResource}
          onUse={useAbility}
        />

        <div className="hud-sheets">
          {showSheet && (
            <CharacterSheet
              name={name}
              characterClass={liveClass}
              level={hud.level}
              experience={hud.experience}
              nextLevelAt={hud.nextLevelAt}
              loadout={hud.loadout}
              slots={world.equipmentSlots}
              items={itemsById}
              onUnequip={(slot) => session.unequip(slot)}
              onEquipIndex={(index) => session.equip(index)}
              onClose={() => setShowSheet(false)}
            />
          )}
          {showInventory && (
            <InventoryPanel
              loadout={hud.loadout}
              items={itemsById}
              onEquip={(index) => session.equip(index)}
              onUse={(index) => session.useItem(index)}
              onDrop={(index) => session.dropItem(index)}
              onClose={() => setShowInventory(false)}
            />
          )}
        </div>

        <div className="hud-toggles">
          <button
            type="button"
            className={showSheet ? 'on' : undefined}
            onClick={() => setShowSheet((current) => !current)}
          >
            Character <kbd>C</kbd>
          </button>
          <button
            type="button"
            className={showInventory ? 'on' : undefined}
            onClick={() => setShowInventory((current) => !current)}
          >
            Pack <kbd>I</kbd>
          </button>
        </div>

        <Minimap store={session.store} position={position} entities={entities} place={place} />
      </div>

      <CombatNumbers session={session} scene={() => scene.current} />

      {showDiagnostics && (
        <Diagnostics
          scene={stats}
          chunks={session.store?.stats() ?? { loaded: 0, active: 0, overlaid: 0, pending: 0 }}
          pendingInputs={session.predictor?.pendingCount ?? 0}
          correctionTiles={session.predictor?.stats.lastErrorTiles ?? 0}
          latencyMs={hud.latencyMs}
          clockOffset={hud.clockOffset}
          topologyVersion={hud.topologyVersion}
          entities={session.entities.size}
          position={session.position}
        />
      )}

      <div className="toasts" aria-live="polite">
        {toasts.map((entry) => (
          <div key={entry.id} className={`toast${entry.bad ? ' bad' : ''}`}>
            {entry.text}
          </div>
        ))}
      </div>

      {composing && (
        <Compose
          current={liveClass}
          classes={world.classes}
          onChoose={(half) => {
            session.compose(half)
            setComposing(false)
          }}
          onDismiss={() => setComposing(false)}
        />
      )}

      {dead && (
        <div className="death">
          <div className="panel death-card">
            <h2>You have fallen</h2>
            <p className="muted">
              Returning to {world.hubs[0]?.name ?? 'the hub'} in a few seconds.
            </p>
            <p className="muted" style={{ fontSize: '8pt', marginTop: 8 }}>
              {RESPAWN_DELAY_SECONDS}s respawn · no durability loss in this build
            </p>
          </div>
        </div>
      )}
    </div>
  )
}

/** The cursor, so aiming does not need to plumb a pointer through the render loop. */
const pointer = { x: -1, y: -1 }

/** Where an ability is aimed: the cursor if it has moved, otherwise just ahead of the player. */
function aimPoint(scene: Scene | null, session: Session): { x: number; y: number } {
  const from = session.position
  if (scene === null || pointer.x < 0) {
    const facing = session.local?.facing ?? 0
    return { x: from.x + Math.cos(facing) * 3, y: from.y + Math.sin(facing) * 3 }
  }
  return scene.screenToTile(pointer.x, pointer.y, from)
}

/** The tile a build or harvest applies to: the cursor, clamped to arm's reach. */
function targetTile(scene: Scene | null, session: Session): { x: number; y: number } {
  const from = session.position
  const aim = aimPoint(scene, session)
  const dx = aim.x - from.x
  const dy = aim.y - from.y
  const distance = Math.hypot(dx, dy)
  // Clamped client-side as a courtesy. The server checks `BUILD_RANGE_TILES` itself, and a
  // refusal is what the player sees if this is wrong.
  if (distance <= 3) return aim
  return { x: from.x + (dx / distance) * 3, y: from.y + (dy / distance) * 3 }
}

interface HudSnapshot {
  health: number
  resource: number
  level: number
  experience: number
  nextLevelAt: number
  classId: number
  composeAvailable: boolean
  dayPhase: number
  weather: number
  population: number
  tier: number
  topologyVersion: number
  latencyMs: number
  clockOffset: number
  chat: readonly ChatLine[]
  loadout: Loadout
}

function snapshotHud(session: Session): HudSnapshot {
  return {
    health: session.local?.health ?? 1,
    resource: session.local?.resource ?? 1,
    level: session.progression.level,
    experience: session.progression.experience,
    nextLevelAt: session.progression.nextLevelAt,
    classId: session.progression.classId,
    composeAvailable: session.progression.composeAvailable,
    dayPhase: session.dayPhase,
    weather: session.weather,
    // The entity map holds everyone but the local player, who is always present.
    population: session.entities.size + 1,
    tier: session.currentTier,
    topologyVersion: session.topologyVersion,
    latencyMs: session.clock.latencyMs,
    clockOffset: session.clock.offsetSeconds,
    // Copied rather than referenced: the session mutates the array in place, so passing it
    // through would give React the same reference and it would skip the update.
    chat: [...session.chat],
    // Replaced wholesale on every inventory packet, so the reference is the change
    // signal and there is nothing to copy.
    loadout: session.loadout,
  }
}

/** A readable name for where the player is: the hub they are in, or the corridor. */
function describePlace(session: Session, world: WorldInfo): string {
  const at = session.position
  for (const hub of world.hubs) {
    if (Math.max(Math.abs(at.x - hub.x), Math.abs(at.y - hub.y)) <= hub.radiusTiles) {
      return hub.name
    }
  }
  return 'The corridor'
}

/**
 * The biome tint under the camera, for the renderer's colour grading.
 *
 * Read from the store's generator rather than from the server: the biome is a pure function of
 * position and seed, which both sides compute identically, so asking would be a round trip for
 * something already known.
 */
function biomeTintAt(
  store: NonNullable<Session['store']>,
  camera: { x: number; y: number },
  world: WorldInfo,
): [number, number, number] {
  const biome = store.biomeAt(camera.x, camera.y)
  const profile = world.biomes.find((candidate) => candidate.biome === biome)
  // 236 is the neutral tint: `tintFromBytes` divides by it, so this scales the scene by 1.
  return profile?.ambientTint ?? [236, 236, 236]
}
