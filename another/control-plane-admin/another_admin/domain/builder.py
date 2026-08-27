"""План per-client сборки инсталлятора (ldflags embed, не private key).

Реальная компиляция — опционально, если задан ANOTHER_BUILD_ENABLED=1 и
есть `go` в PATH. gomobile/Android SDK и wintun.dll — у оператора;
здесь всегда возвращаются точные команды.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

EMBED_PKG = "github.com/another-vpn/another/core/internal/adapters/provisioning"

DEFAULT_PLATFORMS = ("windows/amd64", "linux/amd64")
ANDROID_PLATFORM = "android/arm64"
ALLOWED_DESKTOP_PLATFORMS = ("windows/amd64", "linux/amd64")


@dataclass(frozen=True)
class Artifact:
    platform: str
    path: str | None
    sha256: str | None
    command: str
    compiled: bool


@dataclass(frozen=True)
class BuildPlan:
    job_id: str
    client_id: str
    enrollment_token: str
    build_id: str
    ldflags: str
    artifacts: tuple[Artifact, ...]
    notes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "client_id": self.client_id,
            "enrollment_token": self.enrollment_token,
            "build_id": self.build_id,
            "ldflags": self.ldflags,
            "artifacts": [
                {
                    "platform": a.platform,
                    "path": a.path,
                    "sha256": a.sha256,
                    "command": a.command,
                    "compiled": a.compiled,
                }
                for a in self.artifacts
            ],
            "notes": list(self.notes),
        }


def ldflags_for(
    *,
    token: str,
    client_id: str,
    build_id: str,
    nodes_json: str,
) -> str:
    parts = [
        "-s",
        "-w",
        f"-X {EMBED_PKG}.embeddedToken={token}",
        f"-X {EMBED_PKG}.embeddedClientID={client_id}",
        f"-X {EMBED_PKG}.embeddedBuildID={build_id}",
        f"-X {EMBED_PKG}.embeddedNodesJSON={nodes_json}",
    ]
    return " ".join(parts)


def nodes_json_for_control_plane(control_plane_url: str) -> str:
    """Один Tier1-узел на прод-воркер. Host и control_plane не loopback."""
    url = (control_plane_url or "").rstrip("/")
    host = urlparse(url).hostname or ""
    return json.dumps(
        [
            {
                "name": "cf-worker",
                "tier": "tier1-bootstrap",
                "transport": "vless-ws",
                "host": host,
                "port": 443,
                "path": "/proxy",
                "priority": 1,
                "control_plane": url,
            }
        ],
        separators=(",", ":"),
    )


def artifact_filename(platform: str) -> str:
    return f"another-{platform.replace('/', '-')}.zip"


def plan_installer(
    *,
    client_id: str,
    enrollment_token: str,
    nodes_json: str,
    platforms: list[str] | None = None,
    core_src: str | Path,
    output_dir: str | Path,
    build_id: str | None = None,
    job_id: str | None = None,
) -> BuildPlan:
    platforms = list(platforms or DEFAULT_PLATFORMS)
    build_id = build_id or uuid.uuid4().hex[:12]
    job_id = job_id or str(uuid.uuid4())
    flags = ldflags_for(
        token=enrollment_token,
        client_id=client_id,
        build_id=build_id,
        nodes_json=nodes_json,
    )
    core = Path(core_src)
    out_root = Path(output_dir) / job_id
    artifacts: list[Artifact] = []
    notes: list[str] = [
        "В бинарник эмбеддятся token+client_id+входы, не private key (docs/provisioning.md).",
        "wintun.dll рядом с windows-exe — не в git, кладёт оператор.",
        "Android: gomobile bind у оператора, см. app/native/android/README.md.",
    ]
    for platform in platforms:
        if platform == ANDROID_PLATFORM or platform.startswith("android"):
            cmd = (
                f"cd {core} && gomobile bind -target=android "
                f'-ldflags "{flags}" ./cmd/mobilelib'
            )
            artifacts.append(
                Artifact(platform=platform, path=None, sha256=None, command=cmd, compiled=False)
            )
            continue
        goos, _, goarch = platform.partition("/")
        suffix = ".exe" if goos == "windows" else ""
        out = out_root / f"another-{goos}-{goarch}{suffix}"
        cmd = (
            f"cd {core} && GOOS={goos} GOARCH={goarch} CGO_ENABLED=0 "
            f'go build -trimpath -ldflags "{flags}" -o {out} ./cmd/desktop'
        )
        artifacts.append(
            Artifact(platform=platform, path=str(out), sha256=None, command=cmd, compiled=False)
        )
    return BuildPlan(
        job_id=job_id,
        client_id=client_id,
        enrollment_token=enrollment_token,
        build_id=build_id,
        ldflags=flags,
        artifacts=tuple(artifacts),
        notes=tuple(notes),
    )


RunFn = Callable[..., subprocess.CompletedProcess[str]]


def try_compile(
    plan: BuildPlan,
    *,
    enabled: bool,
    go_bin: str | None = None,
    run: RunFn | None = None,
) -> BuildPlan:
    """Скомпилировать desktop-артефакты, если toolchain доступен. Android — только команда."""
    if not enabled:
        return plan
    go = go_bin or shutil.which("go")
    if not go:
        notes = plan.notes + ("go не найден в PATH — только команды, без бинарников.",)
        return BuildPlan(
            job_id=plan.job_id,
            client_id=plan.client_id,
            enrollment_token=plan.enrollment_token,
            build_id=plan.build_id,
            ldflags=plan.ldflags,
            artifacts=plan.artifacts,
            notes=notes,
        )
    runner = run or subprocess.run
    compiled: list[Artifact] = []
    for art in plan.artifacts:
        if art.platform.startswith("android") or not art.path:
            compiled.append(art)
            continue
        out = Path(art.path)
        out.parent.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        goos, _, goarch = art.platform.partition("/")
        env["GOOS"] = goos
        env["GOARCH"] = goarch
        env["CGO_ENABLED"] = "0"
        cmd = [
            go,
            "build",
            "-trimpath",
            f"-ldflags={plan.ldflags}",
            "-o",
            str(out),
            "./cmd/desktop",
        ]
        core_dir = _core_dir_from_command(art.command)
        result = runner(cmd, cwd=core_dir, env=env, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            compiled.append(
                Artifact(
                    platform=art.platform,
                    path=None,
                    sha256=None,
                    command=art.command,
                    compiled=False,
                )
            )
            continue
        digest = hashlib.sha256(out.read_bytes()).hexdigest() if out.is_file() else None
        compiled.append(
            Artifact(
                platform=art.platform,
                path=str(out) if out.is_file() else None,
                sha256=digest,
                command=art.command,
                compiled=out.is_file(),
            )
        )
    return BuildPlan(
        job_id=plan.job_id,
        client_id=plan.client_id,
        enrollment_token=plan.enrollment_token,
        build_id=plan.build_id,
        ldflags=plan.ldflags,
        artifacts=tuple(compiled),
        notes=plan.notes,
    )


def _core_dir_from_command(command: str) -> str:
    # "cd {core} && ..."
    prefix = command[3:].split(" &&", 1)[0].strip() if command.startswith("cd ") else "."
    return prefix
