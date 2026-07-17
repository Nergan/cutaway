import asyncio
import logging
import os
import tempfile
from contextlib import asynccontextmanager

import magic
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes

SUPPORTED_TYPE_PREFIXES = {
    "image": "image",
    "video": "video",
    "audio": "audio",
}

class UnsupportedMediaTypeError(Exception):
    pass

class MediaProcessingError(Exception):
    pass

def sniff_mime_type(data: bytes) -> str:
    return magic.from_buffer(data, mime=True)

def classify_media_type(mime_type: str) -> str:
    if mime_type == "image/gif":
        return "video"
        
    for media_type, prefix in SUPPORTED_TYPE_PREFIXES.items():
        if mime_type.startswith(prefix + "/"):
            return media_type
    raise UnsupportedMediaTypeError(f"Unsupported content type: {mime_type}")

@asynccontextmanager
async def _temp_workspace(input_bytes: bytes, output_filename: str):
    with tempfile.TemporaryDirectory() as tmp_dir:
        in_path = os.path.join(tmp_dir, "input")
        out_path = os.path.join(tmp_dir, output_filename)
        with open(in_path, "wb") as f:
            f.write(input_bytes)
        yield in_path, out_path

async def _run_ffmpeg(args: list) -> None:
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        logging.error(f"ffmpeg failed: {stderr.decode(errors='ignore')}")
        raise MediaProcessingError("Media processing failed")

def _derive_key(user_id: str) -> bytes:
    hkdf = HKDF(algorithm=hashes.SHA256(), length=32, salt=b'\x00'*32, info=b"netlazy_media_key")
    return hkdf.derive(user_id.encode('utf-8'))

def _encrypt_payload(payload: bytes, user_id: str) -> bytes:
    key = _derive_key(user_id)
    aesgcm = AESGCM(key)
    iv = os.urandom(12)
    ciphertext = aesgcm.encrypt(iv, payload, None)
    return iv + ciphertext

async def process_image(data: bytes, max_dimension: int, user_id: str) -> bytes:
    async with _temp_workspace(data, "output.webp") as (in_path, out_path):
        out_cover = in_path + "_cover.webp"
        
        await _run_ffmpeg(["-y", "-i", in_path, "-vf", "scale='min(320,iw)':-1,gblur=sigma=20", "-vframes", "1", "-quality", "50", out_cover])
        await _run_ffmpeg(["-y", "-i", in_path, "-vf", f"scale='min({max_dimension},iw)':'min({max_dimension},ih)':force_original_aspect_ratio=decrease", "-quality", "82", out_path])
        
        with open(out_cover, "rb") as f: cover_bytes = f.read()
        with open(out_path, "rb") as f: payload_bytes = f.read()
        
        return cover_bytes + b"||NLZ_PAYLOAD||" + _encrypt_payload(payload_bytes, user_id)

async def process_video(data: bytes, max_dimension: int, user_id: str) -> bytes:
    async with _temp_workspace(data, "output.mp4") as (in_path, out_path):
        out_cover = in_path + "_cover.mp4"
        
        cover_vf = "scale='min(320,iw)':'min(320,ih)':force_original_aspect_ratio=decrease,pad=ceil(iw/2)*2:ceil(ih/2)*2,gblur=sigma=20"
        await _run_ffmpeg([
            "-y", "-i", in_path, "-t", "1",
            "-vf", cover_vf,
            "-an", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "35",
            out_cover
        ])
        
        payload_vf = f"scale='min({max_dimension},iw)':'min({max_dimension},ih)':force_original_aspect_ratio=decrease,pad=ceil(iw/2)*2:ceil(ih/2)*2"
        await _run_ffmpeg([
            "-y", "-i", in_path, 
            "-vf", payload_vf, 
            "-c:v", "libx264", "-preset", "fast", "-crf", "28", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k", 
            "-movflags", "+faststart", 
            out_path
        ])
        
        with open(out_cover, "rb") as f: cover_bytes = f.read()
        with open(out_path, "rb") as f: payload_bytes = f.read()
        
        return cover_bytes + b"||NLZ_PAYLOAD||" + _encrypt_payload(payload_bytes, user_id)

async def process_audio(data: bytes, bitrate: str, user_id: str) -> bytes:
    async with _temp_workspace(data, "output.mp3") as (in_path, out_path):
        out_cover = in_path + "_cover.mp3"
        
        await _run_ffmpeg(["-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", "1", "-b:a", "32k", out_cover])
        await _run_ffmpeg(["-y", "-i", in_path, "-ac", "1", "-c:a", "libmp3lame", "-b:a", bitrate, out_path])
        
        with open(out_cover, "rb") as f: cover_bytes = f.read()
        with open(out_path, "rb") as f: payload_bytes = f.read()
        
        return cover_bytes + b"||NLZ_PAYLOAD||" + _encrypt_payload(payload_bytes, user_id)