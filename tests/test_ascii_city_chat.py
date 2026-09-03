"""Chat sanitising, rate limiting and nickname policy."""

from __future__ import annotations

import pytest

from ascii_city.application.chat_service import ChatService
from ascii_city.application.nicknames import NicknameFactory, is_safe_nickname, pick_color
from ascii_city.domain.chat import ChatScope, sanitise_chat_text
from ascii_city.domain.constants import CHAT_MAX_LENGTH, CHAT_RATE_LIMIT, PLAYER_COLOR_COUNT
from ascii_city.domain.errors import ChatRejected
from ascii_city.domain.player import PlayerState


def a_player(player_id: int = 1) -> PlayerState:
    return PlayerState(id=player_id, nickname=f"NeonOtter-{7000 + player_id}", color=0, x=0.0, y=0.0)


# --- sanitising ------------------------------------------------------------


def test_plain_text_survives():
    assert sanitise_chat_text("  hello   city  ") == "hello city"


def test_angle_brackets_are_kept_as_literal_text():
    """Markup never executes because clients render into text nodes and glyph
    cells, so brackets stay usable as ASCII art."""
    assert sanitise_chat_text("<script>alert(1)</script>") == "<script>alert(1)</script>"
    assert sanitise_chat_text("look: <-o->") == "look: <-o->"


@pytest.mark.parametrize(
    "raw",
    [
        "abc\u0000def",
        "abc\u001bdef",
        "abc\u200bdef",
        "abc\u202edef",
        "abc\ufeffdef",
        "abc\ndef",
    ],
)
def test_control_and_bidi_characters_are_stripped(raw):
    cleaned = sanitise_chat_text(raw)
    assert cleaned.replace(" ", "") == "abcdef"


def test_empty_and_whitespace_only_messages_are_rejected():
    for raw in ("", "   ", "\u200b\u200b"):
        with pytest.raises(ChatRejected):
            sanitise_chat_text(raw)


def test_length_ceiling_is_enforced():
    assert len(sanitise_chat_text("a" * CHAT_MAX_LENGTH)) == CHAT_MAX_LENGTH
    with pytest.raises(ChatRejected):
        sanitise_chat_text("a" * (CHAT_MAX_LENGTH + 1))


def test_unicode_is_normalised():
    # Combining acute accent folds into the precomposed character.
    assert sanitise_chat_text("cafe\u0301") == "café"


# --- service ---------------------------------------------------------------


def test_compose_builds_a_message(manual_clock):
    service = ChatService(manual_clock)
    message = service.compose(a_player(), ChatScope.GLOBAL, "hi")
    assert message.text == "hi"
    assert message.sender_id == 1
    assert message.scope is ChatScope.GLOBAL
    assert message.created_at == manual_clock.wall()


def test_message_ids_increase(manual_clock):
    service = ChatService(manual_clock)
    player = a_player()
    ids = [service.compose(player, ChatScope.GLOBAL, str(index)).id for index in range(3)]
    assert ids == sorted(set(ids))


def test_players_cannot_send_system_messages(manual_clock):
    service = ChatService(manual_clock)
    with pytest.raises(ChatRejected):
        service.compose(a_player(), ChatScope.SYSTEM, "server is down")


def test_rate_limit_blocks_the_sixth_message(manual_clock):
    service = ChatService(manual_clock)
    player = a_player()
    for index in range(CHAT_RATE_LIMIT):
        service.compose(player, ChatScope.GLOBAL, f"msg {index}")
    with pytest.raises(ChatRejected) as excinfo:
        service.compose(player, ChatScope.GLOBAL, "one too many")
    assert excinfo.value.retry_after and excinfo.value.retry_after > 0


def test_the_rate_limit_window_slides(manual_clock):
    service = ChatService(manual_clock)
    player = a_player()
    for index in range(CHAT_RATE_LIMIT):
        service.compose(player, ChatScope.GLOBAL, f"msg {index}")
    manual_clock.advance(10.1)
    assert service.compose(player, ChatScope.GLOBAL, "later").text == "later"


def test_the_rate_limit_is_per_player(manual_clock):
    service = ChatService(manual_clock)
    for index in range(CHAT_RATE_LIMIT):
        service.compose(a_player(1), ChatScope.GLOBAL, str(index))
    assert service.compose(a_player(2), ChatScope.GLOBAL, "fresh").text == "fresh"


def test_forgetting_a_player_clears_their_budget(manual_clock):
    service = ChatService(manual_clock)
    player = a_player()
    for index in range(CHAT_RATE_LIMIT):
        service.compose(player, ChatScope.GLOBAL, str(index))
    service.forget(player.id)
    assert service.compose(player, ChatScope.GLOBAL, "reconnected").text == "reconnected"


# --- nicknames -------------------------------------------------------------


def test_issued_nicknames_are_unique_and_safe():
    factory = NicknameFactory()
    issued = {factory.issue() for _ in range(500)}
    assert len(issued) == 500
    for nickname in issued:
        assert is_safe_nickname(nickname), nickname


def test_releasing_a_nickname_returns_it_to_the_pool():
    factory = NicknameFactory()
    nickname = factory.issue()
    assert nickname in factory.taken
    factory.release(nickname)
    assert nickname not in factory.taken


@pytest.mark.parametrize(
    "value",
    ["abc", "a" * 25, "has space", "<script>", "trailing-", "-leading", "emoji\U0001f600x"],
)
def test_unsafe_nicknames_are_rejected(value):
    assert not is_safe_nickname(value)


def test_colours_stay_inside_the_palette():
    assert {pick_color(index) for index in range(200)} <= set(range(PLAYER_COLOR_COUNT))
