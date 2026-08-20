import pytest
import time
import os
import hashlib
from unittest.mock import AsyncMock

from netlazy.application.security_service import SecurityService, ProofOfWorkError, BannedError
from netlazy.domain.models import PoWChallenge, User
from netlazy.domain.risk import (
    RiskThresholds,
    score_entropy,
    shannon_entropy_ratio
)


@pytest.fixture
def security_deps():
    return {
        "security_repo": AsyncMock(),
        "user_repo": AsyncMock(),
        "difficulty": 2,
        "risk_thresholds": RiskThresholds()
    }


@pytest.fixture
def security_service(security_deps):
    return SecurityService(**security_deps)


@pytest.mark.asyncio
async def test_verify_pow_success(security_service, security_deps):
    challenge_id = "challenge_101"
    security_deps["security_repo"].consume_challenge.return_value = PoWChallenge(id=challenge_id, difficulty=2)

    prefix = "00"
    nonce = 0
    while True:
        payload = (challenge_id + str(nonce)).encode("utf-8")
        if hashlib.sha256(payload).hexdigest().startswith(prefix):
            break
        nonce += 1

    await security_service.verify_pow(challenge_id, str(nonce))
    security_deps["security_repo"].consume_challenge.assert_called_with(challenge_id)


@pytest.mark.asyncio
async def test_verify_pow_failure(security_service, security_deps):
    security_deps["security_repo"].consume_challenge.return_value = PoWChallenge(id="ch1", difficulty=4)
    with pytest.raises(ProofOfWorkError):
        await security_service.verify_pow("ch1", "invalid_nonce")


@pytest.mark.asyncio
async def test_verify_not_banned(security_service, security_deps):
    security_deps["security_repo"].is_banned.return_value = True

    with pytest.raises(BannedError):
        await security_service.verify_not_banned("192.168.1.1", "fp_123")


def test_entropy_scoring():
    zero_entropy = b"A" * 128
    assert shannon_entropy_ratio(zero_entropy) == 0.0
    assert score_entropy(shannon_entropy_ratio(zero_entropy), RiskThresholds()) > 0.0

    random_bytes = os.urandom(256)
    assert shannon_entropy_ratio(random_bytes) > 0.8
    assert score_entropy(shannon_entropy_ratio(random_bytes), RiskThresholds()) == 0.0


@pytest.mark.asyncio
async def test_risk_evaluation_cascade_ban_on_low_entropy(security_service, security_deps):
    user = User("u1", "ed_pem", "mldsa_hex", None)
    security_deps["user_repo"].get_by_id.return_value = user
    security_deps["user_repo"].increment_risk_score.return_value = 150.0

    low_entropy_payload = b"A" * 300
    await security_service.evaluate_risk("u1", "2.2.2.2", low_entropy_payload, int(time.time()))

    security_deps["security_repo"].apply_bans.assert_called_once()