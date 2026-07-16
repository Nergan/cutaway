from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel, Field
from netlazy.application.auth_service import InvalidPublicKeyError, AuthenticationError
from netlazy.domain.models import UserAlreadyExistsError
from netlazy.domain.models import User
from netlazy.presentation.dependencies import (
    auth_service, 
    profile_service, 
    inbox_service, 
    verify_pow, 
    verify_request_signature,
    verify_bot_token,
    profile_repo,
    handshake_repo
)

router = APIRouter(prefix="/auth", tags=["Authentication"])

class UserRegisterRequest(BaseModel):
    public_key: str = Field(..., max_length=4096, description="PEM encoded RSA public key (min 2048 bits)")

class UserRegisterResponse(BaseModel):
    user_id: str
    message: str

class UserRotateRequest(BaseModel):
    new_public_key: str = Field(..., max_length=4096, description="PEM encoded RSA public key (min 2048 bits)")

class UserRotateResponse(BaseModel):
    new_user_id: str
    message: str

class BotRegisterRequest(BaseModel):
    public_key: str = Field(..., max_length=4096)
    telegram_id: int

class BotLinkRequest(BaseModel):
    user_id: str
    telegram_id: int

class BotUnlinkRequest(BaseModel):
    telegram_id: int

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
        user = await auth_service.register_user(user_data.public_key, ip=ip, fingerprint=fingerprint)
    except InvalidPublicKeyError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except UserAlreadyExistsError:
        raise HTTPException(status_code=400, detail="Public key already registered")

    return UserRegisterResponse(user_id=user.user_id, message="Registration successful")

@router.post("/rotate", response_model=UserRotateResponse)
async def rotate_key_endpoint(body: UserRotateRequest, user: User = Depends(verify_request_signature)):
    try:
        new_user_id = await auth_service.rotate_key(
            old_user_id=user.user_id,
            new_public_key_pem=body.new_public_key,
            profile_repo=profile_repo,
            handshake_repo=handshake_repo
        )
    except InvalidPublicKeyError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except UserAlreadyExistsError:
        raise HTTPException(status_code=400, detail="Public key already registered")

    return UserRotateResponse(new_user_id=new_user_id, message="Rotation successful")

@router.delete("/account", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(user: User = Depends(verify_request_signature)):
    await profile_service.delete_profile(user.user_id)
    await auth_service.delete_user(user.user_id)
    await inbox_service.delete_user_handshakes(user.user_id)

# --- BOT EXCLUSIVE ENDPOINTS ---

@router.post("/bot/register", status_code=status.HTTP_201_CREATED, dependencies=[Depends(verify_bot_token)])
async def bot_register(body: BotRegisterRequest):
    try:
        # IP/Fingerprint logging is skipped for bot proxy registration
        user = await auth_service.register_user(body.public_key, telegram_id=body.telegram_id)
        return {"user_id": user.user_id, "message": "Bot registration successful"}
    except InvalidPublicKeyError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except UserAlreadyExistsError:
        raise HTTPException(status_code=400, detail="Public key already registered")

@router.post("/bot/link", dependencies=[Depends(verify_bot_token)])
async def bot_link(body: BotLinkRequest):
    try:
        user = await auth_service.link_telegram_id(body.user_id, body.telegram_id)
        return {"user_id": user.user_id, "message": "Telegram ID linked successfully"}
    except AuthenticationError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.post("/bot/unlink", dependencies=[Depends(verify_bot_token)])
async def bot_unlink(body: BotUnlinkRequest):
    await auth_service.unlink_telegram_id(body.telegram_id)
    return {"message": "Telegram ID unlinked successfully"}