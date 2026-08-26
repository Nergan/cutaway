"""In-memory ControlPlaneStore — для тестов API без Mongo."""

from __future__ import annotations

import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Any

from another_admin.adapters.mongo_repository import generate_client_id
from another_admin.domain.models import AdminRecord, ClientRecord, PingTarget


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class InMemoryControlPlaneStore:
    def __init__(self, *, events_cap: int = 500) -> None:
        self.users: dict[str, dict[str, Any]] = {}  # user_id -> doc
        self.admins: dict[str, AdminRecord] = {}
        self.challenges: dict[str, datetime] = {}
        self.ping_targets: list[PingTarget] = []
        self.events: deque[dict[str, Any]] = deque(maxlen=events_cap)
        self.sessions: dict[str, dict[str, Any]] = {}
        self.alert_thresholds: dict[str, Any] = {}
        self.investigation_mode = False

    def _iter_clients(self) -> list[tuple[dict[str, Any], dict[str, Any]]]:
        out: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for doc in self.users.values():
            for client in doc.get("clients", []):
                out.append((doc, client))
        return out

    def _record(self, doc: dict[str, Any], client: dict[str, Any]) -> ClientRecord:
        expires = client.get("enrollment_expires_at")
        last = client.get("last_activity")
        return ClientRecord(
            client_id=client["client_id"],
            comment=doc.get("comment", ""),
            public_key_hex=client.get("public_key"),
            vless_user_id_hex=client.get("vless_user_id"),
            is_banned=bool(client.get("is_banned", False)),
            quota_limit_bytes=int(client.get("quota_limit_bytes", 0)),
            bytes_used=int(client.get("bytes_used", 0)),
            enrollment_token_hash=client.get("enrollment_token_hash"),
            enrollment_expires_at=expires,
            user_id=str(doc.get("user_id", "")),
            public_key_mldsa65_hex=client.get("public_key_mldsa65"),
            last_activity=last,
        )

    async def find_client(self, client_id: str) -> ClientRecord | None:
        for doc, client in self._iter_clients():
            if client.get("client_id") == client_id:
                return self._record(doc, client)
        return None

    async def find_enrollment_by_token_hash(self, token_hash: str) -> tuple[str, datetime] | None:
        for _, client in self._iter_clients():
            if client.get("enrollment_token_hash") == token_hash and client.get("enrollment_expires_at"):
                return client["client_id"], client["enrollment_expires_at"]
        return None

    async def bind_device_identity(
        self,
        client_id: str,
        public_key_hex: str,
        vless_user_id_hex: str,
        public_key_mldsa65_hex: str | None = None,
    ) -> None:
        for _, client in self._iter_clients():
            if client.get("client_id") == client_id:
                client["public_key"] = public_key_hex
                client["vless_user_id"] = vless_user_id_hex
                client["public_key_mldsa65"] = public_key_mldsa65_hex
                client["key_created_at"] = _utcnow()
                return

    async def consume_enrollment_token(self, token_hash: str) -> None:
        for _, client in self._iter_clients():
            if client.get("enrollment_token_hash") == token_hash:
                client["enrollment_token_hash"] = None
                client["enrollment_expires_at"] = None
                return

    async def increment_usage(self, client_id: str, bytes_delta: int) -> None:
        for _, client in self._iter_clients():
            if client.get("client_id") == client_id:
                client["bytes_used"] = int(client.get("bytes_used", 0)) + bytes_delta
                client["last_activity"] = _utcnow()
                return

    def _new_client_fields(
        self,
        *,
        comment: str,
        quota_limit_bytes: int,
        enrollment_token_hash: str,
        expires_at: datetime,
    ) -> tuple[str, dict[str, Any]]:
        client_id = generate_client_id(comment)
        return client_id, {
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

    async def create_client_stub(
        self,
        comment: str,
        quota_limit_bytes: int,
        enrollment_token_hash: str,
        expires_at: datetime,
    ) -> str:
        user_id = str(uuid.uuid4())
        client_id, fields = self._new_client_fields(
            comment=comment,
            quota_limit_bytes=quota_limit_bytes,
            enrollment_token_hash=enrollment_token_hash,
            expires_at=expires_at,
        )
        self.users[user_id] = {
            "user_id": user_id,
            "comment": comment,
            "created_at": _utcnow(),
            "clients": [fields],
        }
        return client_id

    async def add_client_stub(
        self,
        user_id: str,
        comment: str,
        quota_limit_bytes: int,
        enrollment_token_hash: str,
        expires_at: datetime,
    ) -> str:
        doc = self.users.get(user_id)
        if doc is None:
            raise LookupError(f"user_id {user_id!r} не найден")
        client_id, fields = self._new_client_fields(
            comment=comment,
            quota_limit_bytes=quota_limit_bytes,
            enrollment_token_hash=enrollment_token_hash,
            expires_at=expires_at,
        )
        doc["clients"].append(fields)
        return client_id

    async def list_clients(self) -> list[ClientRecord]:
        return [self._record(doc, client) for doc, client in self._iter_clients()]

    async def set_banned(self, client_id: str, banned: bool) -> None:
        for _, client in self._iter_clients():
            if client.get("client_id") == client_id:
                client["is_banned"] = banned
                client["key_revoked_at"] = _utcnow() if banned else None
                return

    async def get_admin(self, admin_id: str) -> AdminRecord | None:
        return self.admins.get(admin_id)

    async def insert_admin(self, record: AdminRecord) -> None:
        if record.admin_id in self.admins:
            raise ValueError("admin already exists")
        self.admins[record.admin_id] = record

    async def replace_admin(self, expected_seq: int, record: AdminRecord) -> bool:
        current = self.admins.get(record.admin_id)
        if current is None or current.last_seq != expected_seq:
            return False
        self.admins[record.admin_id] = record
        return True

    async def put_challenge(self, challenge_hex: str, expires_at: datetime) -> None:
        self.challenges[challenge_hex] = expires_at

    async def consume_challenge(self, challenge_hex: str) -> bool:
        expires = self.challenges.pop(challenge_hex, None)
        if expires is None:
            return False
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        return expires >= _utcnow()

    async def get_ping_targets(self) -> list[PingTarget]:
        return list(self.ping_targets)

    async def set_ping_targets(self, targets: list[PingTarget]) -> None:
        self.ping_targets = list(targets)

    async def append_event(self, event: dict[str, Any]) -> str:
        event_id = str(uuid.uuid4())
        stored = {
            **event,
            "event_id": event_id,
            "ts": event.get("ts") or _utcnow().isoformat(),
            "acked": False,
        }
        self.events.appendleft(stored)
        return event_id

    async def list_events(self, *, limit: int = 100, unacked_only: bool = False) -> list[dict[str, Any]]:
        items = list(self.events)
        if unacked_only:
            items = [e for e in items if not e.get("acked")]
        return items[:limit]

    async def ack_event(self, event_id: str) -> bool:
        for event in self.events:
            if event.get("event_id") == event_id:
                event["acked"] = True
                return True
        return False

    def _session_id(self, client_id: str, ip_hash: str) -> str:
        return f"{client_id}:{ip_hash}"

    async def upsert_session(self, session: dict[str, Any]) -> str:
        client_id = str(session.get("client_id") or "")
        ip_hash = str(session.get("ip_hash") or "")
        if not client_id or not ip_hash:
            raise ValueError("client_id and ip_hash are required")
        sid = str(session.get("session_id") or self._session_id(client_id, ip_hash))
        now = _utcnow()
        current = self.sessions.get(sid, {})
        stored = {
            **current,
            **session,
            "session_id": sid,
            "client_id": client_id,
            "ip_hash": ip_hash,
            "last_seen": now,
            "closed": False,
            "bytes_window": int(current.get("bytes_window") or 0) + int(session.get("bytes_delta") or 0),
        }
        if "started_at" not in stored or current.get("started_at") is None:
            stored["started_at"] = current.get("started_at") or now
        self.sessions[sid] = stored
        return sid

    async def list_sessions(self, *, active_within_s: int = 180) -> list[dict[str, Any]]:
        cutoff = _utcnow().timestamp() - active_within_s
        out: list[dict[str, Any]] = []
        show_ip = self.investigation_mode
        for stored in self.sessions.values():
            if stored.get("closed"):
                continue
            last = stored.get("last_seen")
            if isinstance(last, datetime):
                if last.tzinfo is None:
                    last = last.replace(tzinfo=timezone.utc)
                if last.timestamp() < cutoff:
                    continue
            item = {
                "session_id": stored.get("session_id"),
                "client_id": stored.get("client_id"),
                "ip_hash": stored.get("ip_hash"),
                "node": stored.get("node"),
                "entrypoint": stored.get("entrypoint"),
                "bytes_window": int(stored.get("bytes_window") or 0),
                "started_at": stored["started_at"].isoformat() if isinstance(stored.get("started_at"), datetime) else stored.get("started_at"),
                "last_seen": stored["last_seen"].isoformat() if isinstance(stored.get("last_seen"), datetime) else stored.get("last_seen"),
            }
            if show_ip and stored.get("ip"):
                item["ip"] = stored.get("ip")
            out.append(item)
        return out

    async def close_session(self, *, client_id: str, ip_hash: str, bytes_delta: int = 0) -> bool:
        sid = self._session_id(client_id, ip_hash)
        stored = self.sessions.get(sid)
        if stored is None:
            return False
        stored["closed"] = True
        stored["bytes_window"] = int(stored.get("bytes_window") or 0) + int(bytes_delta)
        stored["last_seen"] = _utcnow()
        return True

    async def get_alert_thresholds(self) -> dict[str, Any]:
        return dict(self.alert_thresholds)

    async def set_alert_thresholds(self, thresholds: dict[str, Any]) -> None:
        self.alert_thresholds = dict(thresholds)

    async def get_investigation_mode(self) -> bool:
        return bool(self.investigation_mode)

    async def set_investigation_mode(self, enabled: bool) -> None:
        self.investigation_mode = bool(enabled)
