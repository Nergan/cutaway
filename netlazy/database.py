import logging
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ASCENDING
from pymongo.errors import OperationFailure
from netlazy.config import settings

class Database:
    client: AsyncIOMotorClient = None
    db = None
    users_collection = None
    used_nonces_collection = None
    tags_collection = None
    profiles_collection = None
    handshakes_collection = None
    challenges_collection = None
    bans_collection = None
    logs_collection = None

db_instance = Database()

async def _safe_create_index(collection, keys, **kwargs):
    try:
        await collection.create_index(keys, **kwargs)
    except OperationFailure as e:
        if e.code in (85, 86):
            logging.warning(f"Index conflict detected on '{collection.name}'. Recreating index...")
            
            index_name = kwargs.get("name")
            if not index_name:
                if isinstance(keys, str):
                    index_name = f"{keys}_1"
                elif isinstance(keys, list):
                    index_name = "_".join([f"{k[0]}_{k[1]}" for k in keys])
            
            if index_name:
                try:
                    await collection.drop_index(index_name)
                except OperationFailure:
                    pass
            
            await collection.create_index(keys, **kwargs)
        else:
            raise

async def sync_collection_indexes(collection, expected_indexes):
    expected_names = {"_id_"}
    for keys, kwargs in expected_indexes:
        name = kwargs.get("name")
        if not name:
            if isinstance(keys, str):
                name = f"{keys}_1"
            elif isinstance(keys, list):
                name = "_".join([f"{k[0]}_{k[1]}" for k in keys])
        if name:
            expected_names.add(name)

    current_indexes = []
    try:
        async for idx in collection.list_indexes():
            current_indexes.append(idx["name"])
    except OperationFailure:
        pass

    for index_name in current_indexes:
        if index_name not in expected_names:
            logging.warning(f"Obsolete index '{index_name}' detected on '{collection.name}'. Dropping...")
            try:
                await collection.drop_index(index_name)
            except OperationFailure:
                pass

    for keys, kwargs in expected_indexes:
        await _safe_create_index(collection, keys, **kwargs)

async def connect_to_mongo():
    logging.info("Connecting to MongoDB for netlazy...")

    kwargs = {}
    if settings.mongo_tls:
        kwargs["tls"] = True
    if settings.mongo_tls_allow_invalid_certificates:
        kwargs["tlsAllowInvalidCertificates"] = True

    db_instance.client = AsyncIOMotorClient(settings.mongodb_uri, readPreference="primaryPreferred", **kwargs)
    db_instance.db = db_instance.client.netlazy

    db_instance.users_collection = db_instance.db.users
    db_instance.used_nonces_collection = db_instance.db.used_nonces
    db_instance.tags_collection = db_instance.db.tags
    db_instance.profiles_collection = db_instance.db.profiles
    db_instance.handshakes_collection = db_instance.db.handshakes
    db_instance.challenges_collection = db_instance.db.challenges
    db_instance.bans_collection = db_instance.db.bans
    db_instance.logs_collection = db_instance.db.logs

    definitions = {
        db_instance.users_collection: [
            ("user_id", {"unique": True})
        ],
        db_instance.used_nonces_collection: [
            ([("user_id", ASCENDING), ("nonce", ASCENDING)], {"unique": True}),
            ("created_at", {"expireAfterSeconds": 300})
        ],
        db_instance.tags_collection: [
            ("name", {"unique": True})
        ],
        db_instance.profiles_collection: [
            ("user_id", {"unique": True}),
            ("created_at", {})
        ],
        db_instance.handshakes_collection: [
            ("sender_id", {}),
            ("receiver_id", {})
        ],
        db_instance.challenges_collection: [
            ("created_at", {"expireAfterSeconds": 300})
        ],
        db_instance.bans_collection: [
            ([("type", ASCENDING), ("value", ASCENDING)], {"unique": True})
        ],
        db_instance.logs_collection: [
            ("timestamp", {"expireAfterSeconds": 30 * 24 * 60 * 60})
        ]
    }

    for collection, indexes in definitions.items():
        await sync_collection_indexes(collection, indexes)

    logging.info("Connected to netlazy MongoDB successfully.")

async def close_mongo_connection():
    if db_instance.client:
        db_instance.client.close()