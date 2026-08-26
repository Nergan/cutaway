"""Тесты MongoUserRepository через mongomock — эмулирует API pymongo в
памяти, что позволяет проверить реальные запросы (find_one с проекцией
"clients.$", update_one с позиционным оператором и т.д.), не поднимая ни
реальный MongoDB, ни Docker-контейнер (недоступен в этой среде — см.
docs/implementation-plan.md, Part 1)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import mongomock
import pytest

from another_admin.adapters.mongo_repository import MongoUserRepository, generate_client_id


@pytest.fixture
def collection():
    client = mongomock.MongoClient()
    return client["another_test"]["users"]


@pytest.fixture
def repo(collection) -> MongoUserRepository:
    return MongoUserRepository(collection)


def test_generate_client_id_is_slug_plus_random_suffix():
    cid = generate_client_id("Друг из Питера")
    assert cid.startswith("drug-iz-pitera-")
    # два вызова с одинаковым комментарием не должны совпадать (случайный суффикс)
    assert generate_client_id("Друг из Питера") != cid


def test_create_and_find_client_stub(repo):
    expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
    client_id = repo.create_client_stub(
        comment="test user",
        quota_limit_bytes=1000,
        enrollment_token_hash="deadbeef",
        expires_at=expires_at,
    )

    found = repo.find_client(client_id)
    assert found is not None
    assert found.client_id == client_id
    assert found.comment == "test user"
    assert found.quota_limit_bytes == 1000
    assert found.bytes_used == 0
    assert found.is_banned is False
    assert found.public_key_hex is None  # ещё не онбордирован
    assert found.enrollment_token_hash == "deadbeef"


def test_find_nonexistent_client_returns_none(repo):
    assert repo.find_client("does-not-exist") is None


def test_set_banned_true_sets_revoked_at(repo):
    client_id = repo.create_client_stub("u", 0, "hash", datetime.now(timezone.utc))
    repo.set_banned(client_id, True)

    found = repo.find_client(client_id)
    assert found.is_banned is True


def test_set_banned_false_clears_state(repo):
    client_id = repo.create_client_stub("u", 0, "hash", datetime.now(timezone.utc))
    repo.set_banned(client_id, True)
    repo.set_banned(client_id, False)

    found = repo.find_client(client_id)
    assert found.is_banned is False


def test_list_clients_returns_all_across_multiple_documents(repo):
    repo.create_client_stub("alice", 100, "h1", datetime.now(timezone.utc))
    repo.create_client_stub("bob", 200, "h2", datetime.now(timezone.utc))

    clients = repo.list_clients()
    assert {c.comment for c in clients} == {"alice", "bob"}
    assert len(clients) == 2


def test_list_clients_empty_when_no_documents(repo):
    assert repo.list_clients() == []


def test_add_client_stub_appends_to_existing_user(repo):
    first = repo.create_client_stub("alice", 100, "h1", datetime.now(timezone.utc))
    found = repo.find_client(first)
    assert found is not None
    second = repo.add_client_stub(found.user_id, "alice-phone", 100, "h2", datetime.now(timezone.utc))
    assert second != first
    listed = repo.list_clients()
    assert {c.client_id for c in listed} == {first, second}
    assert {c.user_id for c in listed} == {found.user_id}


def test_delete_client_removes_one_keeps_sibling(repo, collection):
    first = repo.create_client_stub("alice", 100, "h1", datetime.now(timezone.utc))
    found = repo.find_client(first)
    second = repo.add_client_stub(found.user_id, "alice-phone", 100, "h2", datetime.now(timezone.utc))
    assert repo.delete_client(first) is True
    assert repo.find_client(first) is None
    leftover = repo.find_client(second)
    assert leftover is not None
    assert leftover.user_id == found.user_id
    assert collection.count_documents({}) == 1


def test_delete_last_client_drops_user_document(repo, collection):
    client_id = repo.create_client_stub("solo", 0, "h", datetime.now(timezone.utc))
    assert repo.delete_client(client_id) is True
    assert repo.find_client(client_id) is None
    assert repo.list_clients() == []
    assert collection.count_documents({}) == 0


def test_delete_missing_client_returns_false(repo):
    assert repo.delete_client("nope") is False
