"""Typed, fail-closed configuration for project discovery and deployment."""

from __future__ import annotations

import argparse
import copy
import os
import re
import sys
import tomllib
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any, Iterable, Mapping


PROJECT_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")
VALID_PHASES = frozenset({"run", "build", "deploy"})
VALID_ISOLATION_MODES = frozenset({"isolated", "embedded"})


@dataclass(frozen=True)
class ProjectLimits:
    request_rate: int = 120
    request_window_seconds: int = 60
    request_bytes: int = 16 * 1024 * 1024
    response_bytes: int = 64 * 1024 * 1024
    traffic_bytes_per_minute: int = 256 * 1024 * 1024
    max_concurrency: int = 8
    queue_timeout_seconds: float = 3.0
    request_timeout_seconds: float = 60.0
    max_websockets: int = 0
    websocket_message_bytes: int = 1024 * 1024
    websocket_lifetime_seconds: float = 600.0
    memory_mb: int = 512
    cpu_percent: float = 100.0
    cpu_grace_seconds: float = 30.0
    max_processes: int = 4
    max_connections: int = 64
    temp_mb: int = 512
    idle_timeout_seconds: float = 900.0
    startup_timeout_seconds: float = 30.0
    restart_max: int = 3
    restart_window_seconds: float = 300.0
    restart_backoff_seconds: float = 5.0
    nofile: int = 128
    fsize_mb: int = 256

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any] | None) -> "ProjectLimits":
        raw = raw or {}
        known = {field.name for field in fields(cls)}
        unknown = sorted(set(raw) - known)
        if unknown:
            raise ValueError(f"Unknown limit keys: {', '.join(unknown)}")
        values = {key: raw[key] for key in known if key in raw}
        result = cls(**values)
        for name in (
            "request_rate",
            "request_window_seconds",
            "request_bytes",
            "response_bytes",
            "traffic_bytes_per_minute",
            "max_concurrency",
            "max_websockets",
            "websocket_message_bytes",
            "memory_mb",
            "max_processes",
            "max_connections",
            "temp_mb",
            "restart_max",
            "nofile",
            "fsize_mb",
        ):
            if getattr(result, name) < 0:
                raise ValueError(f"Limit {name} must not be negative.")
        return result


@dataclass(frozen=True)
class NetworkPolicy:
    allowed_hosts: tuple[str, ...] = ()
    allow_private: bool = False
    requests_per_minute: int = 0

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any] | None) -> "NetworkPolicy":
        raw = raw or {}
        unknown = sorted(set(raw) - {"allowed_hosts", "allow_private", "requests_per_minute"})
        if unknown:
            raise ValueError(f"Unknown network policy keys: {', '.join(unknown)}")
        return cls(
            allowed_hosts=tuple(str(host).lower().rstrip(".") for host in raw.get("allowed_hosts", ())),
            allow_private=bool(raw.get("allow_private", False)),
            requests_per_minute=int(raw.get("requests_per_minute", 0)),
        )


@dataclass(frozen=True)
class ProjectConfig:
    project_id: str
    directory: Path
    entrypoint: str
    prefix: str
    requirements: Path | None
    npm_build: bool
    startup: str
    run: bool
    build: bool
    deploy: bool
    ci: bool
    reason: str | None
    port: int
    env_allowlist: tuple[str, ...]
    env_defaults: Mapping[str, str]
    limits: ProjectLimits
    network: NetworkPolicy

    def participates(self, phase: str) -> bool:
        if phase not in VALID_PHASES:
            raise ValueError(f"Unknown project phase: {phase}")
        return bool(getattr(self, phase))


@dataclass(frozen=True)
class RuntimeConfig:
    root: Path
    profile: str
    isolation: str
    dependency_isolation: bool
    worker_host: str
    worker_base_port: int
    monitor_interval_seconds: float
    shutdown_grace_seconds: float
    global_memory_budget_mb: int
    projects: Mapping[str, ProjectConfig]

    def for_phase(self, phase: str) -> tuple[ProjectConfig, ...]:
        return tuple(project for project in self.projects.values() if project.participates(phase))


def _deep_merge(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(dict(base))
    for key, value in override.items():
        if isinstance(value, Mapping) and isinstance(merged.get(key), Mapping):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _normalise_isolation(value: str) -> str:
    value = value.strip().lower()
    aliases = {
        "1": "isolated",
        "true": "isolated",
        "yes": "isolated",
        "0": "embedded",
        "false": "embedded",
        "no": "embedded",
    }
    value = aliases.get(value, value)
    if value == "auto":
        return "isolated" if os.name == "posix" else "embedded"
    if value not in VALID_ISOLATION_MODES:
        allowed = ", ".join(sorted(VALID_ISOLATION_MODES | {"auto"}))
        raise ValueError(f"CUTAWAY_ISOLATION must be one of: {allowed}")
    return value


def _read_ignore_marker(directory: Path) -> tuple[frozenset[str], str | None]:
    marker = directory / ".project-ignore"
    if not marker.is_file():
        return frozenset(), None
    try:
        with marker.open("rb") as handle:
            raw = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        # A broken kill switch must fail closed, never accidentally enable a project.
        return VALID_PHASES, f"Invalid .project-ignore: {exc}"

    ignored = frozenset(phase for phase in VALID_PHASES if raw.get(phase) is True)
    reason = str(raw.get("reason", "")).strip() or None
    return ignored, reason


def _resolve_within(root: Path, value: str, *, field_name: str) -> Path:
    candidate = (root / value).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"{field_name} escapes the repository root: {value}") from exc
    return candidate


def _load_document(root: Path) -> dict[str, Any]:
    path = root / "orchestrator.toml"
    try:
        with path.open("rb") as handle:
            document = tomllib.load(handle)
    except FileNotFoundError as exc:
        raise ValueError(f"Missing orchestrator manifest: {path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"Invalid orchestrator manifest: {exc}") from exc
    if document.get("schema_version") != 1:
        raise ValueError("Unsupported orchestrator.toml schema_version; expected 1.")
    return document


def load_runtime_config(
    root: Path | None = None,
    *,
    profile: str | None = None,
    isolation: str | None = None,
) -> RuntimeConfig:
    root = (root or Path(__file__).resolve().parents[1]).resolve()
    document = _load_document(root)
    profiles = document.get("profiles", {})
    profile_name = profile or os.getenv("CUTAWAY_PROFILE") or document.get("default_profile", "local")
    if profile_name not in profiles:
        raise ValueError(f"Unknown CUTAWAY_PROFILE: {profile_name}")
    profile_data = profiles[profile_name]

    orchestrator_data = document.get("orchestrator", {})
    worker_base_port = int(orchestrator_data.get("worker_base_port", 8100))
    selected_isolation = _normalise_isolation(
        isolation or os.getenv("CUTAWAY_ISOLATION") or str(profile_data.get("isolation", "embedded"))
    )
    dependency_isolation = bool(profile_data.get("dependency_isolation", selected_isolation == "isolated"))
    global_memory_budget_mb = int(
        profile_data.get(
            "global_memory_budget_mb",
            orchestrator_data.get("global_memory_budget_mb", 12 * 1024),
        )
    )

    projects: dict[str, ProjectConfig] = {}
    prefixes: set[str] = set()
    profile_projects = profile_data.get("projects", {})
    for index, (project_id, base_project) in enumerate(document.get("projects", {}).items()):
        if not PROJECT_ID_RE.fullmatch(project_id):
            raise ValueError(f"Invalid project id: {project_id}")
        merged = _deep_merge(base_project, profile_projects.get(project_id, {}))
        directory = _resolve_within(root, str(merged.get("directory", project_id)), field_name="directory")
        ignored_phases, marker_reason = _read_ignore_marker(directory)

        prefix = str(merged.get("prefix", f"/{project_id.replace('_', '-')}"))
        if not prefix.startswith("/") or prefix == "/" or prefix.endswith("/"):
            raise ValueError(f"Invalid prefix for {project_id}: {prefix}")
        if prefix in prefixes:
            raise ValueError(f"Duplicate project prefix: {prefix}")
        prefixes.add(prefix)

        requirements_value = merged.get("requirements")
        requirements = (
            _resolve_within(root, str(requirements_value), field_name="requirements")
            if requirements_value
            else None
        )
        env_allowlist = tuple(str(name) for name in merged.get("env_allowlist", ()))
        env_defaults = {str(key): str(value) for key, value in merged.get("env_defaults", {}).items()}
        undeclared_defaults = sorted(set(env_defaults) - set(env_allowlist))
        if undeclared_defaults:
            raise ValueError(
                f"{project_id} env_defaults are not in env_allowlist: {', '.join(undeclared_defaults)}"
            )

        phase_values = {
            phase: bool(merged.get(phase, True)) and phase not in ignored_phases
            for phase in VALID_PHASES
        }
        if any(phase_values.values()) and not directory.is_dir():
            raise ValueError(f"Active project directory does not exist: {directory}")
        if phase_values["build"] and requirements is not None and not requirements.is_file():
            raise ValueError(f"Requirements file does not exist: {requirements}")
        projects[project_id] = ProjectConfig(
            project_id=project_id,
            directory=directory,
            entrypoint=str(merged["entrypoint"]),
            prefix=prefix,
            requirements=requirements,
            npm_build=bool(merged.get("npm_build", False)),
            startup=str(merged.get("startup", "lazy")),
            run=phase_values["run"],
            build=phase_values["build"],
            deploy=phase_values["deploy"],
            ci=bool(merged.get("ci", True)),
            reason=marker_reason or (str(merged.get("reason")).strip() if merged.get("reason") else None),
            port=worker_base_port + index,
            env_allowlist=env_allowlist,
            env_defaults=env_defaults,
            limits=ProjectLimits.from_mapping(merged.get("limits")),
            network=NetworkPolicy.from_mapping(merged.get("network")),
        )

    declared_memory = sum(project.limits.memory_mb for project in projects.values() if project.run)
    if global_memory_budget_mb > 0 and declared_memory > global_memory_budget_mb:
        raise ValueError(
            f"Profile {profile_name} declares {declared_memory} MiB of project memory, "
            f"above its {global_memory_budget_mb} MiB budget."
        )

    return RuntimeConfig(
        root=root,
        profile=profile_name,
        isolation=selected_isolation,
        dependency_isolation=dependency_isolation,
        worker_host=str(orchestrator_data.get("worker_host", "127.0.0.1")),
        worker_base_port=worker_base_port,
        monitor_interval_seconds=float(orchestrator_data.get("monitor_interval_seconds", 2.0)),
        shutdown_grace_seconds=float(orchestrator_data.get("shutdown_grace_seconds", 10.0)),
        global_memory_budget_mb=global_memory_budget_mb,
        projects=projects,
    )


def _lines(projects: Iterable[ProjectConfig], attribute: str) -> Iterable[str]:
    for project in projects:
        value = getattr(project, attribute)
        if isinstance(value, Path):
            yield value.as_posix()
        elif value is not None:
            yield str(value)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect the cutaway orchestrator manifest.")
    parser.add_argument("--root", type=Path)
    parser.add_argument("--profile")
    parser.add_argument("--isolation")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate")
    list_parser = subparsers.add_parser("list")
    list_parser.add_argument("--phase", choices=sorted(VALID_PHASES), required=True)
    list_parser.add_argument(
        "--field",
        choices=("project_id", "directory", "requirements", "npm_build"),
        default="project_id",
    )
    settings_parser = subparsers.add_parser("settings")
    settings_parser.add_argument(
        "--field",
        choices=("profile", "isolation", "dependency_isolation", "global_memory_budget_mb"),
        required=True,
    )
    args = parser.parse_args(argv)

    try:
        config = load_runtime_config(args.root, profile=args.profile, isolation=args.isolation)
    except ValueError as exc:
        print(f"orchestrator config error: {exc}", file=sys.stderr)
        return 2

    if args.command == "validate":
        print(
            f"profile={config.profile} isolation={config.isolation} "
            f"projects={len(config.projects)} active={len(config.for_phase('run'))}"
        )
        return 0

    if args.command == "settings":
        value = getattr(config, args.field)
        if isinstance(value, bool):
            print("true" if value else "false")
        else:
            print(value)
        return 0

    projects = config.for_phase(args.phase)
    for value in _lines(projects, args.field):
        print(value)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
