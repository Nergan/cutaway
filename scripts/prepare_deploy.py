"""Remove non-deployable projects from an ephemeral hosting checkout."""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from orchestrator.config import load_runtime_config


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--profile", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Allow destructive pruning outside a CI checkout.",
    )
    args = parser.parse_args()

    root = args.root.resolve()
    if not args.dry_run and not args.force and os.getenv("CI", "").lower() != "true":
        parser.error("refusing to prune a non-CI checkout without --force")

    config = load_runtime_config(root, profile=args.profile)
    removed: list[str] = []
    for project in config.projects.values():
        if project.deploy:
            continue
        relative = project.directory.resolve().relative_to(root)
        removed.append(relative.as_posix())
        print(f"exclude {relative.as_posix()}: {project.reason or 'profile policy'}")
        if not args.dry_run and project.directory.exists():
            shutil.rmtree(project.directory)

    print(f"deployment profile {config.profile}: excluded {len(removed)} project(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
