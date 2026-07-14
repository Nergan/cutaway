from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from netlazy.application.profile_service import (
    InvalidTagError,
    MediaLimitExceededError,
    MediaNotFoundError,
    MediaProcessingError,
    UnsupportedMediaTypeError,
)
from netlazy.domain.models import Contact, Profile, User
from netlazy.presentation.dependencies import profile_service, verify_request_signature

router = APIRouter(prefix="/profile", tags=["Profile"])

class ContactRequest(BaseModel):
    type: str = Field(..., pattern="^(email|link|phone|unknown)$")
    value: str = Field(..., max_length=500)
    is_private: bool = True

class ProfileUpdateRequest(BaseModel):
    bio: str = Field("", max_length=200)
    tags: List[str] = Field(default_factory=list, max_length=50)
    contacts: List[ContactRequest] = Field(default_factory=list, max_length=20)

class MediaOrderRequest(BaseModel):
    urls: List[str]

class MediaItemResponse(BaseModel):
    url: str
    media_type: str
    blur: bool

class ContactResponse(BaseModel):
    type: str
    value: str
    is_private: bool

class ProfileResponse(BaseModel):
    user_id: str
    bio: str
    tags: List[str]
    media: List[MediaItemResponse]
    audio: Optional[MediaItemResponse]
    contacts: List[ContactResponse]
    created_at: str

def _to_response(profile: Profile) -> ProfileResponse:
    return ProfileResponse(
        user_id=profile.user_id,
        bio=profile.bio,
        tags=profile.tags,
        media=[MediaItemResponse(url=m.url, media_type=m.media_type, blur=m.blur) for m in profile.media],
        audio=(
            MediaItemResponse(url=profile.audio.url, media_type=profile.audio.media_type, blur=profile.audio.blur)
            if profile.audio else None
        ),
        contacts=[ContactResponse(type=c.type, value=c.value, is_private=c.is_private) for c in profile.contacts],
        created_at=profile.created_at.isoformat(),
    )

@router.get("/me", response_model=ProfileResponse)
async def get_my_profile(user: User = Depends(verify_request_signature)):
    profile = await profile_service.get_or_create_profile(user.user_id)
    return _to_response(profile)

@router.put("/me", response_model=ProfileResponse)
async def update_my_profile(
    body: ProfileUpdateRequest,
    user: User = Depends(verify_request_signature),
):
    try:
        profile = await profile_service.update_profile(
            user_id=user.user_id,
            bio=body.bio,
            tags=body.tags,
            contacts=[Contact(type=c.type, value=c.value, is_private=c.is_private) for c in body.contacts],
        )
    except InvalidTagError as e:
        raise HTTPException(status_code=400, detail=f"Unknown tags: {', '.join(e.unknown_tags)}")
    return _to_response(profile)

@router.put("/me/media/order", response_model=ProfileResponse)
async def reorder_media(body: MediaOrderRequest, user: User = Depends(verify_request_signature)):
    try:
        profile = await profile_service.reorder_media(user.user_id, body.urls)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _to_response(profile)

@router.post("/me/media", response_model=ProfileResponse)
async def upload_media(
    request: Request,
    blur: bool = False,
    user: User = Depends(verify_request_signature),
):
    raw_bytes = await request.body()
    if not raw_bytes:
        raise HTTPException(status_code=400, detail="Empty body")

    try:
        profile = await profile_service.upload_media(user.user_id, raw_bytes, blur=blur)
    except UnsupportedMediaTypeError as e:
        raise HTTPException(status_code=415, detail=str(e))
    except MediaLimitExceededError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except MediaProcessingError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return _to_response(profile)

@router.delete("/me/media", response_model=ProfileResponse)
async def remove_media(
    url: str,
    index: Optional[int] = None,
    user: User = Depends(verify_request_signature),
):
    try:
        profile = await profile_service.remove_media(user.user_id, url, index)
    except MediaNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return _to_response(profile)

@router.delete("/me/audio", response_model=ProfileResponse)
async def clear_audio(user: User = Depends(verify_request_signature)):
    profile = await profile_service.clear_audio(user.user_id)
    return _to_response(profile)

@router.patch("/me/media/blur", response_model=ProfileResponse)
async def set_media_blur(
    url: str,
    blur: bool,
    index: Optional[int] = None,
    user: User = Depends(verify_request_signature),
):
    try:
        profile = await profile_service.set_media_blur(user.user_id, url, blur, index)
    except MediaNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return _to_response(profile)