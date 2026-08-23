from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from typing import List, Optional
from netlazy.domain.models import User
from netlazy.presentation.route_handler import NetlazyRoute
from netlazy.presentation.dependencies import inbox_service, profile_service, verify_request_signature, verify_pow
from netlazy.presentation.profile_router import ProfileResponse, _to_response as profile_to_response
from netlazy.application.inbox_service import HandshakeNotFoundError, UnauthorizedHandshakeActionError, InvalidHandshakeStateError, OtherUserNotFoundError, OtherUserBannedError

router = APIRouter(prefix="/inbox", tags=["Inbox"], route_class=NetlazyRoute)

class HandshakeCreateRequest(BaseModel):
    receiver_id: str
    type: str = Field(..., pattern="^(mutual|demand|share|exchange)$")
    offered_contact: Optional[str] = None
    message: Optional[str] = Field(None, max_length=100)

class HandshakeResolveRequest(BaseModel):
    status: str = Field(..., pattern="^(accepted|declined)$")
    returned_contact: Optional[str] = None

class InboxItemResponse(BaseModel):
    id: str
    type: str
    status: str
    is_sender: bool
    is_read: bool = False
    offered_contact: Optional[str]
    returned_contact: Optional[str]
    message: Optional[str]
    created_at: str
    updated_at: str
    profile: ProfileResponse


def _to_inbox_item(h, profile, is_sender: bool) -> InboxItemResponse:
    updated_at = h.updated_at or h.created_at
    return InboxItemResponse(
        id=h.id,
        type=h.handshake_type,
        status=h.status,
        is_sender=is_sender,
        is_read=h.is_read,
        offered_contact=h.offered_contact,
        returned_contact=h.returned_contact,
        message=h.message,
        created_at=h.created_at.isoformat(),
        updated_at=updated_at.isoformat(),
        profile=profile_to_response(profile),
    )

@router.post("/handshakes", response_model=InboxItemResponse, dependencies=[Depends(verify_pow)])
async def send_handshake(body: HandshakeCreateRequest, user: User = Depends(verify_request_signature)):
    try:
        h = await inbox_service.send_handshake(
            sender_id=user.user_id,
            receiver_id=body.receiver_id,
            handshake_type=body.type,
            offered_contact=body.offered_contact,
            message=body.message
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except InvalidHandshakeStateError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except UnauthorizedHandshakeActionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except OtherUserNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except OtherUserBannedError as e:
        raise HTTPException(status_code=404, detail=str(e))
        
    receiver_profile = await profile_service.get_or_create_profile(body.receiver_id)
    return _to_inbox_item(h, receiver_profile, is_sender=True)

@router.post("/handshakes/{handshake_id}/resolve", response_model=InboxItemResponse)
async def resolve_handshake(handshake_id: str, body: HandshakeResolveRequest, user: User = Depends(verify_request_signature)):
    try:
        h = await inbox_service.resolve_handshake(
            user_id=user.user_id,
            handshake_id=handshake_id,
            status=body.status,
            returned_contact=body.returned_contact
        )
    except HandshakeNotFoundError:
        raise HTTPException(status_code=404, detail="Handshake not found")
    except UnauthorizedHandshakeActionError:
        raise HTTPException(status_code=403, detail="Forbidden")
    except InvalidHandshakeStateError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except OtherUserNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except OtherUserBannedError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    sender_profile = await profile_service.get_or_create_profile(h.sender_id)
    return _to_inbox_item(h, sender_profile, is_sender=False)

@router.post("/handshakes/{handshake_id}/read", response_model=InboxItemResponse)
async def mark_handshake_read(handshake_id: str, user: User = Depends(verify_request_signature)):
    try:
        h = await inbox_service.mark_as_read(user.user_id, handshake_id)
    except HandshakeNotFoundError:
        raise HTTPException(status_code=404, detail="Handshake not found")
    except UnauthorizedHandshakeActionError:
        raise HTTPException(status_code=403, detail="Forbidden")

    other_id = h.receiver_id if h.sender_id == user.user_id else h.sender_id
    other_profile = await profile_service.get_or_create_profile(other_id)
    return _to_inbox_item(h, other_profile, is_sender=(h.sender_id == user.user_id))

@router.delete("/handshakes/{handshake_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_handshake(handshake_id: str, user: User = Depends(verify_request_signature)):
    try:
        await inbox_service.delete_handshake(user.user_id, handshake_id)
    except HandshakeNotFoundError:
        raise HTTPException(status_code=404, detail="Handshake not found")
    except UnauthorizedHandshakeActionError:
        raise HTTPException(status_code=403, detail="Forbidden")
    except InvalidHandshakeStateError as e:
        raise HTTPException(status_code=403, detail=str(e))

@router.get("", response_model=List[InboxItemResponse])
async def get_inbox(user: User = Depends(verify_request_signature)):
    items = await inbox_service.get_inbox(user.user_id)
    return [
        _to_inbox_item(h, p, is_sender=(h.sender_id == user.user_id))
        for h, p in items
    ]