import asyncio
import secrets
from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel
from netlazy.config import settings
from netlazy.presentation.route_handler import NetlazyRoute
from netlazy.presentation.dependencies import security_service

router = APIRouter(prefix="/security", tags=["Security"], route_class=NetlazyRoute)

async def verify_admin(x_admin_key: str = Header(None)):
    if not settings.admin_api_key or not x_admin_key or not secrets.compare_digest(x_admin_key, settings.admin_api_key):
        raise HTTPException(status_code=403, detail="Forbidden")

class ChallengeResponse(BaseModel):
    challenge_id: str
    difficulty: int

@router.get("")
async def security_index():
    return {
        "challenge": "/netlazy/api/security/challenge",
        "ban": "POST /netlazy/api/security/ban?user={id}",
    }


@router.get("/challenge", response_model=ChallengeResponse)
async def get_challenge():
    await asyncio.sleep(settings.bot_protection_delay)
    data = await security_service.generate_challenge()
    return ChallengeResponse(**data)

@router.post("/ban", dependencies=[Depends(verify_admin)])
async def cascade_ban_user(user: str = ""):
    if not user:
        raise HTTPException(status_code=400, detail="Missing user.")
    try:
        await security_service.cascade_ban_user(user)
        return {"message": f"User {user} and all network footprints banned permanently."}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))