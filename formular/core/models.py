"""Кэш весов: скачивание после старта и удаление, когда задача отпустила модель.

В образе лежат только правила. Файл модели появляется на диске на время задачи.
"""

from __future__ import annotations

import hashlib
import threading
from dataclasses import dataclass
from pathlib import Path
from urllib.request import Request, build_opener

from shared_network import SafeRedirectHandler, validate_outbound_url

from formular.core.errors import FormularError

_ALLOWED_LICENSES = frozenset(
    {
        "mit",
        "apache-2.0",
        "bsd-2-clause",
        "bsd-3-clause",
        "isc",
        "zlib",
        "cc0-1.0",
        "unlicense",
        "cc-by-4.0",
        "cc-by-3.0",
    }
)


def license_allowed(name: str) -> bool:
    return name.strip().lower() in _ALLOWED_LICENSES


@dataclass(frozen=True)
class ModelSpec:
    model_id: str
    url: str
    license_name: str
    sha256: str
    max_bytes: int


class ModelCache:
    def __init__(self, root: Path, *, max_total_bytes: int):
        self.root = root
        self.max_total_bytes = max_total_bytes
        self.root.mkdir(parents=True, exist_ok=True)
        self._refs: dict[str, int] = {}
        self._lock = threading.Lock()

    def acquire(self, spec: ModelSpec) -> Path:
        if not license_allowed(spec.license_name):
            raise FormularError("This model license is not allowed.", 422)
        if spec.max_bytes <= 0 or spec.max_bytes > self.max_total_bytes:
            raise FormularError("This model is larger than the cache budget.", 413)
        with self._lock:
            path = self._path(spec)
            if not path.is_file():
                self._download(spec, path)
            self._refs[spec.model_id] = self._refs.get(spec.model_id, 0) + 1
            return path

    def release(self, model_id: str) -> None:
        with self._lock:
            left = self._refs.get(model_id, 0) - 1
            if left > 0:
                self._refs[model_id] = left
                return
            self._refs.pop(model_id, None)
            folder = self.root / _safe_id(model_id)
            if folder.exists():
                for child in folder.iterdir():
                    child.unlink(missing_ok=True)
                folder.rmdir()

    def _path(self, spec: ModelSpec) -> Path:
        return self.root / _safe_id(spec.model_id) / "weights"

    def _download(self, spec: ModelSpec, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        partial = destination.with_suffix(".partial")
        try:
            download_file(spec.url, partial, max_bytes=spec.max_bytes, sha256=spec.sha256)
            partial.replace(destination)
        except Exception:
            partial.unlink(missing_ok=True)
            raise
        if self._used_bytes() > self.max_total_bytes:
            destination.unlink(missing_ok=True)
            raise FormularError("Model cache is full.", 429)

    def _used_bytes(self) -> int:
        total = 0
        for entry in self.root.rglob("*"):
            if entry.is_file():
                total += entry.stat().st_size
        return total


def download_file(url: str, destination: Path, *, max_bytes: int, sha256: str) -> None:
    validate_outbound_url(url)
    opener = build_opener(SafeRedirectHandler())
    request = Request(url, headers={"User-Agent": "formular"})
    digest = hashlib.sha256()
    written = 0
    with opener.open(request, timeout=60) as response, destination.open("wb") as handle:
        while True:
            chunk = response.read(65536)
            if not chunk:
                break
            written += len(chunk)
            if written > max_bytes:
                raise FormularError("Model file is larger than its limit.", 413)
            digest.update(chunk)
            handle.write(chunk)
    if digest.hexdigest() != sha256:
        raise FormularError("Model file did not match the expected hash.", 422)


def _safe_id(model_id: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in "._-" else "_" for char in model_id)
    if not cleaned:
        raise FormularError("Model id is empty.", 422)
    return cleaned
