"""Helpers for static frontend contract checks in pytest."""

from __future__ import annotations

import re
from pathlib import Path

NETLAZY_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = NETLAZY_DIR / "frontend"
FRONTEND_SRC = FRONTEND_DIR / "src"

LOCALES = ("en", "ru", "pt", "zh", "ja", "ko")

INBOX_UI_KEYS = (
    "select_chat_prompt",
    "no_chats",
    "no_message",
    "back",
    "matched_label",
    "decline",
    "send",
    "no_valid_private",
    "failed_delete_chat",
)

MOTION_CSS_TOKENS = (
    "--motion-ease",
    "--motion-hover-scale",
    "--motion-press-scale",
    "--motion-disabled-opacity",
)


def read_text(relative_path: str) -> str:
    path = NETLAZY_DIR / relative_path
    assert path.is_file(), f"Missing file: {relative_path}"
    return path.read_text(encoding="utf-8")


def extract_vue_scoped_css(vue_relative_path: str) -> str:
    content = read_text(vue_relative_path)
    match = re.search(r"<style scoped>(.*?)</style>", content, re.DOTALL)
    assert match, f"No scoped <style> block in {vue_relative_path}"
    return match.group(1)


def extract_locale_keys(translations_content: str, locale: str) -> set[str]:
    pattern = rf"^\s+{re.escape(locale)}:\s*\{{"
    match = re.search(pattern, translations_content, re.MULTILINE)
    assert match, f"Locale block '{locale}' not found"

    start = match.end()
    depth = 1
    idx = start
    while idx < len(translations_content) and depth:
        char = translations_content[idx]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        idx += 1

    block = translations_content[start : idx - 1]
    return set(re.findall(r"^\s{4}([a-zA-Z0-9_]+):", block, re.MULTILINE))


def css_rule_block(css: str, selector: str) -> str:
    pattern = rf"{re.escape(selector)}\s*\{{([^}}]*)\}}"
    match = re.search(pattern, css, re.DOTALL)
    assert match, f"CSS rule '{selector}' not found"
    return match.group(1)
