"""HTTP-тесты origin API на InMemoryControlPlaneStore."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from another_admin.adapters.hybrid_crypto import generate_admin_keypair, hybrid_sign
from another_admin.adapters.memory_store import InMemoryControlPlaneStore
from another_admin.api.app import create_app
from another_admin.api.config import ApiConfig
from another_admin.domain.admin_auth import (
    ZERO_HEAD,
    body_hash,
    bootstrap_message,
    command_message,
    genesis_admin,
)


def _cfg() -> ApiConfig:
    return ApiConfig(
        mongo_uri="memory",
        mongo_db_name="another",
        service_secret="test-secret",
        control_plane_url="https://cf-worker.another.example",
        edge_internal_url="",
        events_capped_bytes=1024,
    )


@pytest.fixture
def api():
    store = InMemoryControlPlaneStore()
    app = create_app(store=store, cfg=_cfg())
    with TestClient(app) as client:
        yield client, store


def test_health(api):
    client, _ = api
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_internal_rejects_bad_secret(api):
    client, _ = api
    res = client.post("/internal/v1/clients/find", json={"client_id": "x"})
    assert res.status_code == 401


def test_internal_find_bind_enroll_usage(api):
    client, store = api
    client_id = asyncio.run(
        store.create_client_stub("t", 100, "deadbeef", datetime.now(timezone.utc))
    )
    headers = {"X-Another-Proxy-Secret": "test-secret"}

    missing = client.post("/internal/v1/clients/find", json={"client_id": "nope"}, headers=headers)
    assert missing.status_code == 404

    found = client.post("/internal/v1/clients/find", json={"client_id": client_id}, headers=headers)
    assert found.status_code == 200
    assert found.json()["client_id"] == client_id

    enroll = client.post(
        "/internal/v1/enrollments/find",
        json={"token_hash": "deadbeef"},
        headers=headers,
    )
    assert enroll.status_code == 200
    assert enroll.json()["client_id"] == client_id

    bind = client.post(
        "/internal/v1/clients/bind",
        json={
            "client_id": client_id,
            "public_key_hex": "aa" * 32,
            "vless_user_id_hex": "bb" * 16,
        },
        headers=headers,
    )
    assert bind.status_code == 200

    consume = client.post(
        "/internal/v1/enrollments/consume",
        json={"token_hash": "deadbeef"},
        headers=headers,
    )
    assert consume.status_code == 200

    usage = client.post(
        "/internal/v1/clients/usage",
        json={"client_id": client_id, "bytes_delta": 50},
        headers=headers,
    )
    assert usage.status_code == 200

    again = client.post("/internal/v1/clients/find", json={"client_id": client_id}, headers=headers)
    assert again.json()["bytes_used"] == 50
    assert again.json()["public_key_hex"] == "aa" * 32


def test_admin_invite_list_revoke_via_signed_commands(api):
    client, store = api
    kp = generate_admin_keypair("root")
    asyncio.run(store.insert_admin(genesis_admin("root", kp.ed25519_public_hex, kp.mldsa65_public_hex)))

    ch = client.get("/admin/v1/challenge").json()
    challenge = bytes.fromhex(ch["challenge_hex"])
    sig_ed, sig_pq = hybrid_sign(kp, bootstrap_message(challenge))
    boot = client.post(
        "/admin/v1/bootstrap",
        json={
            "admin_id": "root",
            "challenge_hex": ch["challenge_hex"],
            "sig_ed_hex": sig_ed.hex(),
            "sig_pq_hex": sig_pq.hex(),
        },
    )
    assert boot.status_code == 200
    chain = boot.json()["chain_head_hex"]
    assert chain == ZERO_HEAD.hex()

    def signed_command(seq: int, chain_hex: str, body: dict):
        hashed = body_hash(body)
        msg = command_message(seq, bytes.fromhex(chain_hex), hashed)
        s_ed, s_pq = hybrid_sign(kp, msg)
        return client.post(
            "/admin/v1/command",
            json={
                "admin_id": "root",
                "seq": seq,
                "chain_head_prev_hex": chain_hex,
                "body": body,
                "sig_ed_hex": s_ed.hex(),
                "sig_pq_hex": s_pq.hex(),
            },
        )

    invite_body = {"op": "invite", "comment": "Друг из Питера", "quota_limit_bytes": 1000}
    chain_before_invite = chain
    invite = signed_command(1, chain, invite_body)
    assert invite.status_code == 200, invite.text
    client_id = invite.json()["result"]["client_id"]
    assert invite.json()["result"]["invite_ttl_hours"] == 24
    assert invite.json()["result"]["enrollment_expires_at"]
    chain_after_invite = invite.json()["chain_head_hex"]

    replay = signed_command(1, chain_before_invite, invite_body)
    assert replay.status_code == 200
    assert replay.json()["replayed"] is True
    assert replay.json()["result"]["client_id"] == client_id

    listed = signed_command(2, chain_after_invite, {"op": "list_devices"})
    assert listed.status_code == 200
    device = listed.json()["result"]["devices"][0]
    assert device["client_id"] == client_id
    assert device["invite_pending"] is True
    assert device["enrollment_expires_at"]
    chain = listed.json()["chain_head_hex"]

    revoked = signed_command(3, chain, {"op": "revoke", "client_id": client_id})
    assert revoked.status_code == 200
    assert revoked.json()["result"]["banned"] is True
    chain = revoked.json()["chain_head_hex"]

    unbanned = signed_command(4, chain, {"op": "unban", "client_id": client_id})
    assert unbanned.status_code == 200
    assert unbanned.json()["result"]["banned"] is False
    chain = unbanned.json()["chain_head_hex"]

    deleted = signed_command(5, chain, {"op": "delete", "client_id": client_id})
    assert deleted.status_code == 200
    assert deleted.json()["result"]["deleted"] is True
    chain = deleted.json()["chain_head_hex"]

    listed_after = signed_command(6, chain, {"op": "list_devices"})
    assert listed_after.status_code == 200
    assert listed_after.json()["result"]["devices"] == []

    missing = signed_command(7, listed_after.json()["chain_head_hex"], {"op": "delete", "client_id": client_id})
    assert missing.status_code == 404


def test_ping_targets_roundtrip(api):
    client, store = api
    kp = generate_admin_keypair("root")
    asyncio.run(store.insert_admin(genesis_admin("root", kp.ed25519_public_hex, kp.mldsa65_public_hex)))

    ch = client.get("/admin/v1/challenge").json()
    sig_ed, sig_pq = hybrid_sign(kp, bootstrap_message(bytes.fromhex(ch["challenge_hex"])))
    client.post(
        "/admin/v1/bootstrap",
        json={
            "admin_id": "root",
            "challenge_hex": ch["challenge_hex"],
            "sig_ed_hex": sig_ed.hex(),
            "sig_pq_hex": sig_pq.hex(),
        },
    )

    body = {
        "op": "ping_targets_set",
        "targets": [{"name": "api", "url": "http://localhost:8080/health", "interval_s": 60, "expect_status": 200}],
    }
    hashed = body_hash(body)
    msg = command_message(1, ZERO_HEAD, hashed)
    s_ed, s_pq = hybrid_sign(kp, msg)
    res = client.post(
        "/admin/v1/command",
        json={
            "admin_id": "root",
            "seq": 1,
            "chain_head_prev_hex": ZERO_HEAD.hex(),
            "body": body,
            "sig_ed_hex": s_ed.hex(),
            "sig_pq_hex": s_pq.hex(),
        },
    )
    assert res.status_code == 200, res.text

    headers = {"X-Another-Proxy-Secret": "test-secret"}
    ping = client.get("/internal/v1/ping-targets", headers=headers)
    assert ping.status_code == 200
    assert ping.json()["targets"][0]["name"] == "api"


def _boot_admin(client, store):
    kp = generate_admin_keypair("root")
    asyncio.run(store.insert_admin(genesis_admin("root", kp.ed25519_public_hex, kp.mldsa65_public_hex)))
    ch = client.get("/admin/v1/challenge").json()
    sig_ed, sig_pq = hybrid_sign(kp, bootstrap_message(bytes.fromhex(ch["challenge_hex"])))
    boot = client.post(
        "/admin/v1/bootstrap",
        json={
            "admin_id": "root",
            "challenge_hex": ch["challenge_hex"],
            "sig_ed_hex": sig_ed.hex(),
            "sig_pq_hex": sig_pq.hex(),
        },
    )
    assert boot.status_code == 200
    return kp, boot.json()["chain_head_hex"]


def _signed(client, kp, seq, chain_hex, body):
    hashed = body_hash(body)
    msg = command_message(seq, bytes.fromhex(chain_hex), hashed)
    s_ed, s_pq = hybrid_sign(kp, msg)
    return client.post(
        "/admin/v1/command",
        json={
            "admin_id": "root",
            "seq": seq,
            "chain_head_prev_hex": chain_hex,
            "body": body,
            "sig_ed_hex": s_ed.hex(),
            "sig_pq_hex": s_pq.hex(),
        },
    )


def test_internal_sessions_and_admin_list(api):
    client, store = api
    headers = {"X-Another-Proxy-Secret": "test-secret"}
    up = client.post(
        "/internal/v1/sessions/upsert",
        json={"client_id": "dev-1", "ip_hash": "abcd1234abcd1234", "node": "cf-worker", "entrypoint": "/auth"},
        headers=headers,
    )
    assert up.status_code == 200, up.text
    kp, chain = _boot_admin(client, store)
    listed = _signed(client, kp, 1, chain, {"op": "sessions"})
    assert listed.status_code == 200, listed.text
    sessions = listed.json()["result"]["sessions"]
    assert sessions[0]["client_id"] == "dev-1"
    assert "ip" not in sessions[0]
    assert sessions[0]["ip_hash"] == "abcd1234abcd1234"

    closed = client.post(
        "/internal/v1/sessions/close",
        json={"client_id": "dev-1", "ip_hash": "abcd1234abcd1234", "bytes_delta": 10},
        headers=headers,
    )
    assert closed.status_code == 200
    chain = listed.json()["chain_head_hex"]
    after = _signed(client, kp, 2, chain, {"op": "sessions"})
    assert after.json()["result"]["sessions"] == []


def test_evaluate_alerts_concurrent_and_ack(api):
    client, store = api
    headers = {"X-Another-Proxy-Secret": "test-secret"}
    client.post(
        "/internal/v1/sessions/upsert",
        json={"client_id": "shared", "ip_hash": "1111111111111111"},
        headers=headers,
    )
    client.post(
        "/internal/v1/sessions/upsert",
        json={"client_id": "shared", "ip_hash": "2222222222222222"},
        headers=headers,
    )
    for _ in range(3):
        client.post(
            "/internal/v1/events",
            json={"category": "auth_fail", "client_id": "shared", "detail": {"path": "/auth"}},
            headers=headers,
        )
    kp, chain = _boot_admin(client, store)
    th = _signed(
        client,
        kp,
        1,
        chain,
        {"op": "alert_thresholds_set", "thresholds": {"auth_fail_count": 3, "auth_fail_per_client": 3, "concurrent_ip_hashes": 2}},
    )
    assert th.status_code == 200, th.text
    chain = th.json()["chain_head_hex"]
    ev = _signed(client, kp, 2, chain, {"op": "evaluate_alerts"})
    assert ev.status_code == 200, ev.text
    assert ev.json()["result"]["count"] >= 1
    chain = ev.json()["chain_head_hex"]
    events = _signed(client, kp, 3, chain, {"op": "events", "unacked_only": True})
    cats = [e["category"] for e in events.json()["result"]["events"]]
    assert "anomaly" in cats


def test_build_installer_returns_ldflags_and_reissues(api):
    client, store = api
    kp, chain = _boot_admin(client, store)
    invite = _signed(client, kp, 1, chain, {"op": "invite", "comment": "сборщик", "quota_limit_bytes": 100})
    assert invite.status_code == 200, invite.text
    old_id = invite.json()["result"]["client_id"]
    chain = invite.json()["chain_head_hex"]
    built = _signed(
        client,
        kp,
        2,
        chain,
        {"op": "build_installer", "client_id": old_id, "platforms": ["linux/amd64", "android/arm64"]},
    )
    assert built.status_code == 200, built.text
    result = built.json()["result"]
    assert result["revoked_client_id"] == old_id
    assert result["enrollment_token"]
    assert "embeddedToken=" in result["ldflags"]
    assert result["client_id"] != old_id
    platforms = {a["platform"] for a in result["artifacts"]}
    assert platforms == {"linux/amd64", "android/arm64"}
    assert all(a["compiled"] is False for a in result["artifacts"])
