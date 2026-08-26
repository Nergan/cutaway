"""Passphrase-обёртка админского ключа (PBKDF2-SHA256 + AES-GCM).

Scrypt в WebCrypto нет — PBKDF2 есть и в браузере, и в cryptography.
Файл не кладётся в localStorage; браузер держит расшифровку только в RAM.
"""

from __future__ import annotations

import json
import os
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

from another_admin.adapters.hybrid_crypto import generate_admin_keypair, keypair_from_seeds
from another_admin.domain.models import AdminKeypair

KDF_ITERATIONS = 200_000
WRAPPED_LEN = 64  # ed25519 seed (32) + ml-dsa seed (32)


def _derive_key(passphrase: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=KDF_ITERATIONS)
    return kdf.derive(passphrase.encode("utf-8"))


def wrap_keypair(keypair: AdminKeypair, passphrase: str) -> dict[str, Any]:
    salt = os.urandom(16)
    nonce = os.urandom(12)
    key = _derive_key(passphrase, salt)
    plaintext = keypair.ed25519_seed + keypair.mldsa65_seed
    wrapped = AESGCM(key).encrypt(nonce, plaintext, None)
    return {
        "v": 1,
        "kdf": "pbkdf2-sha256",
        "iterations": KDF_ITERATIONS,
        "admin_id": keypair.admin_id,
        "ed25519_public_hex": keypair.ed25519_public_hex,
        "mldsa65_public_hex": keypair.mldsa65_public_hex,
        "salt_hex": salt.hex(),
        "nonce_hex": nonce.hex(),
        "wrapped_hex": wrapped.hex(),
    }


def unwrap_keypair(doc: dict[str, Any], passphrase: str) -> AdminKeypair:
    if int(doc.get("v", 0)) != 1:
        raise ValueError("unsupported keyfile version")
    if doc.get("kdf") != "pbkdf2-sha256":
        raise ValueError("unsupported kdf")
    salt = bytes.fromhex(doc["salt_hex"])
    nonce = bytes.fromhex(doc["nonce_hex"])
    wrapped = bytes.fromhex(doc["wrapped_hex"])
    key = _derive_key(passphrase, salt)
    plaintext = AESGCM(key).decrypt(nonce, wrapped, None)
    if len(plaintext) != WRAPPED_LEN:
        raise ValueError("unwrapped key material has unexpected length")
    return keypair_from_seeds(doc["admin_id"], plaintext[:32], plaintext[32:])


def create_wrapped_keyfile(admin_id: str, passphrase: str) -> tuple[AdminKeypair, dict[str, Any]]:
    keypair = generate_admin_keypair(admin_id)
    return keypair, wrap_keypair(keypair, passphrase)


def dumps_keyfile(doc: dict[str, Any]) -> str:
    return json.dumps(doc, indent=2, sort_keys=True) + "\n"
