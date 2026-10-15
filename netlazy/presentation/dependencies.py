import base64
import binascii
import hashlib
import logging
import time
from typing import Optional
from fastapi import Request, Header, HTTPException, BackgroundTasks
from starlette.requests import ClientDisconnect

from netlazy.application.auth_service import AuthService, AuthenticationError
from netlazy.application.profile_service import ProfileService
from netlazy.application.tag_service import TagService
from netlazy.application.feed_service import FeedService
from netlazy.application.inbox_service import InboxService
from netlazy.application.push_service import PushService
from netlazy.application.security_service import SecurityService, BannedError, ProofOfWorkError
from netlazy.config import settings
from netlazy.database import DatabaseUnavailableError
from netlazy.domain.models import User
from netlazy.domain.chain import build_reader_payload, build_request_payload
from netlazy.domain.risk import RiskThresholds
from netlazy.domain.repository import RiskEventDispatcherPort, HashChainDesyncError
from netlazy.infrastructure.cloudinary_adapter import CloudinaryMediaStorage
from netlazy.infrastructure.crypto_adapter import CryptographyHybridAdapter
from netlazy.infrastructure.media_processor import FFmpegMediaProcessor
from netlazy.infrastructure.yaml_loader import YamlTagLoader
from netlazy.infrastructure.mongo_repo import (
    MongoChainRepository,
    MongoHandshakeRepository,
    MongoNonceRepository,
    MongoProfileRepository,
    MongoSecurityRepository,
    MongoTagRepository,
    MongoUserRepository,
    MongoPushRepository,
    MongoTransactionManager,
)

def create_auth_error() -> HTTPException:
    return HTTPException(status_code=401, detail="Invalid authentication credentials")

def create_banned_error() -> HTTPException:
    return HTTPException(status_code=403, detail="banned")

def create_pow_error() -> HTTPException:
    return HTTPException(status_code=400, detail="Invalid or missing Proof of Work")

user_repo = MongoUserRepository()
chain_repo = MongoChainRepository()
nonce_repo = MongoNonceRepository()
tag_repo = MongoTagRepository()
profile_repo = MongoProfileRepository()
handshake_repo = MongoHandshakeRepository()
push_repo = MongoPushRepository()
security_repo = MongoSecurityRepository()
media_storage = CloudinaryMediaStorage()

hybrid_crypto = CryptographyHybridAdapter()
media_processor = FFmpegMediaProcessor()
tag_loader = YamlTagLoader()
transaction_manager = MongoTransactionManager()

auth_service = AuthService(
    user_repo=user_repo,
    chain_repo=chain_repo,
    nonce_repo=nonce_repo, 
    crypto_port=hybrid_crypto, 
    transaction_manager=transaction_manager
)

tag_service = TagService(tag_repo=tag_repo, tag_loader=tag_loader)

profile_service = ProfileService(
    profile_repo=profile_repo,
    tag_repo=tag_repo,
    media_storage=media_storage,
    media_processor=media_processor,
    max_media_items=settings.max_media_items,
    max_bio_length=settings.max_bio_length,
    max_upload_bytes=settings.max_upload_bytes,
    image_max_dimension=settings.image_max_dimension,
    audio_bitrate=settings.audio_bitrate,
)

feed_service = FeedService(
    profile_repo=profile_repo,
    handshake_repo=handshake_repo
)

inbox_service = InboxService(
    handshake_repo=handshake_repo,
    profile_repo=profile_repo,
    user_repo=user_repo
)

push_service = PushService(repo=push_repo)

security_service = SecurityService(
    security_repo=security_repo,
    user_repo=user_repo,
    difficulty=settings.pow_difficulty,
    risk_thresholds=RiskThresholds()
)


class FastAPIBackgroundRiskDispatcher(RiskEventDispatcherPort):
    def __init__(self, background_tasks: BackgroundTasks, security_service: SecurityService):
        self._background_tasks = background_tasks
        self._security_service = security_service

    def dispatch_risk_evaluation(self, user_id: str, ip: str, payload: bytes, timestamp: int) -> None:
        self._background_tasks.add_task(self._security_service.evaluate_risk, user_id, ip, payload, timestamp)


def _get_client_footprint(request: Request) -> tuple:
    direct_peer = request.client.host if request.client else "127.0.0.1"
    trusted_proxies = {ip.strip() for ip in settings.trusted_proxy_ips.split(",") if ip.strip()}
    
    if direct_peer in trusted_proxies:
        forwarded = request.headers.get("X-Forwarded-For")
        real_ip = request.headers.get("X-Real-IP")
        if forwarded:
            ip = forwarded.split(",")[0].strip()
        elif real_ip:
            ip = real_ip.strip()
        else:
            ip = direct_peer
    else:
        ip = direct_peer

    fingerprint = request.headers.get("X-Fingerprint")
    if fingerprint in ("unknown", "", None):
        fingerprint = None
    return ip, fingerprint


def _normalize_path(path: str) -> str:
    cleaned = "/" + path.strip("/").split("?")[0]
    if cleaned.startswith("/netlazy/"):
        cleaned = cleaned[len("/netlazy"):]
    return cleaned


async def _presented_user(
    request: Request,
    background_tasks: BackgroundTasks,
    *,
    x_user_id: Optional[str],
    x_timestamp: Optional[int],
    x_nonce: Optional[str],
    x_body_hash: Optional[str],
    x_chain_anchor: Optional[str],
    x_signature_ed25519: Optional[str],
    x_signature_mldsa: Optional[str],
    x_signed_path: Optional[str],
    advance_chain: bool,
) -> User:
    required_headers = [
        x_user_id, x_timestamp, x_nonce, x_body_hash,
        x_signature_ed25519, x_signature_mldsa, x_signed_path,
    ]
    if advance_chain:
        required_headers.append(x_chain_anchor)
    if any(h is None for h in required_headers):
        raise create_auth_error()

    norm_signed = _normalize_path(x_signed_path)
    norm_req = _normalize_path(request.url.path)
    if norm_signed != norm_req:
        raise create_auth_error()

    ip, fingerprint = _get_client_footprint(request)

    try:
        await security_service.verify_not_banned(ip, fingerprint, x_user_id)
    except DatabaseUnavailableError:
        raise
    except BannedError:
        raise create_banned_error()

    try:
        body_bytes = await request.body()
        if len(body_bytes) > settings.max_upload_bytes:
            raise HTTPException(status_code=413, detail="Payload Too Large")
    except ClientDisconnect:
        raise HTTPException(status_code=400, detail="Client disconnected")

    request.state.body_bytes = body_bytes

    actual_body_hash = hashlib.sha256(body_bytes).hexdigest()
    if actual_body_hash != x_body_hash:
        raise create_auth_error()

    query_string = request.url.query
    if advance_chain:
        canonical_payload = build_request_payload(
            method=request.method,
            path=x_signed_path,
            query=query_string,
            timestamp=x_timestamp,
            nonce=x_nonce,
            body_hash=x_body_hash,
            prev_anchor=x_chain_anchor,
        )
    else:
        canonical_payload = build_reader_payload(
            method=request.method,
            path=x_signed_path,
            query=query_string,
            timestamp=x_timestamp,
            nonce=x_nonce,
            body_hash=x_body_hash,
        )

    try:
        ed_sig_bytes = base64.b64decode(x_signature_ed25519)
        mldsa_sig_bytes = base64.b64decode(x_signature_mldsa)
    except (binascii.Error, ValueError):
        raise create_auth_error()

    try:
        if advance_chain:
            user, next_anchor = await auth_service.authenticate_request(
                user_id=x_user_id,
                method=request.method,
                path=x_signed_path,
                timestamp=x_timestamp,
                nonce=x_nonce,
                body_hash=x_body_hash,
                prev_anchor=x_chain_anchor,
                canonical_payload=canonical_payload,
                ed25519_signature=ed_sig_bytes,
                mldsa_signature=mldsa_sig_bytes,
            )
        else:
            user = await auth_service.authenticate_reader(
                user_id=x_user_id,
                timestamp=x_timestamp,
                nonce=x_nonce,
                canonical_payload=canonical_payload,
                ed25519_signature=ed_sig_bytes,
                mldsa_signature=mldsa_sig_bytes,
            )
            next_anchor = None
    except DatabaseUnavailableError:
        raise
    except HashChainDesyncError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except AuthenticationError as e:
        if str(e) == "Unknown user":
            raise HTTPException(status_code=401, detail="Unknown user")
        raise create_auth_error()
    except Exception as e:
        logging.error(f"Unexpected error during signature verification: {e}")
        raise create_auth_error()

    if user.is_banned:
        raise create_banned_error()

    if next_anchor:
        request.state.next_anchor = next_anchor
        dispatcher = FastAPIBackgroundRiskDispatcher(background_tasks, security_service)
        dispatcher.dispatch_risk_evaluation(x_user_id, ip, body_bytes, int(time.time()))
        background_tasks.add_task(user_repo.log_footprint, x_user_id, ip, fingerprint)

    return user


async def verify_request_signature(
    request: Request,
    background_tasks: BackgroundTasks,
    x_user_id: str = Header(None),
    x_timestamp: int = Header(None),
    x_nonce: str = Header(None),
    x_body_hash: str = Header(None),
    x_chain_anchor: str = Header(None),
    x_signature_ed25519: str = Header(None),
    x_signature_mldsa: str = Header(None),
    x_signed_path: str = Header(None),
) -> User:
    return await _presented_user(
        request,
        background_tasks,
        x_user_id=x_user_id,
        x_timestamp=x_timestamp,
        x_nonce=x_nonce,
        x_body_hash=x_body_hash,
        x_chain_anchor=x_chain_anchor,
        x_signature_ed25519=x_signature_ed25519,
        x_signature_mldsa=x_signature_mldsa,
        x_signed_path=x_signed_path,
        advance_chain=True,
    )


async def verify_reader(
    request: Request,
    background_tasks: BackgroundTasks,
    x_user_id: str = Header(None),
    x_timestamp: int = Header(None),
    x_nonce: str = Header(None),
    x_body_hash: str = Header(None),
    x_signature_ed25519: str = Header(None),
    x_signature_mldsa: str = Header(None),
    x_signed_path: str = Header(None),
) -> User:
    return await _presented_user(
        request,
        background_tasks,
        x_user_id=x_user_id,
        x_timestamp=x_timestamp,
        x_nonce=x_nonce,
        x_body_hash=x_body_hash,
        x_chain_anchor=None,
        x_signature_ed25519=x_signature_ed25519,
        x_signature_mldsa=x_signature_mldsa,
        x_signed_path=x_signed_path,
        advance_chain=False,
    )


def _header_int(value: Optional[str]) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except ValueError:
        return None


async def optional_user(
    request: Request,
    background_tasks: BackgroundTasks,
) -> Optional[User]:
    if not request.headers.get("x-user-id"):
        ip, fingerprint = _get_client_footprint(request)
        try:
            await security_service.verify_not_banned(ip, fingerprint)
        except BannedError:
            raise create_banned_error()
        return None
    return await _presented_user(
        request,
        background_tasks,
        x_user_id=request.headers.get("x-user-id"),
        x_timestamp=_header_int(request.headers.get("x-timestamp")),
        x_nonce=request.headers.get("x-nonce"),
        x_body_hash=request.headers.get("x-body-hash"),
        x_chain_anchor=None,
        x_signature_ed25519=request.headers.get("x-signature-ed25519"),
        x_signature_mldsa=request.headers.get("x-signature-mldsa"),
        x_signed_path=request.headers.get("x-signed-path"),
        advance_chain=False,
    )


async def verify_pow(
    request: Request,
    x_challenge_id: str = Header(None),
    x_pow_nonce: str = Header(None),
) -> None:
    if not x_challenge_id or not x_pow_nonce:
        raise create_pow_error()

    ip, fingerprint = _get_client_footprint(request)
    try:
        await security_service.verify_not_banned(ip, fingerprint)
        await security_service.verify_pow(x_challenge_id, x_pow_nonce)
    except DatabaseUnavailableError:
        raise
    except BannedError:
        raise create_banned_error()
    except ProofOfWorkError:
        raise create_pow_error()