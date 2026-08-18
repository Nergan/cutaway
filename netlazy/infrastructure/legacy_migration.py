"""
LEGACY MIGRATION ADAPTERS — TEMPORARY.
DELETE-AFTER: 2026-09-17
"""
import hashlib
from typing import Optional, Any
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from cryptography.exceptions import InvalidSignature

from netlazy.domain.legacy import LegacyCryptoPort, LegacyUserLookupPort, LegacyUserRecord
from netlazy.domain.repository import InvalidPublicKeyError, SignatureVerificationError
from netlazy.database import db_instance


class LegacyCryptographyAdapter(LegacyCryptoPort):
    def derive_legacy_user_id(self, public_key_pem: str) -> str:
        try:
            key = load_pem_public_key(public_key_pem.encode('utf-8'))
            der_bytes = key.public_bytes(
                encoding=serialization.Encoding.DER,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            )
            return hashlib.sha256(der_bytes).hexdigest()
        except Exception as e:
            raise InvalidPublicKeyError("Invalid RSA key format") from e

    def verify_legacy_signature(self, public_key_pem: str, payload: bytes, signature: bytes) -> None:
        try:
            public_key = load_pem_public_key(public_key_pem.encode('utf-8'))
            public_key.verify(
                signature,
                payload,
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.AUTO
                ),
                hashes.SHA256()
            )
        except InvalidSignature as e:
            raise SignatureVerificationError("Legacy signature mismatch") from e
        except Exception as e:
            raise SignatureVerificationError("Malformed legacy signature or key") from e


class MongoLegacyUserLookup(LegacyUserLookupPort):
    async def get_legacy_user(self, user_id: str) -> Optional[LegacyUserRecord]:
        doc = await db_instance.users_collection.find_one({
            "user_id": user_id,
            "public_key": {"$exists": True}  # Old schema
        })
        if not doc:
            return None
        return LegacyUserRecord(
            user_id=doc["user_id"],
            public_key_pem=doc["public_key"],
            known_ips=doc.get("known_ips", []),
            known_fingerprints=doc.get("known_fingerprints", [])
        )

    async def delete_legacy_user(self, user_id: str, session: Any = None) -> None:
        await db_instance.users_collection.delete_one({"user_id": user_id}, session=session)