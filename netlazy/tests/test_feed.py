import pytest
from unittest.mock import AsyncMock
from netlazy.application.feed_service import FeedService
from netlazy.domain.models import Profile


@pytest.fixture
def feed_deps():
    return {
        "profile_repo": AsyncMock(),
        "handshake_repo": AsyncMock()
    }


@pytest.fixture
def feed_service(feed_deps):
    return FeedService(**feed_deps)


@pytest.mark.asyncio
async def test_get_feed_excludes_interacted(feed_service, feed_deps):
    feed_deps["handshake_repo"].get_interacted_user_ids.return_value = ["u2", "u3"]
    feed_deps["profile_repo"].get_feed.return_value = [
        Profile(user_id="u4", bio="Target User")
    ]

    profiles = await feed_service.get_feed(
        viewer_id="u1",
        seen_ids=["u5"],
        requires=["tech"],
        excludes=["spam"],
        bonus=["python"],
        abonus=["crypto"],
        limit=20
    )

    assert len(profiles) == 1
    assert profiles[0].user_id == "u4"
    
    called_kwargs = feed_deps["profile_repo"].get_feed.call_args.kwargs
    assert set(called_kwargs["exclude_ids"]) == {"u2", "u3", "u5"}
    assert called_kwargs["requires"] == ["tech"]