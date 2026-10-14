from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from netlazy.domain.models import User
from netlazy.presentation.route_handler import NetlazyRoute
from netlazy.presentation.dependencies import feed_service, optional_user, profile_service
from netlazy.presentation.profile_router import ProfileResponse, _to_response as profile_to_response

router = APIRouter(prefix="/feed", tags=["Feed"], route_class=NetlazyRoute)

class FeedSearchRequest(BaseModel):
    seen_ids: List[str] = []
    requires: List[str] = []
    excludes: List[str] = []
    bonus: List[str] = []
    abonus: List[str] = []

@router.get("")
async def feed_index():
    return {"search": "POST /netlazy/api/feed/search"}


@router.post("/search", response_model=List[ProfileResponse])
async def get_feed(
    body: FeedSearchRequest,
    user: Optional[User] = Depends(optional_user)
):
    profiles = await feed_service.get_feed(
        viewer_id=user.user_id if user else None,
        seen_ids=body.seen_ids,
        requires=body.requires,
        excludes=body.excludes,
        bonus=body.bonus,
        abonus=body.abonus,
        limit=20
    )
    return [profile_to_response(p, hide_private=user is None) for p in profiles]

@router.get("/form/{slug}", response_model=ProfileResponse)
async def get_profile_by_form(slug: str, user: Optional[User] = Depends(optional_user)):
    profile = await profile_service.get_public_by_form(slug)
    if profile is None:
        raise HTTPException(status_code=404, detail="form_not_found")
    return profile_to_response(profile, hide_private=user is None)