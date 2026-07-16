import base64
import hashlib
import logging
from fastapi import Request, Header, HTTPException
from starlette.requests import ClientDisconnect
from netlazy.application.auth_service import AuthService, AuthenticationError
from netlazy.application.profile_service import ProfileService
from netlazy.application.tag_service import TagService
from netlazy.application.feed_service import FeedService
from netlazy.application.inbox_service import InboxService
from netlazy.application.security_service import SecurityService, BannedError, ProofOfWorkError
from netlazy.config import settings
from netlazy.domain.models import User
from netlazy.infrastructure.cloudinary_adapter import CloudinaryMediaStorage
from netlazy.infrastructure.mongo_repo import (
    MongoHandshakeRepository,
    MongoNonceRepository,
    MongoProfileRepository,
    MongoSecurityRepository,
    MongoTagRepository,
    MongoUserRepository,
)

AUTH_ERROR = HTTPException(status_code=401, detail="Invalid authentication credentials")
BANNED_ERROR = HTTPException(status_code=403, detail="banned")
POW_ERROR = HTTPException(status_code=400, detail="Invalid or missing Proof of Work")

user_repo = MongoUserRepository()
nonce_repo = MongoNonceRepository()
tag_repo = MongoTagRepository()
profile_repo = MongoProfileRepository()
handshake_repo = MongoHandshakeRepository()
security_repo = MongoSecurityRepository()
media_storage = CloudinaryMediaStorage()

auth_service = AuthService(user_repo=user_repo, nonce_repo=nonce_repo)

tag_service = TagService(tag_repo=tag_repo)

profile_service = ProfileService(
    profile_repo=profile_repo,
    tag_repo=tag_repo,
    media_storage=media_storage,
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

security_service = SecurityService(
    security_repo=security_repo,
    user_repo=user_repo,
    difficulty=settings.pow_difficulty
)


def _get_client_footprint(request: Request) -> tuple:
    ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else "127.0.0.1").split(",")[0].strip()
    fingerprint = request.headers.get("X-Fingerprint", "unknown")
    return ip, fingerprint


async def verify_request_signature(
    request: Request,
    x_user_id: str = Header(None),
    x_timestamp: int = Header(None),
    x_nonce: str = Header(None),
    x_signature: str = Header(None),
    x_bot_token: str = Header(None),
    x_telegram_id: int = Header(None),
) -> User:
    
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="Payload Too Large")

    # Bot Backdoor Check: Bypass RSA signature entirely if valid token & Telegram ID is present
    if settings.bot_api_token and x_bot_token == settings.bot_api_token:
        if not x_telegram_id:
            raise HTTPException(status_code=400, detail="Missing X-Telegram-Id for bot auth")
            
        user = await user_repo.get_by_telegram_id(x_telegram_id)
        if not user:
            raise AUTH_ERROR
            
        try:
            # We explicitly pass None for IP and Fingerprint so the bot's static Render IP 
            # doesn't trigger shared cascade bans across all Telegram users.
            await security_service.verify_not_banned(ip=None, fingerprint=None, user_id=user.user_id, telegram_id=x_telegram_id)
        except BannedError:
            raise BANNED_ERROR
            
        if user.is_banned:
            raise BANNED_ERROR
            
        return user

    # Standard Web/App Auth: Fallback to RSA-PSS signature verification
    if not all([x_user_id, x_timestamp, x_nonce, x_signature]):
        raise AUTH_ERROR

    ip, fingerprint = _get_client_footprint(request)
    
    try:
        await security_service.verify_not_banned(ip, fingerprint, x_user_id)
    except BannedError:
        raise BANNED_ERROR

    try:
        body_bytes = await request.body()
    except ClientDisconnect:
        raise HTTPException(status_code=400, detail="Client disconnected")

    body_hash = hashlib.sha256(body_bytes).hexdigest()
    query_string = request.url.query

    canonical_payload = (
        f"{request.method}\n{request.url.path}\n{query_string}\n"
        f"{x_timestamp}\n{x_nonce}\n{body_hash}"
    ).encode('utf-8')

    try:
        signature_bytes = base64.b64decode(x_signature)
    except Exception:
        raise AUTH_ERROR

    try:
        user = await auth_service.authenticate_request(
            user_id=x_user_id,
            timestamp=x_timestamp,
            nonce=x_nonce,
            signature=signature_bytes,
            canonical_payload=canonical_payload,
        )
    except AuthenticationError:
        raise AUTH_ERROR
    except Exception as e:
        logging.error(f"Unexpected error during signature verification: {e}")
        raise AUTH_ERROR

    if user.is_banned:
        raise BANNED_ERROR

    await user_repo.log_footprint(x_user_id, ip, fingerprint)

    return user


async def verify_pow(
    request: Request,
    x_challenge_id: str = Header(None),
    x_pow_nonce: str = Header(None),
    x_bot_token: str = Header(None),
) -> None:
    # Trusted bot traffic bypasses Proof of Work completely
    if settings.bot_api_token and x_bot_token == settings.bot_api_token:
        return

    if not x_challenge_id or not x_pow_nonce:
        raise POW_ERROR

    ip, fingerprint = _get_client_footprint(request)
    try:
        await security_service.verify_not_banned(ip, fingerprint)
        await security_service.verify_pow(x_challenge_id, x_pow_nonce)
    except BannedError:
        raise BANNED_ERROR
    except ProofOfWorkError:
        raise POW_ERROR


async def verify_bot_token(x_bot_token: str = Header(...)) -> None:
    if not settings.bot_api_token or x_bot_token != settings.bot_api_token:
        raise HTTPException(status_code=403, detail="Invalid bot token")