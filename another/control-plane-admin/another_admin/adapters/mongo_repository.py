"""MongoUserRepository — реализация UserRepositoryPort через обычный
pymongo-драйвер (TCP wire-protocol). В отличие от edge/ (Cloudflare Worker,
вынужденного использовать Atlas Data API через HTTPS — см.
edge/src/adapters/mongo_atlas_user_repository.ts), control-plane-admin —
обычный серверный Python-процесс без ограничений V8-изолята, поэтому здесь
используется штатный драйвер напрямую.

Схема документа — §10 архитектурной спецификации: один документ на
user_id, массив clients[] внутри. В v1 один invite = один новый документ
пользователя с единственным client внутри (см. комментарий в
create_client_stub про упрощение).
"""

from __future__ import annotations

import re
import secrets
import unicodedata
import uuid
from datetime import datetime, timezone
from typing import Any

from pymongo.collection import Collection

from another_admin.domain.models import ClientRecord


_CYRILLIC_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def _transliterate_cyrillic(text: str) -> str:
    """Простая практическая транслитерация кириллицы в латиницу. Нужна
    отдельно от unicodedata.normalize("NFKD", ...): NFKD раскладывает
    диакритику ТОЛЬКО для латиницы с акцентами (é → e + combining accent),
    а не разные алфавиты — для кириллицы она не делает ничего, и
    "Друг из Питера" (пример из §10 спецификации) без явной транслитерации
    схлопнулся бы в пустую строку и ушёл в fallback "device"."""
    return "".join(_CYRILLIC_TRANSLIT.get(ch, ch) for ch in text.lower())


def _slugify(text: str, max_len: int = 24) -> str:
    """Человекочитаемая часть client_id из комментария ("Друг из Питера"
    → "drug-iz-pitera"). Не криптографически значима — уникальность
    гарантирует случайный суффикс в generate_client_id, не сам slug."""
    transliterated = _transliterate_cyrillic(text)
    normalized = unicodedata.normalize("NFKD", transliterated)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_only).strip("-").lower()
    return slug[:max_len] or "device"


def generate_client_id(comment: str) -> str:
    return f"{_slugify(comment)}-{secrets.token_hex(3)}"


def _client_fields(
    *,
    client_id: str,
    enrollment_token_hash: str,
    expires_at: datetime,
    quota_limit_bytes: int,
) -> dict[str, Any]:
    return {
        "client_id": client_id,
        "public_key": None,
        "public_key_mldsa65": None,
        "vless_user_id": None,
        "enrollment_token_hash": enrollment_token_hash,
        "enrollment_expires_at": expires_at,
        "is_banned": False,
        "quota_limit_bytes": quota_limit_bytes,
        "bytes_used": 0,
        "last_activity": None,
        "key_created_at": None,
        "key_revoked_at": None,
    }


def _doc_to_client_record(doc: dict[str, Any], raw_client: dict[str, Any] | None = None) -> ClientRecord | None:
    clients = doc.get("clients") or []
    c = raw_client if raw_client is not None else (clients[0] if clients else None)
    if not c:
        return None
    expires_at = c.get("enrollment_expires_at")
    if isinstance(expires_at, datetime) and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    last_activity = c.get("last_activity")
    if isinstance(last_activity, datetime) and last_activity.tzinfo is None:
        last_activity = last_activity.replace(tzinfo=timezone.utc)
    return ClientRecord(
        client_id=c["client_id"],
        comment=doc.get("comment", ""),
        public_key_hex=c.get("public_key"),
        vless_user_id_hex=c.get("vless_user_id"),
        is_banned=bool(c.get("is_banned", False)),
        quota_limit_bytes=int(c.get("quota_limit_bytes", 0)),
        bytes_used=int(c.get("bytes_used", 0)),
        enrollment_token_hash=c.get("enrollment_token_hash"),
        enrollment_expires_at=expires_at,
        user_id=str(doc.get("user_id", "")),
        public_key_mldsa65_hex=c.get("public_key_mldsa65"),
        last_activity=last_activity,
    )


class MongoUserRepository:
    def __init__(self, collection: Collection) -> None:
        self._collection = collection

    def create_client_stub(
        self,
        comment: str,
        quota_limit_bytes: int,
        enrollment_token_hash: str,
        expires_at: datetime,
    ) -> str:
        client_id = generate_client_id(comment)
        user_doc = {
            "user_id": str(uuid.uuid4()),
            "comment": comment,
            "created_at": datetime.now(timezone.utc),
            "clients": [
                _client_fields(
                    client_id=client_id,
                    enrollment_token_hash=enrollment_token_hash,
                    expires_at=expires_at,
                    quota_limit_bytes=quota_limit_bytes,
                )
            ],
        }
        self._collection.insert_one(user_doc)
        return client_id

    def add_client_stub(
        self,
        user_id: str,
        comment: str,
        quota_limit_bytes: int,
        enrollment_token_hash: str,
        expires_at: datetime,
    ) -> str:
        client_id = generate_client_id(comment)
        result = self._collection.update_one(
            {"user_id": user_id},
            {"$push": {"clients": _client_fields(
                client_id=client_id,
                enrollment_token_hash=enrollment_token_hash,
                expires_at=expires_at,
                quota_limit_bytes=quota_limit_bytes,
            )}},
        )
        if result.matched_count == 0:
            raise LookupError(f"user_id {user_id!r} не найден")
        return client_id

    def find_client(self, client_id: str) -> ClientRecord | None:
        # Без positional projection ("clients.$": 1) — не все реализации/
        # версии драйверов одинаково хорошо её поддерживают (в частности,
        # mongomock, используемый в тестах, не поддерживает её вовсе), а
        # выигрыш в трафике на документах такого размера (один пользователь,
        # единицы устройств) незначителен. Фильтруем клиента в Python.
        doc = self._collection.find_one({"clients.client_id": client_id})
        if doc is None:
            return None
        for raw_client in doc.get("clients", []):
            if raw_client.get("client_id") == client_id:
                return _doc_to_client_record(doc, raw_client)
        return None

    def list_clients(self) -> list[ClientRecord]:
        records: list[ClientRecord] = []
        for doc in self._collection.find({}, {"comment": 1, "clients": 1, "user_id": 1}):
            for raw_client in doc.get("clients", []):
                record = _doc_to_client_record(doc, raw_client)
                if record is not None:
                    records.append(record)
        return records

    def set_banned(self, client_id: str, banned: bool) -> None:
        update: dict[str, Any] = {"clients.$.is_banned": banned}
        update["clients.$.key_revoked_at"] = datetime.now(timezone.utc) if banned else None
        self._collection.update_one({"clients.client_id": client_id}, {"$set": update})
