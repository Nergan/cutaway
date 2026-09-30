from minecraft_mods.catalog import (
    JarLink,
    ModEntry,
    Catalog,
    classify_jars,
    classify_modrinth,
    github_repo_of,
    is_mod_repo_name,
    minecraft_and_loaders,
    parse_readme,
)
from minecraft_mods.render import render_inline, render_page
from orchestrator.config import load_runtime_config

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

TAMED_BODY = """
Minecraft **1.21.1** / NeoForge. Put the jars you need into the `mods` folder.

| File | Required | Source |
| --- | --- | --- |
| `tamedphantoms-1.0.0.jar` | Yes | this mod |
| `kotlinforforge-5.8.0-all.jar` | Yes | [Kotlin for Forge](https://modrinth.com/mod/kotlin-for-forge) (LGPL-2.1) |
| `Patchouli-*-NEOFORGE.jar` | No, only for the guidebook | [Patchouli](https://modrinth.com/mod/patchouli) (CC-BY-NC-SA-3.0) |
"""

HAMSTERS_BODY = """
Minecraft **1.20.1** / Forge 47 or NeoForge 20.1. Put the jars you need into the `mods` folder.

| File | Required | Source |
| --- | --- | --- |
| `hamsterscreatecompat-1.20.1-1.0.0.jar` | Yes | this compat |
| `create-1.20.1-6.0.8.jar` | Yes | [Create](https://modrinth.com/mod/create) |
| `hamsters-forge-1.0.3-1.20.1.jar` | Yes | [Hamsters](https://modrinth.com/mod/hamsters) |
"""

TAMED_README = """# Tamed Phantoms

**[English](README.md)** · **[Русский](README.ru.md)**

A **Minecraft 1.21.1** NeoForge mod: tame phantoms. Written with [Kotlin for Forge](https://modrinth.com/mod/kotlin-for-forge).

The UI is available in English and Russian.
"""

HAMSTERS_README = """# Create: Hamsters Compat

<img src="ico.jpg" alt="Create: Hamsters Compat" width="128">

[English version](README.md)

Компат-мод для [Create](https://modrinth.com/mod/create) и [Hamsters](https://modrinth.com/mod/hamsters) на **Minecraft 1.20.1**.

К ступице колеса можно подключить вал.
"""


def _asset(name: str) -> dict:
    return {
        "name": name,
        "browser_download_url": f"https://github.com/Nergan/example/releases/download/v1.0.0/{name}",
    }


def test_only_repository_names_ending_in_mod_are_collected():
    assert is_mod_repo_name("tamedphantoms-mod")
    assert is_mod_repo_name("more-critters-port-mod")
    assert not is_mod_repo_name("cull-less-leaves-for-neoforge")
    assert not is_mod_repo_name("more-critters-port")
    assert github_repo_of("https://github.com/Nergan/tamedphantoms-mod/issues") == "tamedphantoms-mod"
    assert github_repo_of("https://github.com/Nergan/placed-sticks-mod.git") == "placed-sticks-mod"


def test_readme_summary_keeps_links_and_skips_the_language_switch():
    title, paragraph = parse_readme(TAMED_README)
    assert title == "Tamed Phantoms"
    assert paragraph.startswith("A **Minecraft 1.21.1**")
    assert "Kotlin for Forge" in paragraph
    assert "English" not in paragraph

    title, paragraph = parse_readme(HAMSTERS_README)
    assert title == "Create: Hamsters Compat"
    assert paragraph.startswith("Компат-мод")
    assert "Hamsters" in paragraph
    assert "вал" not in paragraph


def test_release_table_splits_the_mod_jar_from_companion_jars():
    assets = [
        _asset("kotlinforforge-5.8.0-all.jar"),
        _asset("Patchouli-1.21.1-93-NEOFORGE.jar"),
        _asset("tamedphantoms-1.0.0.jar"),
        _asset("tamedphantoms-1.0.0-sources.jar"),
    ]
    mod_jars, deps, classified = classify_jars(assets, TAMED_BODY)
    assert classified
    assert [jar.name for jar in mod_jars] == ["tamedphantoms-1.0.0.jar"]
    assert [jar.name for jar in deps] == [
        "kotlinforforge-5.8.0-all.jar",
        "Patchouli-1.21.1-93-NEOFORGE.jar",
    ]
    minecraft, loaders = minecraft_and_loaders(TAMED_BODY)
    assert minecraft == "1.21.1"
    assert loaders == ["NeoForge"]


def test_compat_release_keeps_both_loaders_and_does_not_treat_hamsters_as_the_mod():
    assets = [
        _asset("create-1.20.1-6.0.8.jar"),
        _asset("hamsters-forge-1.0.3-1.20.1.jar"),
        _asset("hamsterscreatecompat-1.20.1-1.0.0.jar"),
    ]
    mod_jars, deps, classified = classify_jars(assets, HAMSTERS_BODY)
    assert classified
    assert [jar.name for jar in mod_jars] == ["hamsterscreatecompat-1.20.1-1.0.0.jar"]
    assert {jar.name for jar in deps} == {
        "create-1.20.1-6.0.8.jar",
        "hamsters-forge-1.0.3-1.20.1.jar",
    }
    minecraft, loaders = minecraft_and_loaders(HAMSTERS_BODY)
    assert minecraft == "1.20.1"
    assert loaders == ["NeoForge", "Forge"]


def test_modrinth_review_is_reported_separately_from_a_missing_page():
    state, url, status = classify_modrinth(
        {"slug": "tamed-phantoms", "project_type": "mod", "status": "processing"},
        declared_slug="tamed-phantoms",
        authenticated=True,
    )
    assert state == "moderation"
    assert url == "https://modrinth.com/mod/tamed-phantoms"
    assert status == "processing"

    hidden, hidden_url, _status = classify_modrinth(
        None,
        declared_slug="tamed-phantoms",
        authenticated=False,
    )
    assert hidden == "unavailable"
    assert hidden_url.endswith("/tamed-phantoms")

    missing, missing_url, _status = classify_modrinth(None, declared_slug="", authenticated=True)
    assert missing == "missing"
    assert missing_url == ""


def test_description_links_are_kept_and_markup_is_escaped():
    rendered = render_inline(
        'Port of [PatchouliButton](https://modrinth.com/mod/patchoulibutton). <script>alert(1)</script>',
        "https://github.com/Nergan/patchouli-button-rework-mod",
    )
    assert 'href="https://modrinth.com/mod/patchoulibutton"' in rendered
    assert "<script>" not in rendered
    assert "&lt;script&gt;" in rendered


def test_page_shows_a_mod_compactly_with_the_design_controls():
    mod = ModEntry(
        repo="tamedphantoms-mod",
        name="Tamed Phantoms",
        description_en="Tame phantoms with [cookies](https://modrinth.com/mod/kotlin-for-forge).",
        description_ru="Приручение фантомов через [Kotlin for Forge](https://modrinth.com/mod/kotlin-for-forge).",
        github_url="https://github.com/Nergan/tamedphantoms-mod",
        license_id="MPL-2.0",
        license_name="Mozilla Public License 2.0",
        license_url="https://github.com/Nergan/tamedphantoms-mod/blob/main/LICENSE",
        version="1.0.0",
        minecraft="1.21.1",
        loaders=["NeoForge"],
        mod_jars=[JarLink("tamedphantoms-1.0.0.jar", "https://github.com/Nergan/tamedphantoms-mod/releases/download/v1.0.0/tamedphantoms-1.0.0.jar")],
        dependency_jars=[JarLink("kotlinforforge-5.8.0-all.jar", "https://github.com/Nergan/tamedphantoms-mod/releases/download/v1.0.0/kotlinforforge-5.8.0-all.jar")],
        jars_classified=True,
        has_release=True,
        modrinth_state="moderation",
        modrinth_url="https://modrinth.com/mod/tamed-phantoms",
        modrinth_status="processing",
        license_text="Mozilla Public License Version 2.0\nThis is the license body.",
    )
    page = render_page(Catalog(mods=[mod], fetched_at=1_700_000_000), "ru", "name")
    assert "Приручение фантомов" in page
    assert "ещё проходит модерацию" in page
    assert "tamedphantoms-1.0.0.jar" in page
    assert "kotlinforforge-5.8.0-all.jar" in page
    assert "MPL-2.0" in page
    assert "This is the license body." in page
    assert "blob/main/LICENSE" not in page
    assert 'class="btn ext"' in page
    assert 'class="btn jar"' in page
    assert "<details" in page
    assert "--radius: 6px" in page
    assert 'class="custom-select"' not in page
    assert "на главную" not in page
    assert "Minecraft mods by" in page
    assert "<em>Nargan</em>" in page
    assert "::selection" in page
    assert "::-webkit-scrollbar" in page
    assert 'href="/mods?lang=en"' in page


def test_minecraft_mods_is_registered_on_the_public_prefix():
    config = load_runtime_config(ROOT, profile="local", isolation="embedded")
    project = config.projects["minecraft_mods"]
    assert project.prefix == "/mods"
    assert project.entrypoint == "minecraft_mods.minecraft_mods"
    assert project.run and project.deploy
    assert "MODRINTH_TOKEN" in project.env_allowlist
    assert "api.github.com" in project.network.allowed_hosts
    assert "api.modrinth.com" in project.network.allowed_hosts
