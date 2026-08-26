"""Тесты seq/chain админ-аутентификации — без Mongo и без HTTP."""

from __future__ import annotations

import pytest

from another_admin.adapters.hybrid_crypto import generate_admin_keypair, hybrid_sign, hybrid_verify, HybridVerifyError
from another_admin.adapters.keyfile import create_wrapped_keyfile, unwrap_keypair
from another_admin.domain.admin_auth import (
    AdminAuthError,
    ZERO_HEAD,
    body_hash,
    bootstrap_message,
    command_message,
    commit_command,
    decide_command,
    genesis_admin,
)


def test_hybrid_sign_verify_roundtrip():
    kp = generate_admin_keypair("op")
    msg = b"another-admin-v1|test"
    sig_ed, sig_pq = hybrid_sign(kp, msg)
    hybrid_verify(kp.ed25519_public_hex, kp.mldsa65_public_hex, msg, sig_ed, sig_pq)


def test_hybrid_verify_rejects_tampered_message():
    kp = generate_admin_keypair("op")
    sig_ed, sig_pq = hybrid_sign(kp, b"one")
    with pytest.raises(HybridVerifyError):
        hybrid_verify(kp.ed25519_public_hex, kp.mldsa65_public_hex, b"two", sig_ed, sig_pq)


def test_keyfile_wrap_unwrap():
    kp, doc = create_wrapped_keyfile("op", "correct horse")
    restored = unwrap_keypair(doc, "correct horse")
    assert restored.ed25519_public_hex == kp.ed25519_public_hex
    assert restored.mldsa65_public_hex == kp.mldsa65_public_hex
    assert restored.ed25519_seed == kp.ed25519_seed


def test_keyfile_wrong_passphrase():
    _, doc = create_wrapped_keyfile("op", "right")
    with pytest.raises(Exception):
        unwrap_keypair(doc, "wrong")


def test_decide_execute_then_replay():
    rec = genesis_admin("op", "aa", "bb")
    hashed = body_hash({"op": "list_devices"})
    sig_ed, sig_pq = b"ed", b"pq"
    d = decide_command(rec, 1, ZERO_HEAD, hashed, sig_ed, sig_pq)
    assert d.kind == "execute"
    committed = commit_command(rec, 1, hashed, sig_ed, sig_pq, {"ok": True})
    replay = decide_command(committed, 1, ZERO_HEAD, hashed, sig_ed, sig_pq)
    assert replay.kind == "replay"
    assert replay.cached_response == {"ok": True}


def test_decide_fork_same_seq_different_body():
    rec = genesis_admin("op", "aa", "bb")
    h1 = body_hash({"op": "invite", "comment": "a"})
    committed = commit_command(rec, 1, h1, b"ed", b"pq", {"ok": 1})
    h2 = body_hash({"op": "invite", "comment": "b"})
    with pytest.raises(AdminAuthError) as exc:
        decide_command(committed, 1, bytes.fromhex(committed.chain_head_hex), h2, b"ed", b"pq")
    assert exc.value.code == "fork"


def test_decide_rejects_wrong_seq_and_wrong_head():
    rec = genesis_admin("op", "aa", "bb")
    hashed = body_hash({"op": "list_devices"})
    with pytest.raises(AdminAuthError) as exc:
        decide_command(rec, 2, ZERO_HEAD, hashed, b"e", b"p")
    assert exc.value.code == "bad_seq"
    committed = commit_command(rec, 1, hashed, b"e", b"p", {})
    with pytest.raises(AdminAuthError) as exc2:
        decide_command(committed, 2, ZERO_HEAD, hashed, b"e", b"p")
    assert exc2.value.code == "bad_chain"


def test_command_message_encoding_is_stable():
    hashed = body_hash({"b": 1, "a": 2})
    m1 = command_message(1, ZERO_HEAD, hashed)
    m2 = command_message(1, ZERO_HEAD, hashed)
    assert m1 == m2
    assert m1.startswith(b"another-admin-v1|")
    assert bootstrap_message(b"\x00" * 16).startswith(b"another-admin-v1-bootstrap|")
