from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from typing import List, Optional
from netlazy.domain.models import User
from netlazy.presentation.dependencies import inbox_service, profile_service, verify_request_signature, verify_pow, handshake_repo
from netlazy.presentation.profile_router import ProfileResponse, _to_response as profile_to_response
from netlazy.application.inbox_service import HandshakeNotFoundError, UnauthorizedHandshakeActionError, InvalidHandshakeStateError, OtherUserNotFoundError, OtherUserBannedError

router = APIRouter(prefix="/inbox", tags=["Inbox"])

class HandshakeCreateRequest(BaseModel):
    receiver_id: str
    type: str = Field(..., pattern="^(mutual|demand|share|exchange)$")
    offered_contact: Optional[str] = None

class HandshakeResolveRequest(BaseModel):
    status: str = Field(..., pattern="^(accepted|declined)$")
    returned_contact: Optional[str] = None

class InboxItemResponse(BaseModel):
    id: str
    type: str
    status: str
    is_sender: bool
    offered_contact: Optional[str]
    returned_contact: Optional[str]
    created_at: str
    updated_at: str
    profile: ProfileResponse

@router.post("/handshakes", response_model=InboxItemResponse, dependencies=[Depends(verify_pow)])
async def send_handshake(body: HandshakeCreateRequest, user: User = Depends(verify_request_signature)):
    try:
        h = await inbox_service.send_handshake(
            sender_id=user.user_id,
            receiver_id=body.receiver_id,
            handshake_type=body.type,
            offered_contact=body.offered_contact
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except InvalidHandshakeStateError as e:
        raise HTTPException(status_code=403, detail=str(e))
        
    receiver_profile = await profile_service.get_or_create_profile(body.receiver_id)
    return InboxItemResponse(
        id=h.id, type=h.handshake_type, status=h.status,
        is_sender=True, offered_contact=h.offered_contact, returned_contact=h.returned_contact,
        created_at=h.created_at.isoformat(), updated_at=h.updated_at.isoformat(),
        profile=profile_to_response(receiver_profile)
    )

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
    return InboxItemResponse(
        id=h.id, type=h.handshake_type, status=h.status,
        is_sender=False, offered_contact=h.offered_contact, returned_contact=h.returned_contact,
        created_at=h.created_at.isoformat(), updated_at=h.updated_at.isoformat(),
        profile=profile_to_response(sender_profile)
    )

@router.delete("/handshakes/{handshake_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_handshake(handshake_id: str, user: User = Depends(verify_request_signature)):
    h = await handshake_repo.get_by_id(handshake_id)
    if not h:
        raise HTTPException(status_code=404, detail="Handshake not found")
    
    if h.sender_id == user.user_id:
        h.sender_deleted = True
    elif h.receiver_id == user.user_id:
        h.receiver_deleted = True
    else:
        raise HTTPException(status_code=403, detail="Forbidden")
        
    if h.sender_deleted and h.receiver_deleted:
        await handshake_repo.delete(handshake_id)
    else:
        await handshake_repo.update(h)

@router.get("", response_model=List[InboxItemResponse])
async def get_inbox(user: User = Depends(verify_request_signature)):
    items = await inbox_service.get_inbox(user.user_id)
    return [
        InboxItemResponse(
            id=h.id, type=h.handshake_type, status=h.status,
            is_sender=(h.sender_id == user.user_id),
            offered_contact=h.offered_contact, returned_contact=h.returned_contact,
            created_at=h.created_at.isoformat(), updated_at=h.updated_at.isoformat(),
            profile=profile_to_response(p)
        ) for h, p in items
    ]