"""Render the mods catalog as a compact old-style list."""

from __future__ import annotations

import html
import re
import urllib.parse
from html.parser import HTMLParser
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from minecraft_mods.catalog import Catalog, ModEntry, loader_panels, loader_slug

_PAGE = Path(__file__).with_name("page.html")
_INLINE = re.compile(
    r"\[([^\]]+)\]\(([^)\s]+)\)"
    r"|`([^`]+)`"
    r"|\*\*([^*]+)\*\*"
    r"|(https?://[^\s)<]+)"
)

_TEXT = {
    "en": {
        "title": "Minecraft mods",
        "empty": "No repositories ending in mod were found.",
        "jar": "mod",
        "download_all": "download all",
        "zip_busy": "preparing zip…",
        "zip_fail": "could not build the zip",
        "deps": "deps",
        "files": "jars",
        "no_release": "No GitHub release yet.",
        "rate_limit": "GitHub is rate-limiting this server, so the jar links are missing for now.",
        "no_jars": "The latest release has no jar files.",
        "unclassified": "These jars are in the release; the mod jar could not be picked out of them.",
        "license_missing": "License is not set",
        "readme": "README",
        "close": "Close",
        "updated": "updated",
        "stale": "Could not refresh the list. Showing the last saved copy.",
        "fetch": "Could not load the list from GitHub.",
        "partial": "Some repositories could not be read.",
        "modrinth": {
            "archived": "Archived on Modrinth.",
            "unlisted": "On Modrinth, hidden from search.",
            "moderation": "On Modrinth and still in review. The page may not open yet.",
            "draft": "Modrinth draft, not published.",
            "rejected": "Modrinth rejected this project.",
            "withheld": "Hidden by Modrinth moderation.",
            "unavailable": "No public Modrinth page. If it was submitted, it may still be in review.",
            "missing": "No Modrinth page.",
        },
    },
    "ru": {
        "title": "Minecraft mods",
        "empty": "Репозиториев с именем на mod не найдено.",
        "jar": "мод",
        "download_all": "скачать всё",
        "zip_busy": "готовится zip…",
        "zip_fail": "не удалось собрать zip",
        "deps": "зависимости",
        "files": "jar",
        "no_release": "Релиза на GitHub пока нет.",
        "rate_limit": "GitHub временно ограничил запросы с этого сервера, поэтому ссылок на jar сейчас нет.",
        "no_jars": "В последнем релизе нет jar-файлов.",
        "unclassified": "Эти jar лежат в релизе; отделить файл мода от зависимостей не получилось.",
        "license_missing": "Лицензия не указана",
        "readme": "README",
        "close": "Закрыть",
        "updated": "обновлено",
        "stale": "Не удалось обновить список. Показана прошлая сохранённая копия.",
        "fetch": "Не удалось загрузить список с GitHub.",
        "partial": "Часть репозиториев прочитать не удалось.",
        "modrinth": {
            "archived": "Архив на Modrinth.",
            "unlisted": "Есть на Modrinth, скрыт из поиска.",
            "moderation": "Есть на Modrinth и ещё проходит модерацию. Страница может не открываться.",
            "draft": "Черновик на Modrinth, ещё не опубликован.",
            "rejected": "Modrinth отклонил проект.",
            "withheld": "Modrinth скрыл проект.",
            "unavailable": "Публичной страницы Modrinth нет. Если проект уже отправлен, он может ещё проходить модерацию.",
            "missing": "Страницы на Modrinth нет.",
        },
    },
}


def render_page(catalog: Catalog, lang: str, sort: str = "name") -> str:
    del sort  # the page lists by name; the query is kept so older links still open
    language = lang if lang in _TEXT else "en"
    text = _TEXT[language]
    shell = _PAGE.read_text(encoding="utf-8")
    app = _app(catalog, language, text)
    return (
        shell.replace("__LANG__", language)
        .replace("__TITLE__", html.escape(text["title"]))
        .replace("__APP__", app)
    )


def render_inline(text: str, repo_url: str) -> str:
    parts: list[str] = []
    cursor = 0
    for match in _INLINE.finditer(text):
        parts.append(html.escape(text[cursor : match.start()]))
        if match.group(1) is not None:
            href = _safe_href(match.group(2), repo_url)
            label = html.escape(match.group(1))
            parts.append(f'<a href="{href}" class="inline">{label}</a>' if href else label)
        elif match.group(3) is not None:
            parts.append(f"<code>{html.escape(match.group(3))}</code>")
        elif match.group(4) is not None:
            parts.append(f"<strong>{html.escape(match.group(4))}</strong>")
        else:
            raw = match.group(5).rstrip(".,;:")
            href = _safe_href(raw, repo_url)
            label = html.escape(raw)
            parts.append(f'<a href="{href}" class="inline">{label}</a>' if href else label)
            parts.append(html.escape(match.group(5)[len(raw) :]))
        cursor = match.end()
    parts.append(html.escape(text[cursor:]))
    return "".join(parts)


def _app(catalog: Catalog, lang: str, text: dict) -> str:
    other = "en" if lang == "ru" else "ru"
    other_label = "English" if other == "en" else "Русский"
    mods = sorted(catalog.mods, key=lambda item: item.name.casefold())
    notes = "".join(f'<p class="note">{html.escape(note)}</p>' for note in _notes(catalog, text))
    if mods:
        cards = "".join(_card(mod, lang, text) for mod in mods)
    else:
        cards = f'<p class="note">{html.escape(text["empty"])}</p>'
    stamp = ""
    if catalog.fetched_at:
        moment = datetime.fromtimestamp(catalog.fetched_at, timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        stamp = f'<p class="stamp">{html.escape(text["updated"])} {moment}</p>'
    return f"""
<div class="page">
<header class="mast">
  <p>Minecraft mods by <a class="by" href="https://github.com/Nergan"><em>Nargan</em></a> <a class="lang" href="/mods?lang={other}">{other_label}</a></p>
</header>
{notes}
<div class="mods">{cards}</div>
{stamp}
</div>
"""


def _card(mod: ModEntry, lang: str, text: dict) -> str:
    description = mod.description_ru if lang == "ru" else mod.description_en
    panels = loader_panels(mod)
    meta = []
    if mod.minecraft:
        meta.append(f"Minecraft {mod.minecraft}")
    if not panels:
        meta.extend(mod.loaders)
    if mod.version:
        meta.append(f"v{mod.version}")
    meta_html = f'<p class="meta">{html.escape(" · ".join(meta))}</p>' if meta else ""
    desc_html = f'<p class="desc">{render_inline(description, mod.github_url)}</p>' if description else ""
    links = [
        f'<a class="btn ext" href="{html.escape(mod.github_url, quote=True)}">GitHub</a>'
    ]
    status = text["modrinth"].get(mod.modrinth_state, "")
    if mod.modrinth_url and mod.modrinth_state not in {"unavailable", "missing"}:
        links.append(f'<a class="btn ext" href="{html.escape(mod.modrinth_url, quote=True)}">Modrinth</a>')
    else:
        tip = text["modrinth"]["unavailable"]
        links.append(
            f'<span class="btn ext is-disabled" role="link" aria-disabled="true" tabindex="0">Modrinth<span class="tip">{html.escape(tip)}</span></span>'
        )
        if mod.modrinth_state in {"", "unavailable", "missing"}:
            status = ""
    license_button, license_dialog = _license(mod, text)
    readme_button, readme_dialog = _readme(mod, lang, text)
    status_html = f'<p class="note">{html.escape(status)}</p>' if status else ""
    return f"""
<article class="mod">
  <h2>{html.escape(mod.name)}</h2>
  {meta_html}
  {desc_html}
  <p class="links">{"".join(links)}{license_button}{readme_button}</p>
  {status_html}
  {_loader_tabs(mod, panels, text) if panels else _files(mod, text)}
  {"" if panels else _download_all(mod, text)}
  {license_dialog}
  {readme_dialog}
</article>
"""


def _loader_tabs(mod: ModEntry, panels: list[tuple[str, list, list]], text: dict) -> str:
    buttons: list[str] = []
    bodies: list[str] = []
    for index, (loader, mod_jars, dependency_jars) in enumerate(panels):
        slug = loader_slug(loader)
        active = index == 0
        selected = "true" if active else "false"
        current = " is-active" if active else ""
        buttons.append(
            f'<button type="button" class="loader-tab{current}" role="tab" '
            f'aria-selected="{selected}" data-loader="{slug}">{html.escape(loader)}</button>'
        )
        hidden = "" if active else " hidden"
        bodies.append(
            f'<div class="loader-panel" role="tabpanel" data-loader-panel="{slug}"{hidden}>'
            f"{_files(mod, text, mod_jars, dependency_jars)}"
            f"{_download_all(mod, text, slug)}"
            f"</div>"
        )
    return f'<div class="loader-tabs" role="tablist">{"".join(buttons)}</div>{"".join(bodies)}'


def _files(
    mod: ModEntry,
    text: dict,
    mod_jars: list | None = None,
    dependency_jars: list | None = None,
) -> str:
    mod_jars = mod.mod_jars if mod_jars is None else mod_jars
    dependency_jars = mod.dependency_jars if dependency_jars is None else dependency_jars
    if mod.release_limited and not mod_jars and not dependency_jars:
        return f'<p class="note">{html.escape(text["rate_limit"])}</p>'
    if not mod.has_release:
        return f'<p class="note">{html.escape(text["no_release"])}</p>'
    if not mod_jars and not dependency_jars:
        return f'<p class="note">{html.escape(text["no_jars"])}</p>'
    rows: list[str] = []
    note = ""
    if mod.jars_classified and mod_jars:
        rows.append(_file_row(text["jar"], mod_jars))
        if dependency_jars:
            rows.append(_file_row(text["deps"], dependency_jars))
    else:
        rows.append(_file_row(text["files"], [*mod_jars, *dependency_jars]))
        note = f'<p class="note">{html.escape(text["unclassified"])}</p>'
    body = "".join(row for row in rows if row)
    if not body:
        return note
    return f'<div class="file-list">{body}</div>{note}'


def _download_all(mod: ModEntry, text: dict, loader: str = "") -> str:
    if not loader and not mod.mod_jars and not mod.dependency_jars:
        return ""
    href = f"/mods/{urllib.parse.quote(mod.repo)}/jars.zip"
    filename = f"{mod.repo}.zip"
    if loader:
        href = f"{href}?loader={urllib.parse.quote(loader)}"
        filename = f"{mod.repo}-{loader}.zip"
    label = html.escape(text["download_all"])
    busy = html.escape(text["zip_busy"], quote=True)
    fail = html.escape(text["zip_fail"], quote=True)
    file_attr = html.escape(filename, quote=True)
    return (
        f'<p class="card-foot"><a class="btn zip" href="{html.escape(href, quote=True)}" '
        f'download="{file_attr}" data-file="{file_attr}" data-busy="{busy}" data-fail="{fail}">'
        f'{label}<span class="zip-kind">.zip</span></a></p>'
    )


def _file_row(label: str, jars) -> str:
    links = []
    for jar in jars:
        if not jar.url.startswith(("https://", "http://")):
            continue
        links.append(f'<a class="btn jar" href="{html.escape(jar.url, quote=True)}">{html.escape(jar.name)}</a>')
    if not links:
        return ""
    return f'<span class="kind">{html.escape(label)}</span><div class="jars">{"".join(links)}</div>'


def _license(mod: ModEntry, text: dict) -> tuple[str, str]:
    label = html.escape(_license_label(mod, text))
    if not mod.license_text:
        return f'<span class="kind">{label}</span>', ""
    dialog_id = _dom_id("license", mod.repo)
    body = html.escape(mod.license_text)
    button = f'<button type="button" class="btn pop" data-open="{dialog_id}">{label}</button>'
    return button, _sheet(dialog_id, label, f'<pre class="license-text">{body}</pre>', text)


def _readme(mod: ModEntry, lang: str, text: dict) -> tuple[str, str]:
    if lang == "ru":
        source = mod.readme_ru or mod.readme_en
    else:
        source = mod.readme_en or mod.readme_ru
    if not source:
        return "", ""
    dialog_id = _dom_id("readme", mod.repo)
    title = html.escape(text["readme"])
    body = render_markdown(source, mod.github_url, mod.branch)
    button = f'<button type="button" class="btn pop" data-open="{dialog_id}">{title}</button>'
    return button, _sheet(dialog_id, title, f'<div class="readme">{body}</div>', text)


def _sheet(dialog_id: str, title: str, body: str, text: dict) -> str:
    close = html.escape(text["close"])
    return f"""
<dialog id="{dialog_id}" class="sheet">
  <div class="sheet-head">
    <h3>{title}</h3>
    <form method="dialog"><button class="sheet-close" aria-label="{close}">×</button></form>
  </div>
  <div class="sheet-body">{body}</div>
</dialog>
"""


def render_markdown(text: str, repo_url: str, branch: str = "main") -> str:
    """Render readme Markdown, then drop anything that is not document markup."""
    import markdown

    rendered = markdown.markdown(
        text,
        extensions=["tables", "fenced_code", "sane_lists"],
    )
    cleaner = _MarkdownHTML(repo_url, branch)
    cleaner.feed(rendered)
    cleaner.close()
    return "".join(cleaner.parts)


class _MarkdownHTML(HTMLParser):
    _ALLOWED = {
        "p", "h1", "h2", "h3", "h4", "h5", "h6",
        "ul", "ol", "li", "pre", "code", "strong", "em",
        "a", "table", "thead", "tbody", "tr", "th", "td",
        "blockquote", "hr", "br", "img",
    }
    _VOID = {"br", "hr", "img"}
    _SKIP = {"script", "style", "iframe", "object", "embed"}

    def __init__(self, repo_url: str, branch: str = "main"):
        super().__init__(convert_charrefs=True)
        self.repo_url = repo_url
        self.branch = branch or "main"
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._SKIP:
            self._skip += 1
            return
        if self._skip or tag not in self._ALLOWED:
            return
        self.parts.append(f"<{tag}{self._attributes(tag, attrs)}>")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP:
            if self._skip:
                self._skip -= 1
            return
        if self._skip or tag not in self._ALLOWED or tag in self._VOID:
            return
        self.parts.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(html.escape(data))

    def _attributes(self, tag: str, attrs: list[tuple[str, str | None]]) -> str:
        kept: list[str] = []
        for key, value in attrs:
            if key.startswith("on"):
                continue
            if tag == "a" and key == "href":
                href = _safe_href(value or "", self.repo_url)
                if href:
                    kept.append(f' href="{href}"')
            elif tag == "img" and key == "src":
                src = _image_src(value or "", self.repo_url, self.branch)
                if src:
                    kept.append(f' src="{src}"')
            elif tag == "img" and key == "alt":
                kept.append(f' alt="{html.escape(value or "", quote=True)}"')
            elif tag == "img" and key in {"width", "height"} and value and re.fullmatch(r"\d{1,4}", value):
                kept.append(f' {key}="{value}"')
        return "".join(kept)


def _dom_id(prefix: str, repo: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_-]", "-", repo)
    return html.escape(f"{prefix}-{safe}", quote=True)


def _license_label(mod: ModEntry, text: dict) -> str:
    if mod.license_id and mod.license_id not in {"NOASSERTION", "OTHER"}:
        return mod.license_id
    return mod.license_name or text["license_missing"]


def _notes(catalog: Catalog, text: dict) -> list[str]:
    notes: list[str] = []
    if catalog.error == "stale":
        notes.append(text["stale"])
    elif catalog.error:
        notes.append(text["fetch"])
    if catalog.partial:
        notes.append(text["partial"])
    return notes


def _image_src(url: str, repo_url: str, branch: str) -> str | None:
    """Point a readme image at raw file bytes. GitHub blob pages are not images."""
    candidate = url.strip()
    if candidate.startswith(("http://", "https://")):
        parsed = urlsplit(candidate)
        host = (parsed.hostname or "").lower()
        if parsed.scheme not in {"http", "https"} or not host or parsed.username or parsed.password:
            return None
        if host == "github.com":
            parts = [part for part in parsed.path.split("/") if part]
            if len(parts) >= 5 and parts[2] in {"blob", "raw"}:
                rest = "/".join(urllib.parse.unquote(part) for part in parts[4:])
                raw = f"https://raw.githubusercontent.com/{parts[0]}/{parts[1]}/{parts[3]}/{rest}"
                return html.escape(raw, quote=True)
        return html.escape(candidate, quote=True)
    path = candidate
    while path.startswith("./"):
        path = path[2:]
    if not path or path.startswith("/") or ".." in path.split("/"):
        return None
    if not re.fullmatch(r"[A-Za-z0-9_./~+-]+", path):
        return None
    repo = urlsplit(repo_url)
    repo_parts = [part for part in repo.path.split("/") if part]
    if len(repo_parts) < 2:
        return None
    safe_branch = branch if re.fullmatch(r"[A-Za-z0-9._/-]+", branch) else "main"
    raw = (
        f"https://raw.githubusercontent.com/{repo_parts[0]}/{repo_parts[1]}/"
        f"{safe_branch}/{path}"
    )
    return html.escape(raw, quote=True)


def _safe_href(url: str, repo_url: str) -> str | None:
    candidate = url.strip()
    if candidate.startswith(("http://", "https://")):
        parsed = urlsplit(candidate)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            return None
        return html.escape(candidate, quote=True)
    if not re.fullmatch(r"[A-Za-z0-9_./~+-]+", candidate):
        return None
    joined = urllib.parse.urljoin(repo_url.rstrip("/") + "/blob/main/", candidate)
    return html.escape(joined, quote=True)
