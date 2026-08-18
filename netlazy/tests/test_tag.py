import pytest
from unittest.mock import AsyncMock, MagicMock
from netlazy.application.tag_service import TagService
from netlazy.domain.models import Tag


@pytest.fixture
def tag_deps():
    return {
        "tag_repo": AsyncMock(),
        "tag_loader": MagicMock()
    }


@pytest.fixture
def tag_service(tag_deps):
    return TagService(**tag_deps)


@pytest.mark.asyncio
async def test_tag_service_sync_and_search(tag_service, tag_deps):
    mock_tags = [
        Tag(name="python", aliases=["py", "django"], hidden=False, i18n={"ru": "питон"}),
        Tag(name="music", aliases=["rock"], hidden=False, i18n={"en": "music"})
    ]
    tag_deps["tag_loader"].load_tags.return_value = mock_tags
    tag_deps["tag_repo"].search.return_value = [mock_tags[0]]

    # Test sync delegation
    count = await tag_service.sync_from_yaml("tags.yaml")
    assert count == 2
    tag_deps["tag_repo"].sync.assert_called_once()

    # Test search delegation
    results = await tag_service.search("py")
    assert len(results) == 1
    assert results[0].name == "python"
    tag_deps["tag_repo"].search.assert_called_once_with("py")