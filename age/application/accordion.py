"""The World Manager: drives the accordion and the chunk lifecycle.

:class:`~age.domain.topology.TopologyState` holds the rules; this holds the policy
and the side effects. It decides when to look, gathers the population, asks the
topology what that implies, and then does the work an activation or a retirement
actually requires: generating terrain, spawning creatures, evacuating players, and
persisting the change.

The ordering here is the part worth reading. On expansion the version is bumped
*before* the chunks are ready, so in-flight client packets are rejected and
resynced immediately rather than being applied against a topology that is halfway
changed. On contraction players are evacuated *before* the chunk stops being
simulated, so nobody is ever standing in an unsimulated chunk.

Terrain generation is the one expensive thing in here, so it does not happen
inline. Chunks that need building go on a queue the room drains from a worker
thread, and a chunk is not allowed out of PREPARING until its turn has come up.
That is what the prepare window is for.
"""

from __future__ import annotations

import logging
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass, field
from time import perf_counter

from ..domain.constants import TIER_EVALUATION_INTERVAL_SECONDS
from ..domain.coordinates import ChunkAddress, SpaceType
from ..domain.entities import DirtyField, Entity
from ..domain.ports import EventSink, TopologyRepository
from ..domain.topology import ChunkRecord, ChunkState
from . import ai
from .movement import find_walkable_near
from .world import World

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class AccordionReport:
    """What one evaluation did, for logging and the debug endpoint."""

    evaluated: bool = False
    tier_changed: bool = False
    previous_tier: int = 0
    current_tier: int = 0
    activated: list[str] = field(default_factory=list)
    retiring: list[str] = field(default_factory=list)
    deactivated: list[str] = field(default_factory=list)
    evacuated: int = 0


class WorldManager:
    """Owns tier policy and chunk lifecycle side effects."""

    __slots__ = (
        "world",
        "events",
        "topology_repository",
        "cooldown_seconds",
        "_last_evaluated_at",
        "_pending_persist",
        "_warmup",
        "_chunk_cost",
    )

    def __init__(
        self,
        world: World,
        events: EventSink,
        *,
        topology_repository: TopologyRepository | None = None,
        cooldown_seconds: float,
    ) -> None:
        self.world = world
        self.events = events
        self.topology_repository = topology_repository
        self.cooldown_seconds = cooldown_seconds
        self._last_evaluated_at = 0.0
        self._pending_persist = False
        # Addresses waiting for terrain, in the order they were queued. Callers
        # enqueue nearest-first; a chunk somebody reaches before its turn comes up
        # is generated inline by :meth:`World.chunk` and popped as a no-op later.
        self._warmup: deque[ChunkAddress] = deque()
        # Rolling cost of one generation, in seconds. Zero until measured.
        self._chunk_cost = 0.0

    # --- startup ------------------------------------------------------------

    def bootstrap(self, now: float) -> list[ChunkRecord]:
        """Activate tier 0 and populate it.

        Tier 0 terrain is built inline: there is no client yet to stall, and the
        spawn plaza has to exist before anyone can be placed on it. The rest of the
        hub interiors are queued, so a long boot does not become a long first tick.
        """
        activated = self.world.topology.bootstrap(now)
        for record in activated:
            self._on_activated(record, now)
        for entity in ai.spawn_hub_guards(self.world, now):
            self.events.entity_spawned(entity.entity_id)
        self.enqueue_warmup(self.world.hub_chunk_addresses())
        self._pending_persist = True
        return activated

    # --- per-tick -----------------------------------------------------------

    def tick(self, now: float) -> AccordionReport:
        """Advance transitions, and evaluate the tier when it is time."""
        report = AccordionReport(
            previous_tier=self.world.topology.current_tier,
            current_tier=self.world.topology.current_tier,
        )

        activated, deactivated = self.world.topology.advance_transitions(
            now, self.world.is_chunk_loaded
        )
        for record in activated:
            self._on_activated(record, now)
            report.activated.append(record.address.key)
        for record in deactivated:
            self._on_deactivated(record)
            report.deactivated.append(record.address.key)

        if activated or deactivated:
            self.events.topology_changed(self.world.topology.topology_version)

        if now - self._last_evaluated_at >= TIER_EVALUATION_INTERVAL_SECONDS:
            self._last_evaluated_at = now
            report.evaluated = True
            self._evaluate(now, report)

        return report

    def _evaluate(self, now: float, report: AccordionReport) -> None:
        """Compare population against the thresholds and act if warranted."""
        topology = self.world.topology
        if not topology.may_change_tier(now, self.cooldown_seconds):
            return

        population = self.corridor_population()
        desired = topology.desired_tier(population)
        if desired == topology.current_tier:
            return

        if desired > topology.current_tier:
            self._expand(now, report)
        else:
            self._contract(now, report)

    def corridor_population(self) -> int:
        """Players currently in the corridor rather than in a hub.

        Hub population is deliberately excluded: a crowded market square is not a
        reason to widen the wilderness (Accordion Spec 3.2).
        """
        return sum(
            1
            for entity in self.world.players
            if entity.is_alive and not self.world.is_in_hub(entity.position)
        )

    # --- tier changes -------------------------------------------------------

    def force_tier(self, target_tier: int, now: float) -> AccordionReport:
        """Move to a tier immediately, bypassing thresholds and cooldown.

        Exists so the accordion can be demonstrated and tested. Nobody is going to
        wait fifteen minutes and recruit ten players to watch a corridor widen, and
        the deterministic-simulation tests need to drive transitions directly.
        """
        report = AccordionReport(
            evaluated=True,
            previous_tier=self.world.topology.current_tier,
            current_tier=self.world.topology.current_tier,
        )
        topology = self.world.topology
        target = max(0, min(target_tier, 1))

        if target > topology.current_tier:
            self._expand(now, report)
        elif target < topology.current_tier:
            self._contract(now, report)
        return report

    def _expand(self, now: float, report: AccordionReport) -> None:
        topology = self.world.topology
        preparing = topology.begin_expansion(now)
        report.tier_changed = True
        report.current_tier = topology.current_tier
        report.retiring = []

        # Generation is queued, not done here, and the chunk stays PREPARING and
        # invisible until it comes up. This is the "off-tick" requirement from
        # Accordion Spec 7.6: by the time a chunk goes ACTIVE its terrain is already
        # in memory, so activation is a flag flip rather than a stall.
        self.enqueue_warmup((record.address for record in preparing), urgent=True)

        logger.info(
            "accordion expanded to tier %d (version %d), preparing %d chunks",
            topology.current_tier,
            topology.topology_version,
            len(preparing),
        )
        self.events.topology_changed(topology.topology_version)
        self.events.system_message("The wilds are opening up. New paths are forming.")
        self._pending_persist = True

    def _contract(self, now: float, report: AccordionReport) -> None:
        topology = self.world.topology
        pinned = self._pinned_chunks()
        retiring = topology.begin_contraction(now, pinned)

        if not retiring and pinned:
            logger.info("contraction aborted: %d chunks are pinned", len(pinned))
            return

        report.tier_changed = True
        report.current_tier = topology.current_tier
        report.retiring = [record.address.key for record in retiring]

        for record in retiring:
            report.evacuated += self._evacuate(record, now)

        logger.info(
            "accordion contracted to tier %d (version %d), retiring %d chunks",
            topology.current_tier,
            topology.topology_version,
            len(retiring),
        )
        self.events.topology_changed(topology.topology_version)
        self.events.system_message("The wilds are closing in. Outer paths are fading.")
        self._pending_persist = True

    def _pinned_chunks(self) -> frozenset[str]:
        """Chunks that must survive a contraction.

        In this slice, only chunks holding a player-built structure. Permanent
        claims are hub-only for the MVP (Accordion Spec 7.2), so nothing in the
        corridor is durable; but destroying someone's walls the moment they step
        away is still a bad experience, so an occupied chunk gets a reprieve until
        the next evaluation.
        """
        pinned: set[str] = set()
        for view in self.world.loaded_chunks():
            if view.address.space_type is not SpaceType.EDGE:
                continue
            if view.address.tier_min <= self.world.topology.current_tier - 1:
                continue
            if view.overlay:
                pinned.add(view.address.key)
        return frozenset(pinned)

    # --- terrain warm-up ----------------------------------------------------

    def enqueue_warmup(
        self, addresses: Iterable[ChunkAddress], *, urgent: bool = False
    ) -> None:
        """Queue chunks for background generation, skipping any already built.

        ``urgent`` jumps the queue. An expanding lane has a deadline — it cannot go
        ACTIVE until its terrain exists, and the client is already fading it in —
        whereas hub interiors are speculative and can wait behind it. Without this
        an expansion would sit behind a couple of hundred hub chunks and the corridor
        would take a minute to widen.
        """
        queued = {address.key for address in self._warmup}
        fresh: list[ChunkAddress] = []
        for address in addresses:
            if address.key in queued or self.world.is_chunk_loaded(address):
                continue
            queued.add(address.key)
            fresh.append(address)

        if urgent:
            self._warmup.extendleft(reversed(fresh))
        else:
            self._warmup.extend(fresh)

    def warm_next(self) -> ChunkAddress | None:
        """Build the next queued chunk. Returns its address, or ``None`` if idle.

        One chunk per call: a chunk costs tens of milliseconds in pure Python and the
        caller is the tick loop deciding how much of its remaining slack to spend.
        """
        while self._warmup:
            address = self._warmup.popleft()
            if self._generate(address):
                return address
        return None

    def warmup_pending(self) -> int:
        """How many chunks are still waiting on terrain, for the debug endpoint."""
        return len(self._warmup)

    @property
    def chunk_cost_seconds(self) -> float:
        """What a chunk currently costs to generate, measured.

        The tick loop uses this to decide whether it has room to warm one before its
        next deadline. Until something has actually been generated there is nothing
        to report, so this returns a value the loop will always find affordable
        within one tick: guessing high here would mean never taking the measurement
        that would correct the guess.
        """
        return self._chunk_cost or 0.001

    def _generate(self, address: ChunkAddress) -> bool:
        """Build one chunk unless it already exists. Returns whether it did work."""
        if self.world.is_chunk_loaded(address):
            return False
        started = perf_counter()
        self.world.chunk(address)
        cost = perf_counter() - started
        # Track the ceiling more eagerly than the floor. Underestimating is what
        # makes the loop overrun, so a dear chunk is believed at once and a cheap one
        # only gradually.
        if self._chunk_cost == 0.0:
            self._chunk_cost = cost
        else:
            weight = 0.5 if cost > self._chunk_cost else 0.1
            self._chunk_cost += (cost - self._chunk_cost) * weight
        return True

    # --- lifecycle side effects --------------------------------------------

    def _on_activated(self, record: ChunkRecord, now: float) -> None:
        """A chunk became ACTIVE: make sure it has terrain and inhabitants.

        Normally the terrain is already there — the PREPARING gate does not let a
        chunk through until it is. Bootstrap is the exception, and it generates here.
        """
        self._generate(record.address)
        for entity in ai.spawn_for_chunk(self.world, record.address, now):
            self.events.entity_spawned(entity.entity_id)

    def _on_deactivated(self, record: ChunkRecord) -> None:
        """A chunk became INACTIVE: release its entities and its memory.

        Edits are *not* dropped here. The persistence flush owns that, and it runs
        on its own schedule; dropping the chunk before a flush would lose the last
        thirty seconds of terrain work, which the budget allows for a crash but not
        for a routine contraction.
        """
        key = record.address.key
        for entity_id in ai.despawn_for_chunk(self.world, key):
            self.events.entity_despawned(entity_id, 3)
        self.world.unload_chunk(record.address)

    def _evacuate(self, record: ChunkRecord, now: float) -> int:
        """Move players out of a retiring chunk, to the nearest hub.

        The "return stone" behaviour from Accordion Spec 7.6. Landing them in a hub
        rather than an adjacent lane means they end up somewhere unambiguously safe
        and unambiguously still there after the contraction completes.
        """
        moved = 0
        for entity in self.world.entities_in_chunk(record.address.key):
            if not entity.is_player:
                continue
            hub = self.world.nearest_hub(entity.position)
            destination = find_walkable_near(self.world, self.world.spawn_point_for(hub))
            entity.move_to(destination.x, destination.y)
            entity.velocity = (0.0, 0.0)
            entity.mark(DirtyField.ALL)
            self.world.reindex(entity)
            moved += 1
        return moved

    # --- persistence --------------------------------------------------------

    @property
    def needs_persist(self) -> bool:
        return self._pending_persist

    async def persist(self) -> None:
        """Write topology state durably.

        Immediate rather than batched: TDD 9.1 puts topology in the zero-loss
        category, because a crash that forgets a tier change leaves the world
        claiming chunks it never generated.
        """
        if not self._pending_persist or self.topology_repository is None:
            self._pending_persist = False
            return

        topology = self.world.topology
        await self.topology_repository.save(
            topology.edge_id,
            {
                "current_tier": topology.current_tier,
                "topology_version": topology.topology_version,
                "last_tier_change_at": topology.last_tier_change_at,
            },
        )
        self._pending_persist = False

    def restore(self, payload: dict[str, object], now: float) -> None:
        """Reload topology state after a restart.

        The version is carried forward rather than reset so a client reconnecting
        with a cached version is judged against the same sequence it left. Chunk
        states are not restored: they start INACTIVE and are re-prepared, which is
        exactly the recovery path in Accordion Spec 7.7.
        """
        topology = self.world.topology
        topology.current_tier = int(payload.get("current_tier", 0) or 0)
        topology.topology_version = max(1, int(payload.get("topology_version", 1) or 1))
        # Reset the cooldown clock to now rather than trusting a stored wall-clock
        # value: the monotonic clock restarted with the process, so a persisted
        # timestamp is meaningless in the new epoch.
        topology.last_tier_change_at = now
        logger.info(
            "restored topology for %s: tier %d, version %d",
            topology.edge_id,
            topology.current_tier,
            topology.topology_version,
        )

    def active_chunk_keys(self) -> list[str]:
        return sorted(record.address.key for record in self.world.topology.active_chunks())

    def retiring_chunk_keys(self) -> list[str]:
        return sorted(
            record.address.key
            for record in self.world.topology.chunks.values()
            if record.state is ChunkState.RETIRING
        )
