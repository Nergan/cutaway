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

# A simple fast XOR cipher table to deterministically obfuscate bytes before CDN upload
_XOR_TABLE = bytes(b ^ 0x42 for b in range(256))

class CloudinaryMediaStorage(MediaStorage):
    async def upload(self, file_bytes: bytes, media_type: str, public_id_hint: str) -> dict:
        # Deterministically distort the file so it appears as noise/unreadable in the CDN
        obfuscated_bytes = file_bytes.translate(_XOR_TABLE)
        
        result = await asyncio.to_thread(
            cloudinary.uploader.upload,
            obfuscated_bytes,
            resource_type="raw", # Crucial: forces CDN to store it as arbitrary bytes without applying transformations
            public_id=public_id_hint,
            overwrite=True,
        )
        return {
            "url": result["secure_url"],
            "public_id": result.get("public_id"),
            "resource_type": "raw"
        }

    async def delete(self, url: str, public_id: Optional[str] = None, resource_type: Optional[str] = None) -> None:
        if public_id:
            await asyncio.to_thread(cloudinary.uploader.destroy, public_id, resource_type="raw")
        else:
            match = re.search(r'/upload/(?:v\d+/)?(.+?)(?:\.[a-zA-Z0-9]+)?$', url)
            if match:
                pid = match.group(1)
                await asyncio.to_thread(cloudinary.uploader.destroy, pid, resource_type="raw")