import base64
import logging
import binascii
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response, Header
from pydantic import BaseModel, Field

from netlazy.domain.chain import build_identity_payload
from netlazy.domain.legacy import LegacyMigrationExpiredError
from netlazy.domain.repository import InvalidPublicKeyError, HashChainDesyncError, SignatureVerificationError
from netlazy.domain.models import UserAlreadyExistsError, User
from netlazy.database import DatabaseUnavailableError
from netlazy.presentation.dependencies import (
    auth_service,
    migration_service,
    profile_service, 
    inbox_service, 
    verify_pow, 
    verify_request_signature,
    profile_repo,
    handshake_repo,
    _normalize_path
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


class UserRegisterRequest(BaseModel):
    ed25519_public_pem: str = Field(..., description="PEM encoded Ed25519 public key")
    mldsa_public_hex: str = Field(..., description="Hex encoded ML-DSA-65 public key")

class UserRegisterResponse(BaseModel):
    user_id: str
    genesis_anchor: str
    message: str

class UserRotateRequest(BaseModel):
    new_ed25519_public_pem: str
    new_mldsa_public_hex: str

class UserRotateResponse(BaseModel):
    new_user_id: str
    new_anchor: str
    message: str

class LegacyMigrationRequest(BaseModel):
    legacy_public_pem: str
    new_ed25519_public_pem: str
    new_mldsa_public_hex: str
    timestamp: int
    signature_base64: str

class LegacyMigrationResponse(BaseModel):
    new_user_id: str
    message: str


@router.get("/footprint-check")
async def check_footprint(request: Request):
    from netlazy.presentation.dependencies import _get_client_footprint
    from netlazy.database import db_instance
    ip, fingerprint = _get_client_footprint(request)
    
    query = []
    if ip: query.append({"known_ips": ip})
    if fingerprint: query.append({"known_fingerprints": fingerprint})
    
    if not query:
        return {"has_accounts": False}
        
    doc = await db_instance.users_collection.find_one({"$or": query})
    return {"has_accounts": doc is not None}


@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=UserRegisterResponse, dependencies=[Depends(verify_pow)])
async def register(request: Request, user_data: UserRegisterRequest):
    from netlazy.presentation.dependencies import _get_client_footprint
    ip, fingerprint = _get_client_footprint(request)
    try:
        user, genesis_anchor = await auth_service.register_user(
            ed25519_pem=user_data.ed25519_public_pem,
            mldsa_hex=user_data.mldsa_public_hex,
            ip=ip, 
            fingerprint=fingerprint
        )
    except InvalidPublicKeyError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except UserAlreadyExistsError:
        raise HTTPException(status_code=400, detail="Public keys already registered")

    return UserRegisterResponse(user_id=user.user_id, genesis_anchor=genesis_anchor, message="Registration successful")


@router.post("/migrate", response_model=LegacyMigrationResponse)
async def migrate_legacy_user(body: LegacyMigrationRequest):
    try:
        sig_bytes = base64.b64decode(body.signature_base64)
    except binascii.Error as e:
        logging.warning(f"Malformed base64 signature in migration: {e}")
        raise HTTPException(status_code=400, detail="Malformed base64 signature")

    try:
        new_id = await migration_service.migrate_user(
            legacy_public_pem=body.legacy_public_pem,
            new_ed25519_pem=body.new_ed25519_public_pem,
            new_mldsa_hex=body.new_mldsa_public_hex,
            timestamp=body.timestamp,
            signature=sig_bytes
        )
        return LegacyMigrationResponse(new_user_id=new_id, message="Migration successful")
    except DatabaseUnavailableError:
        raise
    except LegacyMigrationExpiredError as e:
        logging.warning(f"Migration expired: {e}")
        raise HTTPException(status_code=410, detail=str(e))
    except ValueError as e:
        logging.warning(f"Migration validation error: {e}")
        raise HTTPException(status_code=404, detail=str(e))
    except (InvalidPublicKeyError, SignatureVerificationError) as e:
        logging.warning(f"Migration crypto error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logging.error(f"Migration failed unexpectedly: {e}")
        raise HTTPException(status_code=400, detail="Unexpected migration error")


@router.get("/anchor")
async def get_current_anchor(
    request: Request,
    x_user_id: str = Header(..., alias="X-User-Id"),
    x_timestamp: int = Header(..., alias="X-Timestamp"),
    x_nonce: str = Header(..., alias="X-Nonce"),
    x_body_hash: str = Header(..., alias="X-Body-Hash"),
    x_signature_ed25519: str = Header(..., alias="X-Signature-Ed25519"),
    x_signature_mldsa: str = Header(..., alias="X-Signature-MLDSA"),
    x_signed_path: str = Header(..., alias="X-Signed-Path"),
):
    norm_signed = _normalize_path(x_signed_path)
    norm_req = _normalize_path(request.url.path)
    if not norm_signed.endswith(norm_req):
        raise HTTPException(status_code=401, detail="Path mismatch")

    try:
        ed_sig = base64.b64decode(x_signature_ed25519)
        pq_sig = base64.b64decode(x_signature_mldsa)
    except binascii.Error:
        raise HTTPException(status_code=400, detail="Malformed base64 signature encoding")
        
    try:
        current_anchor = await auth_service.authenticate_identity(
            user_id=x_user_id,
            timestamp=x_timestamp,
            nonce=x_nonce,
            body_hash=x_body_hash,
            method=request.method,
            path=x_signed_path,
            ed_sig=ed_sig,
            pq_sig=pq_sig
        )
        return {"current_anchor": current_anchor}
    except DatabaseUnavailableError:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid identity signature")


@router.post("/rotate", response_model=UserRotateResponse)
async def rotate_key_endpoint(
    body: UserRotateRequest, 
    request: Request, 
    response: Response, 
    user: User = Depends(verify_request_signature)
):
    try:
        new_id, new_anchor = await auth_service.rotate_key(
            old_user_id=user.user_id,
            new_ed25519_pem=body.new_ed25519_public_pem,
            new_mldsa_hex=body.new_mldsa_public_hex,
            profile_repo=profile_repo,
            handshake_repo=handshake_repo
        )
        if request and hasattr(request.state, "next_anchor"):
            response.headers["X-Next-Anchor"] = request.state.next_anchor
        return UserRotateResponse(new_user_id=new_id, new_anchor=new_anchor, message="Rotation successful")
    except InvalidPublicKeyError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except UserAlreadyExistsError:
        raise HTTPException(status_code=400, detail="Public keys already registered")


@router.delete("/account", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(user: User = Depends(verify_request_signature)):
    await profile_service.delete_profile(user.user_id)
    await auth_service.delete_user(user.user_id)
    await inbox_service.delete_user_handshakes(user.user_id)