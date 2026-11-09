"""Turn a Xaero world-map folder into public WebP tiles and a Mongo catalog.

The raw cache stays on disk. Run this again after replacing the folder:

    python -m mikchan_map.convert --xaero PATH --out PATH

CLOUDINARY_URL (or CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY and
CLOUDINARY_API_SECRET) uploads the tiles. MONGODB_URI, or MONGO_USER /
MONGO_PASS / MONGO_HOST, writes database mikchan_map. Nothing here is printed.
"""

from __future__ import annotations

import argparse
import io
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
script_dir = Path(__file__).resolve().parent
sys.path = [entry for entry in sys.path if Path(entry).resolve() != script_dir]
sys.path.insert(0, str(ROOT))

from mikchan_map.biomes import spread_spots
from mikchan_map.markers import parse_waypoints
from mikchan_map.xaero_cache import CacheFormatError, parse_xwmc

LEVELS = (
    ("cache_1", 0, 512, True),
    ("cache/1", 1, 1024, False),
    ("cache/2", 2, 2048, False),
    ("cache/3", 3, 4096, False),
)
DIMENSIONS = (
    ("null", "overworld", "dim%0"),
    ("DIM-1", "nether", "dim%-1"),
    ("DIM1", "end", "dim%1"),
)
DATABASE = "mikchan_map"


def mongo_uri() -> str:
    uri = os.getenv("MONGODB_URI", "").strip()
    if uri:
        return uri
    user = os.getenv("MONGO_USER", "").strip()
    password = os.getenv("MONGO_PASS", "")
    host = os.getenv("MONGO_HOST", "").strip()
    if not user or not password or not host:
        raise SystemExit("MongoDB is not configured.")
    return (
        "mongodb+srv://"
        + quote(user, safe="")
        + ":"
        + quote(password, safe="")
        + "@"
        + host
        + "/?retryWrites=true&w=majority&appName=mikchan-map"
    )


def configure_cloudinary() -> None:
    import cloudinary

    if os.getenv("CLOUDINARY_URL"):
        cloudinary.config(secure=True, timeout=60)
        return
    name = os.getenv("CLOUDINARY_CLOUD_NAME", "")
    key = os.getenv("CLOUDINARY_API_KEY", "")
    secret = os.getenv("CLOUDINARY_API_SECRET", "")
    if not (name and key and secret):
        raise SystemExit("Image host credentials are not configured.")
    cloudinary.config(cloud_name=name, api_key=key, api_secret=secret, secure=True, timeout=60)


def region_files(folder: Path) -> list[tuple[int, int, Path]]:
    found = []
    if not folder.is_dir():
        return found
    for path in folder.glob("*.xwmc"):
        stem = path.name[: -len(".xwmc")]
        if "_" not in stem:
            continue
        x_text, z_text = stem.split("_", 1)
        try:
            found.append((int(x_text), int(z_text), path))
        except ValueError:
            continue
    return found


def encode_tile(source: Path, dest: Path, *, leaf: bool, level: int) -> bool:
    source_stamp = source.stat().st_mtime_ns
    if dest.exists() and dest.stat().st_size > 0 and dest.stat().st_mtime_ns >= source_stamp:
        return True
    try:
        image = parse_xwmc(source.read_bytes(), leaf=leaf, level=level)
    except (CacheFormatError, OSError):
        return False
    if image.opaque_pixels() == 0:
        return False
    from PIL import Image

    picture = Image.frombytes("RGBA", (image.width, image.height), image.rgba)
    buffer = io.BytesIO()
    picture.save(buffer, format="WEBP", lossless=True, quality=100, method=4)
    dest.parent.mkdir(parents=True, exist_ok=True)
    temporary = dest.with_suffix(".part")
    temporary.write_bytes(buffer.getvalue())
    temporary.replace(dest)
    return True


def upload_tile(path: Path, public_id: str) -> None:
    import time

    import cloudinary.uploader

    delay = 2
    for attempt in range(6):
        try:
            cloudinary.uploader.upload(
                str(path),
                public_id=public_id,
                resource_type="image",
                format="webp",
                overwrite=True,
                invalidate=True,
                unique_filename=False,
                use_filename=False,
            )
            return
        except Exception as exc:
            message = str(exc)
            retry = any(token in message for token in ("420", "429", "500", "502", "503", "Timeout", "timeout"))
            if attempt == 5 or not retry:
                raise
            time.sleep(delay)
            delay *= 2


def should_upload(recorded: int | None, source_stamp: int, dest_fresh: bool) -> bool:
    # A note without a timestamp is the first publication. Keep it until the
    # cache file is newer than the picture already written beside it.
    if recorded == 0 and dest_fresh:
        return False
    return recorded is None or recorded < source_stamp


def load_done(path: Path) -> dict[str, int]:
    found: dict[str, int] = {}
    if not path.exists():
        return found
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) < 4:
            continue
        key = " ".join(parts[:4])
        stamp = int(parts[4]) if len(parts) > 4 and parts[4].isdigit() else 0
        found[key] = max(found.get(key, 0), stamp)
    return found


def _read_biome_region(job: tuple) -> dict | None:
    dimension, x, z, source = job
    try:
        image = parse_xwmc(Path(source).read_bytes(), leaf=True, level=0)
    except (CacheFormatError, OSError):
        return {"failed": True}
    if not image.biomes or not any(image.biomes):
        return None
    import zlib

    spots = []
    seen: set[int] = set()
    for index, value in enumerate(image.biomes):
        if not value or value in seen or value > len(image.biome_names):
            continue
        name = image.biome_names[value - 1]
        if not name:
            continue
        seen.add(value)
        spots.append(
            {
                "id": name,
                "x": x * 512 + (index % 256) * 2 + 1,
                "z": z * 512 + (index // 256) * 2 + 1,
            }
        )
    return {
        "dimension": dimension,
        "x": x,
        "z": z,
        "names": list(image.biome_names),
        "grid": zlib.compress(image.biomes, 6),
        "spots": spots,
    }


def publish_biomes(world: Path, workers: int) -> None:
    from concurrent.futures import ProcessPoolExecutor, as_completed

    from pymongo import MongoClient

    jobs = []
    for folder_name, dimension, _minimap in DIMENSIONS:
        folder = world / folder_name / "mw$default" / "cache_1"
        for x, z, source in region_files(folder):
            jobs.append((dimension, x, z, str(source)))
    print(f"biome regions {len(jobs)}", flush=True)
    grouped: dict[str, dict[str, list[dict]]] = {}
    seen: dict[str, list[str]] = {}
    failed = 0
    written = 0
    client = MongoClient(mongo_uri(), serverSelectionTimeoutMS=15000)
    regions = client[DATABASE].biome_regions
    with ProcessPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [pool.submit(_read_biome_region, job) for job in jobs]
        finished = 0
        for future in as_completed(futures):
            finished += 1
            result = future.result()
            if result and result.get("failed"):
                failed += 1
            elif result:
                dimension = result["dimension"]
                key = f"{dimension}:{result['x']}:{result['z']}"
                regions.replace_one(
                    {"_id": key},
                    {
                        "_id": key,
                        "dimension": dimension,
                        "rx": result["x"],
                        "rz": result["z"],
                        "names": result["names"],
                        "grid": result["grid"],
                    },
                    upsert=True,
                )
                written += 1
                seen.setdefault(dimension, []).append(key)
                for spot in result["spots"]:
                    grouped.setdefault(dimension, {}).setdefault(spot["id"], []).append(spot)
            if finished % 200 == 0:
                print(f"biomes {finished}/{len(jobs)} failed {failed}", flush=True)
    index = client[DATABASE].biome_index
    for _folder_name, dimension, _minimap in DIMENSIONS:
        keys = seen.get(dimension) or []
        spots = []
        for biome_id, points in sorted((grouped.get(dimension) or {}).items()):
            spots.extend(spread_spots(points))
        if keys:
            regions.delete_many({"dimension": dimension, "_id": {"$nin": keys}})
        else:
            regions.delete_many({"dimension": dimension})
        index.replace_one({"_id": dimension}, {"_id": dimension, "spots": spots}, upsert=True)
        print(f"biome index {dimension} spots {len(spots)} regions {len(keys)}", flush=True)
    print(f"biomes {len(jobs)}/{len(jobs)} written {written} failed {failed}", flush=True)
    client.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--xaero", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--biomes-only", action="store_true")
    args = parser.parse_args()
    world = args.xaero / "world-map" / "Multiplayer_play.mikchan.net"
    minimap = args.xaero / "minimap" / "Multiplayer_play.mikchan.net"
    if not world.is_dir():
        raise SystemExit("No Xaero world-map folder.")
    if args.biomes_only:
        publish_biomes(world, args.workers)
        return
    configure_cloudinary()
    import cloudinary.api

    usage = cloudinary.api.usage()
    used = float(usage.get("credits", {}).get("usage", 0) or 0)
    limit = float(usage.get("credits", {}).get("limit", 0) or 0)
    print(f"credits {used:.2f}/{limit:.0f}", flush=True)
    if limit and used >= limit - 3:
        raise SystemExit("Not enough image-host credit left for a map upload.")

    jobs = []
    for folder_name, dimension, _minimap in DIMENSIONS:
        base = world / folder_name / "mw$default"
        for relative, level, _blocks, leaf in LEVELS:
            for x, z, source in region_files(base / relative):
                jobs.append((dimension, level, leaf, x, z, source))
    print(f"regions {len(jobs)}", flush=True)
    args.out.mkdir(parents=True, exist_ok=True)
    done_path = args.out / "uploaded.txt"
    done = load_done(done_path)
    lock = threading.Lock()
    catalog: dict[str, dict[int, list[list[int]]]] = {}
    failed = 0

    def work(job: tuple) -> None:
        nonlocal failed
        dimension, level, leaf, x, z, source = job
        key = f"{dimension} {level} {x} {z}"
        dest = args.out / dimension / str(level) / f"{x}_{z}.webp"
        source_stamp = source.stat().st_mtime_ns
        recorded = done.get(key)
        dest_fresh = dest.exists() and dest.stat().st_mtime_ns >= source_stamp
        # Lines written before timestamps exist mean the tile was uploaded, but
        # only while the local picture is still newer than the cache file.
        upload_needed = should_upload(recorded, source_stamp, dest_fresh)
        if not encode_tile(source, dest, leaf=leaf, level=level):
            return
        if upload_needed:
            try:
                upload_tile(dest, f"mikchan-map/{dimension}/{level}/{x}_{z}")
            except Exception:
                with lock:
                    failed += 1
                return
            with lock:
                with done_path.open("a", encoding="utf-8") as handle:
                    handle.write(f"{key} {source_stamp}\n")
                done[key] = source_stamp
        with lock:
            catalog.setdefault(dimension, {}).setdefault(level, []).append([x, z])

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = [pool.submit(work, job) for job in jobs]
        finished = 0
        for future in as_completed(futures):
            future.result()
            finished += 1
            if finished % 200 == 0:
                print(f"done {finished}/{len(jobs)} failed {failed}", flush=True)
    print(f"done {len(jobs)}/{len(jobs)} failed {failed}", flush=True)

    from pymongo import MongoClient

    client = MongoClient(mongo_uri(), serverSelectionTimeoutMS=15000)
    database = client[DATABASE]
    for folder_name, dimension, minimap_name in DIMENSIONS:
        levels = catalog.get(dimension) or {}
        if not levels:
            continue
        blocks_for = {level: blocks for _relative, level, blocks, _leaf in LEVELS}
        bounds = None
        level_docs = []
        for level, tiles in sorted(levels.items()):
            block = blocks_for[level]
            for x, z in tiles:
                x0, x1, z0, z1 = x * block, (x + 1) * block, z * block, (z + 1) * block
                if bounds is None:
                    bounds = [x0, x1, z0, z1]
                else:
                    bounds[0] = min(bounds[0], x0)
                    bounds[1] = max(bounds[1], x1)
                    bounds[2] = min(bounds[2], z0)
                    bounds[3] = max(bounds[3], z1)
            level_docs.append({"level": level, "blocks": block, "tiles": sorted(tiles)})
        waypoint_path = minimap / minimap_name / "mw$default_1.txt"
        waypoints = []
        if waypoint_path.is_file():
            waypoints = parse_waypoints(waypoint_path.read_text(encoding="utf-8"))
        database.catalog.replace_one(
            {"_id": dimension},
            {
                "_id": dimension,
                "bounds": {"minX": bounds[0], "maxX": bounds[1], "minZ": bounds[2], "maxZ": bounds[3]},
                "levels": level_docs,
                "waypoints": waypoints,
            },
            upsert=True,
        )
        print(f"catalog {dimension} tiles {sum(len(item['tiles']) for item in level_docs)} markers {len(waypoints)}", flush=True)
    client.close()


if __name__ == "__main__":
    main()
