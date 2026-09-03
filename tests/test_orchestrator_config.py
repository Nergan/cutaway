import os
import subprocess
import sys
from pathlib import Path

from orchestrator.config import load_runtime_config


ROOT = Path(__file__).resolve().parents[1]
SCRATCH = ROOT / ".pytest-tmp"


def _scratch_dir(name: str) -> Path:
    path = SCRATCH / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def test_hf_profile_disables_policy_sensitive_projects():
    config = load_runtime_config(ROOT, profile="hf", isolation="isolated")

    assert config.isolation == "isolated"
    assert config.projects["another"].run is False
    assert config.projects["another"].build is False
    assert config.projects["another"].deploy is False
    assert config.projects["another"].ci is True
    assert config.projects["yellow_mirror"].run is False
    assert config.projects["yellow_mirror"].deploy is False
    assert {project.project_id for project in config.for_phase("run")} == {
        "formular",
        "toadcode",
        "markbin",
        "kanban",
        "snake",
        "soon",
        "evenfest",
        "dnd",
        "netlazy",
        "ascii_city",
    }


def test_project_ignore_is_a_global_kill_switch():
    config = load_runtime_config(ROOT, profile="local", isolation="embedded")

    another = config.projects["another"]
    assert another.run is False
    assert another.build is False
    assert another.deploy is False
    assert another.reason
    assert config.projects["yellow_mirror"].run is True


def test_hf_defaults_to_process_isolation(monkeypatch):
    monkeypatch.delenv("CUTAWAY_ISOLATION", raising=False)
    config = load_runtime_config(ROOT, profile="hf")
    assert config.isolation == "isolated"


def test_isolation_env_overrides_profile(monkeypatch):
    monkeypatch.setenv("CUTAWAY_ISOLATION", "embedded")
    config = load_runtime_config(ROOT, profile="hf")
    assert config.isolation == "embedded"


def test_invalid_ignore_marker_fails_closed():
    tmp_path = _scratch_dir("test_invalid_ignore_marker")
    (tmp_path / "demo").mkdir(exist_ok=True)
    (tmp_path / "demo" / ".project-ignore").write_text("not valid = [", encoding="utf-8")
    (tmp_path / "orchestrator.toml").write_text(
        """
schema_version = 1
default_profile = "test"

[orchestrator]
global_memory_budget_mb = 1024

[profiles.test]
isolation = "embedded"

[projects.demo]
directory = "demo"
entrypoint = "demo.main"
prefix = "/demo"
""",
        encoding="utf-8",
    )

    config = load_runtime_config(tmp_path, profile="test", isolation="embedded")

    assert config.projects["demo"].run is False
    assert config.projects["demo"].build is False
    assert config.projects["demo"].deploy is False
    assert "Invalid .project-ignore" in config.projects["demo"].reason


def test_unregistered_directories_are_never_discovered():
    tmp_path = _scratch_dir("test_unregistered_directories")
    (tmp_path / "declared").mkdir(exist_ok=True)
    (tmp_path / "surprise").mkdir(exist_ok=True)
    (tmp_path / "orchestrator.toml").write_text(
        """
schema_version = 1
default_profile = "test"

[profiles.test]
isolation = "embedded"

[projects.declared]
directory = "declared"
entrypoint = "declared.main"
prefix = "/declared"
""",
        encoding="utf-8",
    )

    config = load_runtime_config(tmp_path, profile="test", isolation="embedded")

    assert set(config.projects) == {"declared"}


def test_isolated_hub_imports_no_project_modules():
    env = os.environ.copy()
    env.update({"CUTAWAY_PROFILE": "hf", "CUTAWAY_ISOLATION": "isolated"})
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys, main; "
                "names=('formular','toadcode','markbin','kanban','snake','soon','evenfest','dnd','netlazy','another'); "
                "print(','.join(name for name in names if name in sys.modules))"
            ),
        ],
        cwd=ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.stdout.strip() == ""


def test_worker_factory_imports_only_selected_project():
    env = os.environ.copy()
    env.update(
        {
            "CUTAWAY_PROFILE": "local",
            "CUTAWAY_WORKER_PROJECT": "kanban",
        }
    )
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; from orchestrator.worker import create_app; create_app(); "
                "names=('formular','toadcode','markbin','snake','soon','evenfest','dnd','netlazy','another'); "
                "print(','.join(name for name in names if name in sys.modules))"
            ),
        ],
        cwd=ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.stdout.strip() == ""


def test_hf_deploy_pruner_reports_both_exclusions():
    result = subprocess.run(
        [
            sys.executable,
            "scripts/prepare_deploy.py",
            "--root",
            str(ROOT),
            "--profile",
            "hf",
            "--dry-run",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert "exclude another" in result.stdout
    assert "exclude yellow_mirror" in result.stdout
