"""Public collaborative canvas. No accounts; one shared board per room."""

from __future__ import annotations

import asyncio
import io
import logging
import os
import re
import secrets
import sys
from collections import deque
from pathlib import Path
from typing import Any
from urllib.request import urlopen

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import FileResponse, RedirectResponse, Response
from gridfs.errors import NoFile
from motor.motor_asyncio import AsyncIOMotorGridFSBucket
from pymongo.errors import PyMongoError

try:
    from soon.media_store import (
        MEDIA_HASH_RE,
        cloudinary_ready,
        count_media_usage,
        find_media_by_hash,
        is_cdn_url,
        release_media,
        store_image,
        unmask_image,
    )
except ImportError:
    from media_store import (
        MEDIA_HASH_RE,
        cloudinary_ready,
        count_media_usage,
        find_media_by_hash,
        is_cdn_url,
        release_media,
        store_image,
        unmask_image,
    )

router = APIRouter()
BASE_DIR = Path(__file__).parent

sys.path.append(str(BASE_DIR.parent))
try:
    from dotenv import load_dotenv

    load_dotenv(BASE_DIR.parent / ".env")
except Exception:
    pass
from shared_limits import RateLimiter, body_size_limit
from shared_mongo import get_client

logger = logging.getLogger(__name__)

ROOM_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,32}$")
COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
RGBA_RE = re.compile(
    r"^rgba?\(\s*([0-9]{1,3})\s*,\s*([0-9]{1,3})\s*,\s*([0-9]{1,3})"
    r"(?:\s*,\s*(0|1|0?\.[0-9]+))?\s*\)$",
    re.IGNORECASE,
)
EMOJI_RE = re.compile(r"^[\S]{1,8}$")
HTTPS_RE = re.compile(r"^https://[^\s]{3,500}$", re.IGNORECASE)

MAX_OBJECTS = 500
MAX_POINTS = 1000
MAX_TEXT = 2000
MAX_CHAT = 300
MAX_CHAT_TEXT = 240
WS_IDLE = 40.0
MAX_MEDIA_BYTES = 1_500_000
MAX_COORD = 1_000_000.0
MIN_IMAGE = 24.0
MAX_IMAGE = MAX_COORD
DEFAULT_ROOM = "board"

OBJECT_TYPES = frozenset(
    {"stroke", "shape", "text", "note", "image", "file", "stamp", "link"}
)
SHAPE_KINDS = frozenset({"line", "rect", "ellipse", "arrow"})
IMAGE_MIMES = frozenset(
    {"image/png", "image/jpeg", "image/gif", "image/webp"}
)
FILE_MIMES = frozenset(
    {
        "application/pdf",
        "audio/mpeg",
        "audio/ogg",
        "audio/wav",
        "video/webm",
    }
)
ALLOWED_MIMES = IMAGE_MIMES | FILE_MIMES

ADJECTIVES = (
    "тихий", "янтарный", "медный", "тёплый", "лесной", "пыльный",
    "рыжий", "ночной", "медовый", "бронзовый", "дымный", "осенний",
)
NOUNS = (
    "лис", "мох", "дуб", "коршун", "клён", "барсук",
    "грач", "рысь", "ёж", "филин", "кедр", "шакал",
)

upload_guards = [
    Depends(body_size_limit(MAX_MEDIA_BYTES + 64_000)),
    Depends(RateLimiter(limit=12, window_seconds=60)),
]


def _db():
    return get_client()["soon"]


def _fs() -> AsyncIOMotorGridFSBucket:
    return AsyncIOMotorGridFSBucket(_db(), bucket_name="media")


def sniff_mime(data: bytes) -> str | None:
    if len(data) < 12:
        return None
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    if data.startswith(b"%PDF"):
        return "application/pdf"
    if data.startswith(b"ID3") or data[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"):
        return "audio/mpeg"
    if data.startswith(b"OggS"):
        return "audio/ogg"
    if data.startswith(b"RIFF") and data[8:12] == b"WAVE":
        return "audio/wav"
    if data.startswith(b"\x1a\x45\xdf\xa3"):
        return "video/webm"
    return None


def _finite(value: Any, lo: float = -MAX_COORD, hi: float = MAX_COORD) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Expected a number.")
    number = float(value)
    if number != number or number in (float("inf"), float("-inf")):
        raise ValueError("Non-finite number.")
    if number < lo or number > hi:
        raise ValueError("Number out of range.")
    return round(number, 2)


def _int(value: Any, lo: int, hi: int) -> int:
    number = _finite(value, lo, hi)
    return int(round(number))


def _color(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("Invalid color.")
    raw = value.strip()
    if COLOR_RE.fullmatch(raw):
        return raw.lower()
    match = RGBA_RE.fullmatch(raw)
    if match:
        red, green, blue = (int(match.group(index)) for index in range(1, 4))
        if red > 255 or green > 255 or blue > 255:
            raise ValueError("Invalid color.")
        return f"#{red:02x}{green:02x}{blue:02x}"
    raise ValueError("Invalid color.")


def _chat_text(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("Invalid chat.")
    text = " ".join(value.split())
    if not (1 <= len(text) <= MAX_CHAT_TEXT):
        raise ValueError("Invalid chat.")
    return text


def _text(value: Any, limit: int = MAX_TEXT) -> str:
    if not isinstance(value, str):
        raise ValueError("Invalid text.")
    text = value.replace("\x00", "")[:limit]
    return text


def _oid(value: Any) -> str:
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise ValueError("Invalid object id.")
    return value


def _media_id(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("Invalid media id.")
    if MEDIA_HASH_RE.fullmatch(value):
        return value
    try:
        return str(ObjectId(value))
    except (InvalidId, TypeError) as exc:
        raise ValueError("Invalid media id.") from exc


def _url(value: Any) -> str:
    if not isinstance(value, str) or not HTTPS_RE.fullmatch(value.strip()):
        raise ValueError("Only https links are allowed.")
    url = value.strip()
    lowered = url.lower()
    if lowered.startswith("https://javascript:") or "javascript:" in lowered:
        raise ValueError("Rejected link.")
    return url


def _cdn_url(value: Any) -> str:
    url = _url(value)
    if not is_cdn_url(url):
        raise ValueError("Rejected media url.")
    return url


def normalize_room(name: str | None) -> str:
    room = (name or DEFAULT_ROOM).strip().lower()
    if not ROOM_RE.fullmatch(room):
        raise ValueError("Invalid room name.")
    return room


def validate_object(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("Object must be a map.")
    obj_type = raw.get("type")
    if obj_type not in OBJECT_TYPES:
        raise ValueError("Unknown object type.")
    obj: dict[str, Any] = {
        "id": _oid(raw.get("id")),
        "type": obj_type,
        "z": _int(raw.get("z", 1), 0, 1_000_000),
        "rot": round(_finite(raw.get("rot", 0), -360, 360) % 360, 2),
    }
    if obj_type == "stroke":
        points = raw.get("points")
        if not isinstance(points, list) or not (2 <= len(points) <= MAX_POINTS):
            raise ValueError(f"Stroke needs 2–{MAX_POINTS} points.")
        cleaned: list[list[float]] = []
        for point in points:
            if not isinstance(point, (list, tuple)) or len(point) != 2:
                raise ValueError("Invalid point.")
            cleaned.append([_finite(point[0]), _finite(point[1])])
        obj["points"] = cleaned
        obj["color"] = _color(raw.get("color", "#d4a373"))
        obj["width"] = _finite(raw.get("width", 3), 0.5, 100)
        obj["alpha"] = _finite(raw.get("alpha", 1), 0, 1)
    elif obj_type == "shape":
        kind = raw.get("kind")
        if kind not in SHAPE_KINDS:
            raise ValueError("Unknown shape.")
        obj["kind"] = kind
        obj["x1"] = _finite(raw.get("x1", 0))
        obj["y1"] = _finite(raw.get("y1", 0))
        obj["x2"] = _finite(raw.get("x2", 0))
        obj["y2"] = _finite(raw.get("y2", 0))
        obj["color"] = _color(raw.get("color", "#d4a373"))
        obj["width"] = _finite(raw.get("width", 2), 0.5, 40)
        fill = raw.get("fill")
        if fill:
            obj["fill"] = _color(fill)
    elif obj_type == "text":
        obj["x"] = _finite(raw.get("x", 0))
        obj["y"] = _finite(raw.get("y", 0))
        obj["text"] = _text(raw.get("text", ""))
        obj["color"] = _color(raw.get("color", "#e5e1db"))
        obj["size"] = _finite(raw.get("size", 18), 10, 96)
    elif obj_type == "note":
        obj["x"] = _finite(raw.get("x", 0))
        obj["y"] = _finite(raw.get("y", 0))
        obj["w"] = _finite(raw.get("w", 180), 80, 640)
        obj["h"] = _finite(raw.get("h", 120), 60, 480)
        obj["text"] = _text(raw.get("text", ""))
        obj["color"] = _color(raw.get("color", "#4a3c31"))
    elif obj_type in {"image", "file"}:
        obj["x"] = _finite(raw.get("x", 0))
        obj["y"] = _finite(raw.get("y", 0))
        obj["w"] = _finite(raw.get("w", 240), MIN_IMAGE, MAX_IMAGE)
        obj["h"] = _finite(raw.get("h", 180), MIN_IMAGE, MAX_IMAGE)
        obj["media_id"] = _media_id(raw.get("media_id"))
        obj["alpha"] = _finite(raw.get("alpha", 1), 0, 1)
        if obj_type == "image" and raw.get("media_url"):
            obj["media_url"] = _cdn_url(raw.get("media_url"))
        if obj_type == "file":
            obj["filename"] = _text(raw.get("filename", "file"), 180)
            mime = raw.get("mime")
            if mime not in FILE_MIMES:
                raise ValueError("Unsupported file type.")
            obj["mime"] = mime
    elif obj_type == "stamp":
        obj["x"] = _finite(raw.get("x", 0))
        obj["y"] = _finite(raw.get("y", 0))
        obj["size"] = _finite(raw.get("size", 48), 16, 160)
        emoji = raw.get("emoji", "✦")
        if not isinstance(emoji, str) or not EMOJI_RE.fullmatch(emoji.strip()):
            raise ValueError("Invalid stamp.")
        obj["emoji"] = emoji.strip()
    elif obj_type == "link":
        obj["x"] = _finite(raw.get("x", 0))
        obj["y"] = _finite(raw.get("y", 0))
        obj["w"] = _finite(raw.get("w", 260), 120, 640)
        obj["h"] = _finite(raw.get("h", 72), 48, 160)
        obj["url"] = _url(raw.get("url"))
        obj["title"] = _text(raw.get("title") or obj["url"], 180)
    return obj


def apply_op(store: dict[str, dict[str, Any]], msg: dict[str, Any]) -> dict[str, Any]:
    op = msg.get("op")
    if op == "add":
        obj = validate_object(msg.get("object"))
        if obj["id"] not in store and len(store) >= MAX_OBJECTS:
            raise ValueError("Board is full.")
        store[obj["id"]] = obj
        return {"op": "add", "object": obj}
    if op == "update":
        obj = validate_object(msg.get("object"))
        previous = store.get(obj["id"])
        if previous is None:
            if len(store) >= MAX_OBJECTS:
                raise ValueError("Board is full.")
            store[obj["id"]] = obj
            return {"op": "add", "object": obj}
        store[obj["id"]] = obj
        result: dict[str, Any] = {"op": "update", "object": obj}
        old_media = previous.get("media_id")
        if old_media and old_media != obj.get("media_id"):
            result["released_media_id"] = old_media
        return result
    if op == "delete":
        oid = _oid(msg.get("id"))
        removed = store.pop(oid, None)
        payload: dict[str, Any] = {"op": "delete", "id": oid}
        if removed is not None:
            payload["object"] = removed
        return payload
    if op == "clear":
        media_ids = list(
            dict.fromkeys(
                obj["media_id"]
                for obj in store.values()
                if obj.get("media_id")
            )
        )
        store.clear()
        return {"op": "clear", "media_ids": media_ids}
    raise ValueError("Unknown op.")


class Room:
    def __init__(self, name: str):
        self.name = name
        self.objects: dict[str, dict[str, Any]] = {}
        self.clients: dict[str, WebSocket] = {}
        self.presence: dict[str, dict[str, Any]] = {}
        self.chat: deque[dict[str, Any]] = deque(maxlen=MAX_CHAT)
        self.lock = asyncio.Lock()
        self.loaded = False


class Hub:
    def __init__(self) -> None:
        self.rooms: dict[str, Room] = {}
        self.mongo_ok = False
        self._lock = asyncio.Lock()

    async def room(self, name: str) -> Room:
        async with self._lock:
            room = self.rooms.get(name)
            if room is None:
                room = Room(name)
                self.rooms[name] = room
        async with room.lock:
            if not room.loaded:
                await self._load(room)
                room.loaded = True
        return room

    async def _load(self, room: Room) -> None:
        if not self.mongo_ok:
            return
        try:
            cursor = _db().objects.find({"room": room.name})
            async for doc in cursor:
                data = doc.get("data")
                if isinstance(data, dict) and isinstance(data.get("id"), str):
                    try:
                        room.objects[data["id"]] = validate_object(data)
                    except ValueError:
                        continue
        except PyMongoError:
            logger.exception("soon: failed to load room %s", room.name)

    async def persist(self, room: Room, op: dict[str, Any]) -> None:
        if not self.mongo_ok:
            return
        collection = _db().objects
        released: list[str] = []
        try:
            kind = op["op"]
            if kind in {"add", "update"}:
                obj = op["object"]
                await collection.replace_one(
                    {"room": room.name, "oid": obj["id"]},
                    {"room": room.name, "oid": obj["id"], "data": obj},
                    upsert=True,
                )
                mid = op.get("released_media_id")
                if isinstance(mid, str) and mid:
                    released.append(mid)
            elif kind == "delete":
                await collection.delete_one({"room": room.name, "oid": op["id"]})
                obj = op.get("object")
                if isinstance(obj, dict) and isinstance(obj.get("media_id"), str):
                    released.append(obj["media_id"])
            elif kind == "clear":
                await collection.delete_many({"room": room.name})
                released.extend(
                    mid for mid in op.get("media_ids") or [] if isinstance(mid, str)
                )
        except PyMongoError:
            logger.exception("soon: persist failed for room %s", room.name)
            return
        for media_id in released:
            await _gc_media(media_id)


hub = Hub()


def _guest_name(taken: set[str] | None = None) -> str:
    taken = taken or set()
    for _ in range(40):
        name = f"{secrets.choice(ADJECTIVES)}-{secrets.choice(NOUNS)}"
        if name.casefold() not in taken:
            return name
    return f"гость-{secrets.token_hex(3)}"


def taken_names(presence: dict[str, dict[str, Any]], skip: str | None = None) -> set[str]:
    return {
        str(info.get("name", "")).casefold()
        for client_id, info in presence.items()
        if client_id != skip and info.get("name")
    }


def claim_name(presence: dict[str, dict[str, Any]], client_id: str, raw: Any) -> str:
    name = _text(raw if isinstance(raw, str) else "", 24).strip()
    if len(name) < 2:
        raise ValueError("Слишком короткое имя.")
    if name.casefold() in taken_names(presence, skip=client_id):
        raise ValueError("Это имя уже занято.")
    return name


def session_id(raw: Any) -> str:
    if isinstance(raw, str) and ID_RE.fullmatch(raw):
        return raw
    return secrets.token_hex(8)


def _guest_color(seed: str) -> str:
    palette = (
        "#d4a373", "#d98a59", "#e65c5c", "#a3e09d",
        "#7eb8d4", "#c9a0dc", "#e8dbce", "#f0ebe1",
    )
    return palette[sum(ord(ch) for ch in seed) % len(palette)]


async def _broadcast(room: Room, payload: dict[str, Any], skip: str | None = None) -> None:
    dead: list[str] = []
    for client_id, websocket in list(room.clients.items()):
        if client_id == skip:
            continue
        try:
            await websocket.send_json(payload)
        except Exception:
            dead.append(client_id)
    dropped = False
    for client_id in dead:
        stale = room.clients.pop(client_id, None)
        if stale is not None:
            dropped = True
            try:
                await stale.close(code=1001)
            except Exception:
                pass
        room.presence.pop(client_id, None)
    if dropped and payload.get("type") != "presence":
        await _presence(room)


async def _presence(room: Room) -> None:
    users = [
        {
            "id": client_id,
            "name": info.get("name"),
            "color": info.get("color"),
            "x": info.get("x"),
            "y": info.get("y"),
        }
        for client_id, info in room.presence.items()
    ]
    await _broadcast(room, {"type": "presence", "users": users})


async def ensure_indexes() -> None:
    try:
        await _db().objects.create_index(
            [("room", 1), ("oid", 1)], unique=True, name="room_oid"
        )
        await _db().media.create_index("hash", unique=True, name="media_hash")
        await _db().command("ping")
        hub.mongo_ok = True
        logger.info("soon: mongo ready")
    except Exception:
        hub.mongo_ok = False
        logger.exception("soon: mongo unavailable, board is in-memory only")


async def _gc_media(media_id: str) -> None:
    if not hub.mongo_ok or not media_id:
        return
    try:
        await release_media(_db(), _fs(), media_id)
    except Exception:
        logger.exception("soon: media gc failed for %s", media_id)


async def _fetch_cdn_bytes(url: str) -> bytes:
    def _read() -> bytes:
        if os.getenv("CUTAWAY_PROJECT_NETWORK_HOSTS"):
            from shared_network import safe_urlopen

            return safe_urlopen(url, timeout=30, max_bytes=MAX_MEDIA_BYTES * 4)
        with urlopen(url, timeout=30) as response:
            return response.read(MAX_MEDIA_BYTES * 4)

    return await asyncio.to_thread(_read)


async def migrate_gridfs_images() -> None:
    if not hub.mongo_ok or not cloudinary_ready():
        return
    db = _db()
    fs = _fs()
    moved = 0
    failed = 0
    orphans = 0
    cursor = db.objects.find({"data.type": "image"})
    async for doc in cursor:
        data = doc.get("data")
        if not isinstance(data, dict):
            continue
        media_id = data.get("media_id")
        if isinstance(media_id, str) and MEDIA_HASH_RE.fullmatch(media_id):
            if not data.get("media_url"):
                catalog = await find_media_by_hash(db, media_id)
                if catalog and catalog.get("url"):
                    data["media_url"] = catalog["url"]
                    await db.objects.replace_one({"_id": doc["_id"]}, {**doc, "data": data})
            continue
        try:
            oid = ObjectId(media_id)
            grid_out = await fs.open_download_stream(oid)
            payload = await grid_out.read()
            filename = str(grid_out.filename or "migrated")
        except Exception:
            failed += 1
            continue
        try:
            meta = await store_image(db, payload, filename)
        except Exception:
            logger.exception("soon: failed to migrate media %s", media_id)
            failed += 1
            continue
        data["media_id"] = meta["id"]
        data["media_url"] = meta["url"]
        try:
            await db.objects.replace_one({"_id": doc["_id"]}, {**doc, "data": data})
            await fs.delete(oid)
            moved += 1
        except Exception:
            logger.exception("soon: failed to rewrite migrated object %s", doc.get("oid"))
            failed += 1
    try:
        async for grid_out in fs.find({}):
            meta = grid_out.metadata or {}
            mime = str(meta.get("content_type") or "")
            if mime not in IMAGE_MIMES:
                continue
            oid = str(grid_out._id)
            used = await count_media_usage(db, oid)
            if used:
                continue
            await fs.delete(grid_out._id)
            orphans += 1
    except Exception:
        logger.exception("soon: gridfs image sweep failed")
    if moved or failed or orphans:
        logger.info(
            "soon: migrated %s images to cloudinary (%s failed, %s orphan files removed)",
            moved,
            failed,
            orphans,
        )


async def startup_clients() -> None:
    await ensure_indexes()
    try:
        await migrate_gridfs_images()
    except Exception:
        logger.exception("soon: image migration failed")


async def shutdown_clients() -> None:
    hub.rooms.clear()


router.add_event_handler("startup", startup_clients)
router.add_event_handler("shutdown", shutdown_clients)


def _page() -> FileResponse:
    return FileResponse(BASE_DIR / "soon.html")


@router.get("/", response_class=FileResponse)
async def home() -> FileResponse:
    return _page()


@router.get("/r/{room}")
async def room_page(room: str) -> RedirectResponse:
    return RedirectResponse(url="/soon/", status_code=307)


@router.get("/api/board")
@router.get("/api/board/{room}")
async def board_snapshot(room: str = DEFAULT_ROOM) -> dict[str, Any]:
    state = await hub.room(DEFAULT_ROOM)
    async with state.lock:
        objects = list(state.objects.values())
    return {"room": DEFAULT_ROOM, "objects": objects, "mongo": hub.mongo_ok}


@router.post("/api/upload", dependencies=upload_guards)
async def upload_media(file: UploadFile = File(...)) -> dict[str, str]:
    data = await file.read(MAX_MEDIA_BYTES + 1)
    if len(data) > MAX_MEDIA_BYTES:
        raise HTTPException(status_code=413, detail="File is larger than 1.5 MB.")
    mime = sniff_mime(data)
    if mime not in ALLOWED_MIMES:
        raise HTTPException(
            status_code=415,
            detail="Use PNG, JPEG, GIF, WebP, PDF, MP3, OGG, WAV or WebM.",
        )
    filename = _text(file.filename or "upload", 180) or "upload"
    if not hub.mongo_ok:
        raise HTTPException(status_code=503, detail="Media storage is unavailable.")
    kind = "image" if mime in IMAGE_MIMES else "file"
    if kind == "image" and cloudinary_ready():
        try:
            return await store_image(_db(), data, filename)
        except Exception as exc:
            logger.exception("soon: cloudinary upload failed")
            raise HTTPException(status_code=503, detail="Could not store the file.") from exc
    try:
        file_id = await _fs().upload_from_stream(
            filename,
            io.BytesIO(data),
            metadata={"content_type": mime},
        )
    except PyMongoError as exc:
        logger.exception("soon: media upload failed")
        raise HTTPException(status_code=503, detail="Could not store the file.") from exc
    return {"id": str(file_id), "mime": mime, "filename": filename, "kind": kind}


def _media_headers(mime: str, filename: str, inline: bool) -> dict[str, str]:
    safe_name = filename.replace('"', "").replace("\r", "").replace("\n", "")
    disposition = "inline" if inline else "attachment"
    return {
        "Cache-Control": "public, max-age=86400",
        "X-Content-Type-Options": "nosniff",
        "Content-Disposition": f'{disposition}; filename="{safe_name}"',
        "Content-Security-Policy": "default-src 'none'",
    }


@router.get("/api/media/{media_id}")
async def get_media(media_id: str, unwrap: str = "") -> Response:
    if MEDIA_HASH_RE.fullmatch(media_id):
        if not hub.mongo_ok:
            raise HTTPException(status_code=404, detail="Not found.")
        doc = await find_media_by_hash(_db(), media_id)
        if not doc or not doc.get("url"):
            raise HTTPException(status_code=404, detail="Not found.")
        url = str(doc["url"])
        if unwrap != "1":
            return RedirectResponse(url, status_code=302)
        try:
            payload = unmask_image(await _fetch_cdn_bytes(url))
        except Exception as exc:
            logger.exception("soon: failed to unwrap %s", media_id)
            raise HTTPException(status_code=502, detail="Could not read the file.") from exc
        return Response(
            content=payload,
            media_type="image/webp",
            headers=_media_headers("image/webp", "image.webp", True),
        )
    try:
        oid = ObjectId(media_id)
    except (InvalidId, TypeError) as exc:
        raise HTTPException(status_code=404, detail="Not found.") from exc
    try:
        grid_out = await _fs().open_download_stream(oid)
        payload = await grid_out.read()
    except (NoFile, PyMongoError) as exc:
        raise HTTPException(status_code=404, detail="Not found.") from exc
    meta = grid_out.metadata or {}
    mime = str(meta.get("content_type") or "application/octet-stream")
    if mime not in ALLOWED_MIMES:
        mime = "application/octet-stream"
    inline = mime in IMAGE_MIMES or mime.startswith("audio/") or mime == "video/webm"
    filename = str(grid_out.filename or "file")
    return Response(
        content=payload,
        media_type=mime,
        headers=_media_headers(mime, filename, inline),
    )


@router.websocket("/ws")
async def board_socket(websocket: WebSocket) -> None:
    await _run_socket(websocket)


@router.websocket("/ws/{room}")
async def board_socket_legacy(websocket: WebSocket, room: str) -> None:
    await _run_socket(websocket)


async def _run_socket(websocket: WebSocket) -> None:
    name = DEFAULT_ROOM
    await websocket.accept()
    client_id = session_id(websocket.query_params.get("sid"))
    state = await hub.room(name)
    color = _guest_color(client_id)
    bucket: list[float] = []
    old: WebSocket | None = None

    async with state.lock:
        old = state.clients.get(client_id)
        state.clients[client_id] = websocket
        if client_id not in state.presence:
            state.presence[client_id] = {
                "name": _guest_name(taken_names(state.presence)),
                "color": color,
                "x": None,
                "y": None,
            }
        info = state.presence[client_id]
        name_hint = info.get("name") or _guest_name(taken_names(state.presence))
        color = info.get("color") or color
        info["name"] = name_hint
        info["color"] = color
        snapshot = list(state.objects.values())
        chat = list(state.chat)

    if old is not None and old is not websocket:
        try:
            await asyncio.wait_for(old.close(code=1001), timeout=1.0)
        except Exception:
            pass

    try:
        await websocket.send_json(
            {
                "type": "hello",
                "id": client_id,
                "room": name,
                "name": name_hint,
                "color": color,
                "mongo": hub.mongo_ok,
                "objects": snapshot,
                "chat": chat,
            }
        )
        await _presence(state)
        while True:
            try:
                message = await asyncio.wait_for(
                    websocket.receive_json(), timeout=WS_IDLE
                )
            except TimeoutError:
                try:
                    await websocket.close(code=1001)
                except Exception:
                    pass
                break
            if not isinstance(message, dict):
                continue
            kind = message.get("type")
            if kind == "ping":
                await websocket.send_json({"type": "pong"})
                continue
            now = asyncio.get_running_loop().time()
            if kind not in {"cursor", "draft"}:
                bucket = [stamp for stamp in bucket if now - stamp < 1.0]
                if len(bucket) >= 40:
                    await websocket.send_json(
                        {"type": "error", "message": "Slow down."}
                    )
                    continue
                bucket.append(now)

            if kind == "hello":
                async with state.lock:
                    try:
                        guest = claim_name(
                            state.presence, client_id, message.get("name")
                        )
                    except ValueError as exc:
                        await websocket.send_json(
                            {"type": "error", "message": str(exc)}
                        )
                        continue
                    info = state.presence.get(client_id)
                    if info is not None:
                        info["name"] = guest
                await websocket.send_json({"type": "nick", "name": guest})
                await _presence(state)
            elif kind == "cursor":
                try:
                    x = _finite(message.get("x", 0))
                    y = _finite(message.get("y", 0))
                except ValueError:
                    continue
                async with state.lock:
                    info = state.presence.get(client_id)
                    if info is not None:
                        info["x"] = x
                        info["y"] = y
                await _broadcast(
                    state,
                    {
                        "type": "cursor",
                        "id": client_id,
                        "x": x,
                        "y": y,
                        "name": state.presence.get(client_id, {}).get("name"),
                        "color": color,
                    },
                    skip=client_id,
                )
            elif kind == "chat":
                try:
                    text = _chat_text(message.get("text"))
                except ValueError:
                    continue
                nick = state.presence.get(client_id, {}).get("name") or name_hint
                entry = {
                    "id": secrets.token_hex(4),
                    "from": client_id,
                    "name": nick,
                    "text": text,
                    "color": state.presence.get(client_id, {}).get("color") or color,
                }
                async with state.lock:
                    state.chat.append(entry)
                await _broadcast(state, {"type": "chat", **entry})
            elif kind == "draft":
                draft = message.get("object")
                payload: dict[str, Any] = {"type": "draft", "from": client_id}
                if draft is None:
                    payload["object"] = None
                    payload["id"] = message.get("id")
                else:
                    try:
                        payload["object"] = validate_object(draft)
                    except ValueError:
                        continue
                await _broadcast(state, payload, skip=client_id)
            elif kind == "op":
                async with state.lock:
                    try:
                        canonical = apply_op(state.objects, message)
                    except ValueError as exc:
                        rejected = {
                            "type": "error",
                            "message": str(exc),
                            "op": message.get("op"),
                        }
                        obj = message.get("object")
                        if isinstance(obj, dict) and isinstance(obj.get("id"), str):
                            rejected["id"] = obj["id"]
                        elif isinstance(message.get("id"), str):
                            rejected["id"] = message["id"]
                        await websocket.send_json(rejected)
                        continue
                await hub.persist(state, canonical)
                await _broadcast(
                    state,
                    {"type": "op", "from": client_id, **canonical},
                    skip=client_id,
                )
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("soon: socket failed")
    finally:
        dropped = False
        async with state.lock:
            if state.clients.get(client_id) is websocket:
                state.clients.pop(client_id, None)
                state.presence.pop(client_id, None)
                dropped = True
        if dropped:
            await _presence(state)
