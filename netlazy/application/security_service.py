import asyncio
import hashlib
import uuid
import time
from typing import Optional

from netlazy.domain.models import PoWChallenge
from netlazy.domain.repository import SecurityRepository, UserRepository
from netlazy.domain.risk import RiskThresholds, score_entropy, shannon_entropy_ratio

class BannedError(Exception):
    pass

class ProofOfWorkError(Exception):
    pass

class SecurityService:
    def __init__(
        self, 
        security_repo: SecurityRepository, 
        user_repo: UserRepository, 
        difficulty: int,
        risk_thresholds: RiskThresholds = RiskThresholds()
    ):
        self._security_repo = security_repo
        self._user_repo = user_repo
        self._difficulty = difficulty
        self._thresholds = risk_thresholds

    async def generate_challenge(self) -> dict:
        challenge = PoWChallenge(id=uuid.uuid4().hex, difficulty=self._difficulty)
        await self._security_repo.create_challenge(challenge)
        return {"challenge_id": challenge.id, "difficulty": challenge.difficulty}

    async def verify_pow(self, challenge_id: str, nonce: str) -> None:
        challenge = await self._security_repo.consume_challenge(challenge_id)
        if not challenge:
            raise ProofOfWorkError("Challenge expired, invalid, or already consumed.")
        
        target_prefix = "0" * challenge.difficulty
        payload = (challenge.id + nonce).encode('utf-8')
        result_hash = hashlib.sha256(payload).hexdigest()
        
        if not result_hash.startswith(target_prefix):
            raise ProofOfWorkError("Invalid Proof of Work solution.")

    async def verify_not_banned(self, ip: str, fingerprint: str, user_id: Optional[str] = None) -> None:
        if await self._security_repo.is_banned(ip, fingerprint, user_id):
            if user_id:
                user = await self._user_repo.get_by_id(user_id)
                if user and not user.is_banned:
                    return
            raise BannedError("Access denied by security policy.")

    async def cascade_ban_user(self, user_id: str) -> None:
        user = await self._user_repo.get_by_id(user_id)
        if not user:
            raise ValueError("User not found")
            
        await self._security_repo.apply_bans(
            ips=user.known_ips,
            fingerprints=user.known_fingerprints,
            user_id=user.user_id
        )

    async def evaluate_risk(self, user_id: str, ip: str, payload: bytes, current_time: int) -> None:
        user = await self._user_repo.get_by_id(user_id)
        if not user or user.is_banned:
            return

        total_penalty = 0.0

        if payload and len(payload) >= 256:
            sampled_payload = payload[:8192]
            ratio = await asyncio.to_thread(shannon_entropy_ratio, sampled_payload)
            if ratio < 0.05:
                total_penalty += score_entropy(ratio, self._thresholds)

        if total_penalty > 0:
            new_score = await self._user_repo.increment_risk_score(user_id, total_penalty)
            if new_score >= self._thresholds.ban_threshold:
                await self.cascade_ban_user(user_id)