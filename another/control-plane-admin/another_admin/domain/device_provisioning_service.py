"""DeviceProvisioningService — прямой перенос псевдокода §12 архитектурной
спецификации (``create_invite``/``revoke_device``) в рабочий код. Не знает
ничего про Mongo/Telegram/CLI/Typer/aiogram — только через
UserRepositoryPort.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from another_admin.domain.models import ClientRecord, InviteResult
from another_admin.ports.user_repository_port import UserRepositoryPort

DEFAULT_INVITE_TTL_HOURS = 24
# TTL согласован с TTL-индексом на enrollment_expires_at в MongoDB (§10
# спецификации) — если поменять здесь, нужно поменять и в схеме/индексе.


class ClientNotFoundError(LookupError):
    def __init__(self, client_id: str) -> None:
        super().__init__(f"client_id {client_id!r} не найден")
        self.client_id = client_id


@dataclass(frozen=True)
class DeviceProvisioningService:
    repo: UserRepositoryPort
    control_plane_url: str
    invite_ttl_hours: int = DEFAULT_INVITE_TTL_HOURS

    def create_invite(self, comment: str, quota_limit_bytes: int) -> InviteResult:
        """Создаёт одноразовое приглашение. В БД сохраняется только
        SHA-256(token) (см. §7.1: "хранится в БД как hash") — сам токен
        существует только в возвращаемом значении и в QR-коде/сообщении,
        отправленном пользователю; повторно получить его нельзя."""
        token = secrets.token_hex(32)
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        expires_at = datetime.now(timezone.utc) + timedelta(hours=self.invite_ttl_hours)

        client_id = self.repo.create_client_stub(
            comment=comment,
            quota_limit_bytes=quota_limit_bytes,
            enrollment_token_hash=token_hash,
            expires_at=expires_at,
        )

        qr_payload = (
            f"another://enroll?token={quote(token)}&cp={quote(self.control_plane_url)}"
        )
        return InviteResult(
            client_id=client_id,
            enrollment_token=token,
            qr_payload=qr_payload,
            enrollment_expires_at=expires_at,
        )

    def revoke_device(self, client_id: str) -> None:
        """Прямой перенос ``revoke_device`` из §7.3 спецификации. На
        стороне edge/ эффект — форс-инвалидация KvBanCache при следующем
        /auth (без ожидания TTL кэша) — но сама инвалидация кэша сюда не
        дотягивается напрямую (control-plane-admin не имеет доступа к
        Workers KV из вне Cloudflare); мгновенный эффект достигается только
        если control-plane-admin дополнительно дёргает служебный endpoint
        edge/ для форс-инвалидации — TODO v2, см. control-plane-admin/README.md."""
        if self.repo.find_client(client_id) is None:
            raise ClientNotFoundError(client_id)
        self.repo.set_banned(client_id, True)

    def unban_device(self, client_id: str) -> None:
        if self.repo.find_client(client_id) is None:
            raise ClientNotFoundError(client_id)
        self.repo.set_banned(client_id, False)

    def delete_device(self, client_id: str) -> None:
        if self.repo.find_client(client_id) is None:
            raise ClientNotFoundError(client_id)
        self.repo.delete_client(client_id)

    def list_devices(self) -> list[ClientRecord]:
        return self.repo.list_clients()

    def reissue_device(self, client_id: str) -> InviteResult:
        """Бан старого client_id и новое одноразовое приглашение на том же user_id."""
        existing = self.repo.find_client(client_id)
        if existing is None:
            raise ClientNotFoundError(client_id)
        self.repo.set_banned(client_id, True)

        token = secrets.token_hex(32)
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        expires_at = datetime.now(timezone.utc) + timedelta(hours=self.invite_ttl_hours)
        comment = existing.comment or client_id
        quota = existing.quota_limit_bytes

        if existing.user_id:
            new_id = self.repo.add_client_stub(
                user_id=existing.user_id,
                comment=comment,
                quota_limit_bytes=quota,
                enrollment_token_hash=token_hash,
                expires_at=expires_at,
            )
        else:
            new_id = self.repo.create_client_stub(
                comment=comment,
                quota_limit_bytes=quota,
                enrollment_token_hash=token_hash,
                expires_at=expires_at,
            )

        qr_payload = (
            f"another://enroll?token={quote(token)}&cp={quote(self.control_plane_url)}"
        )
        return InviteResult(
            client_id=new_id,
            enrollment_token=token,
            qr_payload=qr_payload,
            enrollment_expires_at=expires_at,
        )
