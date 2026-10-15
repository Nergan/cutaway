from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from netlazy.domain.models import Profile, User
from netlazy.presentation.route_handler import NetlazyRoute
from netlazy.presentation.dependencies import feed_service, optional_user, profile_service
from netlazy.presentation.profile_router import PublicProfileResponse, public_profile_response

router = APIRouter(prefix="/feed", tags=["Feed"], route_class=NetlazyRoute)

class FeedSearchRequest(BaseModel):
    seen_ids: List[str] = []
    requires: List[str] = []
    excludes: List[str] = []
    bonus: List[str] = []
    abonus: List[str] = []

async def _publish(profile: Profile) -> PublicProfileResponse:
    await profile_service.ensure_public_id(profile)
    return public_profile_response(profile)

@router.get("")
async def feed_index():
    return {"search": "POST /netlazy/api/feed/search"}


@router.post("/search", response_model=List[PublicProfileResponse])
async def get_feed(
    body: FeedSearchRequest,
    user: Optional[User] = Depends(optional_user)
):
    seen_user_ids = await profile_service.user_ids_for_public_ids(body.seen_ids)
    profiles = await feed_service.get_feed(
        viewer_id=user.user_id if user else None,
        seen_ids=seen_user_ids,
        requires=body.requires,
        excludes=body.excludes,
        bonus=body.bonus,
        abonus=body.abonus,
        limit=20
    )
    published = []
    for profile in profiles:
        published.append(await _publish(profile))
    return published

@router.get("/form/{slug}", response_model=PublicProfileResponse)
async def get_profile_by_form(slug: str, user: Optional[User] = Depends(optional_user)):
    profile = await profile_service.get_public_by_form(slug)
    if profile is None:
        raise HTTPException(status_code=404, detail="form_not_found")
    return await _publish(profile)