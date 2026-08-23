"""Static and HTTP contract tests for the Vue frontend."""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from netlazy.presentation.inbox_router import InboxItemResponse
from frontend_utils import (
    INBOX_UI_KEYS,
    LOCALES,
    MOTION_CSS_TOKENS,
    NETLAZY_DIR,
    css_rule_block,
    extract_locale_keys,
    extract_vue_scoped_css,
    read_text,
)


@pytest.fixture
def app_client(monkeypatch):
    async def _noop_async(*_args, **_kwargs):
        return 0

    class _NoopMongoHandler:
        def start_worker(self):
            return None

        async def stop_worker(self):
            return None

    monkeypatch.setattr("netlazy.main.connect_to_mongo", _noop_async)
    monkeypatch.setattr("netlazy.main.close_mongo_connection", _noop_async)
    monkeypatch.setattr("netlazy.main.tag_service.sync_from_yaml", _noop_async)
    monkeypatch.setattr("netlazy.main.mongo_handler", _NoopMongoHandler())

    from netlazy.main import app

    with TestClient(app) as client:
        yield client


class TestFrontendStructure:
    def test_core_frontend_files_exist(self):
        required = [
            "frontend/src/main.js",
            "frontend/src/App.vue",
            "frontend/src/components/Inbox.vue",
            "frontend/src/components/Feed.vue",
            "frontend/src/store/state.js",
            "frontend/src/store/translations.js",
            "frontend/css/components.css",
            "frontend/css/variables.css",
        ]
        for rel in required:
            assert (NETLAZY_DIR / rel).is_file(), f"Missing file: {rel}"


class TestInboxUiContracts:
    def test_filter_icons_use_active_class_binding(self):
        inbox = read_text("frontend/src/components/Inbox.vue")
        match = re.search(r"<template>(.*?)</template>\s*<script", inbox, re.DOTALL)
        assert match, "Inbox template block not found"
        markup = match.group(1)
        assert len(re.findall(r'class="[^"]*filter-icon', markup)) == 5
        assert markup.count(":class=\"{active:") == 5
        assert "bi-envelope-arrow-down filter-icon" not in markup
        assert "bi-envelope-arrow-up filter-icon" not in markup

    def test_active_filter_uses_minimal_shape_marker(self):
        css = extract_vue_scoped_css("frontend/src/components/Inbox.vue")
        active_block = css_rule_block(css, ".filter-icon.active")
        assert "background:" not in active_block
        assert "border" not in active_block
        assert ".filter-icon.active::after" in css
        assert "border-radius: 50%" in css_rule_block(css, ".filter-icon.active::after")

    def test_inbox_or_filter_logic(self):
        inbox = read_text("frontend/src/components/Inbox.vue")
        assert "function isChatVisible" in inbox
        assert "filters.state[chat.chatState] || filters.type[chat.type]" in inbox
        assert "chat.chatState === 'received' || chat.chatState === 'sent'" in inbox

    def test_active_chat_shape_highlight(self):
        css = extract_vue_scoped_css("frontend/src/components/Inbox.vue")
        active_block = css_rule_block(css, ".chat-preview.active")
        assert "box-shadow:" in active_block or "background:" in active_block

    def test_is_read_mapped_from_api(self):
        state_js = read_text("frontend/src/store/state.js")
        assert "is_read: r.is_read" in state_js


class TestGlobalUiContracts:
    def test_motion_tokens_defined(self):
        variables = read_text("frontend/css/variables.css")
        for token in MOTION_CSS_TOKENS:
            assert token in variables

    def test_unified_disabled_style(self):
        components = read_text("frontend/css/components.css")
        assert ":disabled" in components
        assert "var(--motion-disabled-opacity)" in components
        assert "not-allowed" in components

    def test_disabled_buttons_do_not_use_inline_opacity_in_inbox_or_feed(self):
        for rel in ("frontend/src/components/Inbox.vue", "frontend/src/components/Feed.vue", "frontend/src/App.vue"):
            content = read_text(rel)
            assert "cursor: 'not-allowed'" not in content
            assert 'opacity: (validPrivateContacts' not in content


class TestTranslations:
    @pytest.fixture
    def translations(self):
        return read_text("frontend/src/store/translations.js")

    def test_inbox_keys_present_in_all_locales(self, translations):
        for locale in LOCALES:
            keys = extract_locale_keys(translations, locale)
            missing = [key for key in INBOX_UI_KEYS if key not in keys]
            assert not missing, f"Locale '{locale}' missing keys: {missing}"

    def test_english_inbox_strings(self, translations):
        keys = extract_locale_keys(translations, "en")
        assert "select_chat_prompt" in keys
        en_block = translations.split("en: {", 1)[1]
        assert 'select_chat_prompt: "select a chat..."' in en_block


class TestBackendFrontendAlignment:
    def test_inbox_response_includes_is_read(self):
        assert "is_read" in InboxItemResponse.model_fields

    def test_main_redirects_root_to_profile(self):
        main_py = read_text("main.py")
        assert 'url=f"{base}/profile"' in main_py
        assert "async def root_redirect" in main_py


class TestSpaRoutes:
    def test_root_redirects_to_profile(self, app_client):
        response = app_client.get("/", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"].endswith("/profile")

    def test_netlazy_root_redirects_to_profile(self, app_client):
        response = app_client.get("/netlazy", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"].endswith("/netlazy/profile")

    @pytest.mark.parametrize("path", ["profile", "inbox", "feed", "privacy"])
    def test_spa_routes_serve_shell_or_fallback(self, app_client, path):
        response = app_client.get(f"/{path}", headers={"accept": "text/html"})
        assert response.status_code == 200
        assert "Frontend Not Built Yet" in response.text or "<" in response.text

    def test_unknown_spa_path_redirects_to_profile(self, app_client):
        response = app_client.get("/unknown-page", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"].endswith("/profile")

    def test_browser_api_request_redirects_to_profile(self, app_client):
        response = app_client.get("/api/inbox", headers={"accept": "text/html"}, follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"].endswith("/profile")
