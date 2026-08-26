"""UserRepositoryPort — доступ к источнику истины (MongoDB Atlas, §10
спецификации). Используется typing.Protocol (структурная типизация), а не
abc.ABC — идиоматичнее для Python и не требует явного наследования от
адаптеров и тестовых fake-реализаций (см. tests/test_device_provisioning_service.py).
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from another_admin.domain.models import ClientRecord


class UserRepositoryPort(Protocol):
    def create_client_stub(
        self,
        comment: str,
        quota_limit_bytes: int,
        enrollment_token_hash: str,
        expires_at: datetime,
    ) -> str: ...

    def add_client_stub(
        self,
        user_id: str,
        comment: str,
        quota_limit_bytes: int,
        enrollment_token_hash: str,
        expires_at: datetime,
    ) -> str:
        """Добавляет ещё одно устройство к существующему user_id (переиздание)."""
        ...

    def find_client(self, client_id: str) -> ClientRecord | None: ...

    def list_clients(self) -> list[ClientRecord]: ...

    def set_banned(self, client_id: str, banned: bool) -> None: ...
