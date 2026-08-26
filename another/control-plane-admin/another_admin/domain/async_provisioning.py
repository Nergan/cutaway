"""Асинхронный провижининг поверх ControlPlaneStore — тот же смысл, что
DeviceProvisioningService, но для FastAPI."""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from another_admin.domain.device_provisioning_service import ClientNotFoundError
from another_admin.domain.models import ClientRecord, InviteResult
from another_admin.ports.control_plane_store import ControlPlaneStore

DEFAULT_INVITE_TTL_HOURS = 24


@dataclass(frozen=True)
class AsyncDeviceProvisioningService:
    store: ControlPlaneStore
    control_plane_url: str
    invite_ttl_hours: int = DEFAULT_INVITE_TTL_HOURS

    def _token(self) -> tuple[str, str, datetime]:
        token = secrets.token_hex(32)
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        expires_at = datetime.now(timezone.utc) + timedelta(hours=self.invite_ttl_hours)
        return token, token_hash, expires_at

    def _invite_result(self, client_id: str, token: str) -> InviteResult:
        qr_payload = (
            f"another://enroll?token={quote(token)}&cp={quote(self.control_plane_url)}"
        )
        return InviteResult(client_id=client_id, enrollment_token=token, qr_payload=qr_payload)

    async def create_invite(self, comment: str, quota_limit_bytes: int) -> InviteResult:
        token, token_hash, expires_at = self._token()
        client_id = await self.store.create_client_stub(
            comment=comment,
            quota_limit_bytes=quota_limit_bytes,
            enrollment_token_hash=token_hash,
            expires_at=expires_at,
        )
        return self._invite_result(client_id, token)

    async def revoke_device(self, client_id: str) -> None:
        if await self.store.find_client(client_id) is None:
            raise ClientNotFoundError(client_id)
        await self.store.set_banned(client_id, True)

    async def unban_device(self, client_id: str) -> None:
        if await self.store.find_client(client_id) is None:
            raise ClientNotFoundError(client_id)
        await self.store.set_banned(client_id, False)

    async def reissue_device(self, client_id: str) -> InviteResult:
        existing = await self.store.find_client(client_id)
        if existing is None:
            raise ClientNotFoundError(client_id)
        await self.store.set_banned(client_id, True)
        token, token_hash, expires_at = self._token()
        comment = existing.comment or client_id
        if existing.user_id:
            new_id = await self.store.add_client_stub(
                user_id=existing.user_id,
                comment=comment,
                quota_limit_bytes=existing.quota_limit_bytes,
                enrollment_token_hash=token_hash,
                expires_at=expires_at,
            )
        else:
            new_id = await self.store.create_client_stub(
                comment=comment,
                quota_limit_bytes=existing.quota_limit_bytes,
                enrollment_token_hash=token_hash,
                expires_at=expires_at,
            )
        return self._invite_result(new_id, token)

    async def list_devices(self) -> list[ClientRecord]:
        return await self.store.list_clients()
