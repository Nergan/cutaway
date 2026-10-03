"""Локальные рабочие пространства.

Байты живут только на диске процесса. Срок не больше суток. Каталог называется
хэшем идентификатора, сам идентификатор в имя каталога не входит.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

from formular.core.errors import FormularError

_TOKEN_ALPHABET = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")
_MAX_TOKEN = 128
_MIN_TOKEN = 32


def touch_busy() -> None:
    """Продлить маркер занятости, если супервизор его передал."""
    raw = os.environ.get("CUTAWAY_BUSY_FILE", "").strip()
    if not raw:
        return
    try:
        Path(raw).touch()
    except OSError:
        return


@dataclass(frozen=True)
class WorkspaceInfo:
    token: str
    path: Path
    created: float
    expires: float


class WorkspaceStore:
    def __init__(
        self,
        root: Path,
        *,
        ttl_seconds: int = 86_400,
        max_total_bytes: int = 1024 * 1024 * 1024,
        max_workspace_bytes: int = 256 * 1024 * 1024,
    ):
        if ttl_seconds <= 0 or ttl_seconds > 86_400:
            raise ValueError("Workspace lifetime must be between 1 second and 24 hours.")
        self.root = root
        self.ttl_seconds = ttl_seconds
        self.max_total_bytes = max_total_bytes
        self.max_workspace_bytes = max_workspace_bytes
        self.root.mkdir(parents=True, exist_ok=True)

    def create(self) -> WorkspaceInfo:
        self.sweep()
        if self.used_bytes() >= self.max_total_bytes:
            raise FormularError("Storage is full. Try again after existing files expire.", 429)
        token = secrets.token_urlsafe(32)
        folder = self._folder(token)
        folder.mkdir(parents=True)
        now = time.time()
        info = WorkspaceInfo(token, folder, now, now + self.ttl_seconds)
        self._write_meta(info)
        return info

    def open(self, token: str) -> WorkspaceInfo:
        self._check_token(token)
        folder = self._folder(token)
        meta_path = folder / "meta.json"
        if not meta_path.is_file():
            raise FormularError("Workspace was not found.", 404)
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            created = float(meta["created"])
            expires = float(meta["expires"])
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise FormularError("Workspace was not found.", 404) from exc
        if expires <= time.time():
            shutil.rmtree(folder, ignore_errors=True)
            raise FormularError("Workspace has expired.", 410)
        return WorkspaceInfo(token, folder, created, expires)

    def delete(self, token: str) -> None:
        info = self.open(token)
        shutil.rmtree(info.path, ignore_errors=True)

    def reserve(self, info: WorkspaceInfo, extra_bytes: int) -> None:
        if extra_bytes < 0:
            raise FormularError("Invalid size.", 400)
        if self._folder_size(info.path) + extra_bytes > self.max_workspace_bytes:
            raise FormularError("This workspace has reached its size limit.", 413)
        if self.used_bytes() + extra_bytes > self.max_total_bytes:
            raise FormularError("Storage is full. Try again after existing files expire.", 429)

    def sweep(self) -> int:
        removed = 0
        now = time.time()
        for entry in self.root.iterdir():
            meta_path = entry / "meta.json"
            expired = True
            if meta_path.is_file():
                try:
                    meta = json.loads(meta_path.read_text(encoding="utf-8"))
                    expired = float(meta.get("expires", 0)) <= now
                except (OSError, ValueError, TypeError):
                    expired = True
            if expired:
                shutil.rmtree(entry, ignore_errors=True)
                removed += 1
        return removed

    def used_bytes(self) -> int:
        total = 0
        for entry in self.root.rglob("*"):
            if entry.is_file():
                try:
                    total += entry.stat().st_size
                except OSError:
                    continue
        return total

    def _folder(self, token: str) -> Path:
        self._check_token(token)
        digest = hashlib.sha256(token.encode("ascii")).hexdigest()
        return self.root / digest

    def _write_meta(self, info: WorkspaceInfo) -> None:
        payload = {"created": info.created, "expires": info.expires}
        (info.path / "meta.json").write_text(json.dumps(payload), encoding="utf-8")

    @staticmethod
    def _check_token(token: str) -> None:
        if not isinstance(token, str) or not _MIN_TOKEN <= len(token) <= _MAX_TOKEN:
            raise FormularError("Workspace was not found.", 404)
        if any(char not in _TOKEN_ALPHABET for char in token):
            raise FormularError("Workspace was not found.", 404)

    @staticmethod
    def _folder_size(folder: Path) -> int:
        total = 0
        for entry in folder.rglob("*"):
            if entry.is_file():
                try:
                    total += entry.stat().st_size
                except OSError:
                    continue
        return total
