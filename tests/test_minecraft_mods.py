from minecraft_mods.catalog import (
    JarLink,
    ModEntry,
    Catalog,
    _build_mod,
    classify_jars,
    classify_modrinth,
    modrinth_website,
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
        readme_ru="# Приручение\n\nПодробности тут.",
    )
    page = render_page(Catalog(mods=[mod], fetched_at=1_700_000_000), "ru", "name")
    assert "Приручение фантомов" in page
    assert "ещё проходит модерацию" in page
    assert "tamedphantoms-1.0.0.jar" in page
    assert "kotlinforforge-5.8.0-all.jar" in page
    assert "MPL-2.0" in page
    assert "This is the license body." in page
    assert "Подробности тут." in page
    assert "blob/main/LICENSE" not in page
    assert 'class="btn ext"' in page
    assert 'class="btn jar"' in page
    assert "<dialog" in page
    assert "<details" not in page
    assert "donate-widget.js" in page
    assert "column-width: 300px" in page
    assert "--radius: 6px" in page
    assert 'class="custom-select"' not in page
    assert "на главную" not in page
    assert "Minecraft mods by" in page
    assert "<em>Nargan</em>" in page
    assert "::selection" in page
    assert "::-webkit-scrollbar" in page
    assert 'href="/mods?lang=en"' in page
    assert 'href="/mods/tamedphantoms-mod/jars.zip"' in page
    assert 'download="tamedphantoms-mod.zip"' in page
    assert 'class="btn zip"' in page
    assert 'class="file-list"' in page
    assert "скачать всё" in page
    assert ">мод<" in page
    assert ".readme a" in page


def test_addon_release_treats_this_addon_as_the_mod_jar():
    body = """
Minecraft **1.21.1** / NeoForge

| File | Required | Source |
| --- | --- | --- |
| `reallyusefulribbits-*.jar` | Yes | this addon |
| `kotlinforforge-5.8.0-all.jar` | Yes | [Kotlin for Forge](https://modrinth.com/mod/kotlin-for-forge) |
| `Ribbits-1.21.1-NeoForge-4.1.6.jar` | Yes | [Ribbits](https://modrinth.com/mod/ribbits) |
"""
    assets = [
        _asset("reallyusefulribbits-1.0.0.jar"),
        _asset("kotlinforforge-5.8.0-all.jar"),
        _asset("Ribbits-1.21.1-NeoForge-4.1.6.jar"),
        _asset("geckolib-neoforge-1.21.1-4.7.6.jar"),
    ]
    mod_jars, deps, classified = classify_jars(assets, body)
    assert classified
    assert [jar.name for jar in mod_jars] == ["reallyusefulribbits-1.0.0.jar"]
    assert "kotlinforforge-5.8.0-all.jar" in [jar.name for jar in deps]
    assert "geckolib-neoforge-1.21.1-4.7.6.jar" in [jar.name for jar in deps]


def test_jar_archive_packs_the_card_files(monkeypatch):
    import io
    import zipfile

    from minecraft_mods.catalog import build_jar_archive

    def fake_get(url, headers, max_bytes=1_000_000):
        return 200, f"bytes:{url}".encode(), {}

    monkeypatch.setattr("minecraft_mods.catalog._http_get", fake_get)
    mod = ModEntry(
        repo="reallyusefulribbits-mod",
        name="Really Useful Ribbits",
        description_en="",
        description_ru="",
        github_url="https://github.com/Nergan/reallyusefulribbits-mod",
        license_id="MPL-2.0",
        license_name="MPL",
        license_url="",
        version="v1.0.0!",
        minecraft="1.21.1",
        loaders=["NeoForge"],
        mod_jars=[JarLink("reallyusefulribbits-1.0.0.jar", "https://example.test/mod.jar")],
        dependency_jars=[JarLink("kotlinforforge-5.8.0-all.jar", "https://example.test/dep.jar")],
        jars_classified=True,
        has_release=True,
        modrinth_state="published",
        modrinth_url="https://modrinth.com/mod/really-useful-ribbits",
        modrinth_status="",
    )
    payload, filename = build_jar_archive(mod)
    assert filename == "reallyusefulribbits-mod.zip"
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        assert archive.namelist() == [
            "reallyusefulribbits-1.0.0.jar",
            "kotlinforforge-5.8.0-all.jar",
        ]


def test_readme_markdown_renders_tables_and_drops_raw_html():
    from minecraft_mods.render import render_markdown

    rendered = render_markdown(
        "\n".join([
            "| File | Required |",
            "| --- | --- |",
            "| `mod.jar` | Yes |",
            "",
            "See [the guide](README.md).",
            "",
            "<script>alert(1)</script>",
        ]),
        "https://github.com/Nergan/tamedphantoms-mod",
    )
    assert "<table>" in rendered
    assert "<td>mod.jar</td>" in rendered or "mod.jar" in rendered
    assert 'href="https://github.com/Nergan/tamedphantoms-mod/blob/main/README.md"' in rendered
    assert 'src="https://raw.githubusercontent.com/Nergan/tamedphantoms-mod/main/ico.png"' in render_markdown(
        "![logo](ico.png)",
        "https://github.com/Nergan/tamedphantoms-mod",
    )
    assert 'src="https://raw.githubusercontent.com/Nergan/placed-sticks-mod/main/logo.png"' in render_markdown(
        '<img src="https://github.com/Nergan/placed-sticks-mod/blob/main/logo.png" alt="logo">',
        "https://github.com/Nergan/placed-sticks-mod",
    )
    assert "<script>" not in rendered
    assert "alert(1)" not in rendered


def test_about_website_is_the_only_modrinth_page(monkeypatch):
    def fake_get(url, headers, max_bytes=1_000_000):
        if url.endswith("/README.md"):
            return 200, b"# Placed Sticks\n\nPlace sticks.\n", {}
        if "raw.githubusercontent.com" in url:
            return 404, b"", {}
        if url.endswith("/releases/latest"):
            return 404, b"", {}
        raise AssertionError(url)

    monkeypatch.setattr("minecraft_mods.catalog._http_get", fake_get)
    repo = {
        "name": "placed-sticks-mod",
        "html_url": "https://github.com/Nergan/placed-sticks-mod",
        "default_branch": "main",
        "license": {"spdx_id": "MPL-2.0", "name": "MPL"},
    }
    hidden = _build_mod(repo, {}, False, "")
    assert hidden.modrinth_state == "unavailable"
    assert hidden.modrinth_url == ""
    listed = _build_mod({**repo, "homepage": "https://modrinth.com/mod/placed-sticks/"}, {}, False, "")
    assert listed.modrinth_url == "https://modrinth.com/mod/placed-sticks"
    assert listed.modrinth_state == "linked"
    assert modrinth_website("https://github.com/Nergan/placed-sticks-mod") == ""
    assert modrinth_website("") == ""
    page = render_page(Catalog(mods=[listed, hidden]), "en", "name")
    assert page.count('href="https://modrinth.com/mod/placed-sticks"') == 1
    assert 'class="btn ext is-disabled"' in page
    assert '<p class="note">No public Modrinth page' not in page


def test_unavailable_modrinth_is_a_hover_note_instead_of_a_paragraph():
    mod = ModEntry(
        repo="placed-sticks-mod",
        name="Placed Sticks",
        description_en="Place sticks.",
        description_ru="",
        github_url="https://github.com/Nergan/placed-sticks-mod",
        license_id="MPL-2.0",
        license_name="MPL",
        license_url="",
        version="1.0.0",
        minecraft="1.20.1",
        loaders=["Forge"],
        mod_jars=[],
        dependency_jars=[],
        jars_classified=False,
        has_release=False,
        modrinth_state="unavailable",
        modrinth_url="https://modrinth.com/mod/placed-sticks",
        modrinth_status="",
    )
    page = render_page(Catalog(mods=[mod]), "en", "name")
    assert 'class="btn ext is-disabled"' in page
    assert "No public Modrinth page" in page
    assert '<p class="note">No public Modrinth page' not in page


def test_public_pages_cover_a_rate_limited_github_api(monkeypatch):
    profile = """
    <span itemprop="name codeRepository"> cutaway </span>
    <span itemprop="name codeRepository"> tamedphantoms-mod </span>
    """
    repo_page = """
    "defaultBranch":"main"
    "homepageUrl":"https:\\u002F\\u002Fmodrinth.com\\u002Fmod\\u002Ftamed-phantoms"
    "license":{"spdxId":"MPL-2.0","name":"Mozilla Public License 2.0"}
    """
    release_page = """
    <a href="/Nergan/tamedphantoms-mod/releases/tag/v1.0.0">v1.0.0</a>
    <div class="markdown-body my-3">
      <p>Minecraft <strong>1.21.1</strong> / NeoForge</p>
      <table>
        <tr><td><code>tamedphantoms-1.0.0.jar</code></td><td>Yes</td><td>this mod</td></tr>
        <tr><td><code>kotlinforforge-5.8.0-all.jar</code></td><td>Yes</td><td>Kotlin</td></tr>
      </table>
    </div>
    <a href="/Nergan/tamedphantoms-mod/releases/download/v1.0.0/tamedphantoms-1.0.0.jar">jar</a>
    <a href="/Nergan/tamedphantoms-mod/releases/download/v1.0.0/kotlinforforge-5.8.0-all.jar">dep</a>
    """

    def fake_get(url, headers, max_bytes=1_000_000):
        if url.startswith("https://api.github.com/users/Nergan/repos"):
            return 403, b'{"message":"rate limit"}', {"Retry-After": "0"}
        if "tab=repositories" in url:
            return 200, profile.encode(), {}
        if url == "https://github.com/Nergan/tamedphantoms-mod":
            return 200, repo_page.encode(), {}
        if url.startswith("https://raw.githubusercontent.com/") and url.endswith("/README.md"):
            return 200, b"# Tamed Phantoms\n\nTame them.\n", {}
        if url.startswith("https://raw.githubusercontent.com/"):
            return 404, b"", {}
        if url.endswith("/releases/latest") and "api.github.com" in url:
            return 403, b'{"message":"rate limit"}', {"Retry-After": "0"}
        if url.endswith("/releases/latest"):
            return 200, release_page.encode(), {}
        raise AssertionError(url)

    monkeypatch.setattr("minecraft_mods.catalog._http_get", fake_get)
    catalog = __import__("minecraft_mods.catalog", fromlist=["fetch_catalog"]).fetch_catalog()
    assert [mod.repo for mod in catalog.mods] == ["tamedphantoms-mod"]
    mod = catalog.mods[0]
    assert mod.modrinth_url == "https://modrinth.com/mod/tamed-phantoms"
    assert mod.license_id == "MPL-2.0"
    assert mod.minecraft == "1.21.1"
    assert [jar.name for jar in mod.mod_jars] == ["tamedphantoms-1.0.0.jar"]
    assert [jar.name for jar in mod.dependency_jars] == ["kotlinforforge-5.8.0-all.jar"]
    assert not mod.release_limited


def test_rejected_github_token_is_retried_without_it(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "revoked")

    def fake_get(url, headers, max_bytes=1_000_000):
        if "Authorization" in headers:
            return 401, b'{"message":"Bad credentials"}', {}
        return 200, b"[]", {}

    monkeypatch.setattr("minecraft_mods.catalog._http_get", fake_get)
    from minecraft_mods.catalog import _api_get

    status, payload, _headers = _api_get("https://api.github.com/users/Nergan/repos")
    assert status == 200
    assert payload == b"[]"


def test_github_rate_limit_keeps_the_mod_and_reads_the_readme_as_a_file(monkeypatch):
    def fake_get(url, headers, max_bytes=1_000_000):
        if url.startswith("https://raw.githubusercontent.com/") and url.endswith("/README.md"):
            return 200, b"# Tamed Phantoms\n\nTame them with cookies.\n", {}
        if url.startswith("https://raw.githubusercontent.com/"):
            return 404, b"not found", {}
        if url.endswith("/releases/latest"):
            return 403, b'{"message":"API rate limit exceeded"}', {"Retry-After": "0"}
        raise AssertionError(url)

    monkeypatch.setattr("minecraft_mods.catalog._http_get", fake_get)
    mod = _build_mod(
        {
            "name": "tamedphantoms-mod",
            "html_url": "https://github.com/Nergan/tamedphantoms-mod",
            "default_branch": "main",
            "license": {"spdx_id": "MPL-2.0", "name": "Mozilla Public License 2.0"},
        },
        {},
        False,
        "",
    )
    assert mod.name == "Tamed Phantoms"
    assert mod.description_en == "Tame them with cookies."
    assert mod.release_limited
    assert not mod.has_release
    page = render_page(Catalog(mods=[mod]), "en", "name")
    assert "rate-limiting" in page


def test_minecraft_mods_is_registered_on_the_public_prefix():
    config = load_runtime_config(ROOT, profile="local", isolation="embedded")
    project = config.projects["minecraft_mods"]
    assert project.prefix == "/mods"
    assert project.entrypoint == "minecraft_mods.minecraft_mods"
    assert project.run and project.deploy
    assert "MODRINTH_TOKEN" in project.env_allowlist
    assert "GITHUB_TOKEN" in project.env_allowlist
    assert "api.github.com" in project.network.allowed_hosts
    assert "raw.githubusercontent.com" in project.network.allowed_hosts
    assert "api.modrinth.com" in project.network.allowed_hosts
