import pytest
import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from netlazy.application.auth_service import AuthService, AuthenticationError
from netlazy.domain.models import User, UserAlreadyExistsError
from netlazy.domain.repository import (
    SignatureVerificationError,
    HashChainDesyncError
)


@pytest.fixture
def auth_deps():
    return {
        "user_repo": AsyncMock(),
        "chain_repo": AsyncMock(),
        "nonce_repo": AsyncMock(),
        "crypto_port": MagicMock(),
        "transaction_manager": AsyncMock()
    }


@pytest.fixture
def auth_service(auth_deps):
    return AuthService(**auth_deps)


@pytest.mark.asyncio
async def test_register_user_success(auth_service, auth_deps):
    auth_deps["crypto_port"].derive_user_id.return_value = "derived_id_123"

    user, anchor = await auth_service.register_user(
        ed25519_pem="pem_pub",
        mldsa_hex="mldsa_pub",
        ip="127.0.0.1",
        fingerprint="fp_abc"
    )

    assert user.user_id == "derived_id_123"
    assert "127.0.0.1" in user.known_ips
    assert "fp_abc" in user.known_fingerprints
    auth_deps["user_repo"].create.assert_called_once()
    auth_deps["chain_repo"].push_anchor.assert_called_once()
    assert anchor is not None


@pytest.mark.asyncio
async def test_authenticate_request_success(auth_service, auth_deps):
    mock_user = User(
        user_id="id1",
        ed25519_public_pem="ed_pub",
        mldsa_public_hex="pq_hex",
        created_at=datetime.now(timezone.utc)
    )
    auth_deps["user_repo"].get_by_id.return_value = mock_user
    auth_deps["nonce_repo"].insert_if_not_exists.return_value = True
    auth_deps["chain_repo"].get_recent_anchors.return_value = ["anchor_prev"]

    user, next_anchor = await auth_service.authenticate_request(
        user_id="id1",
        method="POST",
        path="/api/feed/search",
        timestamp=int(time.time()),
        nonce="nonce_unique",
        body_hash="hash_123",
        prev_anchor="anchor_prev",
        canonical_payload=b"payload_bytes",
        ed25519_signature=b"sig_ed",
        mldsa_signature=b"sig_pq"
    )

    auth_deps["crypto_port"].verify_hybrid_signature.assert_called_once()
    auth_deps["chain_repo"].push_anchor.assert_called_once()
    assert user == mock_user
    assert next_anchor is not None


@pytest.mark.asyncio
async def test_authenticate_request_invalid_timestamp(auth_service):
    with pytest.raises(AuthenticationError, match="Timestamp out of tolerance window"):
        await auth_service.authenticate_request(
            user_id="id1",
            method="POST",
            path="/",
            timestamp=0,  # Expired timestamp
            nonce="nonce_val",
            body_hash="hash",
            prev_anchor="prev",
            canonical_payload=b"",
            ed25519_signature=b"",
            mldsa_signature=b""
        )


@pytest.mark.asyncio
async def test_authenticate_request_used_nonce(auth_service, auth_deps):
    mock_user = User("id1", "ed", "pq", datetime.now(timezone.utc))
    auth_deps["user_repo"].get_by_id.return_value = mock_user
    auth_deps["nonce_repo"].insert_if_not_exists.return_value = False

    with pytest.raises(AuthenticationError, match="Nonce already used"):
        await auth_service.authenticate_request(
            user_id="id1",
            method="POST",
            path="/",
            timestamp=int(time.time()),
            nonce="replayed_nonce",
            body_hash="hash",
            prev_anchor="prev",
            canonical_payload=b"",
            ed25519_signature=b"",
            mldsa_signature=b""
        )


@pytest.mark.asyncio
async def test_authenticate_request_chain_desync(auth_service, auth_deps):
    mock_user = User("id1", "ed", "pq", datetime.now(timezone.utc))
    auth_deps["user_repo"].get_by_id.return_value = mock_user
    auth_deps["nonce_repo"].insert_if_not_exists.return_value = True
    auth_deps["chain_repo"].get_recent_anchors.return_value = ["anchor_1", "anchor_2"]

    with pytest.raises(HashChainDesyncError):
        await auth_service.authenticate_request(
            user_id="id1",
            method="POST",
            path="/",
            timestamp=int(time.time()),
            nonce="nonce_ok",
            body_hash="hash",
            prev_anchor="anchor_unknown",
            canonical_payload=b"",
            ed25519_signature=b"",
            mldsa_signature=b""
        )


@pytest.mark.asyncio
async def test_rotate_key_transaction(auth_service, auth_deps):
    profile_repo = AsyncMock()
    handshake_repo = AsyncMock()

    auth_deps["crypto_port"].derive_user_id.return_value = "new_user_id"
    auth_deps["user_repo"].get_by_id.return_value = None  # No conflict

    async def mock_execute(cb):
        return await cb(session=None)

    auth_deps["transaction_manager"].execute_in_transaction.side_effect = mock_execute

    new_id, anchor = await auth_service.rotate_key(
        old_user_id="old_user_id",
        new_ed25519_pem="new_ed",
        new_mldsa_hex="new_pq",
        profile_repo=profile_repo,
        handshake_repo=handshake_repo
    )

    assert new_id == "new_user_id"
    assert anchor is not None
    auth_deps["user_repo"].create.assert_called_once()
    auth_deps["user_repo"].delete.assert_called_once_with("old_user_id", session=None)