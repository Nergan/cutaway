"""Orchestrator limits that formular speech depends on."""

from __future__ import annotations

import shutil
import time
from pathlib import Path

from orchestrator.config import ProjectLimits, load_runtime_config
from orchestrator.supervisor import busy_marker_fresh, cpu_contribution

_SCRATCH = Path(__file__).resolve().parents[1] / ".pytest-tmp" / "formular-safety"


def _scratch(name: str) -> Path:
    folder = _SCRATCH / name
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(parents=True)
    return folder


def test_heavy_jobs_stay_one_when_page_concurrency_rises():
    derived = ProjectLimits(max_concurrency=6)
    assert derived.resolved_heavy_jobs() == 2
    pinned = ProjectLimits.from_mapping({"max_concurrency": 6, "heavy_jobs": 1})
    assert pinned.resolved_heavy_jobs() == 1


def test_nice_background_cpu_does_not_count_toward_the_kill():
    assert cpu_contribution(200, 19, 19) == 0
    assert cpu_contribution(200, 0, 19) == 200
    assert cpu_contribution(200, 19, 0) == 200


def test_hf_formular_can_download_weights_inside_the_memory_budget():
    config = load_runtime_config(Path(__file__).resolve().parents[1], profile="hf", isolation="isolated")
    formular = config.projects["formular"]
    assert formular.limits.memory_mb == 5120
    assert formular.limits.temp_mb == 8192
    assert formular.limits.fsize_mb == 4096
    assert formular.limits.cpu_exempt_nice == 19
    assert formular.network.enforce_allowlist is True
    assert formular.network.requests_per_minute >= 2000
    assert "huggingface.co" in formular.network.allowed_hosts
    declared = sum(project.limits.memory_mb for project in config.projects.values() if project.run)
    assert declared <= config.global_memory_budget_mb


def test_busy_marker_blocks_idle_stop_only_while_fresh():
    marker = _scratch("busy") / "busy"
    assert busy_marker_fresh(marker) is False
    marker.write_text("", encoding="utf-8")
    now = time.time()
    assert busy_marker_fresh(marker, now=now) is True
    assert busy_marker_fresh(marker, now=now + 120) is False
