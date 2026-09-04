"""The tick loop: the one place that knows what order systems run in.

Everything above this is a system that does one job on demand. This decides when
each runs and what it sees, which is the part that determines whether the
simulation is deterministic.

The order is not arbitrary:

1. Queued client input, oldest first, so a player's own commands stay in sequence.
2. NPC AI, after players have moved, so creatures react to the current frame
   rather than to the previous one.
3. Regeneration and respawn, which depend on nothing and are cheapest last.
4. Terrain regrowth, then the accordion, both on their own longer schedules.

Input is queued rather than applied on arrival (TDD 5.3). Applying it on arrival
would make the result depend on packet timing, which is not reproducible and
therefore not testable; a queue drained at a fixed point in the tick is.
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field

from ..domain.constants import (
    HEALTH_REGEN_PER_SECOND,
    MAX_QUEUED_INPUTS,
    RESOURCE_REGEN_PER_SECOND,
    TERRAIN_FLUSH_INTERVAL_SECONDS,
    TICK_SECONDS,
)
from ..domain.coordinates import WorldPoint
from ..domain.entities import DirtyField, Entity, EntityId, PlayerSession
from ..domain.ports import TerrainOverlayRepository
from ..infrastructure import wire
from . import ai, combat, terrain, weather
from .accordion import AccordionReport, WorldManager
from .chat import ChatDecision, ChatService
from .events import EventQueue
from .interest import ClientUpdate, build_update, clear_dirty
from .movement import apply_input
from .session import SessionService
from .world import World

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class Command:
    """One queued client intent, with who sent it."""

    session_id: str
    payload: object
    received_at: float


@dataclass(slots=True)
class TickReport:
    """What one tick did. Consumed by the transport and the debug endpoint."""

    tick: int
    inputs_applied: int = 0
    actions_resolved: int = 0
    corrections: list[EntityId] = field(default_factory=list)
    rejections: list[tuple[str, int]] = field(default_factory=list)
    accordion: AccordionReport | None = None
    weather_changed: bool = False
    events: EventQueue = field(default_factory=EventQueue)
    # Chat carries its own recipient list rather than going through the event
    # queue, because re-deriving the audience from a position would lose the
    # distinction between the local and global channels.
    chat: list[ChatDecision] = field(default_factory=list)


class Simulation:
    """Owns the world and runs it forward one tick at a time.

    Deliberately synchronous. The only async things here are the persistence
    flushes, which are awaited by :meth:`flush` on its own schedule so a slow
    database can never stretch a tick.
    """

    __slots__ = (
        "world",
        "manager",
        "sessions",
        "chat",
        "events",
        "_queues",
        "_last_flush_at",
        "overlays",
        "allow_dev_controls",
    )

    def __init__(
        self,
        *,
        world: World,
        manager: WorldManager,
        sessions: SessionService,
        chat: ChatService,
        events: EventQueue,
        overlays: TerrainOverlayRepository | None = None,
        allow_dev_controls: bool = False,
    ) -> None:
        self.world = world
        self.manager = manager
        self.sessions = sessions
        self.chat = chat
        self.events = events
        self.overlays = overlays
        self.allow_dev_controls = allow_dev_controls
        self._queues: dict[str, deque[Command]] = {}
        self._last_flush_at = world.now

    # --- input intake -------------------------------------------------------

    def enqueue(self, session_id: str, payload: object) -> bool:
        """Accept a command for the next tick.

        The queue is bounded. A client that floods loses its *oldest* pending
        commands rather than its newest: dropping the newest would make a laggy
        client permanently rewind, while dropping the oldest just means it skips
        forward, which is what a correction does anyway.
        """
        queue = self._queues.get(session_id)
        if queue is None:
            queue = deque(maxlen=MAX_QUEUED_INPUTS)
            self._queues[session_id] = queue
        queue.append(Command(session_id, payload, self.world.now))
        return True

    def forget(self, session_id: str) -> None:
        self._queues.pop(session_id, None)

    # --- the tick -----------------------------------------------------------

    def tick(self, delta_time: float = TICK_SECONDS) -> TickReport:
        """Advance the world by one step."""
        now = self.world.now
        self.world.tick_count += 1
        report = TickReport(tick=self.world.tick_count)

        self._drain_commands(now, delta_time, report)

        ai.tick(self.world, now, delta_time, self.events)

        for entity in self.world.entities.values():
            if entity.is_player:
                combat.regenerate(
                    entity, delta_time, HEALTH_REGEN_PER_SECOND, RESOURCE_REGEN_PER_SECOND
                )
                if not entity.is_alive:
                    self.sessions.respawn(entity, now)
            entity.record_history(now)

        terrain.tick_regrowth(self.world, now, self.events)

        report.accordion = self.manager.tick(now)
        report.weather_changed = self.world.update_weather(now, weather.choose)

        report.events = self.events.drain()
        return report

    def _drain_commands(self, now: float, delta_time: float, report: TickReport) -> None:
        """Apply every queued command, per session, in arrival order."""
        for session_id, queue in self._queues.items():
            session = self.world.sessions.get(session_id)
            if session is None:
                queue.clear()
                continue

            entity = self.world.entities.get(session.entity_id)
            if entity is None:
                queue.clear()
                continue

            while queue:
                command = queue.popleft()
                self._apply(session, entity, command, now, delta_time, report)

    def _apply(
        self,
        session: PlayerSession,
        entity: Entity,
        command: Command,
        now: float,
        delta_time: float,
        report: TickReport,
    ) -> None:
        payload = command.payload
        session.last_seen_at = now

        if isinstance(payload, wire.InputCommand):
            self._apply_input(session, entity, payload, delta_time, report)
        elif isinstance(payload, wire.ActionCommand):
            self._apply_action(session, entity, payload, now, command.received_at, report)
        elif isinstance(payload, wire.BuildRequest):
            self._apply_build(session, entity, payload, now, report)
        elif isinstance(payload, wire.ChatRequest):
            self._apply_chat(session, entity, payload, now, report)
        elif isinstance(payload, wire.DevTierRequest):
            self._apply_dev_tier(session, payload, now, report)

    # --- individual commands ------------------------------------------------

    def _stale(self, session: PlayerSession, topology_version: int) -> bool:
        """Whether a command was composed against a superseded topology.

        Accordion Spec 5.3: a command carrying an old version is rejected rather
        than best-effort applied, because the coordinates in it may refer to a lane
        that no longer exists.
        """
        return topology_version != self.world.topology.topology_version

    def _apply_input(
        self,
        session: PlayerSession,
        entity: Entity,
        payload: wire.InputCommand,
        delta_time: float,
        report: TickReport,
    ) -> None:
        if self._stale(session, payload.topology_version):
            report.rejections.append((session.session_id, wire.ERROR_STALE_TOPOLOGY))
            return
        if payload.sequence <= session.last_input_sequence:
            # A duplicate or a reordered packet. Re-applying it would move the
            # player twice for one keypress.
            return
        if not entity.is_alive:
            session.last_input_sequence = payload.sequence
            return

        result = apply_input(
            self.world,
            entity,
            payload.move_axis,
            payload.running,
            payload.facing,
            min(delta_time * 2.0, payload.delta_time) if payload.delta_time > 0 else delta_time,
            predicted=WorldPoint(payload.predicted_x, payload.predicted_y),
        )

        session.last_input_sequence = payload.sequence
        report.inputs_applied += 1
        if result.corrected:
            # Force the position into the next snapshot even if the authoritative
            # value happens to match the last one sent, so the client reconciles.
            entity.mark(DirtyField.POSITION | DirtyField.VELOCITY)
            report.corrections.append(entity.entity_id)

    def _apply_action(
        self,
        session: PlayerSession,
        entity: Entity,
        payload: wire.ActionCommand,
        now: float,
        received_at: float,
        report: TickReport,
    ) -> None:
        if self._stale(session, payload.topology_version):
            report.rejections.append((session.session_id, wire.ERROR_STALE_TOPOLOGY))
            return

        # How long the command has been waiting is the rewind the target deserves.
        # Using arrival time rather than a client-supplied timestamp means a client
        # cannot ask for an arbitrary rewind (TDD 15.4).
        outcome = combat.resolve_action(
            self.world,
            entity,
            payload.ability_id,
            WorldPoint(payload.target_x, payload.target_y),
            payload.target_entity,
            now,
            client_time_offset=max(0.0, now - received_at),
        )

        if not outcome.ok:
            report.rejections.append((session.session_id, outcome.error))
            return

        report.actions_resolved += 1

        if outcome.dash_to is not None:
            entity.move_to(outcome.dash_to.x, outcome.dash_to.y)
            self.world.reindex(entity)

        for target_id, damage, healing, killed in outcome.hits:
            self.events.combat_resolved(
                entity.entity_id,
                target_id,
                payload.ability_id,
                damage,
                healing,
                killed,
            )
            if killed:
                self._award_kill(entity, target_id)

        if not outcome.hits and outcome.ability is not None:
            # A miss still needs to reach the client, or the ability appears to do
            # nothing at all when it was simply aimed badly.
            self.events.combat_resolved(
                entity.entity_id, 0, payload.ability_id, 0, 0, False
            )

    def _award_kill(self, killer: Entity, target_id: EntityId) -> None:
        """Grant experience for a kill, levelling up when the bar fills.

        The curve is deliberately shallow and the cap low: this slice needs
        levelling to be *visible*, not tuned (GDD 6.2).
        """
        target = self.world.entities.get(target_id)
        if target is None or not target.is_npc or target.archetype is None:
            return

        killer.experience += target.archetype.experience
        threshold = 40 + killer.level * 60
        while killer.experience >= threshold and killer.level < 20:
            killer.experience -= threshold
            killer.level += 1
            killer.max_health += 6
            killer.health = killer.max_health
            killer.max_resource += 4
            killer.resource = killer.max_resource
            killer.mark(DirtyField.HEALTH | DirtyField.RESOURCE | DirtyField.STATE)
            threshold = 40 + killer.level * 60
            self.events.system_message(f"{killer.name} reached level {killer.level}.")

        for item, count in target.archetype.loot:
            killer.give(item, count)

    def _apply_build(
        self,
        session: PlayerSession,
        entity: Entity,
        payload: wire.BuildRequest,
        now: float,
        report: TickReport,
    ) -> None:
        if self._stale(session, payload.topology_version):
            report.rejections.append((session.session_id, wire.ERROR_STALE_TOPOLOGY))
            return

        point = WorldPoint(payload.tile_x + 0.5, payload.tile_y + 0.5)

        if payload.action == wire.BUILD_HARVEST:
            outcome = terrain.harvest(self.world, entity, point, now)
        else:
            outcome = terrain.place(self.world, entity, point, payload.material, now)

        if not outcome.ok:
            report.rejections.append((session.session_id, outcome.error))
            return

        self.events.tiles_changed(outcome.chunk_key, {outcome.tile_index: outcome.tile})

    def _apply_chat(
        self,
        session: PlayerSession,
        entity: Entity,
        payload: wire.ChatRequest,
        now: float,
        report: TickReport,
    ) -> None:
        decision = self.chat.submit(
            self.world, session, entity, payload.channel, payload.text, now
        )
        if not decision.accepted:
            report.rejections.append((session.session_id, wire.ERROR_RATE_LIMITED))
            return
        report.chat.append(decision)

    def _apply_dev_tier(
        self,
        session: PlayerSession,
        payload: wire.DevTierRequest,
        now: float,
        report: TickReport,
    ) -> None:
        if not self.allow_dev_controls:
            report.rejections.append((session.session_id, wire.ERROR_INVALID))
            return
        report.accordion = self.manager.force_tier(payload.target_tier, now)

    # --- snapshot assembly --------------------------------------------------

    def build_updates(self) -> dict[str, ClientUpdate]:
        """One update per ready session, then clear the dirty flags.

        Flags are cleared here rather than in :meth:`tick` because they are what
        every client's delta is derived from; clearing them at the end of the tick
        would leave a slower snapshot cadence with nothing to send.
        """
        updates: dict[str, ClientUpdate] = {}
        tick = self.world.tick_count
        server_time = self.world.now

        for session_id, session in self.world.sessions.items():
            if not session.ready:
                continue
            entity = self.world.entities.get(session.entity_id)
            if entity is None:
                continue
            updates[session_id] = build_update(
                self.world, session, entity, tick=tick, server_time=server_time
            )

        clear_dirty(self.world)
        return updates

    # --- persistence --------------------------------------------------------

    @property
    def flush_due(self) -> bool:
        return self.world.now - self._last_flush_at >= TERRAIN_FLUSH_INTERVAL_SECONDS

    async def flush(self) -> int:
        """Persist terrain edits, topology, and every live character.

        Returns the number of chunks written. Terrain is batched on the interval
        TDD 9.1 allows; topology writes immediately when it is dirty, and it checks
        its own flag, so calling this often is cheap.
        """
        self._last_flush_at = self.world.now

        await self.manager.persist()

        written = 0
        pending = terrain.collect_dirty_overlays(self.world)
        if pending and self.overlays is not None:
            await self.overlays.save_batch(pending)
            written = len(pending)

        for session in list(self.world.sessions.values()):
            entity = self.world.entities.get(session.entity_id)
            if entity is not None:
                await self.sessions.persist(entity)

        return written

    async def load_overlays(self) -> None:
        """Restore persisted edits for every currently loaded chunk."""
        if self.overlays is None:
            return
        for view in self.world.loaded_chunks():
            stored = await self.overlays.load(view.address.key)
            if stored:
                self.world.apply_overlay(view.address, stored)
