import time
from datetime import datetime, timezone
from typing import Tuple

from netlazy.domain.models import User, UserAlreadyExistsError
from netlazy.domain.repository import (
    ChainRepository, NonceRepository, UserRepository, ProfileRepository, HandshakeRepository, HybridCryptoPort,
    TransactionManager, SignatureVerificationError, HashChainDesyncError
)
from netlazy.domain.chain import compute_genesis_anchor, compute_next_anchor, build_identity_payload

TIMESTAMP_TOLERANCE_SECONDS = 120

class AuthenticationError(Exception):
    pass

class AuthService:
    def __init__(
        self, 
        user_repo: UserRepository, 
        chain_repo: ChainRepository,
        nonce_repo: NonceRepository, 
        crypto_port: HybridCryptoPort, 
        transaction_manager: TransactionManager
    ):
        self._user_repo = user_repo
        self._chain_repo = chain_repo
        self._nonce_repo = nonce_repo
        self._crypto_port = crypto_port
        self._transaction_manager = transaction_manager

    async def register_user(self, ed25519_pem: str, mldsa_hex: str, ip: str = None, fingerprint: str = None) -> Tuple[User, str]:
        user_id = self._crypto_port.derive_user_id(ed25519_pem, mldsa_hex)

        user = User(
            user_id=user_id,
            ed25519_public_pem=ed25519_pem,
            mldsa_public_hex=mldsa_hex,
            created_at=datetime.now(timezone.utc),
            known_ips=[ip] if ip else [],
            known_fingerprints=[fingerprint] if fingerprint else []
        )
        await self._user_repo.create(user)
        
        genesis_anchor = compute_genesis_anchor(user_id)
        await self._chain_repo.push_anchor(user_id, genesis_anchor)
        
        return user, genesis_anchor

    async def rotate_key(
        self,
        old_user_id: str,
        new_ed25519_pem: str,
        new_mldsa_hex: str,
        profile_repo: ProfileRepository,
        handshake_repo: HandshakeRepository
    ) -> Tuple[str, str]:
        new_user_id = self._crypto_port.derive_user_id(new_ed25519_pem, new_mldsa_hex)

        async def _transaction_callback(session):
            existing_user = await self._user_repo.get_by_id(new_user_id, session=session)
            if existing_user:
                raise UserAlreadyExistsError("New public keys already registered")

            old_user = await self._user_repo.get_by_id(old_user_id, session=session)
            known_ips = old_user.known_ips if old_user else []
            known_fingerprints = old_user.known_fingerprints if old_user else []
            score = old_user.risk_score if old_user else 0.0

            new_user = User(
                user_id=new_user_id,
                ed25519_public_pem=new_ed25519_pem,
                mldsa_public_hex=new_mldsa_hex,
                created_at=datetime.now(timezone.utc),
                known_ips=known_ips,
                known_fingerprints=known_fingerprints,
                risk_score=score
            )
            await self._user_repo.create(new_user, session=session)

            old_profile = await profile_repo.get_by_user_id(old_user_id, session=session)
            if old_profile:
                old_profile.user_id = new_user_id
                old_profile.updated_at = datetime.now(timezone.utc)
                await profile_repo.upsert(old_profile, session=session)
                await profile_repo.delete(old_user_id, session=session)

            await handshake_repo.delete_for_user(old_user_id, session=session)
            await self._nonce_repo.delete_for_user(old_user_id, session=session)
            await self._chain_repo.delete_for_user(old_user_id, session=session)
            await self._user_repo.delete(old_user_id, session=session)
            
            # Restart the hash chain for the new identity
            genesis_anchor = compute_genesis_anchor(new_user_id)
            await self._chain_repo.push_anchor(new_user_id, genesis_anchor, session=session)

            return new_user_id, genesis_anchor

        return await self._transaction_manager.execute_in_transaction(_transaction_callback)

    async def authenticate_identity(
        self, user_id: str, timestamp: int, nonce: str, body_hash: str, method: str, path: str, ed_sig: bytes, pq_sig: bytes
    ) -> str:
        """Lightweight non-mutating check used to resync clients with the current chain head."""
        user = await self._validate_basics(user_id, timestamp)
        payload = build_identity_payload(method, path, timestamp, nonce, body_hash)
        
        self._crypto_port.verify_hybrid_signature(
            user.ed25519_public_pem, user.mldsa_public_hex, payload, ed_sig, pq_sig
        )

        is_fresh = await self._nonce_repo.insert_if_not_exists(user_id, nonce)
        if not is_fresh:
            raise AuthenticationError("Nonce already used")
        
        anchors = await self._chain_repo.get_recent_anchors(user_id)
        if not anchors:
            raise AuthenticationError("Chain broken")
        return anchors[-1]

    async def authenticate_request(
        self,
        user_id: str,
        method: str,
        path: str,
        timestamp: int,
        nonce: str,
        body_hash: str,
        prev_anchor: str,
        canonical_payload: bytes,
        ed25519_signature: bytes,
        mldsa_signature: bytes,
    ) -> Tuple[User, str]:
        """Stateful/mutating request check that enforces and advances the hash chain."""
        user = await self._validate_basics(user_id, timestamp)

        # 1. Verify Hybrid Signature
        try:
            self._crypto_port.verify_hybrid_signature(
                user.ed25519_public_pem, user.mldsa_public_hex, canonical_payload, ed25519_signature, mldsa_signature
            )
        except SignatureVerificationError:
            raise AuthenticationError("Hybrid signature verification failed")

        # 2. Consume Nonce post-signature
        is_fresh = await self._nonce_repo.insert_if_not_exists(user_id, nonce)
        if not is_fresh:
            raise AuthenticationError("Nonce already used")

        # 3. Trace Continuity
        recent_anchors = await self._chain_repo.get_recent_anchors(user_id)
        if prev_anchor not in recent_anchors:
            raise HashChainDesyncError("Execution trace broken or outdated")

        # 3. Advance the Ratchet
        next_anchor = compute_next_anchor(prev_anchor, user_id, method, path, body_hash, nonce, timestamp)
        await self._chain_repo.push_anchor(user_id, next_anchor)

        return user, next_anchor

    async def _validate_basics(self, user_id: str, timestamp: int) -> User:
        current_time = int(time.time())
        if abs(current_time - timestamp) > TIMESTAMP_TOLERANCE_SECONDS:
            raise AuthenticationError("Timestamp out of tolerance window")

        user = await self._user_repo.get_by_id(user_id)
        if not user:
            raise AuthenticationError("Unknown user")
            
        if user.is_banned:
            raise AuthenticationError("User is banned")
            
        return user

    async def delete_user(self, user_id: str) -> None:
        await self._user_repo.delete(user_id)
        await self._nonce_repo.delete_for_user(user_id)
        await self._chain_repo.delete_for_user(user_id)