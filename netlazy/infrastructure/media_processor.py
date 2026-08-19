import asyncio
import logging
import os
import tempfile
from contextlib import asynccontextmanager

import magic
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes
from netlazy.domain.repository import MediaProcessorPort, UnsupportedMediaTypeError, MediaProcessingError

SUPPORTED_TYPE_PREFIXES = {
    "image": "image",
    "video": "video",
    "audio": "audio",
}

class FFmpegMediaProcessor(MediaProcessorPort):
    def __init__(self, timeout_seconds: float = 60.0):
        self.timeout_seconds = timeout_seconds

    def sniff_mime_type(self, data: bytes) -> str:
        return magic.from_buffer(data, mime=True)

    def classify_media_type(self, mime_type: str) -> str:
        if mime_type == "image/gif":
            return "video"
            
        for media_type, prefix in SUPPORTED_TYPE_PREFIXES.items():
            if mime_type.startswith(prefix + "/"):
                return media_type
        raise UnsupportedMediaTypeError(f"Unsupported content type: {mime_type}")

    @asynccontextmanager
    async def _temp_workspace(self, input_bytes: bytes, output_filename: str):
        with tempfile.TemporaryDirectory() as tmp_dir:
            in_path = os.path.join(tmp_dir, "input")
            out_path = os.path.join(tmp_dir, output_filename)
            with open(in_path, "wb") as f:
                f.write(input_bytes)
            yield in_path, out_path

    async def _run_ffmpeg(self, args: list) -> None:
        safe_args = ["-protocol_whitelist", "file,crypto,data"] + args
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", *safe_args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            # FIX: Introduce execution timeout to prevent infinite transcoder hanging (Issue 10)
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=self.timeout_seconds)
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            logging.error("ffmpeg process timed out and was killed.")
            raise MediaProcessingError("Media processing timed out")

        if proc.returncode != 0:
            logging.error(f"ffmpeg failed: {stderr.decode(errors='ignore')}")
            raise MediaProcessingError("Media processing failed")

    def _derive_key(self, user_id: str) -> bytes:
        hkdf = HKDF(algorithm=hashes.SHA256(), length=32, salt=b'\x00'*32, info=b"netlazy_media_key")
        return hkdf.derive(user_id.encode('utf-8'))

    def _encrypt_payload(self, payload: bytes, user_id: str) -> bytes:
        key = self._derive_key(user_id)
        aesgcm = AESGCM(key)
        iv = os.urandom(12)
        ciphertext = aesgcm.encrypt(iv, payload, None)
        return iv + ciphertext

    async def process_image(self, data: bytes, max_dimension: int, user_id: str) -> bytes:
        async with self._temp_workspace(data, "output.webp") as (in_path, out_path):
            out_cover = in_path + "_cover.webp"
            
            cover_vf = "scale=16:16,scale=320:320:flags=neighbor,gblur=sigma=20,eq=saturation=1.5"
            await self._run_ffmpeg(["-y", "-i", in_path, "-vf", cover_vf, "-vframes", "1", "-quality", "50", out_cover])
            
            await self._run_ffmpeg(["-y", "-i", in_path, "-vf", f"scale='min({max_dimension},iw)':'min({max_dimension},ih)':force_original_aspect_ratio=decrease", "-quality", "82", out_path])
            
            with open(out_cover, "rb") as f: cover_bytes = f.read()
            with open(out_path, "rb") as f: payload_bytes = f.read()
            
            return cover_bytes + b"||NLZ_PAYLOAD||" + self._encrypt_payload(payload_bytes, user_id)

    async def process_video(self, data: bytes, max_dimension: int, user_id: str) -> bytes:
        async with self._temp_workspace(data, "output.mp4") as (in_path, out_path):
            out_cover = in_path + "_cover.mp4"
            
            cover_vf = "scale=16:16,scale=320:320:flags=neighbor,gblur=sigma=20,eq=saturation=1.5"
            await self._run_ffmpeg([
                "-y", "-i", in_path, "-vframes", "1",
                "-vf", cover_vf,
                "-an", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "35",
                out_cover
            ])
            
            payload_vf = f"scale='min({max_dimension},iw)':'min({max_dimension},ih)':force_original_aspect_ratio=decrease,pad=ceil(iw/2)*2:ceil(ih/2)*2"
            
            await self._run_ffmpeg([
                "-y", "-i", in_path, 
                "-vf", payload_vf, 
                "-c:v", "libx264", "-preset", "fast", "-crf", "28", "-pix_fmt", "yuv420p",
                "-movflags", "+faststart", 
                out_path
            ])
            
            with open(out_cover, "rb") as f: cover_bytes = f.read()
            with open(out_path, "rb") as f: payload_bytes = f.read()
            
            return cover_bytes + b"||NLZ_PAYLOAD||" + self._encrypt_payload(payload_bytes, user_id)

    async def process_audio(self, data: bytes, bitrate: str, user_id: str) -> bytes:
        async with self._temp_workspace(data, "output.mp3") as (in_path, out_path):
            out_cover = in_path + "_cover.mp3"
            
            await self._run_ffmpeg(["-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", "1", "-b:a", "32k", out_cover])
            await self._run_ffmpeg(["-y", "-i", in_path, "-ac", "1", "-c:a", "libmp3lame", "-b:a", bitrate, out_path])
            
            with open(out_cover, "rb") as f: cover_bytes = f.read()
            with open(out_path, "rb") as f: payload_bytes = f.read()
            
            return cover_bytes + b"||NLZ_PAYLOAD||" + self._encrypt_payload(payload_bytes, user_id)