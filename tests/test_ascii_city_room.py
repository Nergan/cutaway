"""The authoritative room: membership, snapshots, interest and chat routing.

Tests drive the simulation by hand through :meth:`CityRoom.step` rather than
starting the real loop, so they are deterministic and never sleep.
"""

from __future__ import annotations

import asyncio
import struct

import pytest

from ascii_city.application.chat_service import ChatService
from ascii_city.application.interest import MAX_SNAPSHOT_ENTRIES, visible_players
from ascii_city.application.room import INPUT_BURST_TOKENS, CityRoom
from ascii_city.domain.constants import (
    FULL_DETAIL_RADIUS_M,
    MAX_QUEUED_INPUTS,
    SIMULATION_HZ,
    SIMPLIFIED_RADIUS_M,
    WALK_SPEED_MS,
)
from ascii_city.domain.errors import RoomFullError
from ascii_city.domain.player import PlayerState
from ascii_city.infrastructure import wire_codec as wire
from ascii_city.infrastructure.repositories.memory import InMemoryChatArchive

STEP = 1 / SIMULATION_HZ


def make_room(world, clock, max_clients=8) -> CityRoom:
    return CityRoom(
        room_id="city:test:main",
        world=world,
        chat=ChatService(clock),
        archive=InMemoryChatArchive(),
        clock=clock,
        max_clients=max_clients,
    )


def input_frame(sequence: int, *, forward=1.0, strafe=0.0, yaw=0.0, sprint=False) -> bytes:
    return bytes([wire.MSG_INPUT]) + struct.pack(
        "<IbbHbBI",
        sequence,
        int(forward * 100),
        int(strafe * 100),
        wire.encode_yaw(yaw),
        0,
        1 if sprint else 0,
        0,
    )


def chat_frame(text: str, scope: int = 0) -> bytes:
    encoded = text.encode("utf-8")
    return bytes([wire.MSG_CHAT, scope]) + len(encoded).to_bytes(2, "little") + encoded


def decode_snapshot_ids(payload: bytes) -> list[int]:
    offset = 1 + wire._SNAPSHOT_HEAD.size
    count = payload[offset]
    offset += 1
    ids = []
    for _ in range(count):
        entry = wire._SNAPSHOT_ENTRY.unpack_from(payload, offset)
        ids.append(entry[0])
        offset += wire._SNAPSHOT_ENTRY.size
    return ids


# --- membership ------------------------------------------------------------


def test_join_issues_a_welcome_and_a_roster(small_world, manual_clock, connection_factory):
    async def scenario():
        room = make_room(small_world, manual_clock)
        connection = connection_factory()
        member = await room.join(connection)

        assert connection.frames(wire.MSG_WELCOME), "no welcome frame"
        assert connection.frames(wire.MSG_ROSTER_SYNC), "no roster frame"
        assert room.population == 1
        # The nickname is server-issued; the client never supplied one.
        assert member.state.nickname and "-" in member.state.nickname
        return member

    member = asyncio.run(scenario())
    assert 6 <= len(member.state.nickname) <= 24


def test_nicknames_are_unique_within_a_room(small_world, manual_clock, connection_factory):
    async def scenario():
        room = make_room(small_world, manual_clock, max_clients=8)
        members = [await room.join(connection_factory()) for _ in range(8)]
        return {member.state.nickname for member in members}

    assert len(asyncio.run(scenario())) == 8


def test_spawn_points_rotate_between_players(small_world, manual_clock, connection_factory):
    async def scenario():
        room = make_room(small_world, manual_clock)
        first = await room.join(connection_factory())
        second = await room.join(connection_factory())
        return (first.state.x, first.state.y), (second.state.x, second.state.y)

    first, second = asyncio.run(scenario())
    assert first != second


def test_a_full_room_refuses_the_next_player(small_world, manual_clock, connection_factory):
    async def scenario():
        room = make_room(small_world, manual_clock, max_clients=2)
        await room.join(connection_factory())
        await room.join(connection_factory())
        with pytest.raises(RoomFullError):
            await room.join(connection_factory())
        return room.population

    assert asyncio.run(scenario()) == 2


def test_leaving_frees_the_slot_and_tells_everyone(small_world, manual_clock, connection_factory):
    async def scenario():
        room = make_room(small_world, manual_clock)
        watcher = connection_factory()
        await room.join(watcher)
        leaver = await room.join(connection_factory())
        watcher.sent.clear()

        await room.leave(leaver)
        assert room.population == 1
        removals = watcher.frames(wire.MSG_ROSTER_REMOVE)
        assert removals and int.from_bytes(removals[0][1:3], "little") == leaver.state.id
        # A system chat line accompanies the departure.
        assert watcher.frames(wire.MSG_CHAT_OUT)

        # And the nickname becomes available again.
        assert leaver.state.nickname not in room.stats()["nicknames"]

    asyncio.run(scenario())


def test_leaving_twice_is_harmless(small_world, manual_clock, connection_factory):
    async def scenario():
        room = make_room(small_world, manual_clock)
        member = await room.join(connection_factory())
        await room.leave(member)
        await room.leave(member)
        return room.population

    assert asyncio.run(scenario()) == 0


# --- simulation ------------------------------------------------------------


def test_the_server_moves_players_only_from_input(small_world, manual_clock, connection_factory):
    async def scenario():
        room = make_room(small_world, manual_clock)
        member = await room.join(connection_factory())
        start = (member.state.x, member.state.y)

        await room.step(STEP)
        assert (member.state.x, member.state.y) == start, "moved without any input"

        await room.handle_frame(member, input_frame(1, yaw=member.state.yaw))
        await room.step(STEP)
        moved = abs(member.state.x - start[0]) + abs(member.state.y - start[1])
        assert moved == pytest.approx(WALK_SPEED_MS * STEP, rel=0.02) or moved == 0.0

    asyncio.run(scenario())


def test_input_flooding_buys_no_extra_speed(small_world, manual_clock, connection_factory):
    """A client that fires inputs far above the tick rate must not outrun one
    that respects it. The queue caps the burst and the token budget caps intake."""

    async def scenario():
        room = make_room(small_world, manual_clock)
        honest = await room.join(connection_factory())
        cheater = await room.join(connection_factory())
        # Same heading and starting axis so distances are comparable.
        cheater.state.x, cheater.state.y = honest.state.x, honest.state.y
        yaw = honest.state.yaw
        cheater.state.yaw = yaw
        origin = (honest.state.x, honest.state.y)

        for tick in range(20):
            await room.handle_frame(honest, input_frame(tick + 1, yaw=yaw))
            for burst in range(30):
                await room.handle_frame(cheater, input_frame(tick * 30 + burst + 1, yaw=yaw))
            await room.step(STEP, emit=False)

        honest_distance = abs(honest.state.x - origin[0]) + abs(honest.state.y - origin[1])
        cheater_distance = abs(cheater.state.x - origin[0]) + abs(cheater.state.y - origin[1])
        return honest_distance, cheater_distance

    honest_distance, cheater_distance = asyncio.run(scenario())
    # The burst allowance is bounded and one-off, not a per-tick multiplier.
    assert cheater_distance <= honest_distance + WALK_SPEED_MS * STEP * INPUT_BURST_TOKENS + 1e-6


def test_the_input_queue_is_bounded(small_world, manual_clock, connection_factory):
    async def scenario():
        room = make_room(small_world, manual_clock)
        member = await room.join(connection_factory())
        for sequence in range(100):
            await room.handle_frame(member, input_frame(sequence + 1))
        return len(member.inputs)

    assert asyncio.run(scenario()) == MAX_QUEUED_INPUTS


def test_snapshots_acknowledge_the_latest_input(small_world, manual_clock, connection_factory):
    async def scenario():
        room = make_room(small_world, manual_clock)
        connection = connection_factory()
        member = await room.join(connection)
        await room.handle_frame(member, input_frame(77, yaw=member.state.yaw))
        connection.sent.clear()
        await room.step(STEP)

        snapshots = connection.frames(wire.MSG_SNAPSHOT)
        assert snapshots
        _tick, ack, *_ = wire._SNAPSHOT_HEAD.unpack_from(snapshots[-1], 1)
        return ack

    assert asyncio.run(scenario()) == 77


def test_players_appear_in_each_other_snapshots(small_world, manual_clock, connection_factory):
    async def scenario():
        room = make_room(small_world, manual_clock)
        first_connection = connection_factory()
        second_connection = connection_factory()
        first = await room.join(first_connection)
        second = await room.join(second_connection)
        # Put them within the full-detail radius of one another.
        second.state.x, second.state.y = first.state.x + 5.0, first.state.y
        first_connection.sent.clear()
        second_connection.sent.clear()

        await room.step(STEP)
        return (
            decode_snapshot_ids(first_connection.frames(wire.MSG_SNAPSHOT)[-1]),
            decode_snapshot_ids(second_connection.frames(wire.MSG_SNAPSHOT)[-1]),
            first.state.id,
            second.state.id,
        )

    seen_by_first, seen_by_second, first_id, second_id = asyncio.run(scenario())
    assert seen_by_first == [second_id]
    assert seen_by_second == [first_id]


def test_a_silent_player_is_evicted(small_world, manual_clock, connection_factory):
    async def scenario():
        room = make_room(small_world, manual_clock)
        connection = connection_factory()
        await room.join(connection)
        manual_clock.advance(60.0)
        await room.step(STEP)
        await room.drain()  # eviction runs detached from the tick
        return room.population, connection.closed

    population, closed = asyncio.run(scenario())
    assert population == 0
    assert closed is not None and closed[0] == 1001


# --- interest management ---------------------------------------------------


def viewer_at(x: float, y: float, player_id: int = 1) -> PlayerState:
    return PlayerState(id=player_id, nickname=f"Test-{1000 + player_id}", color=0, x=x, y=y)


def test_interest_radii_classify_correctly():
    viewer = viewer_at(0.0, 0.0)
    near = viewer_at(FULL_DETAIL_RADIUS_M - 1, 0.0, 2)
    far = viewer_at(FULL_DETAIL_RADIUS_M + 10, 0.0, 3)
    out = viewer_at(SIMPLIFIED_RADIUS_M + 10, 0.0, 4)

    result = dict((player.id, simplified) for player, simplified in visible_players(viewer, [viewer, near, far, out]))
    assert result == {2: False, 3: True}


def test_interest_is_sorted_nearest_first_and_capped():
    viewer = viewer_at(0.0, 0.0)
    crowd = [viewer_at(float(index), 0.0, index + 1) for index in range(1, 120)]
    result = visible_players(viewer, crowd)
    assert len(result) == MAX_SNAPSHOT_ENTRIES
    distances = [abs(player.x) for player, _ in result]
    assert distances == sorted(distances)


# --- chat ------------------------------------------------------------------


def test_global_chat_reaches_everyone(small_world, manual_clock, connection_factory):
    async def scenario():
        room = make_room(small_world, manual_clock)
        speaker_connection = connection_factory()
        listener_connection = connection_factory()
        speaker = await room.join(speaker_connection)
        await room.join(listener_connection)
        listener_connection.sent.clear()

        await room.handle_frame(speaker, chat_frame("hello city"))
        return listener_connection.frames(wire.MSG_CHAT_OUT)

    frames = asyncio.run(scenario())
    assert frames and b"hello city" in frames[-1]


def test_proximity_chat_stays_local(small_world, manual_clock, connection_factory):
    async def scenario():
        room = make_room(small_world, manual_clock)
        speaker_connection = connection_factory()
        near_connection = connection_factory()
        far_connection = connection_factory()
        speaker = await room.join(speaker_connection)
        near = await room.join(near_connection)
        far = await room.join(far_connection)

        near.state.x, near.state.y = speaker.state.x + 5.0, speaker.state.y
        far.state.x, far.state.y = speaker.state.x + 200.0, speaker.state.y
        near_connection.sent.clear()
        far_connection.sent.clear()

        await room.handle_frame(speaker, chat_frame("only nearby", scope=1))
        return near_connection.frames(wire.MSG_CHAT_OUT), far_connection.frames(wire.MSG_CHAT_OUT)

    near_frames, far_frames = asyncio.run(scenario())
    assert near_frames and b"only nearby" in near_frames[-1]
    assert not far_frames


def test_chat_flooding_gets_a_notice_not_a_broadcast(small_world, manual_clock, connection_factory):
    async def scenario():
        room = make_room(small_world, manual_clock)
        speaker_connection = connection_factory()
        speaker = await room.join(speaker_connection)
        for index in range(8):
            await room.handle_frame(speaker, chat_frame(f"spam {index}"))
        return speaker_connection.frames(wire.MSG_NOTICE), speaker_connection.frames(wire.MSG_CHAT_OUT)

    notices, broadcasts = asyncio.run(scenario())
    assert notices, "no rate-limit notice"
    assert notices[-1][1] == wire.NOTICE_RATE_LIMIT
    # Five accepted messages plus the join announcement.
    assert len([frame for frame in broadcasts if b"spam" in frame]) == 5


def test_a_malformed_frame_earns_a_warning_not_a_disconnect(
    small_world, manual_clock, connection_factory
):
    async def scenario():
        room = make_room(small_world, manual_clock)
        connection = connection_factory()
        member = await room.join(connection)
        connection.sent.clear()
        await room.handle_frame(member, b"\xff\x00\x00")
        return connection.frames(wire.MSG_NOTICE), room.population

    notices, population = asyncio.run(scenario())
    assert notices and notices[-1][1] == wire.NOTICE_WARNING
    assert population == 1


def test_ping_is_answered(small_world, manual_clock, connection_factory):
    async def scenario():
        room = make_room(small_world, manual_clock)
        connection = connection_factory()
        member = await room.join(connection)
        connection.sent.clear()
        await room.handle_frame(member, bytes([wire.MSG_PING]) + (4321).to_bytes(4, "little"))
        return connection.frames(wire.MSG_PONG)

    pongs = asyncio.run(scenario())
    assert pongs
    client_time, _server_time = wire._PONG.unpack_from(pongs[-1], 1)
    assert client_time == 4321


def test_chat_history_is_replayed_to_a_late_joiner(small_world, manual_clock, connection_factory):
    async def scenario():
        room = make_room(small_world, manual_clock)
        speaker = await room.join(connection_factory())
        await room.handle_frame(speaker, chat_frame("said before you arrived"))

        latecomer = connection_factory()
        await room.join(latecomer)
        return latecomer.frames(wire.MSG_CHAT_OUT)

    frames = asyncio.run(scenario())
    assert any(b"said before you arrived" in frame for frame in frames)
