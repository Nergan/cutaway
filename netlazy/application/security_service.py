import asyncio
import hashlib
import uuid
import time
from typing import Optional
from fastapi import BackgroundTasks

from netlazy.domain.models import PoWChallenge
from netlazy.domain.repository import SecurityRepository, UserRepository
from netlazy.domain.risk import RiskThresholds, score_request_rate, score_geo_velocity, score_entropy, shannon_entropy_ratio

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
                    await self._security_repo.remove_bans(
                        ips=user.known_ips + ([ip] if ip else []),
                        fingerprints=user.known_fingerprints + ([fingerprint] if fingerprint else []),
                        user_id=user.user_id
                    )
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

    def dispatch_risk_evaluation(self, background_tasks: BackgroundTasks, user_id: str, ip: str, payload: bytes):
        background_tasks.add_task(self._evaluate_risk, user_id, ip, payload, int(time.time()))

    async def _evaluate_risk(self, user_id: str, ip: str, payload: bytes, current_time: int) -> None:
        user = await self._user_repo.get_by_id(user_id)
        if not user or user.is_banned:
            return

        total_penalty = 0.0

        if payload:
            ratio = await asyncio.to_thread(shannon_entropy_ratio, payload)
            total_penalty += score_entropy(ratio, self._thresholds)

        last_ip, last_time = await self._user_repo.get_last_activity(user_id)
        if last_ip and ip != last_ip and last_time:
            elapsed_hours = (current_time - last_time) / 3600.0 
            total_penalty += score_geo_velocity(1000.0, elapsed_hours, self._thresholds)

        if total_penalty > 0:
            new_score = await self._user_repo.increment_risk_score(user_id, total_penalty)
            if new_score >= self._thresholds.ban_threshold:
                await self.cascade_ban_user(user_id)