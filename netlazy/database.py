import asyncio
import logging
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ASCENDING
from pymongo.errors import OperationFailure
from netlazy.config import settings

class DatabaseUnavailableError(AttributeError):
    pass

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
    chains_collection = None

    def __getattribute__(self, name):
        val = super().__getattribute__(name)
        if val is None and (name.endswith('_collection') or name in ('client', 'db')):
            raise DatabaseUnavailableError(f"Database property '{name}' is not initialized")
        return val

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

    max_retries = 5
    for attempt in range(max_retries):
        try:
            client = AsyncIOMotorClient(
                settings.mongodb_uri, 
                readPreference="primaryPreferred", 
                serverSelectionTimeoutMS=10000,
                **kwargs
            )
            await client.admin.command('ping')
            db_instance.client = client
            break
        except Exception as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                logging.warning(f"MongoDB connection attempt {attempt + 1} failed: {e}. Retrying in {wait_time}s...")
                await asyncio.sleep(wait_time)
            else:
                logging.critical(f"MongoDB connection failed definitively during startup: {e}")
                raise DatabaseUnavailableError("Failed to initialize database connection") from e

    db_instance.db = db_instance.client.netlazy

    db_instance.users_collection = db_instance.db.users
    db_instance.used_nonces_collection = db_instance.db.used_nonces
    db_instance.tags_collection = db_instance.db.tags
    db_instance.profiles_collection = db_instance.db.profiles
    db_instance.handshakes_collection = db_instance.db.handshakes
    db_instance.challenges_collection = db_instance.db.challenges
    db_instance.bans_collection = db_instance.db.bans
    db_instance.logs_collection = db_instance.db.logs
    db_instance.chains_collection = db_instance.db.chains

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
            ("created_at", {}),
            ("random_index", {})
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
        ],
        db_instance.chains_collection: [
            ("user_id", {"unique": True})
        ]
    }

    for collection, indexes in definitions.items():
        await sync_collection_indexes(collection, indexes)

    logging.info("Connected to netlazy MongoDB successfully.")

async def close_mongo_connection():
    if getattr(db_instance, 'client', None):
        db_instance.client.close()