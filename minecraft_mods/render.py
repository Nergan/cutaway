"""Render the mods catalog with the warm mid-dark page from the design set."""

from __future__ import annotations

import html
import re
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from minecraft_mods.catalog import Catalog, ModEntry, version_tuple

_PAGE = Path(__file__).with_name("page.html")
_INLINE = re.compile(
    r"\[([^\]]+)\]\(([^)\s]+)\)"
    r"|`([^`]+)`"
    r"|\*\*([^*]+)\*\*"
    r"|(https?://[^\s)<]+)"
)

_TEXT = {
    "en": {
        "title": "mods",
        "tagline": "Minecraft mods from github.com/Nergan. Names ending in mod.",
        "home": "home",
        "github": "GitHub",
        "modrinth_account": "Modrinth",
        "search": "Search",
        "search_placeholder": "name or description",
        "sort": "Sort",
        "sort_name": "Name",
        "sort_minecraft": "Minecraft version",
        "loader": "Loader",
        "loader_all": "All loaders",
        "empty": "No repositories ending in mod were found.",
        "filter_empty": "Nothing matches this filter.",
        "jar": "Mod jar",
        "deps": "Dependencies",
        "files": "Release jars",
        "no_release": "No GitHub release yet.",
        "no_jars": "The latest release has no jar files.",
        "unclassified": "These jars are in the release; the mod jar could not be picked out of them.",
        "license_missing": "License is not set",
        "updated": "List updated",
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
        "title": "моды",
        "tagline": "Моды Minecraft с github.com/Nergan. В список попадают репозитории, имя которых кончается на mod.",
        "home": "на главную",
        "github": "GitHub",
        "modrinth_account": "Modrinth",
        "search": "Поиск",
        "search_placeholder": "название или описание",
        "sort": "Сортировка",
        "sort_name": "По названию",
        "sort_minecraft": "По версии Minecraft",
        "loader": "Загрузчик",
        "loader_all": "Все загрузчики",
        "empty": "Репозиториев с именем на mod не найдено.",
        "filter_empty": "Ничего не подошло под фильтр.",
        "jar": "Jar мода",
        "deps": "Зависимости",
        "files": "Jar из релиза",
        "no_release": "Релиза на GitHub пока нет.",
        "no_jars": "В последнем релизе нет jar-файлов.",
        "unclassified": "Эти jar лежат в релизе; отделить файл мода от зависимостей не получилось.",
        "license_missing": "Лицензия не указана",
        "updated": "Список обновлён",
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


def render_page(catalog: Catalog, lang: str, sort: str) -> str:
    language = lang if lang in _TEXT else "en"
    ordering = sort if sort in {"name", "minecraft"} else "name"
    text = _TEXT[language]
    shell = _PAGE.read_text(encoding="utf-8")
    app = _app(catalog, language, ordering, text)
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
            parts.append(f'<a href="{href}" class="nav-link">{label}</a>' if href else label)
        elif match.group(3) is not None:
            parts.append(f"<code>{html.escape(match.group(3))}</code>")
        elif match.group(4) is not None:
            parts.append(f"<strong>{html.escape(match.group(4))}</strong>")
        else:
            raw = match.group(5).rstrip(".,;:")
            href = _safe_href(raw, repo_url)
            label = html.escape(raw)
            parts.append(f'<a href="{href}" class="nav-link">{label}</a>' if href else label)
            parts.append(html.escape(match.group(5)[len(raw) :]))
        cursor = match.end()
    parts.append(html.escape(text[cursor:]))
    return "".join(parts)


def _app(catalog: Catalog, lang: str, sort: str, text: dict) -> str:
    other = "en" if lang == "ru" else "ru"
    other_label = "English" if other == "en" else "Русский"
    mods = _sorted(catalog.mods, sort)
    notes = _notes(catalog, text)
    note_html = "".join(f'<p class="note">{html.escape(note)}</p>' for note in notes)
    if mods:
        cards = "".join(_card(mod, lang, text) for mod in mods)
        empty = ""
    else:
        cards = f'<section class="section"><p>{html.escape(text["empty"])}</p></section>'
        empty = ""
    stamp = ""
    if catalog.fetched_at:
        moment = datetime.fromtimestamp(catalog.fetched_at, timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        stamp = f'{html.escape(text["updated"])} {moment}'
    return f"""
<div class="app-container">
  <header class="app-header">
    <div class="brand-row">
      <img class="brand-mark" src="https://cdn.jsdelivr.net/gh/Nergan/cdn@main/mods/favicon.jpg" alt="">
      <h1 class="brand-title">{html.escape(text["title"])}</h1>
    </div>
    <p class="brand-tagline">{html.escape(text["tagline"])}</p>
    <nav class="app-nav" aria-label="mods">
      <a class="nav-link" href="/">{html.escape(text["home"])}</a>
      <a class="nav-link" href="https://github.com/Nergan">github.com/Nergan</a>
      <a class="nav-link" href="https://modrinth.com/user/nargan">modrinth.com/user/nargan</a>
      <a class="nav-link" href="{html.escape(_href(other, sort), quote=True)}">{other_label}</a>
    </nav>
  </header>
  {note_html}
  <section class="section">
    <div class="form-grid">
      <div class="form-group">
        <label for="mod-search">{html.escape(text["search"])}</label>
        <input id="mod-search" class="form-control" type="search" placeholder="{html.escape(text["search_placeholder"])}">
      </div>
      {_dropdown(text["sort"], "sort-label", _sort_options(lang, sort, text), text["sort_name"] if sort == "name" else text["sort_minecraft"])}
      {_dropdown(text["loader"], "loader-label", _loader_options(mods, text), text["loader_all"])}
    </div>
  </section>
  <p id="filter-empty" class="note is-hidden">{html.escape(text["filter_empty"])}</p>
  {cards}
  {empty}
  <footer class="app-footer">{stamp}</footer>
</div>
"""


def _card(mod: ModEntry, lang: str, text: dict) -> str:
    description = mod.description_ru if lang == "ru" else mod.description_en
    pills = []
    if mod.minecraft:
        pills.append(f'<span class="pill">Minecraft {html.escape(mod.minecraft)}</span>')
    for loader in mod.loaders:
        pills.append(f'<span class="pill">{html.escape(loader)}</span>')
    if mod.version:
        pills.append(f'<span class="pill">v{html.escape(mod.version)}</span>')
    pill_html = f'<div class="pill-group">{"".join(pills)}</div>' if pills else ""
    links = [
        f'<a class="btn" href="{html.escape(mod.github_url, quote=True)}">{html.escape(text["github"])}</a>'
    ]
    if mod.modrinth_url:
        links.append(
            f'<a class="btn" href="{html.escape(mod.modrinth_url, quote=True)}">{html.escape(text["modrinth_account"])}</a>'
        )
    license_label = _license_label(mod, text)
    if mod.license_url and license_label != text["license_missing"]:
        links.append(
            f'<a class="btn" href="{html.escape(mod.license_url, quote=True)}">{html.escape(license_label)}</a>'
        )
    else:
        links.append(f'<span class="pill">{html.escape(license_label)}</span>')
    status = text["modrinth"].get(mod.modrinth_state, "")
    status_html = f'<p class="mod-note">{html.escape(status)}</p>' if status else ""
    loaders = " ".join(item.lower() for item in mod.loaders)
    return f"""
<article class="section mod-card" data-loaders="{html.escape(loaders, quote=True)}">
  <div class="mod-head">
    <h2>{html.escape(mod.name)}</h2>
    {pill_html}
  </div>
  <p class="mod-desc">{render_inline(description, mod.github_url) if description else ""}</p>
  <div class="mod-links">{"".join(links)}</div>
  {status_html}
  {_files(mod, text)}
</article>
"""


def _files(mod: ModEntry, text: dict) -> str:
    if not mod.has_release:
        return f'<p class="mod-note">{html.escape(text["no_release"])}</p>'
    if not mod.mod_jars and not mod.dependency_jars:
        return f'<p class="mod-note">{html.escape(text["no_jars"])}</p>'
    rows: list[str] = []
    if mod.jars_classified and mod.mod_jars:
        rows.append(_file_row(text["jar"], mod.mod_jars, primary=True))
        if mod.dependency_jars:
            rows.append(_file_row(text["deps"], mod.dependency_jars, primary=False))
    else:
        rows.append(_file_row(text["files"], [*mod.mod_jars, *mod.dependency_jars], primary=False))
        rows.append(f'<p class="mod-note">{html.escape(text["unclassified"])}</p>')
    return f'<div class="mod-files">{"".join(rows)}</div>'


def _file_row(label: str, jars, *, primary: bool) -> str:
    css = "btn btn-primary" if primary else "btn"
    links = []
    for jar in jars:
        href = html.escape(jar.url, quote=True) if jar.url.startswith(("https://", "http://")) else ""
        if not href:
            continue
        links.append(f'<a class="{css}" href="{href}">{html.escape(jar.name)}</a>')
    if not links:
        return ""
    return (
        f'<div class="file-row"><span class="file-label">{html.escape(label)}</span>{"".join(links)}</div>'
    )


def _dropdown(label: str, label_id: str, options: str, selected_label: str) -> str:
    return f"""
<div class="form-group">
  <label id="{label_id}">{html.escape(label)}</label>
  <div class="custom-select" tabindex="0" role="combobox" aria-haspopup="listbox" aria-expanded="false" aria-labelledby="{label_id}">
    <div class="select-trigger">
      <span class="selected-text">{html.escape(selected_label)}</span>
      <span class="select-arrow" aria-hidden="true"></span>
    </div>
    <div class="select-options-panel" role="listbox">{options}</div>
  </div>
</div>
"""


def _sort_options(lang: str, sort: str, text: dict) -> str:
    rows = [("name", text["sort_name"]), ("minecraft", text["sort_minecraft"])]
    return "".join(
        _option(label, selected=key == sort, href=_href(lang, key))
        for key, label in rows
    )


def _loader_options(mods: list[ModEntry], text: dict) -> str:
    found: list[str] = []
    for mod in mods:
        for loader in mod.loaders:
            if loader not in found:
                found.append(loader)
    options = [_option(text["loader_all"], selected=True, filter_value="all")]
    options.extend(_option(loader, selected=False, filter_value=loader.lower()) for loader in found)
    return "".join(options)


def _option(label: str, *, selected: bool, href: str = "", filter_value: str = "") -> str:
    css = "select-option selected" if selected else "select-option"
    attrs = f' aria-selected="{"true" if selected else "false"}"'
    if href:
        attrs += f' data-href="{html.escape(href, quote=True)}"'
    if filter_value:
        attrs += f' data-filter="{html.escape(filter_value, quote=True)}"'
    return f'<div class="{css}" role="option"{attrs}>{html.escape(label)}</div>'


def _href(lang: str, sort: str) -> str:
    return f"/mods?{urllib.parse.urlencode({'lang': lang, 'sort': sort})}"


def _sorted(mods: list[ModEntry], sort: str) -> list[ModEntry]:
    if sort == "minecraft":
        return sorted(mods, key=lambda item: (version_tuple(item.minecraft), item.name.casefold()), reverse=True)
    return sorted(mods, key=lambda item: item.name.casefold())


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
