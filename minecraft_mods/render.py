"""Render the mods catalog as a compact old-style list."""

from __future__ import annotations

import html
import re
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from minecraft_mods.catalog import Catalog, ModEntry

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
        "jar": "jar",
        "deps": "deps",
        "files": "jars",
        "no_release": "No GitHub release yet.",
        "no_jars": "The latest release has no jar files.",
        "unclassified": "These jars are in the release; the mod jar could not be picked out of them.",
        "license_missing": "License is not set",
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
        "jar": "jar",
        "deps": "зависимости",
        "files": "jar",
        "no_release": "Релиза на GitHub пока нет.",
        "no_jars": "В последнем релизе нет jar-файлов.",
        "unclassified": "Эти jar лежат в релизе; отделить файл мода от зависимостей не получилось.",
        "license_missing": "Лицензия не указана",
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
    meta = []
    if mod.minecraft:
        meta.append(f"Minecraft {mod.minecraft}")
    meta.extend(mod.loaders)
    if mod.version:
        meta.append(f"v{mod.version}")
    meta_html = f'<span class="meta">{html.escape(" · ".join(meta))}</span>' if meta else ""
    desc_html = f'<p class="desc">{render_inline(description, mod.github_url)}</p>' if description else ""
    links = [
        f'<a class="btn ext" href="{html.escape(mod.github_url, quote=True)}">GitHub</a>'
    ]
    if mod.modrinth_url:
        links.append(f'<a class="btn ext" href="{html.escape(mod.modrinth_url, quote=True)}">Modrinth</a>')
    status = text["modrinth"].get(mod.modrinth_state, "")
    status_html = f'<p class="note">{html.escape(status)}</p>' if status else ""
    return f"""
<article class="mod">
  <h2>{html.escape(mod.name)}</h2>
  {meta_html}
  {desc_html}
  <p class="links">{"".join(links)}</p>
  {status_html}
  {_files(mod, text)}
  {_license(mod, text)}
</article>
"""


def _files(mod: ModEntry, text: dict) -> str:
    if not mod.has_release:
        return f'<p class="note">{html.escape(text["no_release"])}</p>'
    if not mod.mod_jars and not mod.dependency_jars:
        return f'<p class="note">{html.escape(text["no_jars"])}</p>'
    rows: list[str] = []
    if mod.jars_classified and mod.mod_jars:
        rows.append(_file_row(text["jar"], mod.mod_jars))
        if mod.dependency_jars:
            rows.append(_file_row(text["deps"], mod.dependency_jars))
    else:
        rows.append(_file_row(text["files"], [*mod.mod_jars, *mod.dependency_jars]))
        rows.append(f'<p class="note">{html.escape(text["unclassified"])}</p>')
    return "".join(rows)


def _file_row(label: str, jars) -> str:
    links = []
    for jar in jars:
        if not jar.url.startswith(("https://", "http://")):
            continue
        links.append(f'<a class="btn jar" href="{html.escape(jar.url, quote=True)}">{html.escape(jar.name)}</a>')
    if not links:
        return ""
    return f'<p class="files"><span class="kind">{html.escape(label)}</span>{"".join(links)}</p>'


def _license(mod: ModEntry, text: dict) -> str:
    label = html.escape(_license_label(mod, text))
    if not mod.license_text:
        return f'<p class="license"><span class="kind">{label}</span></p>'
    body = html.escape(mod.license_text)
    return f'<details class="license"><summary>{label}</summary><pre class="license-text">{body}</pre></details>'


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
