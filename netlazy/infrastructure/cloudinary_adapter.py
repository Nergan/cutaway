import asyncio
import re
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
    urllib3_kwargs={'maxsize': 10}
)

_RESOURCE_TYPE_MAP = {"image": "raw", "video": "raw", "audio": "raw"}

class CloudinaryMediaStorage(MediaStorage):
    async def upload(self, file_bytes: bytes, media_type: str, public_id_hint: str) -> dict:
        resource_type = _RESOURCE_TYPE_MAP.get(media_type, "raw")
        
        result = await asyncio.to_thread(
            cloudinary.uploader.upload,
            file_bytes,
            resource_type=resource_type,
            public_id=public_id_hint,
            overwrite=True,
        )
        return {
            "url": result["secure_url"],
            "public_id": result.get("public_id"),
            "resource_type": result.get("resource_type")
        }

    async def delete(self, url: str, public_id: Optional[str] = None, resource_type: Optional[str] = None) -> None:
        try:
            if public_id and resource_type:
                await asyncio.to_thread(cloudinary.uploader.destroy, public_id, resource_type=resource_type)
            else:
                match = re.search(r'/upload/(?:v\d+/)?(.+?)(?:\.[a-zA-Z0-9]+)?$', url)
                if match:
                    pid = match.group(1)
                    await asyncio.to_thread(cloudinary.uploader.destroy, pid, resource_type="raw")
                    rtype = "image" if "image" in url else "video"
                    await asyncio.to_thread(cloudinary.uploader.destroy, pid, resource_type=rtype)
        except Exception:
            pass # Suppress Cloudinary 404s if the file is already gone to prevent false failure cascades