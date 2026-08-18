import pytest
from unittest.mock import AsyncMock
from netlazy.application.inbox_service import (
    InboxService,
    InvalidHandshakeStateError,
    UnauthorizedHandshakeActionError,
    HandshakeNotFoundError
)
from netlazy.domain.models import Handshake, User


@pytest.fixture
def inbox_deps():
    return {
        "handshake_repo": AsyncMock(),
        "profile_repo": AsyncMock(),
        "user_repo": AsyncMock()
    }


@pytest.fixture
def inbox_service(inbox_deps):
    return InboxService(**inbox_deps)


@pytest.mark.asyncio
async def test_send_handshake_missing_offered_contact(inbox_service):
    with pytest.raises(ValueError, match="offered_contact is required"):
        await inbox_service.send_handshake(
            sender_id="s1",
            receiver_id="r1",
            handshake_type="share",
            offered_contact=None
        )


@pytest.mark.asyncio
async def test_send_handshake_success(inbox_service, inbox_deps):
    inbox_deps["handshake_repo"].get_between_users.return_value = None

    h = await inbox_service.send_handshake(
        sender_id="s1",
        receiver_id="r1",
        handshake_type="exchange",
        offered_contact="telegram:@s1_handle",
        message="Let's connect"
    )

    assert h.status == "pending"
    assert h.sender_id == "s1"
    assert h.receiver_id == "r1"
    inbox_deps["handshake_repo"].create.assert_called_once()


@pytest.mark.asyncio
async def test_resolve_handshake_unauthorized(inbox_service, inbox_deps):
    mock_handshake = Handshake(
        id="h1",
        sender_id="s1",
        receiver_id="r1",
        handshake_type="share",
        status="pending"
    )
    inbox_deps["handshake_repo"].get_by_id.return_value = mock_handshake

    with pytest.raises(UnauthorizedHandshakeActionError):
        # Non-receiver attempting to accept
        await inbox_service.resolve_handshake(
            user_id="intruder",
            handshake_id="h1",
            status="accepted"
        )


@pytest.mark.asyncio
async def test_resolve_handshake_accept_exchange(inbox_service, inbox_deps):
    mock_handshake = Handshake(
        id="h1",
        sender_id="s1",
        receiver_id="r1",
        handshake_type="exchange",
        status="pending",
        offered_contact="phone:123"
    )
    inbox_deps["handshake_repo"].get_by_id.return_value = mock_handshake
    inbox_deps["user_repo"].get_by_id.return_value = User("s1", "ed", "pq", None, is_banned=False)

    resolved = await inbox_service.resolve_handshake(
        user_id="r1",
        handshake_id="h1",
        status="accepted",
        returned_contact="phone:456"
    )

    assert resolved.status == "accepted"
    assert resolved.returned_contact == "phone:456"
    inbox_deps["handshake_repo"].update.assert_called_once()