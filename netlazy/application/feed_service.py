from datetime import datetime
from typing import List, Optional
from netlazy.domain.models import Profile
from netlazy.domain.repository import HandshakeRepository, ProfileRepository

class FeedService:
    def __init__(self, profile_repo: ProfileRepository, handshake_repo: HandshakeRepository):
        self._profile_repo = profile_repo
        self._handshake_repo = handshake_repo

    async def get_feed(self, viewer_id: str, cursor: datetime, cursor_score: Optional[int], requires: List[str], excludes: List[str], bonus: List[str], abonus: List[str], limit: int = 20) -> List[Profile]:
        interacted_ids = await self._handshake_repo.get_interacted_user_ids(viewer_id)
        return await self._profile_repo.get_feed(
            viewer_id=viewer_id,
            exclude_ids=interacted_ids,
            cursor_dt=cursor,
            cursor_score=cursor_score,
            requires=requires,
            excludes=excludes,
            bonus=bonus,
            abonus=abonus,
            limit=limit
        )