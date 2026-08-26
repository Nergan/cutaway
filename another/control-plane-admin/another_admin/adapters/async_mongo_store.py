"""AsyncMongoStore — PyMongo Async API (не motor). Источник истины Atlas по MONGO_URI."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from pymongo import AsyncMongoClient
from pymongo.errors import CollectionInvalid, DuplicateKeyError

from another_admin.adapters.mongo_repository import _client_fields, _doc_to_client_record, generate_client_id
from another_admin.domain.models import AdminRecord, ClientRecord, PingTarget

DEFAULT_EVENTS_CAPPED_BYTES = 64 * 1024 * 1024


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _admin_from_doc(doc: dict[str, Any]) -> AdminRecord:
    return AdminRecord(
        admin_id=doc["admin_id"],
        ed25519_public_hex=doc["ed25519_public_hex"],
        mldsa65_public_hex=doc["mldsa65_public_hex"],
        last_seq=int(doc.get("last_seq", 0)),
        chain_head_hex=doc.get("chain_head_hex", ""),
        last_body_hash_hex=doc.get("last_body_hash_hex", ""),
        last_response=doc.get("last_response"),
        revoked=bool(doc.get("revoked", False)),
    )


def _admin_to_doc(record: AdminRecord) -> dict[str, Any]:
    return {
        "admin_id": record.admin_id,
        "ed25519_public_hex": record.ed25519_public_hex,
        "mldsa65_public_hex": record.mldsa65_public_hex,
        "last_seq": record.last_seq,
        "chain_head_hex": record.chain_head_hex,
        "last_body_hash_hex": record.last_body_hash_hex,
        "last_response": record.last_response,
        "revoked": record.revoked,
    }


class AsyncMongoStore:
    def __init__(self, db: Any, *, events_capped_bytes: int = DEFAULT_EVENTS_CAPPED_BYTES) -> None:
        self._db = db
        self._events_capped_bytes = events_capped_bytes
        self.users = db["users"]
        self.admins = db["admins"]
        self.challenges = db["admin_challenges"]
        self.settings = db["settings"]
        self.events = db["events"]
        self.sessions = db["sessions"]

    @classmethod
    def from_client(
        cls,
        client: AsyncMongoClient,
        db_name: str,
        *,
        events_capped_bytes: int = DEFAULT_EVENTS_CAPPED_BYTES,
    ) -> AsyncMongoStore:
        return cls(client[db_name], events_capped_bytes=events_capped_bytes)

    async def ensure_schema(self) -> None:
        await self.users.create_index("clients.client_id", unique=True)
        await self.users.create_index("clients.enrollment_token_hash")
        await self.users.create_index("user_id", unique=True)
        await self.admins.create_index("admin_id", unique=True)
        await self.challenges.create_index("expires_at", expireAfterSeconds=0)
        await self.sessions.create_index("session_id", unique=True)
        await self.sessions.create_index("client_id")
        await self.sessions.create_index("last_seen", expireAfterSeconds=900)
        existing = await self._db.list_collection_names()
        if "events" not in existing:
            try:
                await self._db.create_collection(
                    "events",
                    capped=True,
                    size=self._events_capped_bytes,
                )
            except CollectionInvalid:
                pass
        # capped-коллекция не умеет TTL; затирание — свойство capped.
        # acked хранится в документе, пока его не вытеснит хвост.

    async def find_client(self, client_id: str) -> ClientRecord | None:
        doc = await self.users.find_one({"clients.client_id": client_id})
        if doc is None:
            return None
        for raw in doc.get("clients", []):
            if raw.get("client_id") == client_id:
                return _doc_to_client_record(doc, raw)
        return None

    async def find_enrollment_by_token_hash(self, token_hash: str) -> tuple[str, datetime] | None:
        doc = await self.users.find_one({"clients.enrollment_token_hash": token_hash})
        if doc is None:
            return None
        for raw in doc.get("clients", []):
            if raw.get("enrollment_token_hash") == token_hash and raw.get("enrollment_expires_at"):
                expires = raw["enrollment_expires_at"]
                if isinstance(expires, datetime) and expires.tzinfo is None:
                    expires = expires.replace(tzinfo=timezone.utc)
                return raw["client_id"], expires
        return None

    async def bind_device_identity(
        self,
        client_id: str,
        public_key_hex: str,
        vless_user_id_hex: str,
        public_key_mldsa65_hex: str | None = None,
    ) -> None:
        update: dict[str, Any] = {
            "clients.$.public_key": public_key_hex,
            "clients.$.vless_user_id": vless_user_id_hex,
            "clients.$.key_created_at": _utcnow(),
        }
        if public_key_mldsa65_hex is not None:
            update["clients.$.public_key_mldsa65"] = public_key_mldsa65_hex
        await self.users.update_one({"clients.client_id": client_id}, {"$set": update})

    async def consume_enrollment_token(self, token_hash: str) -> None:
        await self.users.update_one(
            {"clients.enrollment_token_hash": token_hash},
            {"$set": {
                "clients.$.enrollment_token_hash": None,
                "clients.$.enrollment_expires_at": None,
            }},
        )

    async def increment_usage(self, client_id: str, bytes_delta: int) -> None:
        await self.users.update_one(
            {"clients.client_id": client_id},
            {
                "$inc": {"clients.$.bytes_used": bytes_delta},
                "$set": {"clients.$.last_activity": _utcnow()},
            },
        )

    async def create_client_stub(
        self,
        comment: str,
        quota_limit_bytes: int,
        enrollment_token_hash: str,
        expires_at: datetime,
    ) -> str:
        client_id = generate_client_id(comment)
        await self.users.insert_one(
            {
                "user_id": str(uuid.uuid4()),
                "comment": comment,
                "created_at": _utcnow(),
                "clients": [
                    _client_fields(
                        client_id=client_id,
                        enrollment_token_hash=enrollment_token_hash,
                        expires_at=expires_at,
                        quota_limit_bytes=quota_limit_bytes,
                    )
                ],
            }
        )
        return client_id

    async def add_client_stub(
        self,
        user_id: str,
        comment: str,
        quota_limit_bytes: int,
        enrollment_token_hash: str,
        expires_at: datetime,
    ) -> str:
        client_id = generate_client_id(comment)
        result = await self.users.update_one(
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

    async def list_clients(self) -> list[ClientRecord]:
        records: list[ClientRecord] = []
        cursor = self.users.find({}, {"comment": 1, "clients": 1, "user_id": 1})
        async for doc in cursor:
            for raw in doc.get("clients", []):
                rec = _doc_to_client_record(doc, raw)
                if rec is not None:
                    records.append(rec)
        return records

    async def set_banned(self, client_id: str, banned: bool) -> None:
        await self.users.update_one(
            {"clients.client_id": client_id},
            {"$set": {
                "clients.$.is_banned": banned,
                "clients.$.key_revoked_at": _utcnow() if banned else None,
            }},
        )

    async def delete_client(self, client_id: str) -> bool:
        doc = await self.users.find_one({"clients.client_id": client_id}, {"_id": 1})
        if doc is None:
            return False
        await self.users.update_one(
            {"_id": doc["_id"]},
            {"$pull": {"clients": {"client_id": client_id}}},
        )
        leftover = await self.users.find_one({"_id": doc["_id"]}, {"clients": 1})
        if leftover is not None and not leftover.get("clients"):
            await self.users.delete_one({"_id": doc["_id"]})
        await self.sessions.delete_many({"client_id": client_id})
        return True

    async def get_admin(self, admin_id: str) -> AdminRecord | None:
        doc = await self.admins.find_one({"admin_id": admin_id})
        if doc is None:
            return None
        return _admin_from_doc(doc)

    async def insert_admin(self, record: AdminRecord) -> None:
        try:
            await self.admins.insert_one(_admin_to_doc(record))
        except DuplicateKeyError as exc:
            raise ValueError("admin already exists") from exc

    async def replace_admin(self, expected_seq: int, record: AdminRecord) -> bool:
        result = await self.admins.replace_one(
            {"admin_id": record.admin_id, "last_seq": expected_seq},
            _admin_to_doc(record),
        )
        return result.matched_count == 1

    async def put_challenge(self, challenge_hex: str, expires_at: datetime) -> None:
        await self.challenges.replace_one(
            {"challenge_hex": challenge_hex},
            {"challenge_hex": challenge_hex, "expires_at": expires_at},
            upsert=True,
        )

    async def consume_challenge(self, challenge_hex: str) -> bool:
        doc = await self.challenges.find_one_and_delete({"challenge_hex": challenge_hex})
        if doc is None:
            return False
        expires = doc.get("expires_at")
        if not isinstance(expires, datetime):
            return False
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        return expires >= _utcnow()

    async def get_ping_targets(self) -> list[PingTarget]:
        doc = await self.settings.find_one({"_id": "ping_targets"})
        if not doc:
            return []
        return [
            PingTarget(
                name=t["name"],
                url=t["url"],
                interval_s=int(t.get("interval_s", 300)),
                expect_status=int(t.get("expect_status", 200)),
            )
            for t in doc.get("targets", [])
        ]

    async def set_ping_targets(self, targets: list[PingTarget]) -> None:
        await self.settings.replace_one(
            {"_id": "ping_targets"},
            {
                "_id": "ping_targets",
                "targets": [
                    {
                        "name": t.name,
                        "url": t.url,
                        "interval_s": t.interval_s,
                        "expect_status": t.expect_status,
                    }
                    for t in targets
                ],
            },
            upsert=True,
        )

    async def append_event(self, event: dict[str, Any]) -> str:
        event_id = str(uuid.uuid4())
        stored = {
            **event,
            "event_id": event_id,
            "ts": event.get("ts") or _utcnow(),
            "acked": False,
        }
        await self.events.insert_one(stored)
        return event_id

    async def list_events(self, *, limit: int = 100, unacked_only: bool = False) -> list[dict[str, Any]]:
        query: dict[str, Any] = {"acked": False} if unacked_only else {}
        cursor = self.events.find(query).sort("$natural", -1).limit(limit)
        out: list[dict[str, Any]] = []
        async for doc in cursor:
            doc.pop("_id", None)
            ts = doc.get("ts")
            if isinstance(ts, datetime):
                doc["ts"] = ts.isoformat()
            out.append(doc)
        return out

    async def ack_event(self, event_id: str) -> bool:
        # Capped collection: update in place, не меняя размер документа сильно.
        result = await self.events.update_one({"event_id": event_id}, {"$set": {"acked": True}})
        return result.matched_count == 1

    def _session_id(self, client_id: str, ip_hash: str) -> str:
        return f"{client_id}:{ip_hash}"

    def _session_json(self, doc: dict[str, Any], *, show_ip: bool) -> dict[str, Any]:
        item = {
            "session_id": doc.get("session_id"),
            "client_id": doc.get("client_id"),
            "ip_hash": doc.get("ip_hash"),
            "node": doc.get("node"),
            "entrypoint": doc.get("entrypoint"),
            "bytes_window": int(doc.get("bytes_window") or 0),
        }
        for key in ("started_at", "last_seen"):
            value = doc.get(key)
            if isinstance(value, datetime):
                item[key] = value.isoformat()
            elif value is not None:
                item[key] = value
        if show_ip and doc.get("ip"):
            item["ip"] = doc.get("ip")
        return item

    async def upsert_session(self, session: dict[str, Any]) -> str:
        client_id = str(session.get("client_id") or "")
        ip_hash = str(session.get("ip_hash") or "")
        if not client_id or not ip_hash:
            raise ValueError("client_id and ip_hash are required")
        sid = str(session.get("session_id") or self._session_id(client_id, ip_hash))
        now = _utcnow()
        fields = {
            "session_id": sid,
            "client_id": client_id,
            "ip_hash": ip_hash,
            "node": session.get("node"),
            "entrypoint": session.get("entrypoint"),
            "last_seen": now,
            "closed": False,
        }
        if session.get("ip"):
            fields["ip"] = session.get("ip")
        await self.sessions.update_one(
            {"session_id": sid},
            {
                "$set": fields,
                "$setOnInsert": {"started_at": now, "bytes_window": 0},
                "$inc": {"bytes_window": int(session.get("bytes_delta") or 0)},
            },
            upsert=True,
        )
        return sid

    async def list_sessions(self, *, active_within_s: int = 180) -> list[dict[str, Any]]:
        cutoff = _utcnow() - timedelta(seconds=active_within_s)
        show_ip = await self.get_investigation_mode()
        cursor = self.sessions.find(
            {"closed": {"$ne": True}, "last_seen": {"$gte": cutoff}}
        )
        out: list[dict[str, Any]] = []
        async for doc in cursor:
            out.append(self._session_json(doc, show_ip=show_ip))
        return out

    async def close_session(self, *, client_id: str, ip_hash: str, bytes_delta: int = 0) -> bool:
        sid = self._session_id(client_id, ip_hash)
        result = await self.sessions.update_one(
            {"session_id": sid},
            {
                "$set": {"closed": True, "last_seen": _utcnow()},
                "$inc": {"bytes_window": int(bytes_delta)},
            },
        )
        return result.matched_count == 1

    async def get_alert_thresholds(self) -> dict[str, Any]:
        doc = await self.settings.find_one({"_id": "alert_thresholds"})
        if not doc:
            return {}
        doc.pop("_id", None)
        return doc

    async def set_alert_thresholds(self, thresholds: dict[str, Any]) -> None:
        await self.settings.replace_one(
            {"_id": "alert_thresholds"},
            {"_id": "alert_thresholds", **thresholds},
            upsert=True,
        )

    async def get_investigation_mode(self) -> bool:
        doc = await self.settings.find_one({"_id": "investigation"})
        return bool(doc and doc.get("enabled"))

    async def set_investigation_mode(self, enabled: bool) -> None:
        await self.settings.replace_one(
            {"_id": "investigation"},
            {"_id": "investigation", "enabled": bool(enabled)},
            upsert=True,
        )
