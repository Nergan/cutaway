"""
LEGACY MIGRATION BRIDGE — TEMPORARY.

Every contract in this file exists only to let an existing RSA-identity user
prove ownership of their old key one last time, in order to link a new hybrid
PQ identity to the same account. Nothing here is used by the regular
authenticated request path (see domain/repository.py::HybridCryptoPort for that).

DELETE-AFTER: 2026-09-17
  - this file
  - infrastructure/legacy_migration.py
  - application/migration_service.py
  - the /auth/migrate route in presentation/auth_router.py
  - the migration_service wiring in presentation/dependencies.py
Any account still unmigrated after that date is considered abandoned.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from typing import Any, List, Optional

MIGRATION_DEADLINE = date(2026, 9, 17)


class LegacyMigrationExpiredError(Exception):
    pass


@dataclass
class LegacyUserRecord:
    user_id: str
    public_key_pem: str
    known_ips: List[str] = field(default_factory=list)
    known_fingerprints: List[str] = field(default_factory=list)


class LegacyCryptoPort(ABC):
    """RSA-PSS verification, kept alive only to authorize migration."""

    @abstractmethod
    def derive_legacy_user_id(self, public_key_pem: str) -> str:
        ...

    @abstractmethod
    def verify_legacy_signature(self, public_key_pem: str, payload: bytes, signature: bytes) -> None:
        ...


class LegacyUserLookupPort(ABC):
    """Reads/deletes old-schema user documents (the ones with no hybrid keys)."""

    @abstractmethod
    async def get_legacy_user(self, user_id: str) -> Optional[LegacyUserRecord]:
        ...

    @abstractmethod
    async def delete_legacy_user(self, user_id: str, session: Any = None) -> None:
        ...
