"""Тесты domain-сервиса на fake-репозитории — тот же принцип, что и в
core/internal/app/connect_usecase_test.go (Go) и
edge/test/challenge_response_service.test.ts (TS): бизнес-логика
тестируется без единого обращения к реальной инфраструктуре."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

import pytest

from another_admin.domain.device_provisioning_service import (
    ClientNotFoundError,
    DeviceProvisioningService,
)
from another_admin.domain.models import ClientRecord


class FakeUserRepository:
    """Реализует UserRepositoryPort (Protocol) чисто структурно — не
    наследуется ни от чего явно."""

    def __init__(self) -> None:
        self.clients: dict[str, ClientRecord] = {}
        self.created_calls: list[dict] = []
        self.banned_calls: list[tuple[str, bool]] = []

    def create_client_stub(self, comment, quota_limit_bytes, enrollment_token_hash, expires_at) -> str:
        client_id = f"fake-{len(self.clients) + 1}"
        self.created_calls.append(
            {
                "comment": comment,
                "quota_limit_bytes": quota_limit_bytes,
                "enrollment_token_hash": enrollment_token_hash,
                "expires_at": expires_at,
            }
        )
        self.clients[client_id] = ClientRecord(
            client_id=client_id,
            comment=comment,
            public_key_hex=None,
            vless_user_id_hex=None,
            is_banned=False,
            quota_limit_bytes=quota_limit_bytes,
            bytes_used=0,
            enrollment_token_hash=enrollment_token_hash,
            enrollment_expires_at=expires_at,
            user_id=f"user-{client_id}",
        )
        return client_id

    def add_client_stub(self, user_id, comment, quota_limit_bytes, enrollment_token_hash, expires_at) -> str:
        client_id = f"fake-{len(self.clients) + 1}"
        self.clients[client_id] = ClientRecord(
            client_id=client_id,
            comment=comment,
            public_key_hex=None,
            vless_user_id_hex=None,
            is_banned=False,
            quota_limit_bytes=quota_limit_bytes,
            bytes_used=0,
            enrollment_token_hash=enrollment_token_hash,
            enrollment_expires_at=expires_at,
            user_id=user_id,
        )
        return client_id

    def find_client(self, client_id: str) -> ClientRecord | None:
        return self.clients.get(client_id)

    def list_clients(self) -> list[ClientRecord]:
        return list(self.clients.values())

    def set_banned(self, client_id: str, banned: bool) -> None:
        self.banned_calls.append((client_id, banned))
        c = self.clients[client_id]
        self.clients[client_id] = ClientRecord(**{**c.__dict__, "is_banned": banned})

    def delete_client(self, client_id: str) -> bool:
        return self.clients.pop(client_id, None) is not None


@pytest.fixture
def repo() -> FakeUserRepository:
    return FakeUserRepository()


@pytest.fixture
def service(repo: FakeUserRepository) -> DeviceProvisioningService:
    return DeviceProvisioningService(repo=repo, control_plane_url="https://cf-worker.another.example")


def test_create_invite_stores_only_token_hash_not_plaintext(service, repo):
    result = service.create_invite("Друг из Питера", quota_limit_bytes=1000)

    assert repo.created_calls[0]["comment"] == "Друг из Питера"
    expected_hash = hashlib.sha256(result.enrollment_token.encode()).hexdigest()
    assert repo.created_calls[0]["enrollment_token_hash"] == expected_hash
    # Plaintext-токен НЕ должен совпадать с тем, что "хранится" в репозитории
    assert repo.created_calls[0]["enrollment_token_hash"] != result.enrollment_token


def test_create_invite_sets_expiry_in_the_future(service, repo):
    before = datetime.now(timezone.utc)
    service.create_invite("test", quota_limit_bytes=0)
    expires_at = repo.created_calls[0]["expires_at"]

    assert expires_at > before
    assert expires_at <= before + timedelta(hours=25)  # с запасом на выполнение теста


def test_create_invite_qr_payload_contains_token_and_control_plane_url(service):
    result = service.create_invite("test", quota_limit_bytes=0)
    assert result.enrollment_token in result.qr_payload
    assert "cf-worker.another.example" in result.qr_payload
    assert result.qr_payload.startswith("another://enroll?")


def test_revoke_device_marks_banned(service, repo):
    result = service.create_invite("test", quota_limit_bytes=0)
    service.revoke_device(result.client_id)

    assert repo.banned_calls == [(result.client_id, True)]
    assert repo.clients[result.client_id].is_banned is True


def test_revoke_unknown_device_raises(service):
    with pytest.raises(ClientNotFoundError):
        service.revoke_device("does-not-exist")


def test_unban_device(service, repo):
    result = service.create_invite("test", quota_limit_bytes=0)
    service.revoke_device(result.client_id)
    service.unban_device(result.client_id)

    assert repo.banned_calls == [(result.client_id, True), (result.client_id, False)]
    assert repo.clients[result.client_id].is_banned is False


def test_delete_device_removes_record(service, repo):
    result = service.create_invite("test", quota_limit_bytes=0)
    service.delete_device(result.client_id)
    assert result.client_id not in repo.clients
    assert service.list_devices() == []


def test_delete_unknown_device_raises(service):
    with pytest.raises(ClientNotFoundError):
        service.delete_device("does-not-exist")


def test_list_devices_returns_all(service, repo):
    service.create_invite("a", quota_limit_bytes=0)
    service.create_invite("b", quota_limit_bytes=0)

    devices = service.list_devices()
    assert {d.comment for d in devices} == {"a", "b"}


def test_reissue_bans_old_and_creates_new_invite(service, repo):
    first = service.create_invite("phone", quota_limit_bytes=100)
    second = service.reissue_device(first.client_id)

    assert second.client_id != first.client_id
    assert repo.clients[first.client_id].is_banned is True
    assert repo.clients[second.client_id].user_id == repo.clients[first.client_id].user_id
    assert repo.clients[second.client_id].is_banned is False
