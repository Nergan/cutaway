from typing import List
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from netlazy.domain.models import User
from netlazy.presentation.dependencies import feed_service, verify_request_signature
from netlazy.presentation.profile_router import ProfileResponse, _to_response as profile_to_response

router = APIRouter(prefix="/feed", tags=["Feed"])

class FeedSearchRequest(BaseModel):
    seen_ids: List[str] = []
    requires: List[str] = []
    excludes: List[str] = []
    bonus: List[str] = []
    abonus: List[str] = []

@router.post("/search", response_model=List[ProfileResponse])
async def get_feed(
    body: FeedSearchRequest,
    user: User = Depends(verify_request_signature)
):
    profiles = await feed_service.get_feed(
        viewer_id=user.user_id,
        seen_ids=body.seen_ids,
        requires=body.requires,
        excludes=body.excludes,
        bonus=body.bonus,
        abonus=body.abonus,
        limit=20
    )
    return [profile_to_response(p) for p in profiles]