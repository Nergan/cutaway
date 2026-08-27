#!/usr/bin/env python3
"""Сборка zip инсталлятора в GitHub Actions: job_id без token в логах.

Ожидает окружение:
  ANOTHER_ORIGIN_URL  https://nargan-projects.hf.space/another
  ANOTHER_SERVICE_SECRET
  INSTALLER_JOB_ID
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import urllib.error
import urllib.request


def _origin() -> str:
    return os.environ["ANOTHER_ORIGIN_URL"].rstrip("/")


def _secret() -> str:
    return os.environ["ANOTHER_SERVICE_SECRET"]


def _headers() -> dict[str, str]:
    return {"X-Another-Proxy-Secret": _secret(), "Accept": "application/json"}


def _request(
    method: str,
    url: str,
    data: bytes | None = None,
    content_type: str | None = None,
    timeout: int = 120,
) -> bytes:
    headers = _headers()
    if content_type:
        headers["Content-Type"] = content_type
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as err:
        body = err.read()[:500]
        raise SystemExit(f"HTTP {err.code} {url}: {body!r}") from err


def _mark_failed(job_id: str, error: str) -> None:
    try:
        payload = json.dumps({"status": "failed", "error": error}).encode()
        _request(
            "POST",
            f"{_origin()}/internal/v1/installer-jobs/{job_id}/status",
            data=payload,
            content_type="application/json",
            timeout=30,
        )
    except Exception:
        return


def _fetch_job(job_id: str) -> dict:
    raw = _request("GET", f"{_origin()}/internal/v1/installer-jobs/{job_id}", timeout=30)
    return json.loads(raw.decode("utf-8"))


def _download_wintun(dest: Path) -> None:
    url = "https://www.wintun.net/builds/wintun-0.14.1.zip"
    req = urllib.request.Request(url, headers={"User-Agent": "another-installer-build"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        blob = resp.read()
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        for name in zf.namelist():
            if name.replace("\\", "/").endswith("bin/amd64/wintun.dll"):
                dest.write_bytes(zf.read(name))
                return
    raise SystemExit("wintun.dll amd64 not found in upstream zip")


def _pack(job_id: str) -> int:
    job = _fetch_job(job_id)
    platform = str(job.get("platform") or "windows/amd64")
    ldflags = str(job.get("ldflags") or "")
    if not ldflags:
        raise SystemExit("job has no ldflags")
    goos, _, goarch = platform.partition("/")
    core = Path(__file__).resolve().parents[2] / "core"
    out_dir = Path(os.environ.get("RUNNER_TEMP") or ".") / "another-out"
    out_dir.mkdir(parents=True, exist_ok=True)
    exe_name = "another.exe" if goos == "windows" else "another"
    exe_path = out_dir / exe_name
    env = os.environ.copy()
    env["GOOS"] = goos
    env["GOARCH"] = goarch
    env["CGO_ENABLED"] = "0"
    cmd = [
        "go",
        "build",
        "-trimpath",
        f"-ldflags={ldflags}",
        "-o",
        str(exe_path),
        "./cmd/desktop",
    ]
    proc = subprocess.run(cmd, cwd=core, env=env, check=False)
    if proc.returncode != 0:
        _mark_failed(job_id, "go_build")
        return proc.returncode
    zip_path = out_dir / "bundle.zip"
    readme = (
        "Another VPN\n\n"
        "Windows: распакуйте, запустите another.exe от имени администратора.\n"
        "Другой VPN выключите. wintun.dll должен лежать рядом с exe.\n"
        "Linux: sudo ./another  (нужен /dev/net/tun).\n"
    )
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(exe_path, arcname=exe_name)
        zf.writestr("README.txt", readme)
        if goos == "windows":
            dll = out_dir / "wintun.dll"
            _download_wintun(dll)
            zf.write(dll, arcname="wintun.dll")
            notice = (
                "Wintun is Copyright (C) WireGuard LLC. Licensed under GPLv2.\n"
                "See https://www.wintun.net/\n"
            )
            zf.writestr("WINTUN-NOTICE.txt", notice)
    _request(
        "PUT",
        f"{_origin()}/internal/v1/installer-jobs/{job_id}/artifact",
        data=zip_path.read_bytes(),
        content_type="application/zip",
        timeout=180,
    )
    return 0


def main() -> int:
    job_id = os.environ.get("INSTALLER_JOB_ID", "").strip()
    if not job_id:
        print("INSTALLER_JOB_ID empty", file=sys.stderr)
        return 2
    try:
        return _pack(job_id)
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 1
        if code:
            _mark_failed(job_id, "build_failed")
        raise
    except Exception as exc:
        _mark_failed(job_id, type(exc).__name__)
        print(exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
