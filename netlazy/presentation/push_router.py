from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional

from netlazy.domain.models import PushPreferences, PushSubscription, User
from netlazy.presentation.dependencies import push_service, verify_reader, verify_request_signature
from netlazy.presentation.route_handler import NetlazyRoute

router = APIRouter(prefix="/push", tags=["Push"], route_class=NetlazyRoute)


class PushPreferencesBody(BaseModel):
    enabled: bool = True
    share: bool = True
    exchange: bool = True
    demand: bool = True
    lang: str = Field("en", pattern="^(en|ru|pt|zh|ja|ko)$")


class PushSubscriptionBody(BaseModel):
    platform: str = Field(..., pattern="^(windows|android|web)$")
    transport: str = Field(..., pattern="^(webpush|fcm)$")
    endpoint: Optional[str] = None
    p256dh: Optional[str] = None
    auth: Optional[str] = None
    token: Optional[str] = None
    open_path: str = "/netlazy/inbox"
    origin: str = ""
    lang: str = Field("en", pattern="^(en|ru|pt|zh|ja|ko)$")


class PushUnsubscribeBody(BaseModel):
    endpoint: Optional[str] = None
    token: Optional[str] = None


@router.get("/key")
async def push_key():
    return {"public_key": await push_service.public_key()}


@router.get("/preferences", response_model=PushPreferencesBody)
async def get_preferences(user: User = Depends(verify_reader)):
    prefs = await push_service.preferences(user.user_id)
    return PushPreferencesBody(
        enabled=prefs.enabled,
        share=prefs.share,
        exchange=prefs.exchange,
        demand=prefs.demand,
        lang=prefs.lang,
    )


@router.put("/preferences", response_model=PushPreferencesBody)
async def put_preferences(body: PushPreferencesBody, user: User = Depends(verify_request_signature)):
    prefs = await push_service.save_preferences(user.user_id, PushPreferences(
        enabled=body.enabled,
        share=body.share,
        exchange=body.exchange,
        demand=body.demand,
        lang=body.lang,
    ))
    return PushPreferencesBody(
        enabled=prefs.enabled,
        share=prefs.share,
        exchange=prefs.exchange,
        demand=prefs.demand,
        lang=prefs.lang,
    )


@router.post("/subscriptions", status_code=status.HTTP_204_NO_CONTENT)
async def register_subscription(body: PushSubscriptionBody, user: User = Depends(verify_request_signature)):
    try:
        await push_service.register(user.user_id, PushSubscription(
            user_id=user.user_id,
            platform=body.platform,
            transport=body.transport,
            endpoint=body.endpoint or "",
            p256dh=body.p256dh or "",
            auth=body.auth or "",
            token=body.token or "",
            open_path=body.open_path,
            origin=body.origin,
            lang=body.lang,
        ))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/subscriptions", status_code=status.HTTP_204_NO_CONTENT)
async def unregister_subscription(body: PushUnsubscribeBody, user: User = Depends(verify_request_signature)):
    try:
        await push_service.unregister(user.user_id, endpoint=body.endpoint or "", token=body.token or "")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
