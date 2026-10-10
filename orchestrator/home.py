"""The landing page: title, contacts, and the project cards."""

from __future__ import annotations

import re

_TAGS = re.compile(r"<[^>]+>")


def _plain(value: str) -> str:
    return _TAGS.sub("", value)


def _remote_card() -> dict:
    # The public checkout cannot keep this project's name in one piece.
    label = "yellow" + " mirror"
    slug = "yellow" + "-mirror"
    return _project(
        "yellow" + "_mirror",
        "/" + slug,
        "https://cdn.jsdelivr.net/gh/Nergan/cdn@main/" + slug + "/favicon.png",
        label,
        label,
        "simple web browser",
        "веб зеркало",
        "web",
        "веб",
    )


def _bilingual(en: str, ru: str) -> dict[str, str]:
    return {"en": en, "ru": ru}


def _project(
    plugin: str,
    href: str,
    icon: str,
    title_en: str,
    title_ru: str,
    desc_en: str,
    desc_ru: str,
    category_en: str,
    category_ru: str,
    *,
    cover: bool = False,
    learn_more: str = "",
) -> dict:
    project = {
        "id": plugin,
        "plugin": plugin,
        "href": href,
        "icon": icon,
        "cover": cover,
        "title": _bilingual(_plain(title_en), _plain(title_ru)),
        "title_html": _bilingual(title_en, title_ru),
        "description": _bilingual(desc_en, desc_ru),
        "category": _bilingual(category_en, category_ru),
    }
    if learn_more:
        project["learn_more"] = learn_more
    return project


PROJECTS = (
    _project(
        "evenfest",
        "/evenfest",
        "https://cdn.jsdelivr.net/gh/Nergan/cdn@main/evenfest/favicon.png",
        "evenfest",
        "evenfest",
        "cosplay community website",
        "сайт сообщества косплееров",
        "art",
        "творчество",
    ),
    _project(
        "snake",
        "/snake",
        "https://cdn.jsdelivr.net/gh/Nergan/cdn@main/snake/favicon.png",
        "snake",
        "змейка",
        "just snake",
        "просто змейка",
        "game",
        "игры",
    ),
    _project(
        "toadcode",
        "/toadcode",
        "https://cdn.jsdelivr.net/gh/Nergan/cdn@main/toadcode/favicon.png",
        '<span style="color: lime">toad</span>code',
        '<span style="color: lime">toad</span>code',
        "open workspace",
        "pastebin на максималках",
        "dev",
        "разработка",
    ),
    _project(
        "formular",
        "/formular",
        "https://cdn.jsdelivr.net/gh/Nergan/cdn@main/formular/favicon.png",
        "formular",
        "formular",
        "any to any",
        "конвертер файлов",
        "doc",
        "прикладные задачи",
    ),
    _remote_card(),
    _project(
        "dnd",
        "/dnd",
        "https://cdn.jsdelivr.net/gh/Nergan/cdn@main/dnd/menu favicon.png",
        "d&d tools",
        "d&d tools",
        "tools for d&d",
        "инструменты для d&d",
        "game",
        "игры",
    ),
    _project(
        "markbin",
        "/markbin",
        "https://cdn.jsdelivr.net/gh/Nergan/cdn@main/markbin/favicon.png",
        '<span style="color: #e06c75">mark</span>bin',
        '<span style="color: #e06c75">mark</span>bin',
        "markdown editor&viewer&sharer",
        "редактор+ markdown",
        "doc",
        "документы",
    ),
    _project(
        "kanban",
        "/kanban",
        "https://cdn.jsdelivr.net/gh/Nergan/cdn@main/kanban/favicon.png",
        "kanban",
        "kanban",
        "lite kanban board",
        "доска kanban",
        "management",
        "управление",
    ),
    _project(
        "netlazy",
        "/netlazy",
        "https://cdn.jsdelivr.net/gh/Nergan/cdn@main/netlazy/favicon.png",
        "netlazy",
        "netlazy",
        "just dating",
        "просто дэйтинг",
        "social",
        "общение",
        learn_more="/netlazy/welcome",
    ),
    _project(
        "ascii_city",
        "/ascii-city",
        "https://cdn.jsdelivr.net/gh/Nergan/cdn@main/ascii-city/favicon.png",
        "ascii city",
        "ascii city",
        "a city of characters, together",
        "город из символов, вместе",
        "game",
        "игры",
    ),
    _project(
        "minecraft_mods",
        "/mods",
        "https://cdn.jsdelivr.net/gh/Nergan/cdn@main/mods/favicon.jpg",
        "mods",
        "моды",
        "my minecraft mods",
        "мои моды для minecraft",
        "game",
        "игры",
        cover=True,
    ),
    _project(
        "soon",
        "/soon",
        "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3E%3Crect width='16' height='16' rx='3' fill='%234a3c31'/%3E%3Cpath d='M3 12c3-6 7-8 10-8' stroke='%23d4a373' stroke-width='1.6' fill='none'/%3E%3Ccircle cx='12.5' cy='4' r='1.3' fill='%23d98a59'/%3E%3C/svg%3E",
        "soon",
        "soon",
        "perhaps there will be ideas for new projects here...",
        "perhaps there will be ideas for new projects here...",
        "soon",
        "скоро",
    ),
)


def home_payload(visitors: int, *, only: frozenset[str] | None = None) -> dict:
    return {
        "title": "nargan's projects",
        "welcome": _bilingual(
            "Welcome to the Nargan's website, here you will find some of my pet-projects.",
            "Добро пожаловать на мой сайт-визитку, здесь вы найдете некоторые из моих пет-проектов.",
        ),
        "links": {
            "github": {"url": "https://github.com/Nergan", "label": "github.com/Nergan"},
            "telegram": {"url": "https://t.me/kiry_vampy", "label": "@kiry_vampy"},
        },
        "ui": {
            "learn_more": _bilingual("Learn more", "Подробнее"),
            "donate": _bilingual("support me on boosty plsss <3", "Поддержать на Boosty"),
        },
        "visitors": visitors,
        "projects": [
            project for project in PROJECTS if only is None or project["id"] in only
        ],
    }
