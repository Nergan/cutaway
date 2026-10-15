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

    def test_active_filter_uses_underline_and_accent_colors(self):
        css = extract_vue_scoped_css("frontend/src/components/Inbox.vue")
        base_block = css_rule_block(css, ".filter-icon")
        underline_block = css_rule_block(css, ".filter-icon::after")
        active_underline_block = css_rule_block(css, ".filter-icon.active::after")

        assert "align-items: center" in base_block
        assert "justify-content: center" in base_block
        assert re.search(r"width:\s*[\d.]+rem", base_block)
        assert re.search(r"height:\s*[\d.]+rem", base_block)
        assert "height: 1px" in underline_block
        assert "opacity: 0" in underline_block
        assert "scaleX(0)" in underline_block
        assert "transition:" in underline_block
        assert "opacity: 1" in active_underline_block
        assert "scaleX(1)" in active_underline_block
        assert "border-color: currentColor" not in css
        assert "type-share.active { color: var(--accent-info)" in css
        assert "type-exchange.active { color: var(--accent-moss)" in css
        assert "type-demand.active { color: var(--accent-danger)" in css

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
        assert "export function isInboxUnread" in state_js
        assert "item.status === 'pending' && !item.is_sender" in state_js
        assert "item.status !== 'pending' && item.is_sender" in state_js

    def test_sidebar_badge_counts_unread_not_all_pending(self):
        app = read_text("frontend/src/App.vue")
        assert "isInboxUnread" in app
        assert "r.status === 'pending' && !r.is_sender" not in app

    def test_sent_exchange_demand_cannot_be_deleted(self):
        inbox = read_text("frontend/src/components/Inbox.vue")
        assert "function canDeleteChat" in inbox
        assert "chat.chatState === 'sent' && chat.type === 'share'" in inbox
        assert "canDeleteChat(selectedChat)" in inbox


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
        assert 'select_chat_prompt: "select a request..."' in en_block
        assert 'no_chats: "no requests..."' in en_block


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


class TestInterfaceVersions:
    def test_config_defaults_to_the_flat_interface(self):
        from netlazy.config import Settings

        assert Settings.model_fields["interface_version"].default == "2"

    def test_ui_endpoint_reports_the_configured_version(self, app_client, monkeypatch):
        from netlazy.config import settings

        monkeypatch.setattr(settings, "interface_version", "1")
        response = app_client.get("/api/ui")
        assert response.status_code == 200
        assert response.json() == {"interface_version": "1"}

    def test_served_html_uses_the_configured_version(self):
        from netlazy.main import apply_interface_version

        stamped = apply_interface_version("<html><head></head><body></body></html>", "2")
        assert 'window.__NETLAZY_UI_VERSION__="2"' in stamped
        switched = apply_interface_version(stamped, "1")
        assert 'window.__NETLAZY_UI_VERSION__="1"' in switched
        assert switched.count("window.__NETLAZY_UI_VERSION__") == 1

    def test_version_two_keeps_version_one_markup(self):
        editor = read_text("frontend/src/components/Editor.vue")
        feed = read_text("frontend/src/components/Feed.vue")
        styles = read_text("frontend/css/v2.css")
        assert 'class="tag-library-pane" v-if="!isV2"' in editor
        assert "select_profile_tags" in editor
        assert "not_in_feed" in editor
        assert "profile-tag-header" in editor
        assert "card-self" in feed
        assert "no_tags_found" in feed
        assert "backdrop-filter: none" in styles
        assert "body.ui-v2 .filter-icon" in styles
        assert "profile-sheet" in editor
        assert "tagsMatchingQuery" in editor
        assert "tagsMatchingQuery" in feed
        assert "marquee-group" in editor
        assert 'v-if="!isV2"' not in editor.split("profile-tags-block")[-1][:400]
        state = read_text("frontend/src/store/state.js")
        assert "!contact.is_private" in state
        assert "function tagsMatchingQuery" in state
        assert "rgba(255, 255, 255, 0.78)" in styles
        assert 'name="profile-tag"' in editor
        assert "profile-media-block" in editor
        assert ".chip *" in read_text("frontend/css/components.css")

    def test_new_copy_is_localized(self):
        translations = read_text("frontend/src/store/translations.js")
        for locale in LOCALES:
            keys = extract_locale_keys(translations, locale)
            assert "select_profile_tags" in keys
            assert "not_in_feed" in keys
            assert "form_missing" in keys
            assert "link_copied" in keys
            assert "form_not_shared" in keys
            assert "back_to_feed" in keys


class TestFeedCardAffordance:
    def test_profile_card_background_uses_pointer_cursor(self):
        css = read_text("frontend/css/views.css")
        block = css_rule_block(css, ".masonry-grid .card.card-linkable")
        assert "cursor: pointer" in block
        hover = css_rule_block(css, ".masonry-grid .card.card-linkable:hover")
        assert "var(--accent-moss)" in hover
        assert "var(--bg-surface)" in hover
        child = css_rule_block(css, ".masonry-grid .card.card-linkable > *")
        assert "cursor: auto" in child
        feed = read_text("frontend/src/components/Feed.vue")
        assert "card-linkable" in feed
        assert "feed-results-single" in feed
        components = read_text("frontend/css/components.css")
        plain = css_rule_block(components, ".masonry-grid .card a.contact-link")
        assert "text-decoration: none" in plain
        assert ".masonry-grid .card a.contact-link:hover::after" in components
        assert "contact-link animated-underline" in feed
        assert "card-ripple-layer" in feed
        copy = feed.split("async function copyProfileLink", 1)[1].split("async function fetchFeed", 1)[0]
        assert "playCardRipple(event)" in copy
        assert "function pointHitsText" in feed
        assert "function isEmptyTextFieldClick" in feed
        assert "card-contacts" in feed
        linkClick = feed.split("function onContactLinkClick", 1)[1].split("function onContactValueClick", 1)[0]
        assert "stopPropagation" in linkClick
        assert "preventDefault" in linkClick
        assert "acceptsProfileCopyClick(event, profile)" in feed
        value = css_rule_block(css, ".masonry-grid .card .contact-val")
        assert "flex: 0 1 auto" in value
        ripple = css_rule_block(css, ".card-ripple")
        assert "var(--accent-moss)" in ripple
        assert "card-copy-ripple" in css

    def test_shared_form_survives_saved_feed_view(self):
        state = read_text("frontend/src/store/state.js")
        capture = state.split("async function loadSavedState", 1)[1].split("const { value: raw }", 1)[0]
        assert "formFromLocation" in capture
        view_assign = state.split("function syncUrlToView", 1)[1].split("function syncViewToUrl", 1)[0]
        assert view_assign.index("state.formSlug = formFromLocation()") < view_assign.index("state.currentView = view")
        app = read_text("frontend/src/App.vue")
        watch = app.split("watch(() => store.state.currentView", 1)[1].split("if (window.innerWidth", 1)[0]
        assert "store.state.isInitialized" in watch

    def test_leaving_a_shared_form_loads_the_feed(self):
        feed = read_text("frontend/src/components/Feed.vue")
        watch = feed.split("watch(() => store.state.formSlug", 1)[1].split("function showProfileActions", 1)[0]
        assert "previous" in watch
        assert "store.state.feed.length === 0" in watch
        assert "fetchFeed(true)" in watch

    def test_shared_form_keeps_exchange_actions_for_registered_viewers(self):
        feed = read_text("frontend/src/components/Feed.vue")
        actions = feed.split("function showProfileActions", 1)[1].split("function profileSlug", 1)[0]
        assert "store.state.formSlug" in actions
        assert "store.state.isRegistered" in actions
        assert "handleContactButtonClick(profile, 'share'" in feed
        assert "handleContactButtonClick(profile, 'exchange'" in feed
        assert "handleContactButtonClick(profile, 'demand'" in feed

    def test_feed_loading_stays_visible_beside_the_own_card(self):
        feed = read_text("frontend/src/components/Feed.vue")
        assert "isFeedLoadingMark" in feed
        fetch = feed.split("async function fetchFeed", 1)[1].split("let lastFilterString", 1)[0]
        assert "const requestId = ++feedRequest" in fetch
        assert "requestId !== feedRequest" in fetch
        assert "requestId === feedRequest" in fetch.split("finally", 1)[1]
        editor = read_text("frontend/src/components/Editor.vue")
        links = editor.split('class="form-links-block"', 1)[1].split('class="profile-details"', 1)[0]
        assert "formActionClass" in links
        assert "bi-hourglass-split spin" in editor

    def test_guest_feed_hides_navigation(self):
        app = read_text("frontend/src/App.vue")
        assert 'v-if="store.state.isRegistered" class="sidebar"' in app
        assert 'v-if="store.state.isRegistered" class="mobile-bottom-nav"' in app
        assert "guest-shell" in app
        mobile = read_text("frontend/css/mobile.css")
        header = css_rule_block(mobile, "#app-container.guest-shell .feed-header")
        assert "env(safe-area-inset-bottom)" in header

    def test_own_card_can_copy_its_form_link(self):
        feed = read_text("frontend/src/components/Feed.vue")
        assert "function profileSlug" in feed
        assert "profile.primary_form" in feed
        assert "function blocksProfileCopy" in feed
        assert "profile.isSelf" in feed
        assert "isGuestJoin && isV2" not in feed
        assert "guest-form-join" in feed
        form_join = feed.split('class="guest-form-join"', 1)[1].split('id="feed-bottom"', 1)[0]
        assert "bi-compass" in form_join
        assert "bi-translate" in form_join
        assert "store.toggleTheme" in form_join
        assert "openGuestLangMenu" in form_join
        guest_card = feed.split('class="guest-join"', 1)[1].split("v-else>", 1)[0]
        assert "bi-translate" in guest_card
        assert "store.toggleTheme" in guest_card
        assert "bi-compass" not in guest_card
        app = read_text("frontend/src/App.vue")
        assert "netlazy:lang-menu" in app
        editor = read_text("frontend/src/components/Editor.vue")
        media = editor.split('class="profile-media-block"', 1)[1].split('class="profile-details"', 1)[0]
        assert "form-links-block" in media
        details = editor.split('class="profile-details"', 1)[1]
        assert "form-links-block" not in details.split("</template>", 1)[0]
        styles = read_text("frontend/css/v2.css")
        assert "profile-media-block .form-links-block" in styles
        assert "margin-top: auto" in styles

    def test_public_contacts_open_as_links(self):
        helper = read_text("frontend/src/utils/contact.js")
        assert "export function contactHref" in helper
        assert "mailto:" in helper
        assert "tel:" in helper
        for rel in ("frontend/src/components/Feed.vue", "frontend/src/components/Inbox.vue"):
            content = read_text(rel)
            assert "contactHref(c)" in content
            assert 'rel="noopener noreferrer"' in content
            assert "contact-link" in content

    def test_feed_uses_public_ids_and_does_not_refetch_on_tag_catalog(self):
        feed = read_text("frontend/src/components/Feed.vue")
        assert ".filter(t => t.state !== 'neutral')" in feed
        assert "receiver_id: profile.id" in feed
        assert "p.id).filter(Boolean)" in feed
        assert "store.state.feed = batch" in feed
        api = read_text("frontend/src/utils/api.js")
        crypto = read_text("frontend/src/utils/crypto.js")
        assert "signReaderPayload" in api
        assert "typeof data === 'string'" in api
        assert "PQDA-READ-v1" in crypto
        state = read_text("frontend/src/store/state.js")
        assert "10000" in state
        feed_router = read_text("presentation/feed_router.py")
        inbox = read_text("presentation/inbox_router.py")
        assert "PublicProfileResponse" in feed_router
        assert "user_ids_for_public_ids" in feed_router
        assert "hide_private" not in feed_router
        assert "get_by_public_id" in inbox
        assert "verify_reader" in inbox
