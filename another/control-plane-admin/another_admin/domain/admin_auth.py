"""Another Auth v1 для админки: seq + chain_head, без блокчейна и без ZKP.

См. docs/auth-spec.md §3. Состояние на одну admin_id — O(1). Повтор того же
seq с тем же body_hash возвращает закэшированный ответ (обрыв связи).
Другой body на тот же seq — fork, отклоняется.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Literal

from another_admin.domain.models import AdminRecord

PROTOCOL = b"another-admin-v1"
BOOTSTRAP_PROTOCOL = b"another-admin-v1-bootstrap"
ZERO_HEAD = b"\x00" * 32


class AdminAuthError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def canonical_body_bytes(body: dict[str, Any]) -> bytes:
    return json.dumps(body, separators=(",", ":"), sort_keys=True, ensure_ascii=False).encode("utf-8")


def body_hash(body: dict[str, Any]) -> bytes:
    return hashlib.sha3_256(canonical_body_bytes(body)).digest()


def command_message(seq: int, chain_head: bytes, hashed: bytes) -> bytes:
    if len(chain_head) != 32 or len(hashed) != 32:
        raise AdminAuthError("bad_encoding", "chain_head and body_hash must be 32 bytes")
    return PROTOCOL + b"|" + seq.to_bytes(8, "big") + chain_head + hashed


def bootstrap_message(challenge: bytes) -> bytes:
    if len(challenge) != 16:
        raise AdminAuthError("bad_encoding", "challenge must be 16 bytes")
    return BOOTSTRAP_PROTOCOL + b"|" + challenge


def next_chain_head(chain_head: bytes, seq: int, hashed: bytes, sig_ed: bytes, sig_pq: bytes) -> bytes:
    h = hashlib.sha3_256()
    h.update(chain_head)
    h.update(seq.to_bytes(8, "big"))
    h.update(hashed)
    h.update(sig_ed)
    h.update(sig_pq)
    return h.digest()


def genesis_admin(admin_id: str, ed25519_public_hex: str, mldsa65_public_hex: str) -> AdminRecord:
    return AdminRecord(
        admin_id=admin_id,
        ed25519_public_hex=ed25519_public_hex,
        mldsa65_public_hex=mldsa65_public_hex,
        last_seq=0,
        chain_head_hex=ZERO_HEAD.hex(),
        last_body_hash_hex="",
        last_response=None,
        revoked=False,
    )


Decision = Literal["execute", "replay"]


@dataclass(frozen=True)
class CommandDecision:
    kind: Decision
    new_record: AdminRecord | None  # None на replay — запись не меняется
    cached_response: dict[str, Any] | None


def decide_command(
    record: AdminRecord,
    seq: int,
    chain_head_prev: bytes,
    hashed: bytes,
    sig_ed: bytes,
    sig_pq: bytes,
) -> CommandDecision:
    """Крипто-проверку подписи делает вызывающий *до* этого. Здесь — только
    seq/chain и идемпотентный повтор."""
    if record.revoked:
        raise AdminAuthError("revoked", "admin identity is revoked")

    current_head = bytes.fromhex(record.chain_head_hex)
    last_hash = bytes.fromhex(record.last_body_hash_hex) if record.last_body_hash_hex else b""

    if seq == record.last_seq:
        if last_hash == hashed:
            return CommandDecision(kind="replay", new_record=None, cached_response=record.last_response)
        raise AdminAuthError("fork", "same seq with a different body hash")

    if seq != record.last_seq + 1:
        raise AdminAuthError("bad_seq", f"expected seq {record.last_seq + 1}, got {seq}")

    if chain_head_prev != current_head:
        raise AdminAuthError("bad_chain", "chain_head_prev does not match stored chain_head")

    return CommandDecision(kind="execute", new_record=None, cached_response=None)


def commit_command(
    record: AdminRecord,
    seq: int,
    hashed: bytes,
    sig_ed: bytes,
    sig_pq: bytes,
    response: dict[str, Any],
) -> AdminRecord:
    new_head = next_chain_head(bytes.fromhex(record.chain_head_hex), seq, hashed, sig_ed, sig_pq)
    return AdminRecord(
        admin_id=record.admin_id,
        ed25519_public_hex=record.ed25519_public_hex,
        mldsa65_public_hex=record.mldsa65_public_hex,
        last_seq=seq,
        chain_head_hex=new_head.hex(),
        last_body_hash_hex=hashed.hex(),
        last_response=response,
        revoked=record.revoked,
    )
