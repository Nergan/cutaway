"""The room: the tick loop, the connection registry, and packet fan-out.

This is where the synchronous simulation meets asyncio. The split is deliberate and
it is the most important structural decision in the presentation layer:

:class:`~age.application.simulation.Simulation` is synchronous and knows nothing
about sockets. This class owns the loop, the sockets, and the send queues.

That means a slow client cannot slow the world down. Sends are queued per connection
and drained by a per-connection writer task; a client that stops reading fills its
queue and gets dropped, while the tick keeps its cadence.

The loop uses an absolute deadline rather than sleeping for a fixed interval.
Sleeping for the interval accumulates every scheduling delay, and a 30 Hz loop built
that way drifts to 26 Hz under load without anything looking wrong.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field

from ..application.chat import ChatDecision
from ..application.interest import ClientUpdate
from ..application.simulation import Simulation, TickReport
from ..domain.constants import (
    CHANNEL_SYSTEM,
    CHAT_PROXIMITY_RADIUS_TILES,
    SNAPSHOT_INTERVAL_SECONDS,
    TICK_SECONDS,
)
from ..domain.entities import EntityId
from ..infrastructure import wire
from .connection import Connection

logger = logging.getLogger(__name__)

# How far behind the world a tick may fall before the loop stops trying to catch up.
# Replaying a long backlog at full speed would teleport everyone; skipping to the
# present is the honest recovery, and it is logged.
MAX_CATCHUP_TICKS = 5

# Simulation work above this leaves no room to warm a chunk. Half the tick budget:
# below it the world is idling and can afford to overrun; above it, it cannot.
WARMUP_TICK_BUDGET_MS = TICK_SECONDS * 1000.0 * 0.5


@dataclass(slots=True)
class RoomStats:
    """Rolling counters, for the debug endpoint and the client's diagnostics."""

    ticks: int = 0
    snapshots: int = 0
    dropped_connections: int = 0
    slow_ticks: int = 0
    last_tick_ms: float = 0.0
    peak_tick_ms: float = 0.0
    bytes_sent: int = 0
    # Chunks generated in the loop's spare time, and ticks that had no room to. The
    # ratio is the one number that says whether the world can keep up with itself.
    chunks_warmed: int = 0
    warmups_skipped: int = 0
    tick_ms_window: list[float] = field(default_factory=list)

    def record_tick(self, elapsed_ms: float) -> None:
        self.ticks += 1
        self.last_tick_ms = elapsed_ms
        self.peak_tick_ms = max(self.peak_tick_ms, elapsed_ms)
        if elapsed_ms > TICK_SECONDS * 1000.0:
            self.slow_ticks += 1
        self.tick_ms_window.append(elapsed_ms)
        if len(self.tick_ms_window) > 120:
            del self.tick_ms_window[0]

    @property
    def average_tick_ms(self) -> float:
        window = self.tick_ms_window
        return sum(window) / len(window) if window else 0.0

    def snapshot(self) -> dict[str, object]:
        return {
            "ticks": self.ticks,
            "snapshots": self.snapshots,
            "droppedConnections": self.dropped_connections,
            "slowTicks": self.slow_ticks,
            "lastTickMs": round(self.last_tick_ms, 3),
            "averageTickMs": round(self.average_tick_ms, 3),
            "peakTickMs": round(self.peak_tick_ms, 3),
            "bytesSent": self.bytes_sent,
        }


class Room:
    """Runs one world and everyone connected to it."""

    __slots__ = (
        "simulation",
        "max_clients",
        "stats",
        "_connections",
        "_by_entity",
        "_task",
        "_running",
    )

    def __init__(self, simulation: Simulation, *, max_clients: int) -> None:
        self.simulation = simulation
        self.max_clients = max_clients
        self.stats = RoomStats()
        self._connections: dict[str, Connection] = {}
        self._by_entity: dict[EntityId, Connection] = {}
        self._task: asyncio.Task[None] | None = None
        self._running = False

    # --- lifecycle ----------------------------------------------------------

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop(), name="age-simulation")
        logger.info("Age world running at %.0f Hz", 1.0 / TICK_SECONDS)

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        for connection in list(self._connections.values()):
            await self.detach(connection, code=1001, reason="The world is shutting down.")

        await self.simulation.flush()

    @property
    def is_full(self) -> bool:
        return len(self._connections) >= self.max_clients

    @property
    def population(self) -> int:
        return len(self._connections)

    # --- connection registry -------------------------------------------------

    def attach(self, connection: Connection) -> None:
        self._connections[connection.session_id] = connection

    def bind_entity(self, connection: Connection, entity_id: EntityId) -> None:
        """Associate a connection with its entity, once the character exists."""
        connection.entity_id = entity_id
        self._by_entity[entity_id] = connection

    async def detach(
        self, connection: Connection, *, code: int = 1000, reason: str = ""
    ) -> None:
        """Remove a connection, persist its character, and tell everyone else."""
        self._connections.pop(connection.session_id, None)
        if connection.entity_id is not None:
            self._by_entity.pop(connection.entity_id, None)

        self.simulation.forget(connection.session_id)
        entity_id = await self.simulation.sessions.leave(connection.session_id)

        if entity_id is not None:
            frame = wire.encode_despawn(entity_id, wire.DESPAWN_DISCONNECTED)
            for other in self._connections.values():
                if entity_id in other.known_entity_ids:
                    other.enqueue(frame)

        await connection.close(code, reason)

    # --- the loop -----------------------------------------------------------

    async def _loop(self) -> None:
        """Fixed-cadence tick with an absolute deadline."""
        next_tick = time.perf_counter()
        next_snapshot = next_tick

        try:
            while self._running:
                now = time.perf_counter()
                delay = next_tick - now
                if delay > 0:
                    await asyncio.sleep(delay)

                behind = int((time.perf_counter() - next_tick) / TICK_SECONDS)
                if behind > MAX_CATCHUP_TICKS:
                    logger.warning(
                        "Simulation fell %d ticks behind; skipping to the present.", behind
                    )
                    next_tick = time.perf_counter()
                    next_snapshot = next_tick

                started = time.perf_counter()
                report = self.simulation.tick()
                await self._dispatch(report)

                if started >= next_snapshot:
                    await self._broadcast_snapshots()
                    next_snapshot += SNAPSHOT_INTERVAL_SECONDS
                    if next_snapshot < started:
                        next_snapshot = started + SNAPSHOT_INTERVAL_SECONDS

                if self.simulation.flush_due:
                    await self.simulation.flush()

                self.stats.record_tick((time.perf_counter() - started) * 1000.0)
                next_tick += TICK_SECONDS
                self._warm_up()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("The simulation loop died; the room is no longer ticking.")
            self._running = False

    def _warm_up(self) -> None:
        """Build one queued chunk, between ticks, when the world can spare it.

        A chunk costs roughly 25 ms of pure Python against a 33 ms tick, so it never
        fits in a tick's leftover slack — waiting for enough slack means waiting
        forever. Instead it is allowed to overrun, on every other tick, and only while
        the simulation itself is comfortably inside its budget. The loop keeps an
        absolute deadline, so an overrun delays exactly the next tick and then
        recovers; the visible effect while a queue drains is the tick rate sagging
        towards 24 Hz, which the client's interpolation absorbs.

        A busy world fails the budget check and stops warming. Chunks it skipped are
        generated on first touch instead, which is one hitch for one player rather
        than a sustained sag for everyone. That degradation is the deal: TDD 2.2
        INV-7 asks for it to be explicit, and this is where it is.

        A worker thread was tried and is worse. The GIL makes it preemption rather
        than parallelism, so the cost reappears as tick jitter, and it puts the chunk
        cache under concurrent access for no gain.
        """
        manager = self.simulation.manager
        if not manager.warmup_pending():
            return
        if self.stats.ticks % 2 or self.stats.last_tick_ms > WARMUP_TICK_BUDGET_MS:
            self.stats.warmups_skipped += 1
            return
        if manager.warm_next() is not None:
            self.stats.chunks_warmed += 1

    # --- fan-out ------------------------------------------------------------

    async def _dispatch(self, report: TickReport) -> None:
        """Turn one tick's events into packets for whoever should see them."""
        events = report.events

        for event in events.combat:
            frame = wire.encode_combat(
                attacker_id=event.attacker_id,
                target_id=event.target_id,
                ability_id=event.ability_id,
                damage=event.damage,
                healing=event.healing,
                killed=event.killed,
                x=self._position_of(event.target_id or event.attacker_id)[0],
                y=self._position_of(event.target_id or event.attacker_id)[1],
            )
            self._send_near(event.attacker_id, frame)

        for tiles in events.tiles:
            frame = wire.encode_tiles(tiles.chunk_key, tiles.changes)
            for connection in self._connections.values():
                # Only clients holding the chunk: a tile delta for terrain the
                # client has not generated has nowhere to land.
                session = self.simulation.world.sessions.get(connection.session_id)
                if session is not None and tiles.chunk_key in session.loaded_chunks:
                    connection.enqueue(frame)

        if events.topology_versions:
            frame = wire.encode_topology(
                topology_version=self.simulation.world.topology.topology_version,
                current_tier=self.simulation.world.topology.current_tier,
                active_chunks=self.simulation.manager.active_chunk_keys(),
                retiring_chunks=self.simulation.manager.retiring_chunk_keys(),
            )
            self._broadcast(frame)

        for message in events.messages:
            self._broadcast(
                wire.encode_chat(
                    sender_id=0,
                    channel=CHANNEL_SYSTEM,
                    sender_name="",
                    text=message.text,
                )
            )

        for decision in report.chat:
            self._deliver_chat(decision)

        for session_id, code in report.rejections:
            connection = self._connections.get(session_id)
            if connection is not None:
                connection.enqueue(wire.encode_error(code))

        for entity_id, reason in events.despawned:
            frame = wire.encode_despawn(entity_id, reason)
            for connection in self._connections.values():
                # Only clients that were told about the entity. A despawn for
                # something a client never spawned is a packet it has to parse and
                # then discard.
                if entity_id in connection.known_entity_ids:
                    connection.enqueue(frame)

    def _deliver_chat(self, decision: ChatDecision) -> None:
        if decision.message is None:
            return
        frame = wire.encode_chat(
            sender_id=decision.message.sender_id,
            channel=decision.message.channel,
            sender_name=decision.message.sender_name,
            text=decision.message.text,
        )
        for entity_id in decision.recipients:
            connection = self._by_entity.get(entity_id)
            if connection is not None:
                connection.enqueue(frame)

    async def _broadcast_snapshots(self) -> None:
        """Build and queue one update per ready client."""
        updates = self.simulation.build_updates()
        self.stats.snapshots += 1

        for session_id, update in updates.items():
            connection = self._connections.get(session_id)
            if connection is None:
                continue
            self._queue_update(connection, update)

        # Draining after every client is queued keeps the fan-out cheap: the encode
        # happens once per client, and the awaits happen once per round.
        await self._prune()

    def _queue_update(self, connection: Connection, update: ClientUpdate) -> None:
        session = self.simulation.world.sessions.get(connection.session_id)
        if session is not None:
            connection.known_entity_ids = session.known_entities

        for frame in update.frames:
            connection.enqueue(frame)
            self.stats.bytes_sent += len(frame)

        # Retired chunks are worth telling the client about so it can free the
        # tiles; added chunks it generates itself from the seed, so they cost
        # nothing to announce and are left implicit.
        if update.chunk_keys_removed:
            for chunk_key in update.chunk_keys_removed:
                connection.enqueue(wire.encode_tiles(chunk_key, {}))

    async def _prune(self) -> None:
        """Drop connections whose queue overflowed or whose socket died."""
        for connection in list(self._connections.values()):
            if connection.is_broken:
                self.stats.dropped_connections += 1
                logger.info("Dropping %s: %s", connection.session_id, connection.failure)
                await self.detach(
                    connection, code=1011, reason=connection.failure or "Connection lost."
                )

    def _broadcast(self, frame: bytes) -> None:
        for connection in self._connections.values():
            connection.enqueue(frame)
            self.stats.bytes_sent += len(frame)

    def _send_near(self, origin_id: EntityId, frame: bytes) -> None:
        """Send to everyone who could plausibly have seen it happen."""
        world = self.simulation.world
        origin = world.entities.get(origin_id)
        if origin is None:
            self._broadcast(frame)
            return

        for entity in world.entities_near(origin.position, CHAT_PROXIMITY_RADIUS_TILES):
            if not entity.is_player:
                continue
            connection = self._by_entity.get(entity.entity_id)
            if connection is not None:
                connection.enqueue(frame)
                self.stats.bytes_sent += len(frame)

    def _position_of(self, entity_id: EntityId) -> tuple[float, float]:
        entity = self.simulation.world.entities.get(entity_id)
        return (entity.position.x, entity.position.y) if entity else (0.0, 0.0)

    # --- diagnostics --------------------------------------------------------

    def describe(self) -> dict[str, object]:
        return {
            "population": self.population,
            "maxClients": self.max_clients,
            "running": self._running,
            "stats": self.stats.snapshot(),
            "world": self.simulation.world.describe(),
        }

    def system_message(self, text: str) -> None:
        """Announce something to everyone. Used by the dev controls."""
        message = self.simulation.chat.system(text, self.simulation.world.now)
        self._broadcast(
            wire.encode_chat(
                sender_id=0,
                channel=message.channel,
                sender_name="",
                text=message.text,
            )
        )
