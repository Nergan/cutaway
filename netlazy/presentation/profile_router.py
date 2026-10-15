from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from netlazy.domain.repository import (
    MediaProcessingError,
    UnsupportedMediaTypeError,
)
from netlazy.application.profile_service import (
    InvalidTagError,
    MediaLimitExceededError,
    MediaNotFoundError,
)
from netlazy.domain.forms import (
    FormInvalidError,
    FormLimitError,
    FormNotFoundError,
    FormTakenError,
    primary_form_of,
)
from netlazy.domain.media_key import encode_media_key
from netlazy.domain.models import Contact, Profile, User
from netlazy.config import settings
from netlazy.presentation.route_handler import NetlazyRoute
from netlazy.presentation.dependencies import profile_service, verify_reader, verify_request_signature

router = APIRouter(prefix="/profile", tags=["Profile"], route_class=NetlazyRoute)

class ContactRequest(BaseModel):
    type: str = Field(..., pattern="^(email|link|phone|unknown)$")
    value: str = Field(..., max_length=500)
    is_private: bool = True

class ProfileUpdateRequest(BaseModel):
    bio: str = Field("", max_length=settings.max_bio_length)
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

class FormCreateRequest(BaseModel):
    value: Optional[str] = None

class ProfileResponse(BaseModel):
    id: str = ""
    user_id: str
    media_id: str
    media_key: str = ""
    bio: str
    tags: List[str]
    media: List[MediaItemResponse]
    audio: Optional[MediaItemResponse]
    contacts: List[ContactResponse]
    created_at: str
    score: int = 0
    form: Optional[str] = None
    forms: List[str] = Field(default_factory=list)
    primary_form: Optional[str] = None

class PublicContactResponse(BaseModel):
    type: str
    value: str

class PublicProfileResponse(BaseModel):
    id: str
    bio: str
    tags: List[str]
    media: List[MediaItemResponse]
    audio: Optional[MediaItemResponse] = None
    contacts: List[PublicContactResponse]
    form: Optional[str] = None
    media_key: str = ""

def _media_response(item) -> MediaItemResponse:
    return MediaItemResponse(url=item.url, media_type=item.media_type, blur=item.blur)

def _to_response(profile: Profile, *, include_forms: bool = False, hide_private: bool = False) -> ProfileResponse:
    primary = primary_form_of(profile)
    contacts = profile.contacts
    if hide_private:
        contacts = [c for c in contacts if not c.is_private]
    return ProfileResponse(
        id=profile.public_id,
        user_id=profile.user_id,
        media_id=profile.media_id,
        media_key=encode_media_key(profile.media_id or profile.user_id),
        bio=profile.bio,
        tags=profile.tags,
        media=[_media_response(m) for m in profile.media],
        audio=_media_response(profile.audio) if profile.audio else None,
        contacts=[ContactResponse(type=c.type, value=c.value, is_private=c.is_private) for c in contacts],
        created_at=profile.created_at.isoformat(),
        score=profile.score,
        form=primary,
        forms=list(profile.forms) if include_forms else [],
        primary_form=primary if include_forms else None,
    )

def public_profile_response(profile: Profile) -> PublicProfileResponse:
    """Fields another client is allowed to learn about this profile."""
    contacts = [
        PublicContactResponse(type=c.type, value=c.value)
        for c in profile.contacts
        if not c.is_private and c.type != "unknown" and str(c.value or "").strip()
    ]
    return PublicProfileResponse(
        id=profile.public_id,
        bio=profile.bio,
        tags=list(profile.tags),
        media=[_media_response(m) for m in profile.media],
        audio=_media_response(profile.audio) if profile.audio else None,
        contacts=contacts,
        form=primary_form_of(profile),
        media_key=encode_media_key(profile.media_id or profile.user_id),
    )

def _raise_form_error(exc: Exception) -> None:
    if isinstance(exc, FormInvalidError):
        raise HTTPException(status_code=400, detail="form_invalid")
    if isinstance(exc, FormTakenError):
        raise HTTPException(status_code=409, detail="form_taken")
    if isinstance(exc, FormLimitError):
        raise HTTPException(status_code=400, detail="form_limit")
    if isinstance(exc, FormNotFoundError):
        raise HTTPException(status_code=404, detail="form_not_found")
    raise exc

@router.get("")
async def profile_index():
    return {"me": "/netlazy/api/profile/me"}


@router.get("/me", response_model=ProfileResponse)
async def get_my_profile(user: User = Depends(verify_reader)):
    profile = await profile_service.get_or_create_profile(user.user_id)
    await profile_service.ensure_public_id(profile)
    return _to_response(profile, include_forms=True)

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
    return _to_response(profile, include_forms=True)

@router.put("/me/media/order", response_model=ProfileResponse)
async def reorder_media(body: MediaOrderRequest, user: User = Depends(verify_request_signature)):
    try:
        profile = await profile_service.reorder_media(user.user_id, body.urls)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _to_response(profile, include_forms=True)

@router.post("/me/media", response_model=ProfileResponse)
async def upload_media(
    request: Request,
    blur: bool = False,
    user: User = Depends(verify_request_signature),
):
    raw_bytes = request.state.body_bytes
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
    return _to_response(profile, include_forms=True)

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
    return _to_response(profile, include_forms=True)

@router.delete("/me/audio", response_model=ProfileResponse)
async def clear_audio(user: User = Depends(verify_request_signature)):
    profile = await profile_service.clear_audio(user.user_id)
    return _to_response(profile, include_forms=True)

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
    return _to_response(profile, include_forms=True)

@router.post("/me/forms", response_model=ProfileResponse)
async def add_profile_form(
    body: FormCreateRequest,
    user: User = Depends(verify_request_signature),
):
    try:
        profile = await profile_service.add_form(user.user_id, body.value)
    except (FormInvalidError, FormTakenError, FormLimitError) as exc:
        _raise_form_error(exc)
    return _to_response(profile, include_forms=True)

@router.post("/me/forms/{slug}/regenerate", response_model=ProfileResponse)
async def regenerate_profile_form(slug: str, user: User = Depends(verify_request_signature)):
    try:
        profile = await profile_service.regenerate_form(user.user_id, slug)
    except (FormNotFoundError, FormTakenError) as exc:
        _raise_form_error(exc)
    return _to_response(profile, include_forms=True)

@router.delete("/me/forms/{slug}", response_model=ProfileResponse)
async def delete_profile_form(slug: str, user: User = Depends(verify_request_signature)):
    try:
        profile = await profile_service.delete_form(user.user_id, slug)
    except FormNotFoundError as exc:
        _raise_form_error(exc)
    return _to_response(profile, include_forms=True)

@router.put("/me/forms/{slug}/primary", response_model=ProfileResponse)
async def set_primary_profile_form(slug: str, user: User = Depends(verify_request_signature)):
    try:
        profile = await profile_service.set_primary_form(user.user_id, slug)
    except FormNotFoundError as exc:
        _raise_form_error(exc)
    return _to_response(profile, include_forms=True)