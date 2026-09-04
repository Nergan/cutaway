"""The authoritative city room: one shared space, one simulation loop.

The room owns every player's position. Clients contribute intent and nothing
else, which is what makes the rules in ``docs/architecture.md`` enforceable
rather than advisory.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass, field

from ..domain.chat import ChatMessage, ChatScope
from ..domain.constants import (
    ANIMATION_IDLE,
    CHAT_HISTORY_SIZE,
    CHAT_PROXIMITY_RADIUS_M,
    EYE_HEIGHT_M,
    MAX_CLIENTS,
    MAX_QUEUED_INPUTS,
    SIMULATION_HZ,
    SNAPSHOT_HZ,
)
from ..domain.errors import ChatRejected, ProtocolError, RoomFullError
from ..domain.player import InputCommand, PlayerState
from ..domain.ports import ChatArchivePort, ClockPort
from ..domain.world import World
from ..infrastructure import wire_codec as wire
from .chat_service import ChatService
from .interest import visible_players, within_radius
from .movement import find_safe_position, move_player
from .nicknames import (
    ColorAllocator,
    NicknameFactory,
    is_safe_nickname,
    is_valid_avatar,
    pick_avatar,
)

logger = logging.getLogger(__name__)

SEND_TIMEOUT_S = 1.0
"""A client that cannot absorb a frame in a second is dropped rather than
allowed to back-pressure the simulation loop."""

HEARTBEAT_TIMEOUT_S = 20.0
INPUT_BURST_TOKENS = 3
"""Inputs a player may bank for jitter recovery. Long-run intake stays pinned
to the tick rate, so an input flood cannot buy extra movement."""


class PlayerConnection(ABC):
    """Transport seam. The WebSocket adapter lives in ``presentation``."""

    @abstractmethod
    async def send(self, payload: bytes) -> None:
        ...

    @abstractmethod
    async def close(self, code: int, reason: str) -> None:
        ...


def _sequence_is_newer(candidate: int, seen: int) -> bool:
    """Compare u32 sequences on the short arc, so wrapping is not a rollback."""
    if seen == 0:
        return True
    return 0 < ((candidate - seen) & 0xFFFFFFFF) < 0x80000000


@dataclass(slots=True)
class Member:
    state: PlayerState
    connection: PlayerConnection
    inputs: deque[InputCommand] = field(default_factory=deque)
    budget: int = INPUT_BURST_TOKENS
    alive: bool = True
    last_frame_at: float = 0.0
    spawn_index: int = 0
    highest_sequence: int = 0
    """Newest input sequence accepted, so a duplicate cannot move anyone."""


class CityRoom:
    def __init__(
        self,
        *,
        room_id: str,
        world: World,
        chat: ChatService,
        archive: ChatArchivePort,
        clock: ClockPort,
        max_clients: int = MAX_CLIENTS,
    ) -> None:
        self.room_id = room_id
        self.world = world
        self._chat = chat
        self._archive = archive
        self._clock = clock
        self._max_clients = max_clients
        self._members: dict[int, Member] = {}
        self._nicknames = NicknameFactory()
        self._colors = ColorAllocator()
        self._next_id = 1
        self._spawn_cursor = 0
        self._tick = 0
        self._task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()
        # Detached cleanup tasks are held so the loop cannot collect them early.
        self._background: set[asyncio.Task[None]] = set()

    # --- lifecycle ---------------------------------------------------------

    async def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run(), name=f"ascii-city-room:{self.room_id}")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        await self.drain()
        for member in list(self._members.values()):
            with contextlib.suppress(Exception):
                await member.connection.close(1001, "Server shutting down.")
        self._members.clear()

    async def drain(self) -> None:
        """Await detached cleanup work, which may itself detach more work."""
        while self._background:
            await asyncio.gather(*list(self._background), return_exceptions=True)

    @property
    def population(self) -> int:
        return len(self._members)

    @property
    def tick(self) -> int:
        return self._tick

    def stats(self) -> dict[str, object]:
        return {
            "roomId": self.room_id,
            "population": self.population,
            "maxClients": self._max_clients,
            "tick": self._tick,
            "simulationHz": SIMULATION_HZ,
            "snapshotHz": SNAPSHOT_HZ,
            "nicknames": sorted(self._nicknames.taken),
        }

    # --- membership --------------------------------------------------------

    async def join(self, connection: PlayerConnection) -> Member:
        async with self._lock:
            if len(self._members) >= self._max_clients:
                raise RoomFullError(f"Room {self.room_id} is full.")
            player_id = self._allocate_id()
            spawn_x, spawn_y, heading = self._next_spawn()
            spawn_x, spawn_y = find_safe_position(self.world.grid, spawn_x, spawn_y)
            state = PlayerState(
                id=player_id,
                nickname=self._nicknames.issue(),
                color=self._colors.issue(player_id),
                avatar=pick_avatar(),
                x=spawn_x,
                y=spawn_y,
                z=EYE_HEIGHT_M,
                yaw=heading,
                joined_at=self._clock.wall(),
                last_seen=self._clock.monotonic(),
            )
            member = Member(
                state=state,
                connection=connection,
                last_frame_at=self._clock.monotonic(),
            )
            self._members[player_id] = member

        descriptor = self.world.descriptor
        await self._send(
            member,
            wire.encode_welcome(
                player=state,
                simulation_hz=SIMULATION_HZ,
                snapshot_hz=SNAPSHOT_HZ,
                server_time_ms=int(self._clock.wall() * 1000),
                world_id=descriptor.id,
                world_version=descriptor.version,
                tiles_x=descriptor.tiles_x,
                tiles_y=descriptor.tiles_y,
                tile_cells=descriptor.tile_cells,
                cell_size=descriptor.cell_size,
            ),
        )
        await self._send(
            member,
            wire.encode_roster_sync([other.state for other in self._members.values()]),
        )
        for message in await self._archive.recent(self.room_id, CHAT_HISTORY_SIZE):
            await self._send(member, wire.encode_chat(message))

        await self._broadcast(wire.encode_roster_add(state), exclude=player_id)
        await self._announce(f"{state.nickname} entered the district.")
        logger.info("%s joined %s (%d online)", state.nickname, self.room_id, len(self._members))
        return member

    async def leave(self, member: Member) -> None:
        if not member.alive:
            return
        member.alive = False
        self._members.pop(member.state.id, None)
        self._nicknames.release(member.state.nickname)
        self._colors.release(member.state.color)
        self._chat.forget(member.state.id)
        logger.info("%s left %s (%d online)", member.state.nickname, self.room_id, len(self._members))
        # leave() usually runs in the departing socket's task, which the ASGI
        # server may already be cancelling. Announcing from a room-owned task
        # and shielding the wait keeps the roster from stranding a ghost.
        await self._shielded(self._announce_departure(member.state))

    async def _announce_departure(self, state: PlayerState) -> None:
        await self._broadcast(wire.encode_roster_remove(state.id))
        await self._announce(f"{state.nickname} left the district.")

    async def _shielded(self, coroutine) -> None:
        task = asyncio.create_task(coroutine)
        self._background.add(task)
        task.add_done_callback(self._background.discard)
        await asyncio.shield(task)

    def _allocate_id(self) -> int:
        for _ in range(65535):
            candidate = self._next_id
            self._next_id = self._next_id % 65534 + 1
            if candidate not in self._members:
                return candidate
        raise RoomFullError("No free player identifiers.")

    def _next_spawn(self) -> tuple[float, float, float]:
        spawns = self.world.spawn_points
        spawn = spawns[self._spawn_cursor % len(spawns)]
        self._spawn_cursor += 1
        return spawn

    # --- inbound frames ----------------------------------------------------

    async def handle_frame(self, member: Member, payload: bytes) -> None:
        member.last_frame_at = self._clock.monotonic()
        member.state.last_seen = member.last_frame_at
        try:
            frame = wire.decode_client_frame(payload)
        except ProtocolError as exc:
            await self._send(member, wire.encode_notice(wire.NOTICE_WARNING, str(exc)))
            return

        if isinstance(frame, InputCommand):
            # A replayed or reordered frame would move the player a second time
            # and, worse, walk last_input_sequence backwards, which makes the
            # client re-apply input it had already retired.
            if not _sequence_is_newer(frame.sequence, member.highest_sequence):
                return
            member.highest_sequence = frame.sequence
            if len(member.inputs) >= MAX_QUEUED_INPUTS:
                member.inputs.popleft()  # keep the freshest intent, drop the stale one
            member.inputs.append(frame)
            return

        if isinstance(frame, wire.PingRequest):
            await self._send(
                member,
                wire.encode_pong(frame.client_time, int(self._clock.wall() * 1000)),
            )
            return

        if isinstance(frame, wire.RenameRequest):
            await self._handle_rename(member, frame.nickname)
            return

        if isinstance(frame, wire.SetAvatarRequest):
            await self._handle_set_avatar(member, frame.avatar)
            return

        await self._handle_chat(member, frame.scope, frame.text)

    async def _handle_set_avatar(self, member: Member, avatar: int) -> None:
        if not is_valid_avatar(avatar):
            await self._send(member, wire.encode_notice(wire.NOTICE_WARNING, "No such avatar."))
            return
        if avatar == member.state.avatar:
            return
        member.state.avatar = avatar
        await self._broadcast(wire.encode_roster_update(member.state))

    async def _handle_rename(self, member: Member, nickname: str) -> None:
        cleaned = nickname.strip()
        if not is_safe_nickname(cleaned):
            await self._send(
                member,
                wire.encode_notice(
                    wire.NOTICE_WARNING,
                    "Nicknames are 6-24 characters: letters, digits and hyphens.",
                ),
            )
            return
        if cleaned == member.state.nickname:
            return
        if not self._nicknames.rename(member.state.nickname, cleaned):
            await self._send(member, wire.encode_notice(wire.NOTICE_WARNING, "That nickname is taken."))
            return
        old = member.state.nickname
        member.state.nickname = cleaned
        await self._broadcast(wire.encode_roster_update(member.state))
        await self._announce(f"{old} is now {cleaned}.")

    async def _handle_chat(self, member: Member, scope: ChatScope, text: str) -> None:
        try:
            message = self._chat.compose(member.state, scope, text)
        except ChatRejected as exc:
            await self._send(member, wire.encode_notice(wire.NOTICE_RATE_LIMIT, exc.reason))
            return

        encoded = wire.encode_chat(message)
        if scope is ChatScope.PROXIMITY:
            listeners = within_radius(
                member.state,
                (other.state for other in self._members.values()),
                CHAT_PROXIMITY_RADIUS_M,
            )
            for state in listeners:
                target = self._members.get(state.id)
                if target is not None:
                    await self._send(target, encoded)
            return

        await self._archive.append(self.room_id, message)
        await self._broadcast(encoded)

    async def _announce(self, text: str) -> None:
        await self._broadcast(wire.encode_chat(self._chat.system(text)))

    # --- simulation --------------------------------------------------------

    async def _run(self) -> None:
        step = 1.0 / SIMULATION_HZ
        snapshot_every = max(1, round(SIMULATION_HZ / SNAPSHOT_HZ))
        next_at = self._clock.monotonic() + step
        while True:
            delay = next_at - self._clock.monotonic()
            if delay > 0:
                await asyncio.sleep(delay)
            else:
                # Fell behind: give the loop a chance to breathe, then catch up.
                await asyncio.sleep(0)
                next_at = self._clock.monotonic()
            next_at += step
            try:
                await self.step(step, emit=self._tick % snapshot_every == 0)
            except Exception:
                logger.exception("Simulation tick failed in room %s", self.room_id)

    async def step(self, dt: float, *, emit: bool = True) -> None:
        """One simulation tick. Exposed so tests can drive the room by hand."""
        self._tick += 1
        self._apply_inputs(dt)
        self._evict_silent()
        if emit:
            await self._emit_snapshots()

    def _apply_inputs(self, dt: float) -> None:
        for member in self._members.values():
            member.budget = min(INPUT_BURST_TOKENS, member.budget + 1)
            applied = 0
            while member.inputs and member.budget > 0:
                command = member.inputs.popleft()
                move_player(member.state, command, self.world.grid, dt)
                member.budget -= 1
                applied += 1
            if applied == 0 and member.state.animation != ANIMATION_IDLE:
                # No fresh intent this tick: stop rather than coast.
                member.state.animation = ANIMATION_IDLE
                member.state.velocity_x = 0.0
                member.state.velocity_y = 0.0

    def _evict_silent(self) -> None:
        now = self._clock.monotonic()
        for member in list(self._members.values()):
            if now - member.last_frame_at > HEARTBEAT_TIMEOUT_S:
                logger.info("Dropping silent player %s", member.state.nickname)
                self._spawn_cleanup(member, 1001, "Heartbeat timeout.")

    def _spawn_cleanup(self, member: Member, code: int, reason: str) -> None:
        task = asyncio.create_task(self._disconnect(member, code, reason))
        self._background.add(task)
        task.add_done_callback(self._background.discard)

    async def _disconnect(self, member: Member, code: int, reason: str) -> None:
        await self.leave(member)
        with contextlib.suppress(Exception):
            await member.connection.close(code, reason)

    async def _emit_snapshots(self) -> None:
        states = [member.state for member in self._members.values()]
        for member in list(self._members.values()):
            entries = visible_players(member.state, states)
            await self._send(
                member,
                wire.encode_snapshot(
                    tick=self._tick,
                    ack_sequence=member.state.last_input_sequence,
                    viewer=member.state,
                    entries=entries,
                ),
            )

    # --- outbound ----------------------------------------------------------

    async def _send(self, member: Member, payload: bytes) -> None:
        if not member.alive:
            return
        try:
            await asyncio.wait_for(member.connection.send(payload), timeout=SEND_TIMEOUT_S)
        except Exception:
            # A client that cannot take a frame within the timeout, or whose
            # socket has already gone, is removed instead of stalling the tick.
            if member.alive:
                logger.debug("Dropping unreachable player %s", member.state.nickname)
                self._spawn_cleanup(member, 1011, "Send failed.")

    async def _broadcast(self, payload: bytes, *, exclude: int | None = None) -> None:
        targets = [
            member
            for member in self._members.values()
            if member.alive and member.state.id != exclude
        ]
        if not targets:
            return
        await asyncio.gather(
            *(self._send(member, payload) for member in targets),
            return_exceptions=True,
        )

    def chat_history_message(self, text: str) -> ChatMessage:
        """Helper used by presentation code that needs a system message object."""
        return self._chat.system(text)
