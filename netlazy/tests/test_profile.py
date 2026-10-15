import pytest
from unittest.mock import AsyncMock, MagicMock
from netlazy.application.profile_service import (
    ProfileService,
    InvalidTagError,
    MediaLimitExceededError,
    MediaNotFoundError
)
from netlazy.config import Settings
from netlazy.domain.bio import normalize_bio
from netlazy.domain.forms import (
    GENERATED_FORM_RE,
    FormInvalidError,
    FormLimitError,
    FormNotFoundError,
    FormTakenError,
    MAX_FORM_LINKS,
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


def test_bio_limit_default_is_500():
    assert Settings.model_fields["max_bio_length"].default == 500


def test_normalize_bio_keeps_single_blank_lines():
    text = "\n\nhello\n\n\n\nworld\n \n \n\nnext\n\n"
    assert normalize_bio(text, 500) == "hello\n\nworld\n\nnext"
    assert len(normalize_bio("a" * 600, 500)) == 500


@pytest.mark.asyncio
async def test_update_profile_collapses_bio_and_keeps_forms(profile_service, profile_deps):
    profile_deps["tag_repo"].get_all_names.return_value = []
    profile_deps["profile_repo"].get_by_user_id.return_value = Profile(
        user_id="u1", media_id="u1", forms=["keep-me"], primary_form="keep-me"
    )

    profile = await profile_service.update_profile(
        user_id="u1",
        bio="one\n\n\n\ntwo",
        tags=[],
        contacts=[],
    )

    assert profile.bio == "one\n\ntwo"
    assert profile.forms == ["keep-me"]
    assert profile.primary_form == "keep-me"


@pytest.mark.asyncio
async def test_form_links_follow_primary_and_charset(profile_service, profile_deps):
    profile = Profile(user_id="u1", media_id="u1")
    profile_deps["profile_repo"].get_by_user_id.return_value = profile
    profile_deps["profile_repo"].get_by_form.return_value = None

    added = await profile_service.add_form("u1", "Mik-Chan")
    assert added.forms == ["mik-chan"]
    assert added.primary_form == "mik-chan"

    generated = await profile_service.add_form("u1", None)
    generated_slug = generated.forms[1]
    assert generated.forms[0] == "mik-chan"
    assert GENERATED_FORM_RE.fullmatch(generated_slug)
    assert generated.primary_form == generated_slug

    chosen = await profile_service.set_primary_form("u1", "mik-chan")
    assert chosen.primary_form == "mik-chan"
    assert chosen.forms[1] == generated_slug

    removed = await profile_service.delete_form("u1", generated_slug)
    assert removed.forms == ["mik-chan"]
    assert removed.primary_form == "mik-chan"

    with pytest.raises(FormInvalidError):
        await profile_service.add_form("u1", "job-2")
    with pytest.raises(FormTakenError):
        await profile_service.add_form("u1", "mik-chan")

    profile_deps["profile_repo"].get_by_form.return_value = Profile(user_id="other", forms=["taken-name"])
    with pytest.raises(FormTakenError):
        await profile_service.add_form("u1", "taken-name")

    profile.forms = ["link-one"] * MAX_FORM_LINKS
    profile.primary_form = "link-one"
    with pytest.raises(FormLimitError):
        await profile_service.add_form("u1", "another-name")

    with pytest.raises(FormNotFoundError):
        await profile_service.delete_form("u1", "missing-link")


@pytest.mark.asyncio
async def test_regenerate_form_replaces_the_old_slug(profile_service, profile_deps):
    profile = Profile(user_id="u1", media_id="u1", forms=["old-link"], primary_form="old-link")
    profile_deps["profile_repo"].get_by_user_id.return_value = profile
    profile_deps["profile_repo"].get_by_form.return_value = None

    updated = await profile_service.regenerate_form("u1", "old-link")

    assert "old-link" not in updated.forms
    assert len(updated.forms) == 1
    assert updated.primary_form == updated.forms[0]
    assert GENERATED_FORM_RE.fullmatch(updated.forms[0])


@pytest.mark.asyncio
async def test_public_form_lookup_ignores_unknown_text(profile_service, profile_deps):
    assert await profile_service.get_public_by_form("nope!") is None
    profile_deps["profile_repo"].get_by_form.assert_not_called()


def test_public_profile_omits_identity_and_private_contacts():
    import base64
    from datetime import datetime, timezone

    from netlazy.domain.media_key import derive_media_key, encode_media_key
    from netlazy.presentation.profile_router import _to_response, public_profile_response

    secret = "secret-contact@example.com"
    account_id = "ab" * 32
    profile = Profile(
        user_id=account_id,
        media_id=account_id,
        public_id="c" * 32,
        bio="hello",
        tags=["music"],
        contacts=[
            Contact(type="email", value=secret, is_private=True),
            Contact(type="link", value="https://example.com/public", is_private=False),
            Contact(type="unknown", value="skip-me", is_private=False),
        ],
        created_at=datetime(2020, 1, 2, tzinfo=timezone.utc),
        score=4,
        forms=["my-link", "other-link"],
        primary_form="my-link",
    )

    payload = public_profile_response(profile).model_dump()
    assert set(payload) == {"id", "bio", "tags", "media", "audio", "contacts", "form", "media_key"}
    assert payload["id"] == profile.public_id
    assert payload["form"] == "my-link"
    assert payload["contacts"] == [{"type": "link", "value": "https://example.com/public"}]
    rendered = str(payload)
    assert secret not in rendered
    assert account_id not in rendered
    assert "2020-01-02" not in rendered
    assert len(base64.b64decode(payload["media_key"])) == 32
    assert payload["media_key"] == encode_media_key(account_id)
    assert derive_media_key(account_id) != account_id.encode("utf-8")

    owner = _to_response(profile, include_forms=True).model_dump()
    assert owner["id"] == profile.public_id
    assert owner["user_id"] == account_id
    assert any(item["value"] == secret and item["is_private"] for item in owner["contacts"])
    assert owner["forms"] == ["my-link", "other-link"]