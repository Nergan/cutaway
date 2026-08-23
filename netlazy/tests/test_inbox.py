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
    user_repo = AsyncMock()
    user_repo.get_by_id.side_effect = lambda uid: User(uid, "ed", "pq", None, is_banned=False)
    return {
        "handshake_repo": AsyncMock(),
        "profile_repo": AsyncMock(),
        "user_repo": user_repo
    }


@pytest.fixture
def inbox_service(inbox_deps):
    return InboxService(**inbox_deps)


@pytest.mark.asyncio
async def test_send_handshake_self_rejected(inbox_service):
    with pytest.raises(ValueError, match="Cannot send handshake to self"):
        await inbox_service.send_handshake(
            sender_id="user_same",
            receiver_id="user_same",
            handshake_type="share",
            offered_contact="test@example.com"
        )


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
async def test_send_handshake_already_accepted(inbox_service, inbox_deps):
    existing = Handshake(
        id="h1", sender_id="s1", receiver_id="r1",
        handshake_type="exchange", status="accepted"
    )
    inbox_deps["user_repo"].get_by_id.side_effect = lambda uid: User(uid, "ed", "pq", None, is_banned=False)
    inbox_deps["handshake_repo"].get_between_users.return_value = existing

    with pytest.raises(InvalidHandshakeStateError, match="Handshake already accepted"):
        await inbox_service.send_handshake(
            sender_id="s1",
            receiver_id="r1",
            handshake_type="exchange",
            offered_contact="contact_info"
        )


@pytest.mark.asyncio
async def test_send_handshake_success(inbox_service, inbox_deps):
    inbox_deps["user_repo"].get_by_id.side_effect = lambda uid: User(uid, "ed", "pq", None, is_banned=False)
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
    assert resolved.is_read is False
    inbox_deps["handshake_repo"].update.assert_called_once()


@pytest.mark.asyncio
async def test_mark_as_read_receiver_pending(inbox_service, inbox_deps):
    mock_handshake = Handshake(
        id="h1",
        sender_id="s1",
        receiver_id="r1",
        handshake_type="exchange",
        status="pending",
        is_read=False,
    )
    inbox_deps["handshake_repo"].get_by_id.return_value = mock_handshake

    marked = await inbox_service.mark_as_read("r1", "h1")

    assert marked.is_read is True
    inbox_deps["handshake_repo"].update.assert_called_once()


@pytest.mark.asyncio
async def test_mark_as_read_sender_pending_does_not_consume_flag(inbox_service, inbox_deps):
    mock_handshake = Handshake(
        id="h1",
        sender_id="s1",
        receiver_id="r1",
        handshake_type="share",
        status="pending",
        is_read=False,
    )
    inbox_deps["handshake_repo"].get_by_id.return_value = mock_handshake

    marked = await inbox_service.mark_as_read("s1", "h1")

    assert marked.is_read is False
    inbox_deps["handshake_repo"].update.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("handshake_type", ["exchange", "demand", "mutual"])
async def test_sender_cannot_revoke_pending_response_request(inbox_service, inbox_deps, handshake_type):
    inbox_deps["handshake_repo"].get_by_id.return_value = Handshake(
        id="h1", sender_id="s1", receiver_id="r1",
        handshake_type=handshake_type, status="pending"
    )

    with pytest.raises(InvalidHandshakeStateError, match="Cannot revoke"):
        await inbox_service.delete_handshake("s1", "h1")

    inbox_deps["handshake_repo"].update.assert_not_called()
    inbox_deps["handshake_repo"].delete.assert_not_called()


@pytest.mark.asyncio
async def test_sender_can_delete_pending_share(inbox_service, inbox_deps):
    inbox_deps["handshake_repo"].get_by_id.return_value = Handshake(
        id="h1", sender_id="s1", receiver_id="r1",
        handshake_type="share", status="pending"
    )

    await inbox_service.delete_handshake("s1", "h1")

    updated = inbox_deps["handshake_repo"].update.call_args.args[0]
    assert updated.sender_deleted is True
    inbox_deps["handshake_repo"].delete.assert_not_called()


@pytest.mark.asyncio
async def test_sender_can_delete_resolved_exchange(inbox_service, inbox_deps):
    inbox_deps["handshake_repo"].get_by_id.return_value = Handshake(
        id="h1", sender_id="s1", receiver_id="r1",
        handshake_type="exchange", status="accepted"
    )

    await inbox_service.delete_handshake("s1", "h1")

    updated = inbox_deps["handshake_repo"].update.call_args.args[0]
    assert updated.sender_deleted is True