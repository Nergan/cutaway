"""Wire protocol: encoding fidelity and hostile-input handling."""

from __future__ import annotations

import math
import struct

import pytest

from ascii_city.domain.chat import ChatMessage, ChatScope
from ascii_city.domain.errors import ProtocolError
from ascii_city.domain.player import InputCommand, PlayerState
from ascii_city.infrastructure import wire_codec as wire


def a_player(player_id: int = 7, **overrides) -> PlayerState:
    defaults = dict(
        id=player_id,
        nickname=f"QuietFox-{1000 + player_id}",
        color=3,
        avatar=5,
        x=123.45,
        y=67.89,
        z=1.7,
        yaw=1.25,
        pitch=-0.4,
    )
    defaults.update(overrides)
    return PlayerState(**defaults)


def encode_input(**overrides) -> bytes:
    fields = dict(sequence=42, forward=100, strafe=-50, yaw=1000, pitch=25, flags=1, client_time=99)
    fields.update(overrides)
    return bytes([wire.MSG_INPUT]) + struct.pack(
        "<IbbHbBI",
        fields["sequence"],
        fields["forward"],
        fields["strafe"],
        fields["yaw"],
        fields["pitch"],
        fields["flags"],
        fields["client_time"],
    )


# --- scalar encodings ------------------------------------------------------


@pytest.mark.parametrize("value", [0.0, 1.0, 123.45, 655.35])
def test_position_round_trip_is_centimetre_accurate(value):
    assert wire.decode_position(wire.encode_position(value)) == pytest.approx(value, abs=0.005)


def test_position_encoding_saturates_instead_of_wrapping():
    assert wire.encode_position(-5.0) == 0
    assert wire.encode_position(10_000.0) == 65535


@pytest.mark.parametrize("value", [0.0, 0.5, math.pi, 6.28])
def test_yaw_round_trip(value):
    assert wire.decode_yaw(wire.encode_yaw(value)) == pytest.approx(value, abs=1e-4)


def test_yaw_wraps_a_full_turn_to_zero():
    assert wire.encode_yaw(math.tau) == 0
    assert wire.encode_yaw(-0.1) == wire.encode_yaw(math.tau - 0.1)


def test_pitch_saturates_at_the_signed_byte_limits():
    assert wire.encode_pitch(99.0) == 127
    assert wire.encode_pitch(-99.0) == -127
    assert wire.decode_pitch(wire.encode_pitch(-0.4)) == pytest.approx(-0.4, abs=0.005)


# --- inbound frames --------------------------------------------------------


def test_input_frame_decodes_into_a_sanitised_command():
    frame = wire.decode_client_frame(encode_input())
    assert isinstance(frame, InputCommand)
    assert frame.sequence == 42
    assert frame.forward == pytest.approx(1.0)
    assert frame.strafe == pytest.approx(-0.5)
    assert frame.sprint is True
    assert 0 <= frame.yaw < math.tau


def test_oversized_analogue_axes_are_clamped_on_arrival():
    frame = wire.decode_client_frame(encode_input(forward=127, strafe=-128))
    assert frame.forward == pytest.approx(1.0)
    assert frame.strafe == pytest.approx(-1.0)


def test_chat_frame_decodes():
    text = "hello, city".encode("utf-8")
    payload = bytes([wire.MSG_CHAT, 0]) + len(text).to_bytes(2, "little") + text
    frame = wire.decode_client_frame(payload)
    assert isinstance(frame, wire.ChatRequest)
    assert frame.scope is ChatScope.GLOBAL
    assert frame.text == "hello, city"


def test_ping_frame_decodes():
    payload = bytes([wire.MSG_PING]) + (1234).to_bytes(4, "little")
    frame = wire.decode_client_frame(payload)
    assert isinstance(frame, wire.PingRequest)
    assert frame.client_time == 1234


@pytest.mark.parametrize(
    "payload, reason",
    [
        (b"", "empty"),
        (b"\xff\x00", "unknown type"),
        (bytes([wire.MSG_INPUT]) + b"\x00" * 3, "short input"),
        (bytes([wire.MSG_PING]) + b"\x00" * 9, "long ping"),
        (bytes([wire.MSG_CHAT, 0, 100, 0]) + b"ab", "truncated chat"),
        (bytes([wire.MSG_CHAT, 9, 1, 0]) + b"x", "invalid scope"),
        (bytes([wire.MSG_CHAT, 0, 2, 0]) + b"\xff\xfe", "invalid utf-8"),
    ],
)
def test_malformed_frames_are_rejected(payload, reason):
    with pytest.raises(ProtocolError):
        wire.decode_client_frame(payload)


def test_clients_cannot_forge_system_chat():
    payload = bytes([wire.MSG_CHAT, 2, 1, 0]) + b"x"
    with pytest.raises(ProtocolError):
        wire.decode_client_frame(payload)


def test_a_frame_beyond_the_size_limit_is_refused_before_parsing():
    with pytest.raises(ProtocolError):
        wire.decode_client_frame(bytes([wire.MSG_CHAT]) + b"\x00" * (wire.MAX_FRAME_BYTES + 1))


# --- outbound frames -------------------------------------------------------


def test_welcome_carries_the_world_shape():
    payload = wire.encode_welcome(
        player=a_player(),
        simulation_hz=20,
        snapshot_hz=20,
        server_time_ms=1700,
        world_id="demo",
        world_version=3,
        tiles_x=2,
        tiles_y=2,
        tile_cells=128,
        cell_size=2.0,
    )
    assert payload[0] == wire.MSG_WELCOME
    player_id, color, avatar, nick_len = struct.unpack_from("<HBBB", payload, 1)
    assert player_id == 7 and color == 3 and avatar == 5
    assert payload[6 : 6 + nick_len].decode() == "QuietFox-1007"
    tail = struct.unpack_from("<HHHHBBIBBHfI", payload, 6 + nick_len)
    assert tail[4] == 20 and tail[5] == 20
    assert tail[7] == 2 and tail[8] == 2 and tail[9] == 128
    assert tail[10] == pytest.approx(2.0)
    assert tail[11] == 3
    assert payload.endswith(b"demo")


def test_snapshot_entry_is_twelve_bytes():
    """Entry size drives the bandwidth budget documented in docs/protocol.md."""
    assert wire._SNAPSHOT_ENTRY.size == 12
    viewer = a_player(1)
    others = [(a_player(index), index % 2 == 0) for index in range(2, 6)]
    payload = wire.encode_snapshot(tick=5, ack_sequence=99, viewer=viewer, entries=others)
    header = 1 + wire._SNAPSHOT_HEAD.size + 1
    assert payload[0] == wire.MSG_SNAPSHOT
    assert payload[header - 1] == 4
    assert len(payload) == header + 4 * wire._SNAPSHOT_ENTRY.size


def test_snapshot_marks_distant_players_as_simplified():
    payload = wire.encode_snapshot(
        tick=1,
        ack_sequence=0,
        viewer=a_player(1),
        entries=[(a_player(2), True)],
    )
    offset = 1 + wire._SNAPSHOT_HEAD.size + 1
    _id, _x, _y, _z, _yaw, _pitch, flags = wire._SNAPSHOT_ENTRY.unpack_from(payload, offset)
    assert flags & wire.SNAPSHOT_FLAG_SIMPLIFIED


def test_snapshot_entries_carry_the_height_a_jump_reaches():
    airborne = a_player(2)
    airborne.z = 3.05
    payload = wire.encode_snapshot(
        tick=1, ack_sequence=0, viewer=a_player(1), entries=[(airborne, False)]
    )
    offset = 1 + wire._SNAPSHOT_HEAD.size + 1
    _id, _x, _y, z, *_rest = wire._SNAPSHOT_ENTRY.unpack_from(payload, offset)
    assert wire.decode_position(z) == pytest.approx(3.05)


def test_snapshot_truncates_beyond_the_byte_count_field():
    entries = [(a_player(index), False) for index in range(1, 400)]
    payload = wire.encode_snapshot(tick=1, ack_sequence=0, viewer=a_player(1), entries=entries)
    count = payload[1 + wire._SNAPSHOT_HEAD.size]
    assert count == 255
    assert len(payload) == 1 + wire._SNAPSHOT_HEAD.size + 1 + 255 * wire._SNAPSHOT_ENTRY.size


def test_chat_frame_preserves_unicode():
    message = ChatMessage(
        id=1,
        sender_id=7,
        nickname="AmberGhost-1930",
        text="привет, город \u2588",
        scope=ChatScope.GLOBAL,
        created_at=1_700_000_000.5,
    )
    payload = wire.encode_chat(message)
    assert payload[0] == wire.MSG_CHAT_OUT
    assert message.text.encode("utf-8") in payload
    assert message.nickname.encode("utf-8") in payload


def test_roster_frames():
    player = a_player(9)
    assert wire.encode_roster_add(player)[0] == wire.MSG_ROSTER_ADD
    assert wire.encode_roster_remove(9) == bytes([wire.MSG_ROSTER_REMOVE, 9, 0])
    sync = wire.encode_roster_sync([player, a_player(10)])
    assert sync[0] == wire.MSG_ROSTER_SYNC
    assert int.from_bytes(sync[1:3], "little") == 2
    update = wire.encode_roster_update(player)
    assert update[0] == wire.MSG_ROSTER_UPDATE


def test_rename_frame_decodes():
    nick = "NeonFox-2044".encode("utf-8")
    payload = bytes([wire.MSG_RENAME]) + len(nick).to_bytes(2, "little") + nick
    frame = wire.decode_client_frame(payload)
    assert isinstance(frame, wire.RenameRequest)
    assert frame.nickname == "NeonFox-2044"


def test_input_jump_flag_decodes():
    frame = wire.decode_client_frame(encode_input(flags=wire.INPUT_FLAG_JUMP | wire.INPUT_FLAG_SPRINT))
    assert frame.jump is True
    assert frame.sprint is True


def test_set_avatar_frame_decodes():
    frame = wire.decode_client_frame(wire.encode_set_avatar(9))
    assert isinstance(frame, wire.SetAvatarRequest)
    assert frame.avatar == 9


def test_a_malformed_avatar_frame_is_refused():
    with pytest.raises(ProtocolError):
        wire.decode_client_frame(bytes([wire.MSG_SET_AVATAR, 1, 2]))


def test_roster_entries_carry_the_avatar():
    payload = wire.encode_roster_add(a_player(9))
    # type, id (u16), colour, avatar, nickname length, then the nickname.
    assert payload[3] == 3, "colour"
    assert payload[4] == 5, "avatar"
    assert payload[6 : 6 + payload[5]].decode() == "QuietFox-1009"


def test_notice_is_length_bounded():
    payload = wire.encode_notice(wire.NOTICE_WARNING, "x" * 4000)
    assert payload[0] == wire.MSG_NOTICE
    assert int.from_bytes(payload[2:4], "little") == 512
