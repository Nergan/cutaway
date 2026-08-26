"""Гибрид Ed25519 + ML-DSA-65 (docs/auth-spec.md, ADR 0006).

Оба компонента обязательны: verify успешен только если проходят оба.
Семена (32 байта каждое) — то, что кладётся в passphrase-обёрнутый файл админа.
"""

from __future__ import annotations

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.asymmetric.mldsa import MLDSA65PrivateKey, MLDSA65PublicKey
from cryptography.exceptions import InvalidSignature

from another_admin.domain.models import AdminKeypair


class HybridVerifyError(ValueError):
    pass


def generate_admin_keypair(admin_id: str) -> AdminKeypair:
    ed = Ed25519PrivateKey.generate()
    pq = MLDSA65PrivateKey.generate()
    ed_seed = ed.private_bytes_raw()
    pq_seed = pq.private_bytes_raw()
    return AdminKeypair(
        admin_id=admin_id,
        ed25519_seed=ed_seed,
        mldsa65_seed=pq_seed,
        ed25519_public_hex=ed.public_key().public_bytes_raw().hex(),
        mldsa65_public_hex=pq.public_key().public_bytes_raw().hex(),
    )


def keypair_from_seeds(admin_id: str, ed_seed: bytes, pq_seed: bytes) -> AdminKeypair:
    if len(ed_seed) != 32:
        raise ValueError("ed25519 seed must be 32 bytes")
    if len(pq_seed) != 32:
        raise ValueError("ml-dsa-65 seed must be 32 bytes")
    ed = Ed25519PrivateKey.from_private_bytes(ed_seed)
    pq = MLDSA65PrivateKey.from_seed_bytes(pq_seed)
    return AdminKeypair(
        admin_id=admin_id,
        ed25519_seed=ed_seed,
        mldsa65_seed=pq_seed,
        ed25519_public_hex=ed.public_key().public_bytes_raw().hex(),
        mldsa65_public_hex=pq.public_key().public_bytes_raw().hex(),
    )


def hybrid_sign(keypair: AdminKeypair, message: bytes) -> tuple[bytes, bytes]:
    ed = Ed25519PrivateKey.from_private_bytes(keypair.ed25519_seed)
    pq = MLDSA65PrivateKey.from_seed_bytes(keypair.mldsa65_seed)
    return ed.sign(message), pq.sign(message)


def hybrid_verify(
    ed25519_public_hex: str,
    mldsa65_public_hex: str,
    message: bytes,
    sig_ed: bytes,
    sig_pq: bytes,
) -> None:
    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(ed25519_public_hex)).verify(sig_ed, message)
    except (InvalidSignature, ValueError) as exc:
        raise HybridVerifyError("ed25519 signature invalid") from exc
    try:
        MLDSA65PublicKey.from_public_bytes(bytes.fromhex(mldsa65_public_hex)).verify(sig_pq, message)
    except (InvalidSignature, ValueError) as exc:
        raise HybridVerifyError("ml-dsa-65 signature invalid") from exc
