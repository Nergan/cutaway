import logging
from datetime import date, datetime, timezone

from netlazy.domain.legacy import LegacyCryptoPort, LegacyUserLookupPort, MIGRATION_DEADLINE, LegacyMigrationExpiredError
from netlazy.domain.models import User, UserAlreadyExistsError
from netlazy.domain.chain import compute_genesis_anchor, build_migration_payload
from netlazy.domain.repository import (
    ChainRepository, NonceRepository, ProfileRepository, HandshakeRepository,
    UserRepository, HybridCryptoPort, TransactionManager, InvalidPublicKeyError
)

class MigrationService:
    def __init__(
        self,
        legacy_lookup: LegacyUserLookupPort,
        legacy_crypto: LegacyCryptoPort,
        user_repo: UserRepository,
        chain_repo: ChainRepository,
        profile_repo: ProfileRepository,
        handshake_repo: HandshakeRepository,
        nonce_repo: NonceRepository,
        hybrid_crypto: HybridCryptoPort,
        transaction_manager: TransactionManager
    ):
        self._legacy_lookup = legacy_lookup
        self._legacy_crypto = legacy_crypto
        self._user_repo = user_repo
        self._chain_repo = chain_repo
        self._profile_repo = profile_repo
        self._handshake_repo = handshake_repo
        self._nonce_repo = nonce_repo
        self._hybrid_crypto = hybrid_crypto
        self._transaction_manager = transaction_manager

    async def migrate_user(
        self,
        legacy_public_pem: str,
        new_ed25519_pem: str,
        new_mldsa_hex: str,
        timestamp: int,
        signature: bytes
    ) -> str:
        """Proves ownership of the old RSA key and transfers data to the new Hybrid ID."""
        if date.today() > MIGRATION_DEADLINE:
            raise LegacyMigrationExpiredError("RSA migration period has ended.")

        legacy_user_id = self._legacy_crypto.derive_legacy_user_id(legacy_public_pem)
        legacy_user = await self._legacy_lookup.get_legacy_user(legacy_user_id)
        
        if not legacy_user:
            raise ValueError("Legacy user not found or already migrated.")

        # Authorize the upgrade using the OLD key
        payload = build_migration_payload(new_ed25519_pem.encode('utf-8'), new_mldsa_hex.encode('utf-8'), timestamp)
        self._legacy_crypto.verify_legacy_signature(legacy_public_pem, payload, signature)

        new_user_id = self._hybrid_crypto.derive_user_id(new_ed25519_pem, new_mldsa_hex)

        async def _transaction_callback(session):
            existing_user = await self._user_repo.get_by_id(new_user_id, session=session)
            if existing_user:
                raise UserAlreadyExistsError("New public keys already registered")

            new_user = User(
                user_id=new_user_id,
                ed25519_public_pem=new_ed25519_pem,
                mldsa_public_hex=new_mldsa_hex,
                created_at=datetime.now(timezone.utc),
                known_ips=legacy_user.known_ips,
                known_fingerprints=legacy_user.known_fingerprints
            )
            await self._user_repo.create(new_user, session=session)

            # Re-bind Profile
            old_profile = await self._profile_repo.get_by_user_id(legacy_user_id, session=session)
            if old_profile:
                old_profile.user_id = new_user_id
                old_profile.updated_at = datetime.now(timezone.utc)
                await self._profile_repo.upsert(old_profile, session=session)
                await self._profile_repo.delete(legacy_user_id, session=session)

            # Initialize new Chain state
            await self._chain_repo.delete_for_user(legacy_user_id, session=session)
            genesis_anchor = compute_genesis_anchor(new_user_id)
            await self._chain_repo.push_anchor(new_user_id, genesis_anchor, session=session)

            # Scrub old legacy artifacts
            await self._nonce_repo.delete_for_user(legacy_user_id, session=session)
            await self._legacy_lookup.delete_legacy_user(legacy_user_id, session=session)

            return new_user_id

        logging.info(f"Migrating RSA user {legacy_user_id} -> Hybrid PQ {new_user_id}")
        return await self._transaction_manager.execute_in_transaction(_transaction_callback)