from dataclasses import replace
from pathlib import Path

from orchestrator.config import load_runtime_config
from orchestrator.hosting_policy import (
    published_text,
    scan_published_tree,
    validate_profile,
)
from orchestrator import hosting_policy as policy


ROOT = Path(__file__).resolve().parents[1]


def test_hf_hosting_policy_accepts_current_tree():
    config = load_runtime_config(ROOT, profile="hf", isolation="isolated")
    assert validate_profile(config) == []


def test_hf_policy_requires_remote_browser_to_stay_disabled():
    config = load_runtime_config(ROOT, profile="hf", isolation="isolated")
    project = config.projects["yellow_mirror"]
    broken = replace(
        config,
        projects={**config.projects, project.project_id: replace(project, deploy=True)},
    )
    findings = validate_profile(broken)
    assert any(item.rule_id == "required_exclusion" for item in findings)


def test_published_scan_rejects_tunnel_tooling_in_a_live_project():
    hits = policy._scan_text("toadcode/probe.txt", "npx " + "wra" + "ngler deploy\n")
    assert any(item.rule_id == "tunnel_worker" for item in hits)


def test_formular_browser_runtime_is_scrubbed_from_the_space_tree():
    rewritten = published_text(ROOT, ROOT / "formular" / "requirements.txt")
    assert rewritten is not None
    assert "play" + "wright" not in rewritten.lower()
    assert published_text(ROOT, ROOT / "formular" / "core" / "html_pdf.py") is None


def test_unpublished_projects_stay_on_github_and_leave_the_space_tree():
    config = load_runtime_config(ROOT, profile="hf", isolation="isolated")
    github_readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "yellow" + "_mirror" in github_readme
    space_readme = published_text(ROOT, ROOT / "README.md")
    assert space_readme is not None
    assert "yellow" + "_mirror" not in space_readme

    manifest = published_text(
        ROOT,
        ROOT / "orchestrator.toml",
        unpublished_ids=policy.unpublished_project_ids(config),
    )
    assert manifest is not None
    assert "yellow" + "_mirror" not in manifest
    assert "[projects.another]" not in manifest
    assert "[projects.age]" not in manifest
    assert "[projects.formular]" in manifest


def test_html_to_pdf_keeps_an_office_fallback():
    text = (ROOT / "formular" / "core" / "converter.py").read_text(encoding="utf-8")
    assert "async def _html_to_pdf_office" in text
    assert "render_html_to_pdf is not None" in text
    assert "play" + "wright" not in text.lower()


def test_published_tree_scan_is_clean():
    config = load_runtime_config(ROOT, profile="hf", isolation="isolated")
    assert scan_published_tree(config) == []


def test_stripped_checkout_passes_hosting_policy():
    config = load_runtime_config(ROOT, profile="hf", isolation="isolated")
    unpublished = {"another", "yellow_mirror"}
    stripped = replace(
        config,
        root=ROOT,
        projects={key: value for key, value in config.projects.items() if key not in unpublished},
    )
    # Directories still exist in the GitHub tree, so an unregistered leftover must fail.
    leftover = policy.audit_manifest(stripped)
    assert any(item.rule_id == "missing_exclusion" for item in leftover)

    empty_root = ROOT / ".pytest-tmp" / "stripped-hf-root"
    empty_root.mkdir(parents=True, exist_ok=True)
    published = replace(stripped, root=empty_root)
    assert policy.audit_manifest(published) == []
    assert validate_profile(published, published=True) == []
