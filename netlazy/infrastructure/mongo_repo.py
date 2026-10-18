import random
from datetime import datetime, timezone
from typing import List, Optional, Any, Tuple
from uuid import uuid4
from pymongo.errors import DuplicateKeyError
from pymongo import ReturnDocument, UpdateOne, ReadPreference
from netlazy.database import db_instance
from netlazy.config import settings
from netlazy.domain.forms import FormSlugConflict
from netlazy.domain.models import Contact, Handshake, MediaItem, PoWChallenge, Profile, PushPreferences, PushSubscription, Tag, User, UserAlreadyExistsError
from netlazy.domain.repository import (
    ChainRepository,
    HandshakeRepository,
    NonceRepository,
    ProfileRepository,
    SecurityRepository,
    TagRepository,
    UserRepository,
    TransactionManager,
)


def _force_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class MongoUserRepository(UserRepository):
    async def create(self, user: User, session: Any = None) -> None:
        try:
            await db_instance.users_collection.insert_one({
                "user_id": user.user_id,
                "ed25519_public_pem": user.ed25519_public_pem,
                "mldsa_public_hex": user.mldsa_public_hex,
                "created_at": user.created_at,
                "known_ips": user.known_ips,
                "known_fingerprints": user.known_fingerprints,
                "is_banned": user.is_banned,
                "risk_score": user.risk_score
            }, session=session)
        except DuplicateKeyError:
            raise UserAlreadyExistsError(f"User {user.user_id} already registered")

    async def get_by_id(self, user_id: str, session: Any = None) -> Optional[User]:
        doc = await db_instance.users_collection.find_one({"user_id": user_id}, session=session)
        if not doc or "ed25519_public_pem" not in doc:
            return None
        return self._to_domain(doc)

    def _to_domain(self, doc: dict) -> User:
        return User(
            user_id=doc["user_id"],
            ed25519_public_pem=doc["ed25519_public_pem"],
            mldsa_public_hex=doc["mldsa_public_hex"],
            created_at=_force_utc(doc["created_at"]),
            known_ips=doc.get("known_ips", []),
            known_fingerprints=doc.get("known_fingerprints", []),
            is_banned=doc.get("is_banned", False),
            risk_score=doc.get("risk_score", 0.0)
        )

    async def log_footprint(self, user_id: str, ip: str, fingerprint: str) -> None:
        if not ip and not fingerprint:
            return
        updates = {}
        trusted_ips = [t.strip() for t in settings.trusted_bot_ips.split(",") if t.strip()]
        if ip and ip not in trusted_ips:
            updates["known_ips"] = ip
        if fingerprint:
            updates["known_fingerprints"] = fingerprint
        if updates:
            await db_instance.users_collection.update_one(
                {"user_id": user_id},
                {"$addToSet": updates, "$set": {"last_ip": ip, "last_active": datetime.now(timezone.utc)}}
            )

    async def get_last_activity(self, user_id: str) -> Tuple[Optional[str], Optional[int]]:
        doc = await db_instance.users_collection.find_one({"user_id": user_id}, {"last_ip": 1, "last_active": 1})
        if not doc:
            return None, None
        last_active = doc.get("last_active")
        ts = int(last_active.timestamp()) if last_active else None
        return doc.get("last_ip"), ts

    async def increment_risk_score(self, user_id: str, score_delta: float) -> float:
        if score_delta <= 0:
            return 0.0
        doc = await db_instance.users_collection.find_one_and_update(
            {"user_id": user_id},
            {"$inc": {"risk_score": score_delta}},
            return_document=True
        )
        return doc.get("risk_score", 0.0) if doc else 0.0

    async def delete(self, user_id: str, session: Any = None) -> None:
        await db_instance.users_collection.delete_one({"user_id": user_id}, session=session)

    async def get_active_user_ids(self, user_ids: List[str]) -> List[str]:
        cursor = db_instance.users_collection.find({
            "user_id": {"$in": user_ids},
            "is_banned": {"$ne": True}
        }, {"user_id": 1})
        return [doc["user_id"] async for doc in cursor]


class MongoNonceRepository(NonceRepository):
    async def insert_if_not_exists(self, user_id: str, nonce: str) -> bool:
        try:
            await db_instance.used_nonces_collection.insert_one({
                "nonce": nonce,
                "user_id": user_id,
                "created_at": datetime.now(timezone.utc),
            })
            return True
        except DuplicateKeyError:
            return False

    async def delete_for_user(self, user_id: str, session: Any = None) -> None:
        await db_instance.used_nonces_collection.delete_many({"user_id": user_id}, session=session)


class MongoSecurityRepository(SecurityRepository):
    async def create_challenge(self, challenge: PoWChallenge) -> None:
        await db_instance.challenges_collection.insert_one({
            "id": challenge.id,
            "difficulty": challenge.difficulty,
            "created_at": challenge.created_at
        })

    async def consume_challenge(self, challenge_id: str) -> Optional[PoWChallenge]:
        doc = await db_instance.challenges_collection.find_one_and_delete({"id": challenge_id})
        if not doc:
            return None
        return PoWChallenge(id=doc["id"], difficulty=doc["difficulty"], created_at=_force_utc(doc["created_at"]))

    async def is_banned(self, ip: str, fingerprint: str, user_id: Optional[str] = None) -> bool:
        queries = []
        if ip:
            queries.append({"type": "ip", "value": ip})
        if fingerprint:
            queries.append({"type": "fingerprint", "value": fingerprint})
        if user_id:
            queries.append({"type": "user_id", "value": user_id})

        if not queries:
            return False
        doc = await db_instance.bans_collection.find_one({"$or": queries})
        return doc is not None

    async def apply_bans(self, ips: List[str], fingerprints: List[str], user_id: str) -> None:
        trusted_ips = [t.strip() for t in settings.trusted_bot_ips.split(",") if t.strip()]
        ips_to_ban = [ip for ip in ips if ip not in trusted_ips]

        ops = []
        for ip in ips_to_ban:
            ops.append({"type": "ip", "value": ip, "created_at": datetime.now(timezone.utc)})
        for fp in fingerprints:
            ops.append({"type": "fingerprint", "value": fp, "created_at": datetime.now(timezone.utc)})
        ops.append({"type": "user_id", "value": user_id, "created_at": datetime.now(timezone.utc)})

        for op in ops:
            await db_instance.bans_collection.update_one(
                {"type": op["type"], "value": op["value"]}, {"$set": op}, upsert=True
            )
        await db_instance.users_collection.update_one({"user_id": user_id}, {"$set": {"is_banned": True}})

    async def remove_bans(self, ips: List[str], fingerprints: List[str], user_id: str) -> None:
        ops = []
        for ip in ips:
            ops.append({"type": "ip", "value": ip})
        for fp in fingerprints:
            ops.append({"type": "fingerprint", "value": fp})
        ops.append({"type": "user_id", "value": user_id})

        if ops:
            await db_instance.bans_collection.delete_many({"$or": ops})


class MongoTagRepository(TagRepository):
    async def sync(self, tags: List[Tag], file_hash: Optional[str] = None) -> bool:
        if not tags:
            return False

        if file_hash:
            meta = await db_instance.tags_collection.find_one({"name": "__sync_hash__"})
            if meta and meta.get("hash") == file_hash:
                return False

        valid_names = [t.name for t in tags]
        operations = [
            UpdateOne(
                {"name": tag.name},
                {"$set": {"aliases": tag.aliases, "hidden": tag.hidden, "i18n": tag.i18n}},
                upsert=True,
            )
            for tag in tags
        ]

        if file_hash:
            operations.append(
                UpdateOne(
                    {"name": "__sync_hash__"},
                    {"$set": {"hash": file_hash}},
                    upsert=True
                )
            )
            valid_names.append("__sync_hash__")

        if operations:
            await db_instance.tags_collection.bulk_write(operations)

        if valid_names:
            await db_instance.tags_collection.delete_many({"name": {"$nin": valid_names}})
        else:
            await db_instance.tags_collection.delete_many({})

        profile_valid_names = [t.name for t in tags]
        if profile_valid_names:
            await db_instance.profiles_collection.update_many({}, {"$pull": {"tags": {"$nin": profile_valid_names}}})
        else:
            await db_instance.profiles_collection.update_many({}, {"$pull": {"tags": {"$nin": []}}})

        return True

    async def get_all_tags(self) -> List[Tag]:
        cursor = db_instance.tags_collection.find({"name": {"$ne": "__sync_hash__"}})
        return [self._to_domain(doc) async for doc in cursor]

    async def list_visible(self) -> List[Tag]:
        cursor = db_instance.tags_collection.find({"hidden": False, "name": {"$ne": "__sync_hash__"}})
        return [self._to_domain(doc) async for doc in cursor]

    async def search(self, query: str) -> List[Tag]:
        tokens = query.strip().split()
        if not tokens:
            return await self.list_visible()
        positive = [t.lower() for t in tokens if not t.startswith("-")]
        negative = [t[1:].lower() for t in tokens if t.startswith("-") and len(t) > 1]

        cursor = db_instance.tags_collection.find({"name": {"$ne": "__sync_hash__"}})
        all_tags = [self._to_domain(doc) async for doc in cursor]

        def matches(tag: Tag, term: str) -> bool:
            if term in tag.name.lower():
                return True
            if any(term in str(alias).lower() for alias in tag.aliases):
                return True
            if tag.i18n and any(term in str(v).lower() for v in tag.i18n.values()):
                return True
            return False

        if positive:
            results = [t for t in all_tags if any(matches(t, term) for term in positive)]
        else:
            results = all_tags
        if negative:
            results = [t for t in results if not any(matches(t, term) for term in negative)]
        return results

    async def get_all_names(self) -> List[str]:
        cursor = db_instance.tags_collection.find({"name": {"$ne": "__sync_hash__"}}, {"name": 1})
        return [doc["name"] async for doc in cursor]

    def _to_domain(self, doc: dict) -> Tag:
        return Tag(
            name=doc["name"],
            aliases=doc.get("aliases", []),
            hidden=doc.get("hidden", False),
            i18n=doc.get("i18n", {})
        )


class MongoProfileRepository(ProfileRepository):
    async def get_by_user_id(self, user_id: str, session: Any = None) -> Optional[Profile]:
        doc = await db_instance.profiles_collection.find_one({"user_id": user_id}, session=session)
        if not doc:
            return None
        return self._to_domain(doc)

    async def get_by_user_ids(self, user_ids: List[str]) -> List[Profile]:
        cursor = db_instance.profiles_collection.find({"user_id": {"$in": user_ids}})
        return [self._to_domain(doc) async for doc in cursor]

    async def get_by_public_id(self, public_id: str) -> Optional[Profile]:
        if not public_id:
            return None
        doc = await db_instance.profiles_collection.find_one({"public_id": public_id})
        if not doc:
            return None
        return self._to_domain(doc)

    async def user_ids_for_public_ids(self, public_ids: List[str]) -> List[str]:
        if not public_ids:
            return []
        cursor = db_instance.profiles_collection.find(
            {"public_id": {"$in": list(public_ids)}},
            {"user_id": 1},
        )
        return [doc["user_id"] async for doc in cursor if doc.get("user_id")]

    async def ensure_public_id(self, profile: Profile) -> str:
        if profile.public_id:
            return profile.public_id
        new_id = uuid4().hex
        collection = db_instance.profiles_collection
        missing = {
            "user_id": profile.user_id,
            "$or": [
                {"public_id": {"$exists": False}},
                {"public_id": None},
                {"public_id": ""},
            ],
        }
        doc = await collection.find_one_and_update(
            missing,
            {"$set": {"public_id": new_id}},
            return_document=ReturnDocument.AFTER,
        )
        if doc and doc.get("public_id"):
            profile.public_id = doc["public_id"]
            return profile.public_id
        existing = await collection.find_one({"user_id": profile.user_id}, {"public_id": 1})
        if existing and existing.get("public_id"):
            profile.public_id = existing["public_id"]
            return profile.public_id
        profile.public_id = new_id
        if existing is None:
            try:
                await collection.update_one(
                    {"user_id": profile.user_id},
                    {"$setOnInsert": self._to_doc(profile)},
                    upsert=True,
                )
            except DuplicateKeyError:
                pass
            stored = await collection.find_one({"user_id": profile.user_id}, {"public_id": 1})
            if stored and stored.get("public_id"):
                profile.public_id = stored["public_id"]
            return profile.public_id
        await collection.update_one({"user_id": profile.user_id}, {"$set": {"public_id": new_id}})
        return profile.public_id

    async def get_by_form(self, slug: str) -> Optional[Profile]:
        if not slug:
            return None
        doc = await db_instance.profiles_collection.find_one({"forms": slug})
        if not doc:
            return None
        profile = self._to_domain(doc)
        user_doc = await db_instance.users_collection.find_one(
            {"user_id": profile.user_id},
            {"is_banned": 1},
        )
        if user_doc and user_doc.get("is_banned"):
            return None
        return profile

    async def reassign_owner(self, old_user_id: str, new_user_id: str, session: Any = None) -> None:
        await db_instance.profiles_collection.update_one(
            {"user_id": old_user_id},
            {"$set": {"user_id": new_user_id, "updated_at": datetime.now(timezone.utc)}},
            session=session,
        )

    async def upsert(self, profile: Profile, session: Any = None) -> None:
        try:
            await db_instance.profiles_collection.update_one(
                {"user_id": profile.user_id},
                {"$set": self._to_doc(profile)},
                upsert=True,
                session=session
            )
        except DuplicateKeyError as exc:
            if "forms" in str(exc):
                raise FormSlugConflict() from exc
            raise

    async def get_feed(
        self, viewer_id: str, exclude_ids: List[str], requires: List[str], excludes: List[str],
        bonus: List[str], abonus: List[str], limit: int
    ) -> List[Profile]:
        ignored = list(exclude_ids)
        if viewer_id:
            ignored.append(viewer_id)
        base_match = {"user_id": {"$nin": ignored}} if ignored else {}

        if requires:
            base_match["tags"] = {"$all": requires}
        if excludes:
            base_match.setdefault("tags", {})["$nin"] = excludes

        base_match["$or"] = [
            {"bio": {"$nin": ["", None]}},
            {"tags.0": {"$exists": True}},
            {"media.0": {"$exists": True}},
            {"audio": {"$type": "object"}},
            {"contacts": {"$elemMatch": {"is_private": False, "type": {"$ne": "unknown"}, "value": {"$nin": ["", None]}}}}
        ]

        pipeline = [
            {"$match": base_match},
            {"$lookup": {
                "from": "users",
                "localField": "user_id",
                "foreignField": "user_id",
                "as": "user_info"
            }},
            {"$match": {"user_info.is_banned": {"$ne": True}}},
            {"$addFields": {"_sort_at": {"$ifNull": ["$updated_at", "$created_at"]}}},
            {"$sort": {"_sort_at": -1, "user_id": 1}},
            {"$limit": limit},
        ]
        db_cursor = db_instance.profiles_collection.aggregate(pipeline)
        docs = [self._to_domain(doc) async for doc in db_cursor]
        for profile in docs:
            if bonus or abonus:
                profile.score = len(set(profile.tags) & set(bonus)) - len(set(profile.tags) & set(abonus))
        return docs

    async def delete(self, user_id: str, session: Any = None) -> None:
        await db_instance.profiles_collection.delete_one({"user_id": user_id}, session=session)

    async def count_media_usage(self, file_hash: str) -> int:
        if not file_hash:
            return 0
        return await db_instance.profiles_collection.count_documents({
            "$or": [
                {"media.file_hash": file_hash},
                {"audio.file_hash": file_hash}
            ]
        })

    async def find_media_by_hash(self, file_hash: str) -> Optional[MediaItem]:
        if not file_hash:
            return None
        doc = await db_instance.profiles_collection.find_one({
            "$or": [
                {"media.file_hash": file_hash},
                {"audio.file_hash": file_hash}
            ]
        })
        if doc:
            for m in doc.get("media", []):
                if m.get("file_hash") == file_hash:
                    return self._media_from_doc(m)
            audio = doc.get("audio")
            if audio and audio.get("file_hash") == file_hash:
                return self._media_from_doc(audio)
        return None

    def _to_doc(self, profile: Profile) -> dict:
        doc = {
            "user_id": profile.user_id,
            "media_id": profile.media_id,
            "bio": profile.bio,
            "tags": profile.tags,
            "media": [self._media_to_doc(m) for m in profile.media],
            "audio": self._media_to_doc(profile.audio) if profile.audio else None,
            "contacts": [self._contact_to_doc(c) for c in profile.contacts],
            "forms": list(profile.forms),
            "primary_form": profile.primary_form,
            "created_at": profile.created_at,
            "updated_at": profile.updated_at,
            "random_index": profile.random_index
        }
        if profile.public_id:
            doc["public_id"] = profile.public_id
        return doc

    def _to_domain(self, doc: dict) -> Profile:
        return Profile(
            user_id=doc["user_id"],
            media_id=doc.get("media_id", doc["user_id"]),
            public_id=doc.get("public_id") or "",
            bio=doc.get("bio", ""),
            tags=doc.get("tags", []),
            media=[self._media_from_doc(m) for m in doc.get("media", [])],
            audio=self._media_from_doc(doc["audio"]) if doc.get("audio") else None,
            contacts=[self._contact_from_doc(c) for c in doc.get("contacts", [])],
            forms=[str(item) for item in doc.get("forms", []) if item],
            primary_form=doc.get("primary_form") or None,
            created_at=_force_utc(doc.get("created_at")) or datetime.now(timezone.utc),
            updated_at=_force_utc(doc.get("updated_at")),
            score=doc.get("score", 0),
            random_index=doc.get("random_index", random.random())
        )

    def _media_to_doc(self, m: MediaItem) -> dict:
        return {
            "url": m.url, "media_type": m.media_type, "blur": m.blur,
            "file_hash": m.file_hash, "public_id": m.public_id, "resource_type": m.resource_type
        }

    def _media_from_doc(self, d: dict) -> MediaItem:
        return MediaItem(
            url=d["url"], media_type=d["media_type"], blur=d.get("blur", False),
            file_hash=d.get("file_hash", ""), public_id=d.get("public_id"), resource_type=d.get("resource_type")
        )

    def _contact_to_doc(self, c: Contact) -> dict:
        return {"type": c.type, "value": c.value, "is_private": c.is_private}

    def _contact_from_doc(self, d: dict) -> Contact:
        return Contact(type=d["type"], value=d["value"], is_private=d.get("is_private", True))


class MongoHandshakeRepository(HandshakeRepository):
    async def create(self, handshake: Handshake) -> None:
        await db_instance.handshakes_collection.insert_one(self._to_doc(handshake))

    async def update(self, handshake: Handshake) -> None:
        await db_instance.handshakes_collection.update_one({"id": handshake.id}, {"$set": self._to_doc(handshake)})

    async def delete(self, handshake_id: str) -> None:
        await db_instance.handshakes_collection.delete_one({"id": handshake_id})

    async def get_by_id(self, handshake_id: str) -> Optional[Handshake]:
        doc = await db_instance.handshakes_collection.find_one({"id": handshake_id})
        return self._to_domain(doc) if doc else None

    async def get_between_users(self, user_id_1: str, user_id_2: str) -> Optional[Handshake]:
        doc = await db_instance.handshakes_collection.find_one({
            "$or": [
                {"sender_id": user_id_1, "receiver_id": user_id_2},
                {"sender_id": user_id_2, "receiver_id": user_id_1}
            ]
        })
        return self._to_domain(doc) if doc else None

    async def get_for_user(self, user_id: str) -> List[Handshake]:
        cursor = db_instance.handshakes_collection.find({
            "$or": [
                {"sender_id": user_id, "sender_deleted": {"$ne": True}},
                {"receiver_id": user_id, "receiver_deleted": {"$ne": True}}
            ]
        }).sort("updated_at", -1)
        return [self._to_domain(doc) async for doc in cursor]

    async def get_interacted_user_ids(self, user_id: str) -> List[str]:
        cursor = db_instance.handshakes_collection.find({
            "$or": [
                {"sender_id": user_id, "sender_deleted": {"$ne": True}},
                {"receiver_id": user_id, "receiver_deleted": {"$ne": True}}
            ]
        })
        interacted = set()
        async for doc in cursor:
            if doc["sender_id"] == user_id:
                interacted.add(doc["receiver_id"])
            else:
                interacted.add(doc["sender_id"])
        return list(interacted)

    async def delete_for_user(self, user_id: str, session: Any = None) -> None:
        await db_instance.handshakes_collection.delete_many(
            {"$or": [{"sender_id": user_id}, {"receiver_id": user_id}]},
            session=session
        )

    def _to_doc(self, h: Handshake) -> dict:
        return {
            "id": h.id, "sender_id": h.sender_id, "receiver_id": h.receiver_id,
            "handshake_type": h.handshake_type, "status": h.status,
            "offered_contact": h.offered_contact, "returned_contact": h.returned_contact,
            "message": h.message,
            "sender_deleted": h.sender_deleted, "receiver_deleted": h.receiver_deleted,
            "is_read": h.is_read,
            "created_at": h.created_at, "updated_at": h.updated_at
        }

    def _to_domain(self, doc: dict) -> Handshake:
        return Handshake(
            id=doc["id"], sender_id=doc["sender_id"], receiver_id=doc["receiver_id"],
            handshake_type=doc["handshake_type"], status=doc["status"],
            offered_contact=doc.get("offered_contact"), returned_contact=doc.get("returned_contact"),
            message=doc.get("message"),
            sender_deleted=doc.get("sender_deleted", False), receiver_deleted=doc.get("receiver_deleted", False),
            is_read=doc.get("is_read", False),
            created_at=_force_utc(doc["created_at"]), updated_at=_force_utc(doc.get("updated_at"))
        )


class MongoTransactionManager(TransactionManager):
    async def execute_in_transaction(self, callback: Any) -> Any:
        async with await db_instance.client.start_session() as session:
            return await session.with_transaction(callback, read_preference=ReadPreference.PRIMARY)


class MongoChainRepository(ChainRepository):
    async def get_recent_anchors(self, user_id: str) -> List[str]:
        doc = await db_instance.chains_collection.find_one({"user_id": user_id})
        return doc.get("anchors", []) if doc else []

    async def push_anchor(self, user_id: str, anchor: str, window_size: int = 5, session: Any = None) -> None:
        await db_instance.chains_collection.update_one(
            {"user_id": user_id},
            {"$push": {
                "anchors": {
                    "$each": [anchor],
                    "$slice": -window_size
                }
            }},
            upsert=True,
            session=session
        )

    async def delete_for_user(self, user_id: str, session: Any = None) -> None:
        await db_instance.chains_collection.delete_one({"user_id": user_id}, session=session)


class MongoPushRepository:
    async def get_preferences(self, user_id: str) -> PushPreferences:
        doc = await db_instance.push_preferences_collection.find_one({"_id": user_id})
        if not doc:
            return PushPreferences()
        return PushPreferences(
            enabled=bool(doc.get("enabled", True)),
            share=bool(doc.get("share", True)),
            exchange=bool(doc.get("exchange", True)),
            demand=bool(doc.get("demand", True)),
            lang=doc.get("lang") or "en",
        )

    async def save_preferences(self, user_id: str, prefs: PushPreferences) -> None:
        await db_instance.push_preferences_collection.replace_one(
            {"_id": user_id},
            {
                "_id": user_id,
                "enabled": prefs.enabled,
                "share": prefs.share,
                "exchange": prefs.exchange,
                "demand": prefs.demand,
                "lang": prefs.lang,
            },
            upsert=True,
        )

    async def upsert_subscription(self, sub: PushSubscription) -> None:
        now = datetime.now(timezone.utc)
        doc = {
            "user_id": sub.user_id,
            "platform": sub.platform,
            "transport": sub.transport,
            "endpoint": sub.endpoint,
            "p256dh": sub.p256dh,
            "auth": sub.auth,
            "token": sub.token,
            "open_path": sub.open_path,
            "origin": sub.origin,
            "lang": sub.lang,
            "updated_at": now,
        }
        filt = {"endpoint": sub.endpoint} if sub.transport == "webpush" else {"token": sub.token}
        try:
            await db_instance.push_subscriptions_collection.replace_one(filt, doc, upsert=True)
        except DuplicateKeyError:
            await db_instance.push_subscriptions_collection.replace_one(filt, doc, upsert=False)
        count = await db_instance.push_subscriptions_collection.count_documents({"user_id": sub.user_id})
        extra = count - 10
        if extra > 0:
            cursor = db_instance.push_subscriptions_collection.find({"user_id": sub.user_id}).sort("updated_at", 1).limit(extra)
            async for old in cursor:
                await db_instance.push_subscriptions_collection.delete_one({"_id": old["_id"]})

    async def delete_subscription(self, user_id: str, *, endpoint: str = "", token: str = "") -> None:
        query = {"user_id": user_id}
        if endpoint:
            query["endpoint"] = endpoint
        elif token:
            query["token"] = token
        else:
            return
        await db_instance.push_subscriptions_collection.delete_one(query)

    async def list_subscriptions(self, user_id: str) -> List[PushSubscription]:
        cursor = db_instance.push_subscriptions_collection.find({"user_id": user_id})
        found = []
        async for doc in cursor:
            found.append(PushSubscription(
                user_id=doc["user_id"],
                platform=doc.get("platform") or "web",
                transport=doc.get("transport") or "webpush",
                endpoint=doc.get("endpoint") or "",
                p256dh=doc.get("p256dh") or "",
                auth=doc.get("auth") or "",
                token=doc.get("token") or "",
                open_path=doc.get("open_path") or "/netlazy/inbox",
                origin=doc.get("origin") or "",
                lang=doc.get("lang") or "en",
            ))
        return found

    async def delete_user(self, user_id: str) -> None:
        await db_instance.push_subscriptions_collection.delete_many({"user_id": user_id})
        await db_instance.push_preferences_collection.delete_one({"_id": user_id})

    async def get_vapid_pem(self) -> Optional[str]:
        doc = await db_instance.push_keys_collection.find_one({"_id": "vapid"})
        if not doc:
            return None
        return doc.get("private_pem") or None

    async def save_vapid_pem(self, pem: str) -> str:
        doc = await db_instance.push_keys_collection.find_one_and_update(
            {"_id": "vapid"},
            {"$setOnInsert": {"private_pem": pem}},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return doc["private_pem"]