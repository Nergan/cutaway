import asyncio
import logging
import os
import tempfile
from contextlib import asynccontextmanager

import magic

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

async def process_image(data: bytes, max_dimension: int) -> bytes:
    async with _temp_workspace(data, "output.webp") as (in_path, out_path):
        # Swaps RGB channels + inverts + hue rotates + flips axes (alien camouflage)
        scale_filter = f"scale='min({max_dimension},iw)':'min({max_dimension},ih)':force_original_aspect_ratio=decrease,colorchannelmixer=0:0:1:0:1:0:0:0:0:1:0:0,negate,hue=h=180,hflip,vflip"
        await _run_ffmpeg(["-y", "-i", in_path, "-vf", scale_filter, "-quality", "82", out_path])
        with open(out_path, "rb") as f:
            return f.read()

async def process_video(data: bytes, max_dimension: int) -> bytes:
    async with _temp_workspace(data, "output.mp4") as (in_path, out_path):
        scale_filter = f"scale='min({max_dimension},iw)':'min({max_dimension},ih)':force_original_aspect_ratio=decrease,pad=ceil(iw/2)*2:ceil(ih/2)*2,colorchannelmixer=0:0:1:0:1:0:0:0:0:1:0:0,negate,hue=h=180,hflip,vflip"
        await _run_ffmpeg([
            "-y", "-i", in_path, 
            "-vf", scale_filter, 
            "-c:v", "libx264", "-preset", "fast", "-crf", "28", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k", 
            "-movflags", "+faststart", 
            out_path
        ])
        with open(out_path, "rb") as f:
            return f.read()

async def process_audio(data: bytes, bitrate: str) -> bytes:
    async with _temp_workspace(data, "output.mp3") as (in_path, out_path):
        # areverse physically plays the audio backwards (unintelligible noise to CDN admins & speech-to-text)
        await _run_ffmpeg(["-y", "-i", in_path, "-af", "areverse", "-ac", "1", "-c:a", "libmp3lame", "-b:a", bitrate, out_path])
        with open(out_path, "rb") as f:
            return f.read()