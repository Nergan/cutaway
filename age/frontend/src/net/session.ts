/**
 * The live game session: one WebSocket, the entity table, and the input pump.
 *
 * This is where the client's pieces meet. It owns the socket, feeds snapshots into the
 * predictor for the local player and into tracks for everyone else, and hands the renderer
 * a table of poses to draw. It deliberately knows nothing about Pixi or React: the UI
 * subscribes to events, and the renderer reads state, so both can be replaced without
 * touching the protocol handling.
 *
 * Two rules keep the failure modes boring. Input is sent on a fixed cadence rather than per
 * animation frame, so a 144 Hz machine does not flood the server that a 30 Hz machine
 * trickles to. And a socket that closes for any reason other than an explicit leave is
 * retried with backoff, because a demo that dies on the first blip looks broken.
 */

import {
  BASE_MAX_HEALTH,
  BASE_MAX_RESOURCE,
  CONNECTION_TIMEOUT_SECONDS,
  ENTITY_PLAYER,
  HEARTBEAT_INTERVAL_SECONDS,
  INPUT_HZ,
  PROTOCOL_VERSION,
  WALK_SPEED_TILES_S,
} from '../domain/constants'
import { ChunkStore } from '../world/chunkStore'
import { buildWorld, type WorldLayout } from '../world/coordinates'
import { WorldGenerator } from '../world/generator'
import { ClockSync, Track, type Pose } from '../sim/interpolation'
import { moveAxis } from '../sim/movement'
import { Predictor } from '../sim/prediction'
import {
  BUILD_HARVEST,
  BUILD_PLACE,
  ERROR_VERSION_MISMATCH,
  FIELD_APPEARANCE,
  FIELD_FACING,
  FIELD_HEALTH,
  FIELD_POSITION,
  FIELD_RESOURCE,
  FIELD_STATE,
  INPUT_DOWN,
  INPUT_LEFT,
  INPUT_RIGHT,
  INPUT_RUN,
  INPUT_UP,
  INVENTORY_DROP,
  INVENTORY_EQUIP,
  INVENTORY_UNEQUIP,
  INVENTORY_USE,
  ProtocolError,
  STATE_ALIVE,
  decodeServerPacket,
  encodeAction,
  encodeBuild,
  encodeChat,
  encodeCompose,
  encodeDevTier,
  encodeHello,
  encodeInput,
  encodeInventory,
  encodePing,
  encodeReady,
  type Appearance,
  type Combat,
  type Inventory,
  type ServerPacket,
} from './wire'

export interface RemoteEntity {
  entityId: number
  kind: number
  archetype: number
  name: string
  level: number
  appearance: Appearance
  health: number
  resource: number
  state: number
  track: Track
  /** Last interpolated pose, refreshed once per frame by {@link Session.sample}. */
  pose: Pose
  /**
   * Ground distance covered since spawn, in tiles. Drives the walk cycle.
   *
   * Accumulated from the interpolated positions rather than derived from the reported
   * speed. The renderer used to be handed `speed * elapsed`, which is only the distance
   * travelled if the speed has been constant since the client started: a walker who
   * changed pace at all made the product jump by tens of tiles, so the cycle picked a
   * random frame each time and the legs juddered instead of walking.
   */
  travelled: number
}

export interface LocalPlayer {
  entityId: number
  name: string
  classId: number
  appearance: Appearance
  health: number
  resource: number
  state: number
  facing: number
}

/**
 * The local character's progression, as the server last stated it.
 *
 * Separate from {@link LocalPlayer} because it arrives on its own packet and changes
 * on its own schedule: vitals move every tick, a level moves a handful of times a
 * session.
 */
export interface Progression {
  level: number
  experience: number
  nextLevelAt: number
  classId: number
  /** Whether the level-up class choice is waiting to be made (GDD 6.3). */
  composeAvailable: boolean
  abilityIds: readonly number[]
}

/**
 * What the character is carrying and wearing, and what it adds up to.
 *
 * Private to its owner, so it lives beside {@link Session.progression} rather than on
 * an entity: no remote entity ever has one.
 */
export type Loadout = Omit<Inventory, 'kind'>

export interface ChatLine {
  senderId: number
  senderName: string
  channel: number
  text: string
  receivedAt: number
}

export type SessionStatus =
  | 'idle'
  | 'connecting'
  | 'handshaking'
  | 'playing'
  | 'reconnecting'
  | 'failed'

export interface SessionEvents {
  status: (status: SessionStatus, detail?: string) => void
  chat: (line: ChatLine) => void
  combat: (event: Combat) => void
  /** A recoverable server refusal: out of range, on cooldown, no material. */
  refused: (code: number, detail: string) => void
  topology: (tier: number, version: number) => void
  /** Level, experience, or class changed. ``levelled`` distinguishes a level-up. */
  progress: (progression: Progression, levelled: boolean) => void
  /** The pack or the loadout changed. */
  inventory: (loadout: Loadout) => void
  /** Emitted once the welcome packet has landed and the world is generatable. */
  ready: (layout: WorldLayout) => void
  died: () => void
  respawned: () => void
}

type Listener<K extends keyof SessionEvents> = SessionEvents[K]

export interface InputState {
  up: boolean
  down: boolean
  left: boolean
  right: boolean
  run: boolean
  /** Aim direction in radians, from the pointer. */
  facing: number
}

/** Backoff schedule for reconnects, in milliseconds. Capped rather than exponential forever. */
const RECONNECT_DELAYS_MS = [500, 1000, 2000, 4000, 8000]

export class Session {
  status: SessionStatus = 'idle'

  readonly clock = new ClockSync()
  readonly entities = new Map<number, RemoteEntity>()
  readonly chat: ChatLine[] = []

  local: LocalPlayer | null = null
  predictor: Predictor | null = null
  store: ChunkStore | null = null
  layout: WorldLayout | null = null

  /**
   * Seeded so the HUD has a shape to draw before the first progress packet lands.
   * The empty kit is honest: pressing a button before the server has named one would
   * only be refused.
   */
  progression: Progression = {
    level: 1,
    experience: 0,
    nextLevelAt: 100,
    classId: 0,
    composeAvailable: false,
    abilityIds: [],
  }

  /**
   * Seeded with the nominal pools rather than with zero, because the vitals panel
   * divides by them from the first frame and a maximum of zero would read as a dead
   * character until the first inventory packet landed.
   */
  loadout: Loadout = {
    capacity: 0,
    stacks: [],
    equipped: [],
    maxHealth: BASE_MAX_HEALTH,
    maxResource: BASE_MAX_RESOURCE,
    bonusDamage: 0,
    moveSpeed: WALK_SPEED_TILES_S,
  }

  worldSeed = 0n
  topologyVersion = 0
  currentTier = 0
  dayPhase = 0
  weather = 0
  serverTick = 0

  /** Diagnostics for the debug overlay. */
  readonly stats = {
    bytesIn: 0,
    bytesOut: 0,
    packetsIn: 0,
    snapshotsIn: 0,
    lastSnapshotAt: 0,
    reconnects: 0,
  }

  private socket: WebSocket | null = null
  private inputTimer: ReturnType<typeof setInterval> | null = null
  private heartbeatTimer: ReturnType<typeof setInterval> | null = null
  private lastInputAt = 0
  private lastPacketAt = 0
  private reconnectAttempt = 0
  private leaving = false
  private input: InputState = { up: false, down: false, left: false, right: false, run: false, facing: 0 }

  private readonly listeners: { [K in keyof SessionEvents]: Set<Listener<K>> } = {
    status: new Set(),
    chat: new Set(),
    combat: new Set(),
    refused: new Set(),
    topology: new Set(),
    progress: new Set(),
    inventory: new Set(),
    ready: new Set(),
    died: new Set(),
    respawned: new Set(),
  }

  constructor(
    private readonly url: string,
    private profile: { name: string; classId: number; appearance: Appearance },
  ) {}

  // --- events ---------------------------------------------------------------

  on<K extends keyof SessionEvents>(event: K, listener: Listener<K>): () => void {
    this.listeners[event].add(listener)
    return () => {
      this.listeners[event].delete(listener)
    }
  }

  private emit<K extends keyof SessionEvents>(event: K, ...args: Parameters<Listener<K>>): void {
    for (const listener of this.listeners[event]) {
      // One misbehaving listener must not stop the others or kill the socket handler.
      try {
        ;(listener as (...a: Parameters<Listener<K>>) => void)(...args)
      } catch (error) {
        console.error(`age: a ${event} listener threw`, error)
      }
    }
  }

  private setStatus(status: SessionStatus, detail?: string): void {
    this.status = status
    this.emit('status', status, detail)
  }

  // --- lifecycle ------------------------------------------------------------

  connect(): void {
    this.leaving = false
    this.openSocket()
  }

  private openSocket(): void {
    this.setStatus(this.reconnectAttempt > 0 ? 'reconnecting' : 'connecting')

    const socket = new WebSocket(this.url)
    socket.binaryType = 'arraybuffer'
    this.socket = socket

    socket.onopen = () => {
      this.setStatus('handshaking')
      this.send(encodeHello(this.profile.name, this.profile.classId, this.profile.appearance))
      this.lastPacketAt = performance.now() / 1000
    }

    socket.onmessage = (event) => {
      if (!(event.data instanceof ArrayBuffer)) return
      const bytes = new Uint8Array(event.data)
      this.stats.bytesIn += bytes.byteLength
      this.stats.packetsIn += 1
      this.lastPacketAt = performance.now() / 1000

      try {
        this.handle(decodeServerPacket(bytes))
      } catch (error) {
        if (error instanceof ProtocolError) {
          // A malformed frame means this client and this server disagree about the
          // format. Continuing would mis-parse everything after it.
          console.error('age: malformed packet', error.message)
          this.fail('The server sent something this client could not read.')
        } else {
          throw error
        }
      }
    }

    socket.onclose = (event) => {
      this.stopPumps()
      if (this.leaving) {
        this.setStatus('idle')
        return
      }
      // 1008 is the policy-violation code the server uses to refuse a handshake.
      // Retrying that would loop forever against the same refusal.
      if (event.code === 1008) {
        this.fail(event.reason || 'The server refused the connection.')
        return
      }
      this.scheduleReconnect()
    }

    socket.onerror = () => {
      // Always followed by onclose, which does the actual handling.
    }
  }

  private scheduleReconnect(): void {
    const delay = RECONNECT_DELAYS_MS[Math.min(this.reconnectAttempt, RECONNECT_DELAYS_MS.length - 1)]
    this.reconnectAttempt += 1
    this.stats.reconnects += 1
    this.setStatus('reconnecting', `Retrying in ${Math.round(delay / 1000)}s`)
    setTimeout(() => {
      if (!this.leaving) this.openSocket()
    }, delay)
  }

  private fail(detail: string): void {
    this.leaving = true
    this.stopPumps()
    this.setStatus('failed', detail)
  }

  leave(): void {
    this.leaving = true
    this.stopPumps()
    this.socket?.close(1000, 'leaving')
    this.socket = null
    this.setStatus('idle')
  }

  private stopPumps(): void {
    if (this.inputTimer !== null) clearInterval(this.inputTimer)
    if (this.heartbeatTimer !== null) clearInterval(this.heartbeatTimer)
    this.inputTimer = null
    this.heartbeatTimer = null
  }

  private startPumps(): void {
    this.stopPumps()

    // Fixed cadence, not per frame: a 144 Hz machine would otherwise send five times the
    // input a 30 Hz one does, and the server's anti-cheat measures speed per command.
    this.inputTimer = setInterval(() => this.pumpInput(), 1000 / INPUT_HZ)

    this.heartbeatTimer = setInterval(() => {
      this.send(encodePing(performance.now() / 1000))

      // The server drops a silent client; this is the mirror of that, so a connection
      // that has gone away without closing is noticed rather than waited on forever.
      const silence = performance.now() / 1000 - this.lastPacketAt
      if (silence > CONNECTION_TIMEOUT_SECONDS) {
        console.warn(`age: ${silence.toFixed(1)}s without a packet, reconnecting`)
        this.socket?.close(4000, 'timeout')
      }
    }, HEARTBEAT_INTERVAL_SECONDS * 1000)
  }

  private send(payload: Uint8Array): void {
    if (this.socket?.readyState !== WebSocket.OPEN) return
    this.socket.send(payload)
    this.stats.bytesOut += payload.byteLength
  }

  // --- input ----------------------------------------------------------------

  setInput(input: Partial<InputState>): void {
    this.input = { ...this.input, ...input }
  }

  private pumpInput(): void {
    if (this.predictor === null || this.local === null) return

    const now = performance.now() / 1000
    const deltaTime = this.lastInputAt === 0 ? 1 / INPUT_HZ : now - this.lastInputAt
    this.lastInputAt = now

    let buttons = 0
    if (this.input.up) buttons |= INPUT_UP
    if (this.input.down) buttons |= INPUT_DOWN
    if (this.input.left) buttons |= INPUT_LEFT
    if (this.input.right) buttons |= INPUT_RIGHT
    if (this.input.run) buttons |= INPUT_RUN

    const axis = moveAxis(buttons, INPUT_UP, INPUT_DOWN, INPUT_LEFT, INPUT_RIGHT)
    const sequence = this.predictor.push(axis, this.input.run, deltaTime)
    const predicted = this.predictor.predicted

    this.local.facing = this.input.facing

    this.send(
      encodeInput({
        sequence,
        topologyVersion: this.topologyVersion,
        buttons,
        facing: this.input.facing,
        predictedX: predicted.x,
        predictedY: predicted.y,
        deltaTime,
      }),
    )
  }

  useAbility(abilityId: number, targetX: number, targetY: number, targetEntity = 0): void {
    if (this.predictor === null) return
    // Abilities are not predicted: a mispredicted hit that the server refuses is far worse
    // than a hundred milliseconds of delay before the effect appears.
    this.send(
      encodeAction(0, this.topologyVersion, abilityId, targetX, targetY, targetEntity),
    )
  }

  build(tileX: number, tileY: number, material: string): void {
    this.send(encodeBuild(this.topologyVersion, BUILD_PLACE, tileX, tileY, material))
  }

  harvest(tileX: number, tileY: number): void {
    this.send(encodeBuild(this.topologyVersion, BUILD_HARVEST, tileX, tileY, ''))
  }

  say(channel: number, text: string): void {
    const trimmed = text.trim()
    if (trimmed.length > 0) this.send(encodeChat(channel, trimmed))
  }

  /** Force a tier change. Only honoured when the server has dev controls enabled. */
  requestTier(tier: number): void {
    this.send(encodeDevTier(tier))
  }

  /**
   * Take a second half, becoming the pairing's class (GDD 6.3).
   *
   * Nothing is applied locally: the server owns the class, and predicting a
   * composition would mean showing a kit that a refusal then takes away.
   */
  compose(half: number): void {
    this.send(encodeCompose(half))
  }

  /**
   * Move one slot: wear it, take it off, use it, or throw it away.
   *
   * Nothing is applied locally. The server answers every one of these with a fresh
   * snapshot of the whole pack, so predicting the result would only be a chance to
   * disagree with the answer that is already on its way.
   */
  equip(index: number): void {
    this.send(encodeInventory(INVENTORY_EQUIP, index))
  }

  unequip(slot: number): void {
    this.send(encodeInventory(INVENTORY_UNEQUIP, slot))
  }

  useItem(index: number): void {
    this.send(encodeInventory(INVENTORY_USE, index))
  }

  dropItem(index: number, count = 1): void {
    this.send(encodeInventory(INVENTORY_DROP, index, count))
  }

  // --- packet handling ------------------------------------------------------

  private handle(packet: ServerPacket): void {
    switch (packet.kind) {
      case 'welcome': {
        if (packet.protocolVersion !== PROTOCOL_VERSION) {
          this.fail('This page is out of date. Reload to get the current client.')
          return
        }

        this.worldSeed = packet.worldSeed
        this.topologyVersion = packet.topologyVersion
        this.currentTier = packet.currentTier

        const layout = buildWorld(packet.edgeId, 8)
        this.layout = layout

        // Everything downstream is rebuilt rather than reused: on a reconnect the seed
        // could differ, and a stale generator would produce terrain from the old world.
        const generator = new WorldGenerator(packet.worldSeed)
        this.store = new ChunkStore(generator, layout.hubs, layout.edges)
        this.predictor = new Predictor(this.store.walkable)
        this.predictor.reset(packet.spawnX, packet.spawnY)

        this.local = {
          entityId: packet.entityId,
          name: this.profile.name,
          classId: this.profile.classId,
          appearance: this.profile.appearance,
          // Ratios, not bytes: the wire quantises vitals to a byte but the client works in
          // 0..1 throughout. Full, because that is what the server does on join and on
          // respawn — snapshots only carry fields that changed, so anything less here would
          // survive until the first point of damage and read as a wounded healthy player.
          health: 1,
          resource: 1,
          // Alive, for the same reason the vitals start full: the welcome packet does not
          // carry a state byte, and a zero here means "dead" to everything downstream. It
          // used to be zero, and the local player spent the whole session drawn greyed out
          // in the single-frame hurt pose.
          state: STATE_ALIVE,
          facing: 0,
        }

        this.reconnectAttempt = 0
        this.emit('ready', layout)

        // Tell the server we have the world before asking for snapshots, so the first one
        // does not arrive describing chunks we cannot draw yet.
        this.send(encodeReady())
        this.setStatus('playing')
        this.startPumps()
        break
      }

      case 'snapshot': {
        this.serverTick = packet.tick
        this.dayPhase = packet.dayPhase
        this.weather = packet.weather
        this.stats.snapshotsIn += 1
        this.stats.lastSnapshotAt = performance.now() / 1000

        if (packet.topologyVersion !== this.topologyVersion) {
          // The topology packet may not have arrived yet; adopt the version so inputs are
          // not rejected as stale in the meantime.
          this.topologyVersion = packet.topologyVersion
        }

        const localTime = this.clock.toLocal(packet.serverTime)

        for (const delta of packet.deltas) {
          if (this.local !== null && delta.entityId === this.local.entityId) {
            this.applyLocal(delta, packet.acknowledgedInput)
            continue
          }

          const entity = this.entities.get(delta.entityId)
          if (entity === undefined) continue // not yet spawned; the spawn packet is coming

          if (delta.x !== undefined && delta.y !== undefined) {
            entity.track.push({
              time: localTime,
              x: delta.x,
              y: delta.y,
              facing: delta.facing ?? entity.pose.facing,
            })
          }
          if (delta.health !== undefined) entity.health = delta.health
          if (delta.resource !== undefined) entity.resource = delta.resource
          if (delta.state !== undefined) entity.state = delta.state
          if (delta.appearance !== undefined) entity.appearance = delta.appearance
        }
        break
      }

      case 'spawn': {
        // The viewer is inside their own area of interest, so the server introduces us to
        // ourselves. Take the vitals — they are authoritative — but stay out of the entity
        // table: everything downstream assumes it holds only other people, and a copy of
        // us in there would be drawn a second time, interpolated and lagging behind the
        // predicted body.
        if (this.local !== null && packet.entityId === this.local.entityId) {
          this.local.health = packet.health
          break
        }

        const pose: Pose = { x: packet.x, y: packet.y, facing: packet.facing, speed: 0 }
        const track = new Track()
        track.push({ time: this.clock.toLocal(performance.now() / 1000), ...pose })
        this.entities.set(packet.entityId, {
          entityId: packet.entityId,
          kind: packet.entityKind,
          archetype: packet.archetype,
          name: packet.name,
          level: packet.level,
          appearance: packet.appearance,
          health: packet.health,
          resource: 1,
          travelled: 0,
          state: packet.state,
          track,
          pose,
        })
        break
      }

      case 'despawn':
        this.entities.delete(packet.entityId)
        break

      case 'topology':
        this.topologyVersion = packet.topologyVersion
        this.currentTier = packet.currentTier
        this.store?.setTopology(packet.activeChunks, packet.retiringChunks)
        this.emit('topology', packet.currentTier, packet.topologyVersion)
        break

      case 'combat':
        this.emit('combat', packet)
        break

      case 'chat': {
        const line: ChatLine = {
          senderId: packet.senderId,
          senderName: packet.senderName,
          channel: packet.channel,
          text: packet.text,
          receivedAt: performance.now() / 1000,
        }
        this.chat.push(line)
        if (this.chat.length > 128) this.chat.shift()
        this.emit('chat', line)
        break
      }

      case 'tiles':
        this.store?.applyTiles(packet.chunkKey, packet.changes)
        break

      case 'pong':
        this.clock.observePong(packet.clientTime, packet.serverTime, performance.now() / 1000)
        break

      case 'progress': {
        const levelled = packet.level > this.progression.level
        this.progression = {
          level: packet.level,
          experience: packet.experience,
          nextLevelAt: packet.nextLevelAt,
          classId: packet.classId,
          composeAvailable: packet.composeAvailable,
          abilityIds: packet.abilityIds,
        }
        // The local player's class travels here rather than on the snapshot, so the
        // character sheet and the ability bar follow a composition immediately.
        if (this.local !== null) this.local.classId = packet.classId
        this.emit('progress', this.progression, levelled)
        break
      }

      case 'inventory': {
        const { kind: _kind, ...loadout } = packet
        this.loadout = loadout
        this.emit('inventory', this.loadout)
        break
      }

      case 'error':
        if (packet.code === ERROR_VERSION_MISMATCH) {
          this.fail(packet.detail || 'This page is out of date. Reload to get the current client.')
        } else {
          // Everything else is a refusal of one action, not a failure of the session:
          // out of range, on cooldown, no material, rate limited.
          this.emit('refused', packet.code, packet.detail)
        }
        break
    }
  }

  private applyLocal(
    delta: { fields: number; x?: number; y?: number; health?: number; resource?: number; state?: number },
    acknowledged: number,
  ): void {
    if (this.local === null || this.predictor === null) return

    if (delta.fields & FIELD_POSITION && delta.x !== undefined && delta.y !== undefined) {
      this.predictor.reconcile({ x: delta.x, y: delta.y }, acknowledged)
    }

    const wasDead = this.local.health <= 0
    if (delta.fields & FIELD_HEALTH && delta.health !== undefined) this.local.health = delta.health
    if (delta.fields & FIELD_RESOURCE && delta.resource !== undefined) {
      this.local.resource = delta.resource
    }
    if (delta.fields & FIELD_STATE && delta.state !== undefined) this.local.state = delta.state
    if (delta.fields & (FIELD_FACING | FIELD_APPEARANCE)) {
      // Facing is client-authoritative and appearance never changes mid-session, so both
      // are ignored for the local player: the server is only echoing them back.
    }

    const isDead = this.local.health <= 0
    if (!wasDead && isDead) this.emit('died')
    if (wasDead && !isDead) this.emit('respawned')
  }

  // --- per-frame ------------------------------------------------------------

  /**
   * Refresh every remote entity's pose for this frame, and ease the local correction.
   *
   * Called once per rendered frame. Poses are cached on the entity rather than recomputed
   * per draw call, because the renderer reads a position several times — sprite, shadow,
   * health bar, name plate — and interpolating four times would be four searches.
   */
  sample(now: number, frameTime: number): void {
    this.predictor?.advanceSmoothing(frameTime)

    const renderTime = this.clock.renderTime(now)
    for (const entity of this.entities.values()) {
      const pose = entity.track.poseAt(renderTime)
      if (pose !== undefined) {
        // A teleport — a respawn, or a snap after a long stall — must not be counted, or
        // the walk cycle spins through a hundred frames in one tick.
        const step = Math.hypot(pose.x - entity.pose.x, pose.y - entity.pose.y)
        if (step < 2) entity.travelled += step
        entity.pose = pose
      }
      entity.track.prune(renderTime - 2)
    }

    // Stream terrain around wherever the camera is, which is the player.
    const position = this.predictor?.position
    if (position !== undefined && this.store !== null) {
      for (const address of this.store.addressesAround(position, 3)) this.store.load(address)
    }
  }

  /** The local player's drawn position, or the origin before the world arrives. */
  get position(): { x: number; y: number } {
    return this.predictor?.position ?? { x: 0, y: 0 }
  }

  get players(): RemoteEntity[] {
    return [...this.entities.values()].filter((entity) => entity.kind === ENTITY_PLAYER)
  }
}
