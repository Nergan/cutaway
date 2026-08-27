"""Image storage for Soon: hash dedup, Cloudinary raw upload, cover+payload mask."""

from __future__ import annotations

import asyncio
import hashlib
import io
import logging
import os
import re
from typing import Any
from urllib.parse import urlparse

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from PIL import Image, ImageFilter, ImageOps

logger = logging.getLogger(__name__)

MEDIA_HASH_RE = re.compile(r"^[a-f0-9]{64}$")
MARKER = b"||NLZ_PAYLOAD||"
KEY_ID = b"soon-board"
KEY_INFO = b"soon_media_key"
MAX_EDGE = 1600
COVER_EDGE = 320
WEBP_QUALITY = 82

_CLOUDINARY_SLOTS = asyncio.Semaphore(
    max(1, int(os.getenv("CUTAWAY_CLOUDINARY_CONCURRENCY", "2")))
)


def file_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def cloudinary_ready() -> bool:
    has_url = bool(os.getenv("CLOUDINARY_URL"))
    has_parts = bool(
        os.getenv("CLOUDINARY_CLOUD_NAME") and os.getenv("CLOUDINARY_API_SECRET")
    )
    if not (has_url or has_parts):
        return False
    try:
        import cloudinary  # noqa: F401
    except ImportError:
        return False
    return True


def configure_cloudinary() -> None:
    import cloudinary

    if os.getenv("CLOUDINARY_URL"):
        cloudinary.config(secure=True, timeout=15)
        return
    cloudinary.config(
        cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
        api_key=os.getenv("CLOUDINARY_API_KEY"),
        api_secret=os.getenv("CLOUDINARY_API_SECRET"),
        secure=True,
        timeout=15,
    )


def is_cdn_url(value: str) -> bool:
    host = (urlparse(value).hostname or "").lower()
    return host == "res.cloudinary.com" or host.endswith(".cloudinary.com")


def _derive_key() -> bytes:
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"\x00" * 32,
        info=KEY_INFO,
    ).derive(KEY_ID)


def _encrypt(payload: bytes) -> bytes:
    key = _derive_key()
    iv = os.urandom(12)
    return iv + AESGCM(key).encrypt(iv, payload, None)


def _decrypt(blob: bytes) -> bytes:
    if len(blob) < 13:
        raise ValueError("Masked payload is truncated.")
    key = _derive_key()
    return AESGCM(key).decrypt(blob[:12], blob[12:], None)


def _open_image(data: bytes) -> Image.Image:
    image = Image.open(io.BytesIO(data))
    image = ImageOps.exif_transpose(image)
    image.load()
    return image


def _as_display(image: Image.Image) -> Image.Image:
    if image.mode in {"RGBA", "LA"}:
        return image.convert("RGBA")
    if image.mode == "P":
        return image.convert("RGBA" if "transparency" in image.info else "RGB")
    return image.convert("RGB")


def compress_image(data: bytes, max_edge: int = MAX_EDGE) -> bytes:
    image = _as_display(_open_image(data))
    image.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
    if image.width < 1 or image.height < 1:
        raise ValueError("Invalid image.")
    out = io.BytesIO()
    image.save(out, format="WEBP", quality=WEBP_QUALITY, method=6)
    payload = out.getvalue()
    if not payload:
        raise ValueError("Could not compress image.")
    return payload


def _cover_bytes(data: bytes) -> bytes:
    image = _as_display(_open_image(data)).convert("RGB")
    image = image.resize((16, 16), Image.Resampling.NEAREST)
    image = image.resize((COVER_EDGE, COVER_EDGE), Image.Resampling.NEAREST)
    image = image.filter(ImageFilter.GaussianBlur(20))
    out = io.BytesIO()
    image.save(out, format="WEBP", quality=50, method=4)
    return out.getvalue()


def mask_image(data: bytes) -> bytes:
    """Blur cover + encrypted WebP so Cloudinary only sees the cover as raw bytes."""
    payload = compress_image(data)
    try:
        cover = _cover_bytes(data)
    except Exception:
        cover = _cover_bytes(payload)
    return cover + MARKER + _encrypt(payload)


def is_masked(data: bytes) -> bool:
    return MARKER in data


def unmask_image(data: bytes) -> bytes:
    index = data.find(MARKER)
    if index < 0:
        return data
    return _decrypt(data[index + len(MARKER) :])


async def cloudinary_upload_raw(data: bytes, public_id: str) -> dict[str, str]:
    import cloudinary.uploader

    configure_cloudinary()
    file_obj = io.BytesIO(data)
    async with _CLOUDINARY_SLOTS:
        result = await asyncio.wait_for(
            asyncio.to_thread(
                cloudinary.uploader.upload,
                file_obj,
                resource_type="raw",
                public_id=public_id,
                overwrite=True,
                unique_filename=False,
                use_filename=False,
            ),
            timeout=30,
        )
    url = result.get("secure_url") or result.get("url")
    pid = result.get("public_id") or public_id
    if not url or not pid:
        raise RuntimeError("Cloudinary upload returned no url.")
    return {
        "url": str(url),
        "public_id": str(pid),
        "resource_type": str(result.get("resource_type") or "raw"),
    }


async def cloudinary_destroy(public_id: str, resource_type: str = "raw") -> None:
    if not public_id:
        return
    import cloudinary.uploader

    configure_cloudinary()
    try:
        async with _CLOUDINARY_SLOTS:
            await asyncio.wait_for(
                asyncio.to_thread(
                    cloudinary.uploader.destroy,
                    public_id,
                    resource_type=resource_type or "raw",
                ),
                timeout=30,
            )
    except Exception:
        logger.exception("soon: cloudinary destroy failed for %s", public_id)


async def find_media_by_hash(db: Any, digest: str) -> dict[str, Any] | None:
    if not digest:
        return None
    doc = await db.media.find_one({"hash": digest})
    return doc if isinstance(doc, dict) else None


async def store_image(db: Any, data: bytes, filename: str) -> dict[str, str]:
    digest = file_hash(data)
    existing = await find_media_by_hash(db, digest)
    if existing and existing.get("url") and existing.get("public_id"):
        return {
            "id": digest,
            "url": str(existing["url"]),
            "mime": "image/webp",
            "filename": filename,
            "kind": "image",
        }

    wrapped = await asyncio.to_thread(mask_image, data)
    uploaded: dict[str, str] | None = None
    try:
        uploaded = await cloudinary_upload_raw(wrapped, f"soon/{digest}")
        await db.media.update_one(
            {"hash": digest},
            {
                "$set": {
                    "hash": digest,
                    "public_id": uploaded["public_id"],
                    "url": uploaded["url"],
                    "resource_type": uploaded["resource_type"],
                    "mime": "image/webp",
                }
            },
            upsert=True,
        )
    except Exception:
        if uploaded and uploaded.get("public_id"):
            await cloudinary_destroy(
                uploaded["public_id"], uploaded.get("resource_type") or "raw"
            )
        raise
    return {
        "id": digest,
        "url": uploaded["url"],
        "mime": "image/webp",
        "filename": filename,
        "kind": "image",
    }


async def count_media_usage(db: Any, media_id: str) -> int:
    if not media_id:
        return 0
    return int(await db.objects.count_documents({"data.media_id": media_id}))


async def release_media(db: Any, fs: Any, media_id: str) -> None:
    if not media_id:
        return
    if await count_media_usage(db, media_id) > 0:
        return
    if MEDIA_HASH_RE.fullmatch(media_id):
        doc = await find_media_by_hash(db, media_id)
        if doc:
            await cloudinary_destroy(
                str(doc.get("public_id") or ""),
                str(doc.get("resource_type") or "raw"),
            )
            await db.media.delete_one({"hash": media_id})
        return
    try:
        from bson import ObjectId
        from bson.errors import InvalidId
        from gridfs.errors import NoFile

        await fs.delete(ObjectId(media_id))
    except (InvalidId, TypeError, NoFile, Exception):
        return
