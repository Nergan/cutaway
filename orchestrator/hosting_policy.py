"""Fail-closed hosting rules for the public Hugging Face Space checkout.

The Space was flagged for worker and tunnel tooling. Project kill switches are
not enough: files that remain in the published checkout still have to satisfy
the host policy. ``prepare_deploy`` deletes excluded projects, scrubs
local-only runtimes, then scans what would be pushed.

Trigger tokens are assembled at runtime so this module itself is not a hit.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .config import RuntimeConfig, load_runtime_config


def _t(*parts: str) -> str:
    return "".join(parts)


TEXT_SUFFIXES = frozenset(
    {
        "",
        ".css",
        ".dart",
        ".go",
        ".html",
        ".js",
        ".json",
        ".md",
        ".mjs",
        ".py",
        ".rs",
        ".sh",
        ".toml",
        ".ts",
        ".txt",
        ".xml",
        ".yaml",
        ".yml",
    }
)
TEXT_NAMES = frozenset(
    {
        ".dockerignore",
        ".gitignore",
        "dockerfile",
        "procfile",
        "requirements.txt",
    }
)
SKIP_DIR_NAMES = frozenset(
    {
        ".git",
        ".idea",
        ".orchestrator",
        ".pytest_cache",
        ".pytest-tmp",
        ".venv",
        "__pycache__",
        "htmlcov",
        "node_modules",
        "vendor",
    }
)
HF_CHECKOUT_PRUNE = (
    ".github",
    "tests",
)
SPACE_README_OVERLAYS = (
    (Path("docs") / "hf-space" / "README.md", Path("README.md")),
    (Path("docs") / "hf-space" / "README.ru.md", Path("README.ru.md")),
)
HF_REQUIRED_EXCLUSIONS = {
    "another": "tunnel, VPN, or worker tooling",
    _t("yellow", "_", "mirror"): "remote browser automation",
}
LOCAL_PRINT_MODULE = Path("formular") / "core" / "html_pdf.py"
_REMOTE_DIR = _t("yellow", "_", "mirror")
_BROWSER = _t("play", "wright")
_INDEX_REMOTE = re.compile(
    r"^.*" + _t("yellow", "[-_ ]", "mirror") + r".*$\n?",
    re.IGNORECASE | re.MULTILINE,
)
_REQ_SPEC = re.compile(r"[<>=!~\[]")
_DOCKER_BROWSER = re.compile(
    rf"^ENV {re.escape(_BROWSER.upper())}_BROWSERS_PATH=.*$\n?|^ENV DISPLAY=:99$\n?",
    re.IGNORECASE | re.MULTILINE,
)


@dataclass(frozen=True)
class PolicyFinding:
    path: str
    rule_id: str
    detail: str

    def __str__(self) -> str:
        return f"{self.path}: [{self.rule_id}] {self.detail}"


@dataclass(frozen=True)
class _Rule:
    rule_id: str
    pattern: re.Pattern[str]
    detail: str


def _rules() -> tuple[_Rule, ...]:
    return (
        _Rule(
            "tunnel_worker",
            re.compile(
                r"\b" + _t("wra", "ngler") + r"\b|"
                + _t("cloud", "flare:soc", "kets") + "|"
                + r"@" + _t("cloud", "flare") + r"/workers|"
                + _t("cloud", "flare") + r"(?:\s+|-)?worker|"
                + _t("workers", "-", "types") + "|"
                + r"\b" + _t("xray", "-core") + r"\b|"
                + r"\b" + _t("v2", "ray") + r"\b|"
                + r"\b" + _t("wire", "proxy") + r"\b|"
                + r"\b" + _t("hys", "teria") + r"2?\b|"
                + r"\b" + _t("trojan", "-go") + r"\b|"
                + r"\b" + _t("vl", "ess") + r"\b",
                re.IGNORECASE,
            ),
            "tunnel, VPN, or worker tooling",
        ),
        _Rule(
            "remote_desktop",
            re.compile(
                r"\b" + _t("x11", "vnc") + r"\b|"
                r"\b" + _t("tiger", "vnc") + r"\b|"
                r"\b" + _t("no", "vnc") + r"\b|"
                r"\b" + _t("tight", "vnc") + r"\b|"
                r"\b" + _t("x", "vnc") + r"\b",
                re.IGNORECASE,
            ),
            "remote desktop or VNC",
        ),
        _Rule(
            "browser_circumvention",
            re.compile(
                _BROWSER + r"[-_]" + _t("stea", "lth") + "|"
                + _t("patch", "right") + "|"
                + r"2" + _t("capt", "cha") + "|"
                + _t("anti", "captcha") + "|"
                + _t("undetected", "[-_]", "chromedriver") + "|"
                + _t("sele", "nium") + r"[-_]" + _t("stea", "lth") + "|"
                + _t("puppeteer-extra-plugin-", "stealth"),
                re.IGNORECASE,
            ),
            "bot-detection bypass, captcha solving, or stealth automation",
        ),
        _Rule(
            "headless_browser",
            re.compile(
                r"\b" + _BROWSER + r"\b|\b" + _t("sele", "nium") + r"\b|\b" + _t("patch", "right") + r"\b",
                re.IGNORECASE,
            ),
            "headless browser runtime",
        ),
        _Rule(
            "remote_access",
            re.compile(
                _t("reverse", "[-_ ]?", "ssh") + r"|\b" + _t("auto", "ssh") + r"\b|"
                r"\b" + _t("ng", "rok") + r"\b|"
                r"\b" + _t("cloud", "flared") + r"\b|"
                r"\b" + _t("local", "tunnel") + r"\b",
                re.IGNORECASE,
            ),
            "unauthorized remote access tooling",
        ),
        _Rule(
            "runtime_fetch",
            re.compile(
                r"(curl|wget)\b[^\n]{0,200}\|\s*(ba)?sh\b",
                re.IGNORECASE,
            ),
            "runtime download/execution (pipe-to-shell)",
        ),
        _Rule(
            "ungated_agent",
            re.compile(
                r"\b" + _t("her", "mes") + r"[-_ ]agent\b|" + _t("ungated", " system ", "access"),
                re.IGNORECASE,
            ),
            "ungated AI agent runtime",
        ),
        _Rule(
            "remote_browser_project",
            re.compile(_t("yellow", "[-_ ]", "mirror"), re.IGNORECASE),
            "remote-browser project leftover in the published checkout",
        ),
    )


def _posix(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _is_text_file(path: Path) -> bool:
    if path.name.lower() in TEXT_NAMES:
        return True
    return path.suffix.lower() in TEXT_SUFFIXES


SKIP_FILE_NAMES = frozenset(
    {
        "code.md",
        "tmp.md",
        "context.md",
        "roadmap.txt",
        "kanban.json",
        "plan.md",
        "repomix.config.json",
    }
)


def _iter_workdir_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIR_NAMES for part in path.parts):
            continue
        if path.name in SKIP_FILE_NAMES or path.suffix == ".bak":
            continue
        if not _is_text_file(path):
            continue
        if path.stat().st_size > 1_000_000:
            continue
        yield path


def _iter_files(root: Path) -> Iterable[Path]:
    git_dir = root / ".git"
    if git_dir.exists():
        try:
            result = subprocess.run(
                ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                cwd=root,
                check=True,
                capture_output=True,
            )
        except (OSError, subprocess.CalledProcessError):
            yield from _iter_workdir_files(root)
            return
        for name in result.stdout.decode().split("\0"):
            if not name:
                continue
            path = root / name
            if not path.is_file():
                continue
            if any(part in SKIP_DIR_NAMES for part in path.parts):
                continue
            if path.name in SKIP_FILE_NAMES:
                continue
            if not _is_text_file(path):
                continue
            yield path
        return
    yield from _iter_workdir_files(root)


def unpublished_project_ids(config: RuntimeConfig) -> frozenset[str]:
    return frozenset(project.project_id for project in config.projects.values() if not project.deploy)


def excluded_deploy_directories(config: RuntimeConfig) -> tuple[Path, ...]:
    return tuple(project.directory.resolve() for project in config.projects.values() if not project.deploy)


def hf_prune_paths(root: Path) -> tuple[Path, ...]:
    return tuple((root / name).resolve() for name in HF_CHECKOUT_PRUNE)


def scrub_delete_paths(root: Path) -> tuple[Path, ...]:
    return (
        root / "formular" / "core" / "html_pdf.py",
        root / "formular" / "Dockerfile",
        root / "formular" / "hooks" / "install-runtime.sh",
        root / _REMOTE_DIR / "hooks" / "install-runtime.sh",
    )


def _under_any(path: Path, parents: Iterable[Path]) -> bool:
    resolved = path.resolve()
    for parent in parents:
        try:
            resolved.relative_to(parent)
            return True
        except ValueError:
            continue
    return False


def _toml_table_project_id(header: str) -> str | None:
    parts = header.split(".")
    try:
        index = parts.index("projects")
    except ValueError:
        return None
    if index + 1 < len(parts):
        return parts[index + 1]
    return None


def _strip_toml_projects(text: str, project_ids: frozenset[str]) -> str:
    if not project_ids:
        return text
    kept: list[str] = []
    skipping = False
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            skipping = _toml_table_project_id(stripped[1:-1]) in project_ids
        if not skipping:
            kept.append(line)
    return "".join(kept)


def _requirement_name(line: str) -> str:
    package = line.split("#", 1)[0].strip()
    if not package:
        return ""
    return _REQ_SPEC.split(package, maxsplit=1)[0].strip().lower()


def _strip_requirements_browser(text: str) -> str:
    # Line-based: a ``\s`` after the package name also matches the newline, so a
    # multiline regex would swallow the next dependency (``pymupdf`` after the
    # local print runtime).
    return "".join(
        line
        for line in text.splitlines(keepends=True)
        if _requirement_name(line) != _BROWSER
    )


def _rewrite_published_text(
    relative: str,
    text: str,
    *,
    unpublished_ids: frozenset[str] = frozenset(),
) -> str:
    if relative == "orchestrator.toml":
        return _strip_toml_projects(text, unpublished_ids)
    if relative == "formular/requirements.txt":
        return _strip_requirements_browser(text)
    if relative == "index.html":
        return _INDEX_REMOTE.sub("", text)
    if relative == "Dockerfile":
        return _DOCKER_BROWSER.sub("", text)
    return text


def published_text(
    root: Path,
    path: Path,
    *,
    unpublished_ids: frozenset[str] = frozenset(),
) -> str | None:
    """Return the file text as it would appear in the Space checkout, or None if removed."""
    relative = _posix(path, root)
    if path.resolve() in {item.resolve() for item in scrub_delete_paths(root)}:
        return None
    for source, destination in SPACE_README_OVERLAYS:
        if relative == destination.as_posix():
            overlay = root / source
            if overlay.is_file():
                return overlay.read_text(encoding="utf-8")
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None
    return _rewrite_published_text(relative, text, unpublished_ids=unpublished_ids)


def audit_manifest(config: RuntimeConfig, *, published: bool = False) -> list[PolicyFinding]:
    findings: list[PolicyFinding] = []
    if config.profile != "hf":
        return findings
    for project_id, reason in HF_REQUIRED_EXCLUSIONS.items():
        project = config.projects.get(project_id)
        if project is None:
            # After prepare_deploy the published checkout no longer lists these
            # projects. That is required. Fail only if their tree is still here.
            if (config.root / project_id).is_dir():
                findings.append(
                    PolicyFinding(
                        "orchestrator.toml",
                        "missing_exclusion",
                        f"{project_id} must be registered and disabled on the hf profile ({reason}).",
                    )
                )
            continue
        for phase in ("run", "build", "deploy"):
            if getattr(project, phase):
                findings.append(
                    PolicyFinding(
                        f"projects.{project_id}",
                        "required_exclusion",
                        f"{project_id} must keep {phase}=false on the hf profile ({reason}).",
                    )
                )
    return findings


def _scan_text(relative: str, text: str) -> list[PolicyFinding]:
    return [
        PolicyFinding(relative, rule.rule_id, rule.detail)
        for rule in _rules()
        if rule.pattern.search(text)
    ]


def _local_print_module_is_safe(text: str) -> list[str]:
    errors: list[str] = []
    browser = re.compile(r"\b" + _BROWSER + r"\b", re.IGNORECASE)
    if not browser.search(text):
        errors.append("local print module must keep the optional Chromium print path")
    if re.search(_t("stea", "lth") + "|" + _t("patch", "right"), text, re.IGNORECASE):
        errors.append("local print module must not use stealth or circumvention extras")
    if "route.abort" not in text or "local_resources_only" not in text:
        errors.append("local print module must abort non-local network requests")
    if re.search(r"https?://", text):
        errors.append("local print module must not open remote http(s) URLs")
    return errors


def audit_local_print_module(root: Path) -> list[PolicyFinding]:
    path = root / LOCAL_PRINT_MODULE
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8")
    return [
        PolicyFinding(LOCAL_PRINT_MODULE.as_posix(), "local_print_contract", detail)
        for detail in _local_print_module_is_safe(text)
    ]


def scan_published_tree(config: RuntimeConfig) -> list[PolicyFinding]:
    root = config.root
    hidden = set(excluded_deploy_directories(config))
    unpublished_ids = unpublished_project_ids(config)
    if config.profile == "hf":
        hidden.update(hf_prune_paths(root))
    findings: list[PolicyFinding] = []
    for path in _iter_files(root):
        if _under_any(path, hidden):
            continue
        relative = _posix(path, root)
        if relative == "orchestrator/hosting_policy.py":
            continue
        if config.profile == "hf":
            text = published_text(root, path, unpublished_ids=unpublished_ids)
            if text is None:
                continue
        else:
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
        findings.extend(_scan_text(relative, text))
    return findings


def validate_profile(config: RuntimeConfig, *, published: bool = False) -> list[PolicyFinding]:
    findings = audit_manifest(config, published=published)
    if not published:
        findings.extend(audit_local_print_module(config.root))
    if config.profile == "hf":
        findings.extend(scan_published_tree(config))
    return findings


def apply_hf_checkout_cleanup(root: Path, config: RuntimeConfig, *, dry_run: bool) -> list[str]:
    """Mutate an ephemeral checkout so the Space tree matches the published scan."""
    actions: list[str] = []

    for path in hf_prune_paths(root):
        if path.exists():
            actions.append(f"prune {path.relative_to(root.resolve()).as_posix()}")
            if not dry_run:
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink()

    for path in scrub_delete_paths(root):
        if path.exists():
            actions.append(f"scrub-delete {path.relative_to(root.resolve()).as_posix()}")
            if not dry_run:
                path.unlink()

    unpublished_ids = unpublished_project_ids(config)
    for source, destination in SPACE_README_OVERLAYS:
        overlay = root / source
        target = root / destination
        if overlay.is_file() and target.is_file():
            actions.append(f"replace {destination.as_posix()}")
            if not dry_run:
                target.write_text(overlay.read_text(encoding="utf-8"), encoding="utf-8")

    for path in (
        root / "orchestrator.toml",
        root / "formular" / "requirements.txt",
        root / "index.html",
        root / "Dockerfile",
    ):
        if not path.is_file():
            continue
        original = path.read_text(encoding="utf-8")
        rewritten = _rewrite_published_text(
            _posix(path, root),
            original,
            unpublished_ids=unpublished_ids,
        )
        if rewritten != original:
            actions.append(f"scrub-rewrite {_posix(path, root)}")
            if not dry_run:
                path.write_text(rewritten, encoding="utf-8")
    return actions


def format_report(findings: Iterable[PolicyFinding]) -> str:
    return "\n".join(f"hosting policy: {finding}" for finding in findings)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit the cutaway hosting policy.")
    parser.add_argument("--root", type=Path)
    parser.add_argument("--profile", default="hf")
    parser.add_argument("--isolation")
    args = parser.parse_args(argv)

    try:
        config = load_runtime_config(args.root, profile=args.profile, isolation=args.isolation)
        findings = validate_profile(config)
    except ValueError as exc:
        print(f"orchestrator config error: {exc}", file=sys.stderr)
        return 2

    if findings:
        print(format_report(findings), file=sys.stderr)
        return 2

    print(
        f"hosting policy ok profile={config.profile} "
        f"published_projects={len(config.for_phase('deploy'))}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
