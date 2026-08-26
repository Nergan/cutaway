"""Domain-модели. Ничего не знают про MongoDB/Telegram — только форма
данных и её инварианты. Зеркалят исправленную схему §10 архитектурной
спецификации (без HWID/MAC — идентичность только через public_key,
проставляемый устройством при онбординге, см. edge/src/handlers/enroll.ts).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ClientRecord:
    client_id: str
    comment: str
    public_key_hex: str | None
    vless_user_id_hex: str | None
    is_banned: bool
    quota_limit_bytes: int
    bytes_used: int
    enrollment_token_hash: str | None
    enrollment_expires_at: datetime | None
    user_id: str = ""
    public_key_mldsa65_hex: str | None = None
    last_activity: datetime | None = None

    @property
    def is_enrolled(self) -> bool:
        """Устройство считается онбордированным, когда у него уже есть
        публичный ключ (т.е. оно прошло handlers/enroll.ts на edge/)."""
        return self.public_key_hex is not None


@dataclass(frozen=True)
class InviteResult:
    """Результат создания приглашения. enrollment_token — секрет,
    возвращаемый ТОЛЬКО один раз, при создании (в БД хранится лишь его
    SHA-256, см. adapters/mongo_repository.py) — если он потерян, приглашение
    нужно перевыпускать заново, восстановить его нельзя."""

    client_id: str
    enrollment_token: str
    qr_payload: str
    enrollment_expires_at: datetime | None = None


@dataclass(frozen=True)
class QuotaReportRow:
    client_id: str
    comment: str
    bytes_used: int
    quota_limit_bytes: int
    is_banned: bool

    @property
    def percent_used(self) -> float:
        if self.quota_limit_bytes <= 0:
            return 0.0  # безлимит, см. evaluateAccess в edge/src/domain/ban_policy.ts
        return 100.0 * self.bytes_used / self.quota_limit_bytes


@dataclass(frozen=True)
class AdminRecord:
    """Состояние одной админ-идентичности (docs/auth-spec.md §3)."""

    admin_id: str
    ed25519_public_hex: str
    mldsa65_public_hex: str
    last_seq: int
    chain_head_hex: str
    last_body_hash_hex: str
    last_response: dict | None
    revoked: bool


@dataclass(frozen=True)
class PingTarget:
    name: str
    url: str
    interval_s: int = 300
    expect_status: int = 200


@dataclass(frozen=True)
class AdminKeypair:
    """Приватные ключи только в RAM / в passphrase-обёртке, не в Mongo."""

    admin_id: str
    ed25519_seed: bytes
    mldsa65_seed: bytes
    ed25519_public_hex: str
    mldsa65_public_hex: str
