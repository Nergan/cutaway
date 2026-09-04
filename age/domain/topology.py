"""The accordion: chunk lifecycle, tier rules, and topology versioning.

This module is the formal statement of the invariants in TDD 2.2. It holds no
I/O and no timers of its own; the caller supplies the clock, which is what makes
the whole accordion deterministically testable.

The invariants enforced here:

INV-2
    ``topology_version`` only ever increases, and only on a tier change.
INV-5
    A chunk is ACTIVE if and only if ``current_tier >= chunk.tier_min``.
INV-6
    Existing hubs and chunks never move. Expansion adds lanes; it does not
    renumber or rescale what is already there.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import IntEnum

from .constants import (
    CHUNK_PREPARE_SECONDS,
    CHUNK_RETIRE_SECONDS,
    CONTRACTION_PLAYER_THRESHOLD,
    CORRIDOR_SEGMENTS,
    EXPANSION_PLAYER_THRESHOLD,
    MAX_TIER,
    TIER_0_LANES,
    TIER_1_LANES,
    TIER_COOLDOWN_SECONDS,
)
from .coordinates import ChunkAddress


class ChunkState(IntEnum):
    """The global lifecycle of a chunk, owned by the world server.

    Distinct from per-client streaming state: a chunk can be ACTIVE globally
    while no client has it loaded, and a client can still be rendering a chunk
    that has just gone RETIRING. TDD 7.3 keeps the two layers separate on
    purpose, and only this one moves ``topology_version``.
    """

    INACTIVE = 0
    PREPARING = 1
    ACTIVE = 2
    RETIRING = 3


# The only legal edges of the state machine. Anything else is a bug, and
# :meth:`TopologyState.transition` raises rather than silently accepting it.
_LEGAL_TRANSITIONS: dict[ChunkState, frozenset[ChunkState]] = {
    ChunkState.INACTIVE: frozenset({ChunkState.PREPARING}),
    ChunkState.PREPARING: frozenset({ChunkState.ACTIVE, ChunkState.INACTIVE}),
    ChunkState.ACTIVE: frozenset({ChunkState.RETIRING}),
    ChunkState.RETIRING: frozenset({ChunkState.INACTIVE}),
}


class IllegalTransition(RuntimeError):
    """Raised when a caller asks for a transition the lifecycle forbids."""


def lanes_for_tier(tier: int) -> tuple[int, ...]:
    """Which lanes exist at a given tier.

    Tier 0 is a single-lane corridor; tier 1 widens it to three. The sequence is
    monotonic by design: a lane present at tier N is present at every tier above.
    """
    return TIER_1_LANES if tier >= 1 else TIER_0_LANES


def tier_min_for_lane(lane_offset: int) -> int:
    """The tier at which a lane first appears.

    This is the ``tier_min`` baked into the chunk seed, so a lane's terrain is
    fixed from the moment it is conceived rather than depending on when the world
    happened to expand.
    """
    return 0 if lane_offset == 0 else 1


def chunks_for_tier(edge_id: str, tier: int, segments: int = CORRIDOR_SEGMENTS) -> list[ChunkAddress]:
    """Every corridor chunk that should be ACTIVE at ``tier``."""
    return [
        ChunkAddress.edge(edge_id, segment, lane, tier_min_for_lane(lane))
        for lane in lanes_for_tier(tier)
        for segment in range(segments)
    ]


@dataclass(slots=True)
class ChunkRecord:
    """The live state of one chunk."""

    address: ChunkAddress
    state: ChunkState = ChunkState.INACTIVE
    # When the current state was entered, in the caller's clock. Used only to
    # decide when PREPARING and RETIRING have had long enough.
    entered_at: float = 0.0
    # The topology version at which this chunk last went ACTIVE, for auditing.
    activated_version: int = 0
    dirty: bool = False

    @property
    def is_simulated(self) -> bool:
        """Whether the simulation should tick entities in this chunk.

        RETIRING chunks still simulate so that players inside them keep moving
        while they are evacuated.
        """
        return self.state in (ChunkState.ACTIVE, ChunkState.RETIRING)


@dataclass(slots=True)
class TopologyState:
    """Authoritative accordion state for a single edge.

    One instance per corridor. Multiple edges expand and contract independently,
    which is the long-term sparse-graph model from Accordion Spec 7.3; the MVP
    simply has one.
    """

    edge_id: str
    segments: int = CORRIDOR_SEGMENTS
    current_tier: int = 0
    topology_version: int = 1
    last_tier_change_at: float = 0.0
    chunks: dict[str, ChunkRecord] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Every chunk that could ever exist is registered up front, at every
        # tier. Registration is not activation: the records start INACTIVE and
        # cost a few hundred bytes, which buys a total absence of "unknown chunk"
        # branches everywhere else.
        for tier in range(MAX_TIER + 1):
            for address in chunks_for_tier(self.edge_id, tier, self.segments):
                self.chunks.setdefault(address.key, ChunkRecord(address=address))

    # --- queries ------------------------------------------------------------

    def record(self, address: ChunkAddress) -> ChunkRecord:
        record = self.chunks.get(address.key)
        if record is None:
            raise KeyError(f"chunk {address.key} is not part of edge {self.edge_id}")
        return record

    def should_be_active(self, address: ChunkAddress) -> bool:
        """INV-5, stated directly."""
        return self.current_tier >= address.tier_min

    def active_chunks(self) -> list[ChunkRecord]:
        return [record for record in self.chunks.values() if record.state is ChunkState.ACTIVE]

    def simulated_chunks(self) -> list[ChunkRecord]:
        return [record for record in self.chunks.values() if record.is_simulated]

    def transitioning_chunks(self) -> list[ChunkRecord]:
        return [
            record
            for record in self.chunks.values()
            if record.state in (ChunkState.PREPARING, ChunkState.RETIRING)
        ]

    # --- transitions --------------------------------------------------------

    def transition(self, address: ChunkAddress, target: ChunkState, now: float) -> ChunkRecord:
        """Move one chunk to ``target``, refusing any illegal edge."""
        record = self.record(address)
        if record.state is target:
            return record
        if target not in _LEGAL_TRANSITIONS[record.state]:
            raise IllegalTransition(
                f"{address.key}: {record.state.name} -> {target.name} is not a legal transition"
            )
        record.state = target
        record.entered_at = now
        if target is ChunkState.ACTIVE:
            record.activated_version = self.topology_version
        return record

    def bootstrap(self, now: float) -> list[ChunkRecord]:
        """Bring the tier-0 chunks straight to ACTIVE at world start.

        Skips PREPARING deliberately: there is no client to fade anything in for
        yet, and making startup wait two seconds per chunk would serve nobody.
        """
        activated = []
        for address in chunks_for_tier(self.edge_id, self.current_tier, self.segments):
            record = self.record(address)
            if record.state is ChunkState.ACTIVE:
                continue
            self.transition(address, ChunkState.PREPARING, now)
            activated.append(self.transition(address, ChunkState.ACTIVE, now))
        return activated

    # --- the accordion itself ----------------------------------------------

    def may_change_tier(self, now: float, cooldown: float = TIER_COOLDOWN_SECONDS) -> bool:
        """Whether the cooldown has elapsed (Accordion Spec 4.2 hysteresis)."""
        return (now - self.last_tier_change_at) >= cooldown

    def desired_tier(self, active_players: int) -> int:
        """The tier the current population argues for.

        Two thresholds rather than one: ten players to widen, five to narrow. The
        gap between them is what stops the world flickering when a single player
        walks in and out of the corridor.
        """
        if active_players >= EXPANSION_PLAYER_THRESHOLD and self.current_tier < MAX_TIER:
            return self.current_tier + 1
        if active_players <= CONTRACTION_PLAYER_THRESHOLD and self.current_tier > 0:
            return self.current_tier - 1
        return self.current_tier

    def begin_expansion(self, now: float) -> list[ChunkRecord]:
        """Start generating the chunks the next tier needs.

        Bumps the tier and the version immediately so that in-flight client
        packets are rejected and resynced at once, then moves the newly eligible
        chunks into PREPARING. They only become ACTIVE once
        :meth:`advance_transitions` says generation has had long enough, which is
        what keeps a player from walking into a half-built lane.
        """
        if self.current_tier >= MAX_TIER:
            return []

        self.current_tier += 1
        self.topology_version += 1
        self.last_tier_change_at = now

        preparing = []
        for address in chunks_for_tier(self.edge_id, self.current_tier, self.segments):
            record = self.record(address)
            if record.state is ChunkState.INACTIVE and self.should_be_active(address):
                preparing.append(self.transition(address, ChunkState.PREPARING, now))
        return preparing

    def begin_contraction(self, now: float, pinned: frozenset[str] = frozenset()) -> list[ChunkRecord]:
        """Retire the chunks the lower tier no longer contains.

        ``pinned`` holds chunk keys that must not be retired because something
        durable lives there. In the MVP that is only ever a temporary camp being
        given a grace period; the long-term model in Accordion Spec 7.2 pins a
        chunk for as long as a claim exists on it. Either way, a single pinned
        chunk aborts the whole contraction rather than being retired around,
        because a lane with a hole in it is worse than a lane that stayed.
        """
        if self.current_tier <= 0:
            return []

        target_tier = self.current_tier - 1
        doomed = [
            self.record(address)
            for address in chunks_for_tier(self.edge_id, self.current_tier, self.segments)
            if address.tier_min > target_tier
        ]
        if any(record.address.key in pinned for record in doomed):
            return []

        self.current_tier = target_tier
        self.topology_version += 1
        self.last_tier_change_at = now

        retiring = []
        for record in doomed:
            if record.state is ChunkState.ACTIVE:
                retiring.append(self.transition(record.address, ChunkState.RETIRING, now))
        return retiring

    def advance_transitions(
        self,
        now: float,
        is_ready: Callable[[ChunkAddress], bool] | None = None,
    ) -> tuple[list[ChunkRecord], list[ChunkRecord]]:
        """Complete any PREPARING or RETIRING chunk whose timer has elapsed.

        ``is_ready`` lets the caller hold a chunk in PREPARING past its timer when
        its terrain is not built yet. The timer is a minimum, not a promise:
        generation is budgeted across ticks, and on a slow host it can overrun.
        Activating early would drop a player into a chunk with no tiles, so the
        predicate wins and the chunk simply fades in a little later.

        Returns ``(activated, deactivated)``. Called once per world tick; does
        nothing when no chunk is mid-transition, which is the common case.
        """
        activated: list[ChunkRecord] = []
        deactivated: list[ChunkRecord] = []

        for record in self.chunks.values():
            if record.state is ChunkState.PREPARING:
                if not self.should_be_active(record.address):
                    # The tier moved back down while this was still generating.
                    self.transition(record.address, ChunkState.INACTIVE, now)
                elif now - record.entered_at < CHUNK_PREPARE_SECONDS:
                    continue
                elif is_ready is None or is_ready(record.address):
                    activated.append(self.transition(record.address, ChunkState.ACTIVE, now))
            elif record.state is ChunkState.RETIRING:
                if now - record.entered_at >= CHUNK_RETIRE_SECONDS:
                    deactivated.append(self.transition(record.address, ChunkState.INACTIVE, now))

        return activated, deactivated

    # --- packet validation --------------------------------------------------

    def accepts_version(self, client_version: int) -> bool:
        """Whether a packet carrying ``client_version`` may be processed.

        A stale version means the client has not seen the current topology, so
        acting on its input could apply a move to a chunk that no longer exists.
        A version from the future is impossible against an authoritative server
        and is treated as tampering (TDD 15.5).
        """
        return client_version == self.topology_version

    def snapshot(self) -> dict[str, object]:
        """Serialisable summary, for the topology packet and the debug endpoint."""
        return {
            "edge_id": self.edge_id,
            "current_tier": self.current_tier,
            "topology_version": self.topology_version,
            "segments": self.segments,
            "lanes": list(lanes_for_tier(self.current_tier)),
            "active": sorted(record.address.key for record in self.active_chunks()),
            "transitioning": {
                record.address.key: record.state.name for record in self.transitioning_chunks()
            },
        }
