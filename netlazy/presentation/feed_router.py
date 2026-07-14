from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Query
from typing import List
from netlazy.domain.models import User
from netlazy.presentation.dependencies import feed_service, verify_request_signature
from netlazy.presentation.profile_router import ProfileResponse, _to_response as profile_to_response

router = APIRouter(prefix="/feed", tags=["Feed"])

@router.get("", response_model=List[ProfileResponse])
async def get_feed(
    cursor: str = Query(None, description="ISO8601 timestamp for pagination"),
    requires: List[str] = Query([]),
    excludes: List[str] = Query([]),
    user: User = Depends(verify_request_signature)
):
    if cursor:
        cursor_dt = datetime.fromisoformat(cursor.replace("Z", "+00:00"))
    else:
        cursor_dt = datetime.now(timezone.utc)

    profiles = await feed_service.get_feed(
        viewer_id=user.user_id,
        cursor=cursor_dt,
        requires=requires,
        excludes=excludes,
        limit=20
    )
    return [profile_to_response(p) for p in profiles]