"""Collect public *mod repositories from github.com/Nergan and pair them with Modrinth."""

from __future__ import annotations

import html
import json
import logging
import os
import re
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

GITHUB_USER = "Nergan"
MODRINTH_USER = "nargan"
SCHEMA = 6
FRESH_SECONDS = 60 * 60
STALE_SECONDS = 10 * 60
MAX_BYTES = 1_000_000
JAR_BYTES = 32 * 1024 * 1024
ARCHIVE_BYTES = 64 * 1024 * 1024

GITHUB_HEADERS = {
    "User-Agent": "nargan-cutaway-mods",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}
MODRINTH_HEADERS = {
    "User-Agent": "nargan-cutaway-mods/1.0 (https://github.com/Nergan/cutaway)",
    "Accept": "application/json",
}

_MOD_SOURCE = re.compile(
    r"\b(this (?:mod|compat|port|addon)|этот мод|этот компат|этот порт|этот аддон)\b",
    re.IGNORECASE,
)
_MODRINTH_ID = re.compile(r"(?m)^\s*modrinth-id:\s*([A-Za-z0-9_-]+)\s*$")
_MC_VERSION = re.compile(r"Minecraft\s+\*\*([^*]+)\*\*|Minecraft\s+([0-9][^\s/]*)", re.IGNORECASE)
_H1 = re.compile(r"^#\s+(.+)$", re.MULTILINE)
_LINK = re.compile(r"\[[^\]]*\]\([^)]*\)")

_memory: "Catalog | None" = None
_memory_until = 0.0
_memory_lock = threading.Lock()
_refresh_lock = threading.Lock()
_request_lock = threading.Lock()
_api_lock = threading.Lock()


class CatalogError(RuntimeError):
    def __init__(self, message: str, status: int = 502) -> None:
        super().__init__(message)
        self.status = status


TAB_LOADERS = ("Fabric", "NeoForge", "Forge")


@dataclass
class JarLink:
    name: str
    url: str
    loaders: list[str] = field(default_factory=list)


@dataclass
class ModEntry:
    repo: str
    name: str
    description_en: str
    description_ru: str
    github_url: str
    license_id: str
    license_name: str
    license_url: str
    version: str
    minecraft: str
    loaders: list[str]
    mod_jars: list[JarLink]
    dependency_jars: list[JarLink]
    jars_classified: bool
    has_release: bool
    modrinth_state: str
    modrinth_url: str
    modrinth_status: str
    license_text: str = ""
    release_limited: bool = False
    readme_en: str = ""
    readme_ru: str = ""
    branch: str = "main"


@dataclass
class Catalog:
    mods: list[ModEntry] = field(default_factory=list)
    fetched_at: float = 0.0
    expires_at: float = 0.0
    error: str = ""
    partial: bool = False
    modrinth_authenticated: bool = False
    schema: int = SCHEMA


def is_mod_repo_name(name: str) -> bool:
    return name.lower().endswith("mod")


def parse_readme(markdown: str) -> tuple[str, str]:
    """Return the H1 and the first prose paragraph, skipping badges and language switches."""
    title = ""
    heading = _H1.search(markdown)
    if heading:
        title = heading.group(1).strip()
    paragraph: list[str] = []
    started = False
    for raw in markdown.replace("\r\n", "\n").split("\n"):
        line = raw.strip()
        if not started:
            if not line or line.startswith("#") or _is_image(line) or _is_language_switch(line):
                continue
            started = True
        if not line or line.startswith("#"):
            break
        paragraph.append(line)
    return title, " ".join(paragraph)


def classify_jars(assets: list[dict[str, Any]], body: str) -> tuple[list[JarLink], list[JarLink], bool]:
    """Split release jars into the mod itself and companion jars shipped beside it.

    Each jar is tagged with the loaders it belongs to. A card with two or three
    different sets grows one tab per loader.
    """
    jars = {
        str(asset.get("name") or ""): str(asset.get("browser_download_url") or "")
        for asset in assets
        if str(asset.get("name") or "").lower().endswith(".jar") and not _auxiliary_jar(str(asset.get("name") or ""))
    }
    rows = _jar_table(body)
    mod_patterns = [pattern for pattern, _rest, is_mod in rows if is_mod]
    dep_patterns = [pattern for pattern, _rest, is_mod in rows if not is_mod]

    used: set[str] = set()
    mod_jars = _take(jars, mod_patterns, used)
    dep_jars = _take(jars, dep_patterns, used)
    leftover = [name for name in jars if name not in used]
    classified = bool(mod_jars)
    if mod_jars:
        dep_jars.extend(_link(jars, name) for name in leftover)
    elif len(leftover) == 1:
        mod_jars = [_link(jars, leftover[0])]
        classified = True
    else:
        dep_jars.extend(_link(jars, name) for name in leftover)
    _stamp_loaders(mod_jars, dep_jars, body)
    return mod_jars, dep_jars, classified


def minecraft_and_loaders(body: str) -> tuple[str, list[str]]:
    head = ""
    for line in (body or "").splitlines():
        if line.strip():
            head = line.strip()
            break
    match = _MC_VERSION.search(head)
    minecraft = ""
    if match:
        minecraft = (match.group(1) or match.group(2) or "").strip()
    lowered = head.lower()
    loaders: list[str] = []
    if "neoforge" in lowered:
        loaders.append("NeoForge")
    if re.search(r"(?<!neo)forge", lowered):
        loaders.append("Forge")
    if "fabric" in lowered:
        loaders.append("Fabric")
    if "quilt" in lowered:
        loaders.append("Quilt")
    return minecraft, loaders


def loader_panels(mod: ModEntry) -> list[tuple[str, list[JarLink], list[JarLink]]]:
    """Tabs for a card. Empty when every loader would show the same jars."""
    panels: list[tuple[str, list[JarLink], list[JarLink]]] = []
    for loader in TAB_LOADERS:
        own = [jar for jar in mod.mod_jars if loader in jar.loaders]
        deps = [jar for jar in mod.dependency_jars if loader in jar.loaders]
        if own or deps:
            panels.append((loader, own, deps))
    if len(panels) < 2:
        return []
    signatures = {
        (tuple(jar.name for jar in own), tuple(jar.name for jar in deps))
        for _loader, own, deps in panels
    }
    if len(signatures) < 2:
        return []
    return panels


def loader_slug(loader: str) -> str:
    return {"Fabric": "fabric", "NeoForge": "neoforge", "Forge": "forge"}.get(loader, "")


def _canonical_loader(value: str) -> str | None:
    return {"fabric": "Fabric", "neoforge": "NeoForge", "forge": "Forge"}.get(value.strip().lower())


def classify_modrinth(
    project: dict[str, Any] | None,
    *,
    declared_slug: str,
    authenticated: bool,
) -> tuple[str, str, str]:
    """Return state, public URL and raw Modrinth status.

    ``unavailable`` means the repository names a Modrinth project, but the public
    API does not return it. That is the unauthenticated view of a project that
    may still be in review. With a token, review projects come back as
    ``moderation`` instead of a guess.
    """
    if project:
        slug = str(project.get("slug") or declared_slug)
        kind = str(project.get("project_type") or "mod")
        section = "mod" if kind == "mod" else "project"
        url = f"https://modrinth.com/{section}/{slug}" if slug else ""
        status = str(project.get("status") or "").lower()
        if status == "approved":
            return "linked", url, status
        if status == "archived":
            return "archived", url, status
        if status == "unlisted":
            return "unlisted", url, status
        if status == "rejected":
            return "rejected", url, status
        if status == "withheld":
            return "withheld", url, status
        if status == "draft" and not project.get("requested_status"):
            return "draft", url, status
        return "moderation", url, status or "processing"
    if declared_slug and not authenticated:
        return "unavailable", f"https://modrinth.com/mod/{declared_slug}", ""
    return "missing", "", ""


def modrinth_website(homepage: str) -> str:
    """Public Modrinth page from the GitHub About website field, if that field is one."""
    raw = (homepage or "").strip()
    if not raw:
        return ""
    if "://" not in raw:
        raw = "https://" + raw
    parsed = urllib.parse.urlsplit(raw)
    host = (parsed.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if parsed.scheme not in {"http", "https"} or host != "modrinth.com" or parsed.username or parsed.password:
        return ""
    parts = [part for part in parsed.path.split("/") if part]
    sections = {"mod", "plugin", "datapack", "shader", "resourcepack", "modpack", "project"}
    if len(parts) < 2 or parts[0] not in sections:
        return ""
    return "https://modrinth.com/" + "/".join(parts)


def github_repo_of(url: str) -> str:
    match = re.search(r"github\.com/Nergan/([^/#?\s]+)", url or "", re.IGNORECASE)
    if not match:
        return ""
    name = match.group(1)
    if name.lower().endswith(".git"):
        name = name[:-4]
    return name.lower()


def version_tuple(value: str) -> tuple[int, ...]:
    parts = [int(item) for item in re.findall(r"\d+", value)]
    return tuple(parts) if parts else (0,)


def get_catalog() -> Catalog:
    """Return a cached catalog, refreshing from GitHub and Modrinth when it expires."""
    global _memory, _memory_until
    now = time.time()
    with _memory_lock:
        if _memory is not None and now < _memory_until:
            return _memory
    cached = _read_cache()
    if cached is not None and now < cached.expires_at:
        _remember(cached)
        return cached

    with _refresh_lock:
        with _memory_lock:
            if _memory is not None and time.time() < _memory_until:
                return _memory
        try:
            fresh = fetch_catalog()
        except Exception:
            logger.exception("minecraft mods catalog refresh failed")
            stale = cached or _read_cache(strict_schema=False)
            if stale is not None and stale.mods:
                stale.error = "stale"
                stale.expires_at = time.time() + 60
                _remember(stale)
                return stale
            failed = Catalog(fetched_at=time.time(), expires_at=time.time() + 60, error="fetch", partial=False)
            _remember(failed)
            return failed
        _write_cache(fresh)
        _remember(fresh)
        return fresh


def fetch_catalog() -> Catalog:
    repos = _list_mod_repos()
    partial = False
    mods: list[ModEntry] = []
    workers = min(4, max(1, len(repos)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_build_mod, repo, {}, False, ""): repo for repo in repos
        }
        for future in as_completed(futures):
            repo = futures[future]
            try:
                mods.append(future.result())
            except Exception:
                logger.exception("failed to read mod repository %s", repo.get("name"))
                partial = True
    mods.sort(key=lambda item: item.name.casefold())
    now = time.time()
    ttl = STALE_SECONDS if partial else FRESH_SECONDS
    return Catalog(
        mods=mods,
        fetched_at=now,
        expires_at=now + ttl,
        partial=partial,
        modrinth_authenticated=False,
    )


def _build_mod(
    repo: dict[str, Any],
    by_repo: dict[str, dict[str, Any]],
    authenticated: bool,
    token: str,
) -> ModEntry:
    if repo.get("from_profile"):
        _fill_public_repo(repo)
    name = str(repo["name"])
    html_url = str(repo.get("html_url") or f"https://github.com/{GITHUB_USER}/{name}")
    branch = str(repo.get("default_branch") or "main")
    license_info = repo.get("license") or {}
    license_id = str(license_info.get("spdx_id") or "")
    license_name = str(license_info.get("name") or "")
    readme = _raw_first(name, branch, ("README.md", "README.rst", "README"))
    readme_ru = _raw_text(name, branch, "README.ru.md")
    title_en, description_en = parse_readme(readme or "")
    title_ru, description_ru = parse_readme(readme_ru or "")
    release, release_limited = _latest_release(name)
    body = ""
    assets: list[dict[str, Any]] = []
    version = ""
    has_release = False
    if isinstance(release, dict):
        has_release = True
        body = str(release.get("body") or "")
        assets = list(release.get("assets") or [])
        version = str(release.get("tag_name") or "").lstrip("v")
    mod_jars, dep_jars, classified = classify_jars(assets, body)
    minecraft, loaders = minecraft_and_loaders(body)
    del by_repo, authenticated, token
    website = modrinth_website(str(repo.get("homepage") or ""))
    if website:
        state, modrinth_url, status = "linked", website, ""
    else:
        state, modrinth_url, status = "unavailable", "", ""
    display = title_en or title_ru or _fallback_name(name)
    license_text = _raw_first(name, branch, ("LICENSE", "LICENSE.md", "LICENSE.txt")) or ""
    return ModEntry(
        repo=name,
        name=display,
        description_en=description_en,
        description_ru=description_ru or description_en,
        github_url=html_url,
        license_id=license_id,
        license_name=license_name,
        license_url=f"{html_url}/blob/{branch}/LICENSE",
        version=version,
        minecraft=minecraft,
        loaders=loaders,
        mod_jars=mod_jars,
        dependency_jars=dep_jars,
        jars_classified=classified,
        has_release=has_release,
        modrinth_state=state,
        modrinth_url=modrinth_url,
        modrinth_status=status,
        license_text=license_text.strip(),
        release_limited=release_limited,
        readme_en=(readme or "").strip(),
        readme_ru=(readme_ru or "").strip(),
        branch=branch,
    )


def _list_mod_repos() -> list[dict[str, Any]]:
    try:
        return _list_mod_repos_api()
    except CatalogError as exc:
        logger.warning("GitHub API repository list failed (%s); reading the public profile.", exc)
        try:
            return _list_mod_repos_html()
        except CatalogError:
            raise exc


def _list_mod_repos_api() -> list[dict[str, Any]]:
    url: str | None = (
        f"https://api.github.com/users/{GITHUB_USER}/repos?per_page=100&type=owner&sort=full_name"
    )
    found: list[dict[str, Any]] = []
    pages = 0
    while url and pages < 10:
        status, payload, headers = _api_get(url)
        if status != 200:
            raise CatalogError(
                f"GitHub repository list returned {status}: {_snippet(payload)}"
            )
        batch = json.loads(payload)
        if not isinstance(batch, list):
            raise CatalogError("GitHub repository list had an unexpected shape.")
        for repo in batch:
            repo_name = str(repo.get("name") or "")
            if repo.get("fork") or repo.get("private"):
                continue
            if is_mod_repo_name(repo_name):
                found.append(repo)
        url = _next_link(str(headers.get("Link") or headers.get("link") or ""))
        pages += 1
    return found


_PROFILE_REPO = re.compile(r'itemprop="name codeRepository"[^>]*>\s*([^<]+?)\s*<')
_HOMEPAGE_URL = re.compile(r'"homepageUrl":"((?:\\.|[^"\\])*)"')
_DEFAULT_BRANCH = re.compile(r'"defaultBranch":"([^"]+)"')
_LICENSE_META = re.compile(r'"license":\{"spdxId":"([^"]+)","name":"([^"]*)"\}')
_RELEASE_TAG = re.compile(r"/releases/(?:tag|download|expanded_assets)/([^\"'#?/]+)")
_RELEASE_ASSET = re.compile(r"/releases/download/([^/\"']+)/([^\"'?]+\.jar)")
_HTML_BROWSER = {"User-Agent": "Mozilla/5.0 (compatible; nargan-cutaway-mods)", "Accept": "text/html"}


def _list_mod_repos_html() -> list[dict[str, Any]]:
    status, payload, _headers = _github_html(f"https://github.com/{GITHUB_USER}?tab=repositories&type=source")
    if status != 200:
        raise CatalogError(f"GitHub profile returned {status}.")
    page = payload.decode("utf-8", "replace")
    if not _PROFILE_REPO.search(page):
        raise CatalogError("GitHub profile did not list any repositories.")
    return _repos_from_profile_html(page)


def _repos_from_profile_html(page: str) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw_name in _PROFILE_REPO.findall(page):
        name = html.unescape(raw_name).strip()
        if not name or name in seen or not is_mod_repo_name(name):
            continue
        seen.add(name)
        found.append(
            {
                "name": name,
                "html_url": f"https://github.com/{GITHUB_USER}/{name}",
                "default_branch": "main",
                "private": False,
                "fork": False,
                "from_profile": True,
            }
        )
    return found


def _fill_public_repo(repo: dict[str, Any]) -> None:
    """License and About website are on the public repo page when the API is limited."""
    status, payload, _headers = _github_html(f"https://github.com/{GITHUB_USER}/{repo['name']}")
    if status != 200:
        repo["homepage"] = ""
        return
    fields = _public_repo_fields(payload.decode("utf-8", "replace"))
    repo["default_branch"] = fields["default_branch"] or repo.get("default_branch") or "main"
    repo["homepage"] = fields["homepage"]
    if fields["license_id"]:
        repo["license"] = {"spdx_id": fields["license_id"], "name": fields["license_name"]}


def _public_repo_fields(page: str) -> dict[str, str]:
    homepage = ""
    match = _HOMEPAGE_URL.search(page)
    if match and match.group(1):
        homepage = _github_js_string(match.group(1))
    branch = ""
    branch_match = _DEFAULT_BRANCH.search(page)
    if branch_match:
        branch = branch_match.group(1)
    license_id = ""
    license_name = ""
    license_match = _LICENSE_META.search(page)
    if license_match:
        license_id = license_match.group(1)
        license_name = _github_js_string(license_match.group(2))
    return {
        "homepage": homepage,
        "default_branch": branch,
        "license_id": license_id,
        "license_name": license_name,
    }


def _github_js_string(value: str) -> str:
    return value.replace("\\u002F", "/").replace("\\/", "/").replace("\\u0026", "&")


def _github_html(url: str) -> tuple[int, bytes, dict[str, str]]:
    try:
        return _http_get(url, _HTML_BROWSER, max_bytes=2_000_000)
    except CatalogError:
        logger.warning("could not read %s", url)
        return 0, b"", {}


def _release_from_html(repo: str) -> dict[str, Any] | None:
    status, payload, _headers = _github_html(f"https://github.com/{GITHUB_USER}/{repo}/releases/latest")
    if status != 200 or not payload:
        return None
    page = payload.decode("utf-8", "replace")
    tag = _release_tag(page)
    assets_page = ""
    if tag and not _RELEASE_ASSET.search(page):
        asset_status, asset_payload, _headers = _github_html(
            f"https://github.com/{GITHUB_USER}/{repo}/releases/expanded_assets/{urllib.parse.quote(tag, safe='')}"
        )
        if asset_status == 200:
            assets_page = asset_payload.decode("utf-8", "replace")
    return _release_document_from_html(repo, page, assets_page)


def _release_document_from_html(repo: str, page: str, assets_page: str = "") -> dict[str, Any] | None:
    tag = _release_tag(page) or _release_tag(assets_page)
    assets = _html_assets(page, repo)
    if not assets and assets_page:
        assets = _html_assets(assets_page, repo, tag)
    body = _html_release_notes(page)
    if not assets and not body:
        return None
    return {"tag_name": tag, "body": body, "assets": assets}


def _release_tag(page: str) -> str:
    match = _RELEASE_TAG.search(page)
    if not match:
        return ""
    return urllib.parse.unquote(match.group(1))


def _html_assets(page: str, repo: str, tag: str = "") -> list[dict[str, str]]:
    found: list[dict[str, str]] = []
    seen: set[str] = set()
    for asset_tag, filename in _RELEASE_ASSET.findall(page):
        filename = urllib.parse.unquote(filename)
        if filename in seen:
            continue
        seen.add(filename)
        asset_tag = urllib.parse.unquote(asset_tag)
        found.append(
            {
                "name": filename,
                "browser_download_url": (
                    f"https://github.com/{GITHUB_USER}/{repo}/releases/download/{asset_tag}/{filename}"
                ),
            }
        )
    if found or not tag:
        return found
    for filename in re.findall(r">([^<]+\.jar)<", page):
        filename = html.unescape(filename).strip()
        if not filename or filename in seen or any(char.isspace() for char in filename):
            continue
        seen.add(filename)
        found.append(
            {
                "name": filename,
                "browser_download_url": (
                    f"https://github.com/{GITHUB_USER}/{repo}/releases/download/{tag}/{filename}"
                ),
            }
        )
    return found


def _html_release_notes(page: str) -> str:
    body = _markdown_region(page)
    if not body:
        return ""
    intro = _strip_tags(body.split("<table", 1)[0])
    lines = [intro] if intro else []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", body, flags=re.DOTALL):
        cells = _html_cells(row)
        if not cells or not cells[0].lower().endswith(".jar"):
            continue
        lines.append("| `" + cells[0] + "` | " + " | ".join(cells[1:]) + " |")
    return "\n".join(lines)


def _markdown_region(page: str) -> str:
    marker = page.find("markdown-body")
    if marker < 0:
        return ""
    start = page.find(">", marker)
    if start < 0:
        return ""
    depth = 1
    index = start + 1
    while index < len(page) and depth:
        if page.startswith("<div", index):
            depth += 1
        elif page.startswith("</div", index):
            depth -= 1
            if depth == 0:
                return page[start + 1 : index]
        index += 1
    return page[start + 1 : start + 20000]


def _html_cells(row: str) -> list[str]:
    cells: list[str] = []
    for part in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, flags=re.DOTALL):
        code = re.search(r"<code>(.*?)</code>", part, flags=re.DOTALL)
        cells.append(_strip_tags(code.group(1) if code else part))
    return cells


def _strip_tags(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value)
    return " ".join(html.unescape(text).split())


def _load_modrinth_projects(token: str) -> tuple[list[dict[str, Any]], bool]:
    headers = dict(MODRINTH_HEADERS)
    authenticated = False
    if token:
        headers["Authorization"] = token
    status, payload, _headers = _http_get(
        f"https://api.modrinth.com/v2/user/{MODRINTH_USER}/projects",
        headers,
    )
    if status in {401, 403} and token:
        logger.warning("Modrinth token was rejected; continuing with the public project list.")
        headers.pop("Authorization", None)
        status, payload, _headers = _http_get(
            f"https://api.modrinth.com/v2/user/{MODRINTH_USER}/projects",
            headers,
        )
    elif status == 200 and token:
        authenticated = True
    if status != 200:
        logger.warning("Modrinth user projects returned %s", status)
        return [], authenticated
    identifiers = json.loads(payload)
    if not isinstance(identifiers, list) or not identifiers:
        return [], authenticated
    encoded = urllib.parse.quote(json.dumps([str(item) for item in identifiers]))
    status, payload, _headers = _http_get(
        f"https://api.modrinth.com/v2/projects?ids={encoded}",
        headers,
    )
    if status != 200:
        logger.warning("Modrinth project batch returned %s", status)
        return [], authenticated
    projects = json.loads(payload)
    if not isinstance(projects, list):
        return [], authenticated
    return [item for item in projects if isinstance(item, dict)], authenticated


def _modrinth_project(slug: str, token: str) -> dict[str, Any] | None:
    headers = dict(MODRINTH_HEADERS)
    if token:
        headers["Authorization"] = token
    status, payload, _headers = _http_get(
        f"https://api.modrinth.com/v2/project/{urllib.parse.quote(slug)}",
        headers,
    )
    if status != 200:
        return None
    project = json.loads(payload)
    return project if isinstance(project, dict) else None


def _index_modrinth(projects: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for project in projects:
        for key in ("source_url", "issues_url", "wiki_url"):
            repo = github_repo_of(str(project.get(key) or ""))
            if repo and repo not in indexed:
                indexed[repo] = project
    return indexed


def _github_headers() -> dict[str, str]:
    headers = dict(GITHUB_HEADERS)
    token = os.getenv("GITHUB_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _api_get(url: str) -> tuple[int, bytes, dict[str, str]]:
    """Call the GitHub API one request at a time and retry a rate limit once."""
    with _api_lock:
        headers = _github_headers()
        status, payload, response_headers = _http_get(url, headers)
        if status == 401 and "Authorization" in headers:
            logger.warning("GitHub rejected the token; continuing without it.")
            headers = dict(GITHUB_HEADERS)
            status, payload, response_headers = _http_get(url, headers)
        if status not in {403, 429}:
            return status, payload, response_headers
        delay = _retry_after(response_headers)
        logger.warning("GitHub returned %s for %s: %s", status, url, _snippet(payload))
        time.sleep(delay)
        return _http_get(url, headers)


def _retry_after(headers: dict[str, str]) -> float:
    raw = headers.get("Retry-After") or headers.get("retry-after") or ""
    try:
        return min(2.0, max(0.0, float(raw)))
    except ValueError:
        return 1.0


def _snippet(payload: bytes) -> str:
    return payload.decode("utf-8", "replace")[:300].replace("\n", " ")


def _raw_first(repo: str, branch: str, paths: tuple[str, ...]) -> str | None:
    for path in paths:
        text = _raw_text(repo, branch, path)
        if text is not None:
            return text
    return None


def _raw_text(repo: str, branch: str, path: str) -> str | None:
    quoted_path = urllib.parse.quote(path, safe="/")
    url = (
        f"https://raw.githubusercontent.com/{GITHUB_USER}/"
        f"{urllib.parse.quote(repo)}/{urllib.parse.quote(branch)}/{quoted_path}"
    )
    status, payload, _headers = _http_get(
        url,
        {"User-Agent": GITHUB_HEADERS["User-Agent"], "Accept": "text/plain"},
    )
    if status == 404:
        return None
    if status != 200:
        logger.warning("raw %s for %s returned %s: %s", path, repo, status, _snippet(payload))
        return None
    return payload.decode("utf-8", "replace")


def _latest_release(repo: str) -> tuple[Any, bool]:
    status, payload, _headers = _api_get(_github_url(repo, "releases/latest"))
    if status == 404:
        return None, False
    if status in {401, 403, 429}:
        logger.warning("GitHub releases/latest for %s returned %s: %s", repo, status, _snippet(payload))
        try:
            document = _release_from_html(repo)
        except Exception:
            logger.warning("public release page for %s could not be read", repo, exc_info=True)
            document = None
        if document is not None:
            return document, False
        return None, True
    if status != 200:
        raise CatalogError(f"GitHub releases/latest for {repo} returned {status}: {_snippet(payload)}")
    document = json.loads(payload)
    return (document if isinstance(document, dict) else None), False


def _github_url(repo: str, suffix: str) -> str:
    base = f"https://api.github.com/repos/{GITHUB_USER}/{urllib.parse.quote(repo)}"
    return f"{base}/{suffix}"


def build_jar_archive(mod: ModEntry, loader: str | None = None) -> tuple[bytes, str]:
    """Download the card's jars, or one loader's jars, and pack them into one zip."""
    import io
    import zipfile

    jars = [*mod.mod_jars, *mod.dependency_jars]
    suffix = ""
    if loader:
        canonical = _canonical_loader(loader)
        if canonical is None:
            raise CatalogError(f"Unknown loader {loader}.", status=404)
        jars = [jar for jar in jars if canonical in jar.loaders]
        suffix = f"-{canonical.lower()}"
    if not jars:
        raise CatalogError(f"{mod.repo} has no jars to archive.", status=404)
    buffer = io.BytesIO()
    total = 0
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        seen: set[str] = set()
        for jar in jars:
            if jar.name in seen or not jar.url.startswith(("https://", "http://")):
                continue
            seen.add(jar.name)
            status, payload, _headers = _http_get(
                jar.url,
                {"User-Agent": GITHUB_HEADERS["User-Agent"]},
                max_bytes=JAR_BYTES,
            )
            if status != 200 or not payload:
                raise CatalogError(f"Download of {jar.name} returned {status}.")
            total += len(payload)
            if total > ARCHIVE_BYTES:
                raise CatalogError("The jar archive is too large.")
            archive.writestr(jar.name, payload)
    safe_repo = re.sub(r"[^A-Za-z0-9._-]+", "-", mod.repo).strip("-") or "mods"
    return buffer.getvalue(), f"{safe_repo}{suffix}.zip"


def _http_get(
    url: str,
    headers: dict[str, str],
    max_bytes: int = MAX_BYTES,
) -> tuple[int, bytes, dict[str, str]]:
    request = urllib.request.Request(url, headers=headers)
    governed = bool(os.getenv("CUTAWAY_PROJECT_NETWORK_HOSTS", "").strip())
    if governed:
        from shared_network import SafeRedirectHandler, validate_outbound_url

        with _request_lock:
            validate_outbound_url(url)
        opener = urllib.request.build_opener(SafeRedirectHandler())
    else:
        opener = urllib.request.build_opener()
    try:
        with opener.open(request, timeout=45) as response:
            payload = response.read(max_bytes + 1)
            status = int(getattr(response, "status", 200))
            response_headers = {key: value for key, value in response.headers.items()}
    except urllib.error.HTTPError as exc:
        payload = exc.read(8192) if exc.fp is not None else b""
        status = int(exc.code)
        response_headers = {key: value for key, value in exc.headers.items()} if exc.headers else {}
    if len(payload) > max_bytes:
        raise CatalogError("Outbound response exceeds the size limit.")
    return status, payload, response_headers


def _next_link(header: str) -> str | None:
    for part in header.split(","):
        if 'rel="next"' not in part:
            continue
        match = re.search(r"<([^>]+)>", part)
        if match:
            return match.group(1)
    return None


def _auxiliary_jar(name: str) -> bool:
    lowered = name.lower()
    return lowered.endswith(("-sources.jar", "-javadoc.jar", "-javadocs.jar"))


def _take(jars: dict[str, str], patterns: list[str], used: set[str]) -> list[JarLink]:
    chosen: list[JarLink] = []
    for pattern in patterns:
        for name in jars:
            if name in used or not _name_matches(name, pattern):
                continue
            used.add(name)
            chosen.append(_link(jars, name))
    return chosen


def _name_matches(name: str, pattern: str) -> bool:
    if any(char in pattern for char in "*?["):
        return fnmatchcase(name, pattern)
    return name == pattern


def _link(jars: dict[str, str], name: str) -> JarLink:
    return JarLink(name=name, url=jars[name])


def _jar_table(body: str) -> list[tuple[str, str, bool]]:
    """Jar rows as (pattern, surrounding text, whether the row is the mod itself)."""
    heading = ""
    rows: list[tuple[str, str, bool]] = []
    for raw in (body or "").splitlines():
        stripped = raw.strip()
        if stripped.startswith("#"):
            heading = stripped.lstrip("#").strip()
            continue
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        pattern = cells[0].strip("`").strip()
        if not pattern.lower().endswith(".jar"):
            continue
        rest = " ".join(cell.strip("`").strip() for cell in cells[1:])
        if heading:
            rest = f"{rest} {heading}".strip()
        is_mod = any(_MOD_SOURCE.search(cell) for cell in cells[1:])
        rows.append((pattern, rest, is_mod))
    return rows


def _loader_signals(text: str) -> list[str]:
    lowered = text.lower()
    found: set[str] = set()
    if re.search(r"neo[\s_-]?forge", lowered):
        found.add("NeoForge")
    if "fabric" in lowered:
        found.add("Fabric")
    scrubbed = re.sub(r"neo[\s_-]?forge", " ", lowered)
    if re.search(r"kotlin[\s_-]*for[\s_-]*forge", scrubbed):
        found.add("NeoForge")
        found.add("Forge")
        scrubbed = re.sub(r"kotlin[\s_-]*for[\s_-]*forge", " ", scrubbed)
    if re.search(r"forge", scrubbed):
        found.add("Forge")
    return [loader for loader in TAB_LOADERS if loader in found]


def _signals_for_jar(name: str, rows: list[tuple[str, str, bool]]) -> list[str]:
    signals = _loader_signals(name)
    if signals:
        return signals
    for pattern, rest, _is_mod in rows:
        if _name_matches(name, pattern):
            return _loader_signals(rest)
    return []


def _stamp_loaders(mod_jars: list[JarLink], dep_jars: list[JarLink], body: str) -> None:
    declared = [loader for loader in minecraft_and_loaders(body)[1] if loader in TAB_LOADERS]
    rows = _jar_table(body)
    jars = [*mod_jars, *dep_jars]
    for jar in jars:
        signals = _signals_for_jar(jar.name, rows)
        if signals and declared:
            narrowed = [loader for loader in signals if loader in declared]
            jar.loaders = narrowed or signals
        else:
            jar.loaders = list(signals)
    if not any(jar.loaders for jar in jars):
        if len(declared) == 1:
            for jar in jars:
                jar.loaders = list(declared)
        return
    tagged_mod = {loader for jar in mod_jars for loader in jar.loaders}
    for jar in mod_jars:
        if jar.loaders or not declared:
            continue
        remaining = [loader for loader in declared if loader not in tagged_mod]
        jar.loaders = remaining or list(declared)
    present = [loader for loader in TAB_LOADERS if any(loader in jar.loaders for jar in jars)]
    if len(present) < 2:
        if len(present) == 1:
            for jar in jars:
                if not jar.loaders:
                    jar.loaders = list(present)
        return
    for jar in jars:
        if not jar.loaders:
            jar.loaders = list(present)


def _is_image(line: str) -> bool:
    return line.startswith("![") or line.lower().startswith("<img")


def _is_language_switch(line: str) -> bool:
    if "README" not in line:
        return False
    remainder = _LINK.sub("", line)
    remainder = re.sub(r"[*_·•|\s:：-]", "", remainder)
    return remainder == ""


def _fallback_name(repo: str) -> str:
    title = repo[: -len("mod")] if repo.lower().endswith("mod") else repo
    title = title.rstrip("-_ ").replace("-", " ").replace("_", " ")
    return title or repo


def _cache_path() -> Path:
    base = os.getenv("TMPDIR") or os.getenv("TEMP") or tempfile.gettempdir()
    return Path(base) / "cutaway-minecraft-mods-catalog.json"


def _remember(catalog: Catalog) -> None:
    global _memory, _memory_until
    with _memory_lock:
        _memory = catalog
        _memory_until = catalog.expires_at


def _write_cache(catalog: Catalog) -> None:
    path = _cache_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(catalog), ensure_ascii=False), encoding="utf-8")
    except OSError:
        logger.warning("could not persist the mods catalog cache")


def _read_cache(strict_schema: bool = True) -> Catalog | None:
    path = _cache_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict):
        return None
    schema = raw.get("schema")
    if strict_schema:
        if schema != SCHEMA:
            return None
    elif not isinstance(schema, int) or schema < 3:
        return None
    try:
        mods = [_mod_from_dict(item) for item in raw.get("mods", [])]
    except (KeyError, TypeError, ValueError):
        return None
    return Catalog(
        mods=mods,
        fetched_at=float(raw.get("fetched_at") or 0),
        expires_at=float(raw.get("expires_at") or 0),
        error=str(raw.get("error") or ""),
        partial=bool(raw.get("partial")),
        modrinth_authenticated=bool(raw.get("modrinth_authenticated")),
    )


def _jar_from_dict(item: dict[str, Any]) -> JarLink:
    loaders = item.get("loaders") or []
    if not isinstance(loaders, list):
        loaders = []
    return JarLink(
        name=str(item["name"]),
        url=str(item["url"]),
        loaders=[str(loader) for loader in loaders],
    )


def _mod_from_dict(raw: dict[str, Any]) -> ModEntry:
    return ModEntry(
        repo=str(raw["repo"]),
        name=str(raw["name"]),
        description_en=str(raw.get("description_en") or ""),
        description_ru=str(raw.get("description_ru") or ""),
        github_url=str(raw.get("github_url") or ""),
        license_id=str(raw.get("license_id") or ""),
        license_name=str(raw.get("license_name") or ""),
        license_url=str(raw.get("license_url") or ""),
        version=str(raw.get("version") or ""),
        minecraft=str(raw.get("minecraft") or ""),
        loaders=list(raw.get("loaders") or []),
        mod_jars=[_jar_from_dict(item) for item in raw.get("mod_jars") or []],
        dependency_jars=[_jar_from_dict(item) for item in raw.get("dependency_jars") or []],
        jars_classified=bool(raw.get("jars_classified")),
        has_release=bool(raw.get("has_release")),
        modrinth_state=str(raw.get("modrinth_state") or "missing"),
        modrinth_url=str(raw.get("modrinth_url") or ""),
        modrinth_status=str(raw.get("modrinth_status") or ""),
        license_text=str(raw.get("license_text") or ""),
        release_limited=bool(raw.get("release_limited")),
        readme_en=str(raw.get("readme_en") or ""),
        readme_ru=str(raw.get("readme_ru") or ""),
        branch=str(raw.get("branch") or "main"),
    )
