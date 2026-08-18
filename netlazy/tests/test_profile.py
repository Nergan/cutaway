import pytest
from unittest.mock import AsyncMock, MagicMock
from netlazy.application.profile_service import (
    ProfileService,
    InvalidTagError,
    MediaLimitExceededError,
    MediaNotFoundError
)
from netlazy.domain.models import Profile, Contact, MediaItem
from netlazy.domain.repository import MediaProcessingError


@pytest.fixture
def profile_deps():
    return {
        "profile_repo": AsyncMock(),
        "tag_repo": AsyncMock(),
        "media_storage": AsyncMock(),
        "media_processor": MagicMock(),
        "max_media_items": 3,
        "max_bio_length": 200,
        "max_upload_bytes": 1024 * 1024,
        "image_max_dimension": 1600,
        "audio_bitrate": "96k"
    }


@pytest.fixture
def profile_service(profile_deps):
    return ProfileService(**profile_deps)


@pytest.mark.asyncio
async def test_update_profile_invalid_tag(profile_service, profile_deps):
    profile_deps["tag_repo"].get_all_names.return_value = ["music", "coding"]

    with pytest.raises(InvalidTagError) as exc_info:
        await profile_service.update_profile(
            user_id="u1",
            bio="Hello",
            tags=["music", "non_existent_tag"],
            contacts=[]
        )

    assert "non_existent_tag" in exc_info.value.unknown_tags


@pytest.mark.asyncio
async def test_update_profile_success(profile_service, profile_deps):
    profile_deps["tag_repo"].get_all_names.return_value = ["music", "art"]
    profile_deps["profile_repo"].get_by_user_id.return_value = Profile(user_id="u1", media_id="u1")

    profile = await profile_service.update_profile(
        user_id="u1",
        bio="Creative bio",
        tags=["music"],
        contacts=[Contact(type="email", value="test@test.com", is_private=True)]
    )

    assert profile.bio == "Creative bio"
    assert profile.tags == ["music"]
    assert len(profile.contacts) == 1
    profile_deps["profile_repo"].upsert.assert_called_once()


@pytest.mark.asyncio
async def test_upload_media_size_limit(profile_service):
    oversized_bytes = b"0" * (1024 * 1024 + 1)
    with pytest.raises(MediaProcessingError, match="exceeds maximum upload size"):
        await profile_service.upload_media(user_id="u1", raw_bytes=oversized_bytes)


@pytest.mark.asyncio
async def test_upload_media_deduplication(profile_service, profile_deps):
    profile_deps["profile_repo"].get_by_user_id.return_value = Profile(user_id="u1", media_id="u1")
    
    existing_item = MediaItem(
        url="https://cdn.example.com/cached.webp",
        media_type="image",
        file_hash="mock_hash",
        public_id="pid_1",
        resource_type="raw"
    )
    profile_deps["profile_repo"].find_media_by_hash.return_value = existing_item

    profile = await profile_service.upload_media(user_id="u1", raw_bytes=b"sample_data", blur=False)

    assert len(profile.media) == 1
    assert profile.media[0].url == "https://cdn.example.com/cached.webp"
    # Transcoder and storage should not be called when deduplicated
    profile_deps["media_storage"].upload.assert_not_called()


@pytest.mark.asyncio
async def test_upload_media_exceeds_max_items(profile_service, profile_deps):
    existing_media = [
        MediaItem(url=f"url_{i}", media_type="image") for i in range(3)
    ]
    profile_deps["profile_repo"].get_by_user_id.return_value = Profile(
        user_id="u1", media_id="u1", media=existing_media
    )
    profile_deps["profile_repo"].find_media_by_hash.return_value = None
    profile_deps["media_processor"].sniff_mime_type.return_value = "image/png"
    profile_deps["media_processor"].classify_media_type.return_value = "image"
    profile_deps["media_processor"].process_image = AsyncMock(return_value=b"processed")
    profile_deps["media_storage"].upload.return_value = {"url": "new_url"}

    with pytest.raises(MediaLimitExceededError):
        await profile_service.upload_media(user_id="u1", raw_bytes=b"valid_data")


@pytest.mark.asyncio
async def test_reorder_media_success(profile_service, profile_deps):
    items = [
        MediaItem(url="url_1", media_type="image"),
        MediaItem(url="url_2", media_type="image"),
        MediaItem(url="url_3", media_type="image"),
    ]
    profile_deps["profile_repo"].get_by_user_id.return_value = Profile(
        user_id="u1", media_id="u1", media=items
    )

    reordered = await profile_service.reorder_media(user_id="u1", ordered_urls=["url_3", "url_1", "url_2"])

    assert [m.url for m in reordered.media] == ["url_3", "url_1", "url_2"]
    profile_deps["profile_repo"].upsert.assert_called_once()