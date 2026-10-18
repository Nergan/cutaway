"""Fetch the official ffmpeg.wasm build into formular/static/vendor/ffmpeg.

The core is large and GPL, so it is not stored in git. The page loads the
single-threaded build: a multi-threaded one would need isolation headers on
the shared origin.
"""

from __future__ import annotations

import io
import tarfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "static" / "vendor" / "ffmpeg"
PACKAGES = {
    "loader": ("https://registry.npmjs.org/@ffmpeg/ffmpeg/-/ffmpeg-0.12.10.tgz", "package/dist/esm/"),
    "util": ("https://registry.npmjs.org/@ffmpeg/util/-/util-0.12.1.tgz", "package/dist/esm/"),
    "core": ("https://registry.npmjs.org/@ffmpeg/core/-/core-0.12.6.tgz", "package/dist/esm/"),
}


def _members(archive: tarfile.TarFile, prefix: str) -> list[tarfile.TarInfo]:
    found = [item for item in archive.getmembers() if item.isfile() and item.name.startswith(prefix)]
    if not found:
        raise SystemExit(f"ffmpeg.wasm archive has no {prefix}")
    return found


def fetch() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    for folder, (url, prefix) in PACKAGES.items():
        destination = ROOT / folder
        if folder == "core" and (destination / "ffmpeg-core.wasm").is_file():
            continue
        print(f"fetch {url}")
        with urllib.request.urlopen(url, timeout=120) as response:
            payload = response.read()
        with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
            for item in _members(archive, prefix):
                target = destination / item.name[len(prefix):]
                target.parent.mkdir(parents=True, exist_ok=True)
                source = archive.extractfile(item)
                if source is None:
                    continue
                target.write_bytes(source.read())
    wasm = ROOT / "core" / "ffmpeg-core.wasm"
    if not wasm.is_file() or wasm.stat().st_size < 1_000_000:
        raise SystemExit("ffmpeg-core.wasm is missing after fetch")
    print(f"ffmpeg.wasm ready at {ROOT}")


if __name__ == "__main__":
    fetch()
