import asyncio
import hashlib
from collections import defaultdict
from datetime import datetime, timezone
from typing import List
from netlazy.domain.models import Contact, MediaItem, Profile
from netlazy.domain.repository import MediaStorage, ProfileRepository, TagRepository
from netlazy.infrastructure import media_processor

class InvalidTagError(Exception):
    def __init__(self, unknown_tags: List[str]):
        self.unknown_tags = unknown_tags
        super().__init__(f"Unknown tags: {', '.join(unknown_tags)}")

class MediaLimitExceededError(Exception): pass
class UnsupportedMediaTypeError(Exception): pass
class MediaProcessingError(Exception): pass
class MediaNotFoundError(Exception): pass

class ProfileService:
    def __init__(
        self,
        profile_repo: ProfileRepository,
        tag_repo: TagRepository,
        media_storage: MediaStorage,
        max_media_items: int,
        max_bio_length: int,
        max_upload_bytes: int,
        image_max_dimension: int,
        audio_bitrate: str,
    ):
        self._profile_repo = profile_repo
        self._tag_repo = tag_repo
        self._media_storage = media_storage
        self._max_media_items = max_media_items
        self._max_bio_length = max_bio_length
        self._max_upload_bytes = max_upload_bytes
        self._image_max_dimension = image_max_dimension
        self._audio_bitrate = audio_bitrate
        self._locks = defaultdict(asyncio.Lock)

    async def get_or_create_profile(self, user_id: str) -> Profile:
        profile = await self._profile_repo.get_by_user_id(user_id)
        if profile: return profile
        return Profile(user_id=user_id)

    async def update_profile(self, user_id: str, bio: str, tags: List[str], contacts: List[Contact]) -> Profile:
        valid_names = set(await self._tag_repo.get_all_names())
        unknown = [t for t in tags if t not in valid_names]
        if unknown: raise InvalidTagError(unknown)

        async with self._locks[user_id]:
            profile = await self.get_or_create_profile(user_id)
            profile.bio = bio[: self._max_bio_length]
            profile.tags = tags
            profile.contacts = contacts
            profile.updated_at = datetime.now(timezone.utc)

            await self._profile_repo.upsert(profile)
            return profile

    async def upload_media(self, user_id: str, raw_bytes: bytes, blur: bool = False) -> Profile:
        if len(raw_bytes) > self._max_upload_bytes:
            raise MediaProcessingError("File exceeds maximum upload size")

        def _compute_hash(data: bytes) -> str:
            return hashlib.sha256(data).hexdigest()
            
        file_hash = await asyncio.to_thread(_compute_hash, raw_bytes)
        
        async with self._locks[user_id]:
            profile = await self.get_or_create_profile(user_id)
            existing_media = await self._profile_repo.find_media_by_hash(file_hash)
            if existing_media:
                if existing_media.media_type in ("image", "video") and len(profile.media) >= self._max_media_items:
                    raise MediaLimitExceededError(f"Maximum of {self._max_media_items} media items reached")

                item = MediaItem(
                    url=existing_media.url, 
                    media_type=existing_media.media_type, 
                    blur=blur, 
                    file_hash=file_hash,
                    public_id=existing_media.public_id,
                    resource_type=existing_media.resource_type
                )
                if existing_media.media_type == "audio":
                    profile.audio = item
                else:
                    profile.media.append(item)
                
                profile.updated_at = datetime.now(timezone.utc)
                await self._profile_repo.upsert(profile)
                return profile

        mime_type = media_processor.sniff_mime_type(raw_bytes)
        try:
            media_type = media_processor.classify_media_type(mime_type)
        except media_processor.UnsupportedMediaTypeError as e:
            raise UnsupportedMediaTypeError(str(e)) from e

        try:
            if media_type == "image":
                processed = await media_processor.process_image(raw_bytes, self._image_max_dimension)
            elif media_type == "video":
                processed = await media_processor.process_video(raw_bytes, self._image_max_dimension)
            elif media_type == "audio":
                processed = await media_processor.process_audio(raw_bytes, self._audio_bitrate)
            else:
                processed = raw_bytes
        except media_processor.MediaProcessingError as e:
            raise MediaProcessingError(str(e)) from e

        public_id_hint = f"{user_id}/{media_type}_{int(datetime.now(timezone.utc).timestamp() * 1000)}"
        
        try:
            upload_res = await self._media_storage.upload(processed, media_type, public_id_hint)
        except Exception as e:
            raise MediaProcessingError(f"CDN Upload failed: {str(e)}")

        item = MediaItem(
            url=upload_res["url"], 
            media_type=media_type, 
            blur=blur, 
            file_hash=file_hash,
            public_id=upload_res.get("public_id"),
            resource_type=upload_res.get("resource_type")
        )

        async with self._locks[user_id]:
            profile = await self.get_or_create_profile(user_id)
            if media_type in ("image", "video") and len(profile.media) >= self._max_media_items:
                raise MediaLimitExceededError(f"Maximum of {self._max_media_items} media items reached")
                
            if media_type == "audio":
                profile.audio = item
            else:
                profile.media.append(item)

            profile.updated_at = datetime.now(timezone.utc)
            await self._profile_repo.upsert(profile)
            return profile

    async def remove_media(self, user_id: str, media_url: str, index: int = None) -> Profile:
        async with self._locks[user_id]:
            profile = await self.get_or_create_profile(user_id)
            
            target = None
            if index is not None and 0 <= index < len(profile.media) and profile.media[index].url == media_url:
                target = profile.media.pop(index)
            else:
                for i, m in enumerate(profile.media):
                    if m.url == media_url:
                        target = m
                        profile.media.pop(i)
                        break
            
            if not target:
                raise MediaNotFoundError(f"No media item with url {media_url}")

            profile.updated_at = datetime.now(timezone.utc)
            await self._profile_repo.upsert(profile)

            if target.file_hash:
                count = await self._profile_repo.count_media_usage(target.file_hash)
                if count == 0:
                    await self._media_storage.delete(target.url, target.public_id, target.resource_type)

            return profile

    async def clear_audio(self, user_id: str) -> Profile:
        async with self._locks[user_id]:
            profile = await self.get_or_create_profile(user_id)
            if not profile.audio:
                return profile

            target = profile.audio
            profile.audio = None
            profile.updated_at = datetime.now(timezone.utc)
            await self._profile_repo.upsert(profile)

            if target.file_hash:
                count = await self._profile_repo.count_media_usage(target.file_hash)
                if count == 0:
                    await self._media_storage.delete(target.url, target.public_id, target.resource_type)

            return profile

    async def set_media_blur(self, user_id: str, media_url: str, blur: bool, index: int = None) -> Profile:
        async with self._locks[user_id]:
            profile = await self.get_or_create_profile(user_id)
            found = False
            
            if index is not None and 0 <= index < len(profile.media) and profile.media[index].url == media_url:
                profile.media[index].blur = blur
                found = True
            else:
                for m in profile.media:
                    if m.url == media_url:
                        m.blur = blur
                        found = True
                        break
                if not found and profile.audio and profile.audio.url == media_url:
                    profile.audio.blur = blur
                    found = True
                    
            if not found:
                raise MediaNotFoundError(f"No media item with url {media_url}")

            profile.updated_at = datetime.now(timezone.utc)
            await self._profile_repo.upsert(profile)
            return profile

    async def reorder_media(self, user_id: str, ordered_urls: List[str]) -> Profile:
        async with self._locks[user_id]:
            profile = await self.get_or_create_profile(user_id)
            current_urls = {m.url for m in profile.media}
            
            if set(ordered_urls) != current_urls or len(ordered_urls) != len(profile.media):
                raise ValueError("Payload must contain the exact current URLs for reordering")

            url_to_media = {m.url: m for m in profile.media}
            profile.media = [url_to_media[url] for url in ordered_urls]
            profile.updated_at = datetime.now(timezone.utc)
            await self._profile_repo.upsert(profile)
            return profile

    async def delete_profile(self, user_id: str) -> None:
        async with self._locks[user_id]:
            profile = await self._profile_repo.get_by_user_id(user_id)
            if profile:
                media_items = profile.media + ([profile.audio] if profile.audio else [])
                await self._profile_repo.delete(user_id)
                
                for m in media_items:
                    if m.file_hash:
                        count = await self._profile_repo.count_media_usage(m.file_hash)
                        if count == 0:
                            await self._media_storage.delete(m.url, m.public_id, m.resource_type)