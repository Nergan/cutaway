import asyncio
import os
import re
import io
from typing import Optional
import cloudinary
import cloudinary.uploader
from netlazy.config import settings
from netlazy.domain.repository import MediaStorage

cloudinary.config(
    cloud_name=settings.cloudinary_cloud_name,
    api_key=settings.cloudinary_api_key,
    api_secret=settings.cloudinary_api_secret,
    secure=True,
    timeout=15,
    urllib3_kwargs={'maxsize': 10}
)

# Force "raw" to ensure Cloudinary doesn't strip our custom payload bytes trying to optimize it natively.
_RESOURCE_TYPE_MAP = {"image": "raw", "video": "raw", "audio": "raw"}
_CLOUDINARY_SLOTS = asyncio.Semaphore(
    max(1, int(os.getenv("CUTAWAY_CLOUDINARY_CONCURRENCY", "2")))
)

class CloudinaryMediaStorage(MediaStorage):
    async def upload(self, file_bytes: bytes, media_type: str, public_id_hint: str) -> dict:
        resource_type = _RESOURCE_TYPE_MAP.get(media_type, "raw")
        file_obj = io.BytesIO(file_bytes)
        
        async with _CLOUDINARY_SLOTS:
            result = await asyncio.wait_for(
                asyncio.to_thread(
                    cloudinary.uploader.upload,
                    file_obj,
                    resource_type=resource_type,
                    public_id=public_id_hint,
                    overwrite=True,
                ),
                timeout=30,
            )
        return {
            "url": result["secure_url"],
            "public_id": result.get("public_id"),
            "resource_type": result.get("resource_type")
        }

    async def delete(self, url: str, public_id: Optional[str] = None, resource_type: Optional[str] = None) -> None:
        try:
            async with _CLOUDINARY_SLOTS:
                if public_id and resource_type:
                    await asyncio.wait_for(
                        asyncio.to_thread(
                            cloudinary.uploader.destroy,
                            public_id,
                            resource_type=resource_type,
                        ),
                        timeout=30,
                    )
                else:
                    match = re.search(r'/upload/(?:v\d+/)?(.+?)(?:\.[a-zA-Z0-9]+)?$', url)
                    if match:
                        pid = match.group(1)
                        await asyncio.wait_for(
                            asyncio.to_thread(
                                cloudinary.uploader.destroy,
                                pid,
                                resource_type="raw",
                            ),
                            timeout=30,
                        )
                        rtype = "image" if "image" in url else "video"
                        await asyncio.wait_for(
                            asyncio.to_thread(
                                cloudinary.uploader.destroy,
                                pid,
                                resource_type=rtype,
                            ),
                            timeout=30,
                        )
        except Exception:
            pass