import { reactive, watch, computed } from 'vue';
import api, { apiWithPoW } from '../utils/api.js';
import { generateIdentity, clearIdentity, hasHybridKeys, generateUncommittedIdentity, commitIdentityVault } from '../utils/crypto.js';
import { fetchAndDecryptMedia } from '../utils/media.js';
import translations from './translations.js';
import { normalizeBio } from '../utils/bio.js';
import { Preferences } from '@capacitor/preferences';
import { Capacitor } from '@capacitor/core';
import { syncDevicePush, removeDevicePush, noteIosPushLimit } from '../utils/push.js';
import { startDaylight, pauseDaylight, daylightRunning } from '../utils/daylight.js';

const STORAGE_KEY = 'netlazy_state';

const defaultState = {
    isInitialized: false,
    isRegistered: false,
    isBanned: false,
    authErrorNotified: false,
    currentView: 'editor',
    theme: 'dark',
    lang: 'en',
    
    isUserFriendlyInterface: true,
    pushEnabled: true,
    pushShare: true,
    pushExchange: true,
    pushDemand: true,
    interfaceVersion: '1',
    
    userId: null,
    currentAnchor: null,

    isSidebarCollapsed: window.innerWidth <= 768,
    workspaceWidth: 500,
    isWorkspaceCollapsed: false,
    isInboxSidebarCollapsed: window.innerWidth <= 768,
    inboxFilters: {
        matched: true,
        declined: true,
        share: true,
        exchange: true,
        demand: true
    },
    toasts: [],
    tagSearchQuery: '',
    lastProfileEditTimestamp: 0,
    pendingUrlTags: null,
    formSlug: null,
    
    confirmModal: {
        open: false,
        title: "",
        message: "",
        confirmText: "confirm",
        cancelText: "cancel",
        onConfirm: null,
        isDanger: false
    },

    identityBackup: {
        open: false,
        phrase: '',
        purpose: null
    },
    
    contactSelect: {
        open: false,
        profile: null,
        type: 'share',
        selectedContacts: [],
        message: '',
        isSending: false
    },
    
    isProfileLoading: false,
    isFeedLoading: false,
    isInboxLoading: false,

    myProfile: { bio: "", tags: [], contacts: [], media: [], audio: null, media_id: "" },
    
    availableSearchTags: [],
    feedTagSearch: "",
    feed: [],
    inbox: [],
    inboxChatId: null,
    clearedHandshakeId: null,
    clearedHandshakeTick: 0,
    lightbox: { open: false, mediaList: [], index: 0, isEditable: false }
};

const VALID_VIEWS = ['feed', 'editor', 'inbox', 'vault'];

export function profileHasContent(profile) {
    if (!profile) return false;
    if (String(profile.bio || '').trim()) return true;
    if ((profile.tags || []).some(tag => String(tag || '').trim())) return true;
    if ((profile.media || []).some(item => item && (item.url || item.blobUrl))) return true;
    if (profile.audio && (profile.audio.url || profile.audio.blobUrl)) return true;
    return (profile.contacts || []).some(contact =>
        contact &&
        !contact.is_private &&
        contact.type !== 'unknown' &&
        String(contact.value || '').trim()
    );
}

function labelHits(label, term) {
    const text = String(label || '').toLowerCase();
    if (!text || !term) return false;
    return text.startsWith(term);
}

function tagTextMatches(tag, term) {
    if (labelHits(tag.name, term)) return true;
    if (tag.aliases && tag.aliases.some(alias => labelHits(alias, term))) return true;
    if (tag.i18n && Object.values(tag.i18n).some(value => labelHits(value, term))) return true;
    return false;
}

export function tagsMatchingQuery(tags, query) {
    const tokens = String(query || '').trim().split(/\s+/).filter(Boolean);
    if (!tokens.length) return [];
    const positive = tokens.filter(token => !token.startsWith('-')).map(token => token.toLowerCase());
    const negative = tokens.filter(token => token.startsWith('-') && token.length > 1).map(token => token.slice(1).toLowerCase());
    const pool = tags || [];
    let results = positive.length
        ? pool.filter(tag => positive.some(term => tagTextMatches(tag, term)))
        : pool.slice();
    if (negative.length) {
        results = results.filter(tag => !negative.some(term => tagTextMatches(tag, term)));
    }
    return results;
}

export function isInboxUnread(item) {
    if (!item) return false;
    if (item.status === 'pending' && !item.is_sender) return !item.is_read;
    if (item.status !== 'pending' && item.is_sender) return !item.is_read;
    return false;
}

let instance = null;
let loggingOut = false;
let pushPromptArmed = false;

export function useStore() {
    if (instance) return instance;

    const state = reactive({ ...defaultState });
    let pollInterval = null;
    let followDaylight = typeof window === 'undefined' || window.__NETLAZY_DAYLIGHT__ !== '0';

    function applyInterfaceVersion(value) {
        state.interfaceVersion = String(value) === '2' ? '2' : '1';
        document.body.classList.toggle('ui-v2', state.interfaceVersion === '2');
        document.body.classList.toggle('ui-v1', state.interfaceVersion !== '2');
    }

    async function loadInterfaceVersion() {
        const baked = typeof window !== 'undefined' ? window.__NETLAZY_UI_VERSION__ : '';
        if (baked) applyInterfaceVersion(baked);
        try {
            const root = Capacitor.isNativePlatform()
                ? String(import.meta.env.VITE_API_URL || 'https://nargan-projects.hf.space/netlazy/api').replace(/\/api\/?$/, '')
                : '/netlazy';
            const response = await fetch(`${root}/api/ui`);
            if (response.ok) {
                const data = await response.json();
                applyInterfaceVersion(data.interface_version);
                if (typeof data.daylight_theme === 'boolean') followDaylight = data.daylight_theme;
                return;
            }
        } catch (e) {
            /* keep the version stamped into the page */
        }
        if (!baked) applyInterfaceVersion('1');
    }

    const tagLocalesCache = computed(() => {
        const cache = new Map();
        const lang = state.lang || 'en';
        state.availableSearchTags.forEach(t => {
            cache.set(t.name, (t.i18n && (t.i18n[lang] || t.i18n['en'])) || t.name);
        });
        return cache;
    });

    function startPolling() {
        if (pollInterval) clearInterval(pollInterval);
        pollInterval = setInterval(() => {
            if (state.isRegistered && !state.isBanned) {
                fetchInbox(true);
                if (state.currentView !== 'editor') {
                    fetchMyProfile(true);
                }
                fetchTags();
            }
        }, 10000);
    }

    function isBareAppPath(path) {
        const normalized = (path || '/').replace(/\/+$/, '') || '/';
        return normalized === '/' || normalized === '/netlazy';
    }

    function formFromLocation() {
        const path = window.location.pathname || '';
        if (!/\/feed(\/.*)?$/.test(path)) return null;
        const form = (new URLSearchParams(window.location.search).get('form') || '').trim().toLowerCase();
        return form || null;
    }

    let suppressNextViewHistory = false;

    function syncUrlToView() {
        if (Capacitor.isNativePlatform()) return;
        const path = window.location.pathname;
        if (isBareAppPath(path) && VALID_VIEWS.includes(state.currentView)) {
            syncViewToUrl(true);
            return;
        }
        let view = 'editor';
        if (isBareAppPath(path)) view = 'editor';
        else if (path.match(/\/feed(\/.*)?$/)) view = 'feed';
        else if (path.match(/\/inbox(\/.*)?$/)) view = 'inbox';
        else if (path.match(/\/privacy(\/.*)?$/)) view = 'vault';
        else if (path.match(/\/profile(\/.*)?$/)) view = 'editor';

        if (view === 'feed') {
            const params = new URLSearchParams(window.location.search);
            if (params.has('tags')) {
                state.pendingUrlTags = params.get('tags');
                applyPendingUrlTags();
            } else if (!formFromLocation()) {
                clearFeedFilters();
            }
            state.formSlug = formFromLocation();
        } else {
            state.formSlug = null;
        }
        if (state.currentView !== view) suppressNextViewHistory = true;
        state.currentView = view;
        syncViewToUrl(true);
    }

    function consumeViewHistorySuppression() {
        const suppressed = suppressNextViewHistory;
        suppressNextViewHistory = false;
        return suppressed;
    }

    function syncViewToUrl(replace = false) {
        if (Capacitor.isNativePlatform()) return;
        const viewMap = { feed: 'feed', editor: 'profile', inbox: 'inbox', vault: 'privacy' };
        const segments = window.location.pathname.split('/');
        if (segments[segments.length - 1] === '') segments.pop();
        
        while (segments.length > 0 && ['feed', 'profile', 'inbox', 'privacy', 'config', 'welcome'].includes(segments[segments.length - 1])) {
            segments.pop();
        }
        
        let newUrl = segments.join('/') + '/' + (viewMap[state.currentView] || 'profile');
        if (state.currentView === 'feed') {
            const parts = [];
            if (state.formSlug) parts.push(`form=${encodeURIComponent(state.formSlug)}`);
            const activeTags = state.availableSearchTags
                .filter(t => t.state !== 'neutral')
                .map(t => `${encodeURIComponent(t.name)}:${t.state}`)
                .join(',');
            if (activeTags) parts.push(`tags=${activeTags}`);
            if (parts.length) newUrl += `?${parts.join('&')}`;
        }
        
        if (window.location.pathname + window.location.search !== newUrl) {
            if (replace) window.history.replaceState({ view: state.currentView }, '', newUrl);
            else window.history.pushState({ view: state.currentView }, '', newUrl);
        }
    }

    function clearFeedFilters() {
        state.pendingUrlTags = null;
        state.availableSearchTags.forEach(tag => {
            if (tag.state !== 'neutral') tag.state = 'neutral';
        });
    }

    function applyPendingUrlTags() {
        if (!state.pendingUrlTags || state.availableSearchTags.length === 0) return;
        const tagPairs = state.pendingUrlTags.split(',');
        const validStates = ['require', 'exclude', 'bonus', 'abonus'];
        
        state.availableSearchTags.forEach(t => t.state = 'neutral');
        tagPairs.forEach(pair => {
            const [rawName, tState] = pair.split(':');
            if (rawName && tState && validStates.includes(tState)) {
                const decodedName = decodeURIComponent(rawName);
                const tagObj = state.availableSearchTags.find(t => t.name === decodedName);
                if (tagObj) tagObj.state = tState;
            }
        });
        state.pendingUrlTags = null;
    }

    async function loadSavedState() {
        await loadInterfaceVersion();
        if (!Capacitor.isNativePlatform()) {
            const form = formFromLocation();
            if (form) state.formSlug = form;
        }
        try {
            const { value: raw } = await Preferences.get({ key: STORAGE_KEY });
            if (raw) {
                const parsed = JSON.parse(raw);
                
                ['theme', 'lang', 'isUserFriendlyInterface', 'pushEnabled', 'pushShare', 'pushExchange', 'pushDemand', 'workspaceWidth', 'isWorkspaceCollapsed', 'isInboxSidebarCollapsed'].forEach(k => {
                    if (parsed[k] !== undefined) state[k] = parsed[k];
                });
                if (parsed.inboxFilters && typeof parsed.inboxFilters === 'object') {
                    ['matched', 'declined', 'share', 'exchange', 'demand'].forEach(k => {
                        if (typeof parsed.inboxFilters[k] === 'boolean') state.inboxFilters[k] = parsed.inboxFilters[k];
                    });
                }
                
                ['isRegistered', 'isBanned', 'userId', 'currentAnchor'].forEach(k => {
                    if (parsed[k] !== undefined) state[k] = parsed[k];
                });

                if (parsed.currentView && VALID_VIEWS.includes(parsed.currentView)) {
                    state.currentView = parsed.currentView;
                }

                const vaultReady = await hasHybridKeys();
                if (parsed.isRegistered && !vaultReady) {
                    state.isRegistered = false; 
                }

                syncUrlToView();

                if (state.isRegistered && !state.isBanned) {
                    fetchTags(); 
                    fetchMyProfile();
                    fetchInbox();
                    startPolling();
                } else if (!state.isBanned && state.currentView === 'feed') {
                    fetchTags();
                }
            } else {
                syncUrlToView();
                if (!state.isBanned && state.currentView === 'feed') fetchTags();
            }
        } catch (e) {
            console.warn("could not read preferences state:", e);
        } finally {
            if (state.theme === 'light') document.body.classList.add('light-theme');
            else document.body.classList.remove('light-theme');
            
            if (state.isUserFriendlyInterface) document.body.classList.add('uf-mode');
            else document.body.classList.remove('uf-mode');
            
            state.isInitialized = true;
            if (followDaylight) {
                startDaylight({
                    onLight(light) {
                        state.theme = light ? 'light' : 'dark';
                    },
                });
            }
            if (state.isRegistered && !state.isBanned) loadPushPreferences();
        }
    }

    watch(() => state.isUserFriendlyInterface, (val) => {
        if (val) document.body.classList.add('uf-mode');
        else document.body.classList.remove('uf-mode');
    }, { immediate: true });

    watch(() => state.lang, () => {
        if (!state.isInitialized || !state.isRegistered || !state.pushEnabled) return;
        persistPushPreferences().catch(() => {});
        const native = Capacitor.getPlatform() === 'android';
        const granted = native || (typeof Notification !== 'undefined' && Notification.permission === 'granted');
        if (granted) syncDevicePush().catch(() => {});
    });

    watch(() => [
        state.isRegistered, state.isBanned, state.currentView, state.theme, state.lang, state.isUserFriendlyInterface,
        state.pushEnabled, state.pushShare, state.pushExchange, state.pushDemand,
        state.workspaceWidth, state.isWorkspaceCollapsed, state.isInboxSidebarCollapsed, state.inboxFilters,
        state.userId, state.currentAnchor
    ], async () => {
        if (!state.isInitialized) return;
        try {
            const saveObj = {
                isRegistered: state.isRegistered, isBanned: state.isBanned, currentView: state.currentView,
                theme: state.theme, lang: state.lang, isUserFriendlyInterface: state.isUserFriendlyInterface,
                pushEnabled: state.pushEnabled, pushShare: state.pushShare,
                pushExchange: state.pushExchange, pushDemand: state.pushDemand,
                workspaceWidth: state.workspaceWidth,
                isWorkspaceCollapsed: state.isWorkspaceCollapsed, isInboxSidebarCollapsed: state.isInboxSidebarCollapsed,
                inboxFilters: state.inboxFilters,
                userId: state.userId, currentAnchor: state.currentAnchor
            };
            await Preferences.set({ key: STORAGE_KEY, value: JSON.stringify(saveObj) });
        } catch (e) {}
    }, { deep: true });

    let toastId = 0;
    function addToast(msg, icon = 'bi-info-circle', type = 'minimal') {
        const id = toastId++;
        state.toasts.push({ id, msg, icon, type: 'minimal' });
        setTimeout(() => {
            const idx = state.toasts.findIndex(t => t.id === id);
            if (idx !== -1) state.toasts.splice(idx, 1);
        }, 3000);
    }

    function toggleTheme() {
        if (daylightRunning()) {
            pauseDaylight();
            const light = document.body.classList.contains('light-theme');
            state.theme = light ? 'dark' : 'light';
            document.body.classList.toggle('light-theme', state.theme === 'light');
            return;
        }
        state.theme = state.theme === 'dark' ? 'light' : 'dark';
        document.body.classList.toggle('light-theme', state.theme === 'light');
    }

    function cycleLang() {
        document.body.classList.add('is-translating');
        setTimeout(() => {
            const langs = ['en', 'ru', 'pt', 'zh', 'ja', 'ko'];
            const currentIdx = langs.indexOf(state.lang);
            state.lang = langs[(currentIdx + 1) % langs.length];
            setTimeout(() => document.body.classList.remove('is-translating'), 50);
        }, 150);
    }

    function t(key, replacements = {}) {
        const lang = state.lang || 'en';
        let txt = (translations[lang] && translations[lang][key]) || (translations['en'] && translations['en'][key]) || key;
        for (const [k, v] of Object.entries(replacements)) {
            txt = txt.replace(`{${k}}`, v);
        }
        return txt;
    }

    function getLocalizedTag(tagName) {
        return tagLocalesCache.value.get(tagName) || tagName;
    }

    function tagTip(tagOrName) {
        const tag = typeof tagOrName === 'string'
            ? state.availableSearchTags.find(item => item.name === tagOrName)
            : tagOrName;
        if (!tag || !tag.desc) return '';
        const lang = state.lang || 'en';
        return tag.desc[lang] || tag.desc.en || '';
    }

    function showConfirm(title, message, onConfirm, isDanger = false, confirmText = "confirm", cancelText = "cancel") {
        state.confirmModal.title = title;
        state.confirmModal.message = message;
        state.confirmModal.confirmText = confirmText;
        state.confirmModal.cancelText = cancelText;
        state.confirmModal.isDanger = isDanger;
        state.confirmModal.onConfirm = () => {
            onConfirm();
            state.confirmModal.open = false;
        };
        state.confirmModal.open = true;
    }

    let backupResolver = null;

    function requestIdentityBackupConfirmation(phrase, purpose) {
        return new Promise((resolve, reject) => {
            state.identityBackup.phrase = phrase;
            state.identityBackup.purpose = purpose;
            state.identityBackup.open = true;
            backupResolver = { resolve, reject };
        });
    }

    function confirmIdentityBackup() {
        if (backupResolver) {
            backupResolver.resolve();
            backupResolver = null;
        }
        state.identityBackup = { open: false, phrase: '', purpose: null };
    }

    function cancelIdentityBackup() {
        if (backupResolver) {
            backupResolver.reject(new Error("Identity backup not confirmed"));
            backupResolver = null;
        }
        state.identityBackup = { open: false, phrase: '', purpose: null };
    }

    async function createAccount() {
        addToast("Generating Hardware-Bound Identity...", "bi-hourglass-split");
        try {
            const keys = await generateIdentity();

            try {
                await requestIdentityBackupConfirmation(keys.secretKey, 'register');
            } catch (e) {
                await clearIdentity();
                addToast(t('backup_not_confirmed'), "bi-exclamation-triangle");
                return;
            }

            const res = await apiWithPoW('post', '/auth/register', { 
                ed25519_public_pem: keys.edPubPem,
                mldsa_public_hex: keys.mldsaPubHex
            });
            
            state.userId = keys.userId;
            state.currentAnchor = res.data.genesis_anchor;
            state.isRegistered = true;
            state.currentView = 'vault';
            
            fetchTags();
            fetchMyProfile();
            fetchInbox();
            startPolling();
            loadPushPreferences();
            
            addToast(t('new_identity_loaded'), "bi-person-plus");
        } catch (e) {
            const detail = e.response?.data?.detail;
            if (e.response?.status === 503) {
                addToast("Service temporarily unavailable. Please try again shortly.", "bi-exclamation-triangle");
            } else if (detail) {
                addToast(`Registration failed: ${detail}`, "bi-exclamation-octagon");
            } else {
                addToast("Failed to create account.", "bi-exclamation-octagon");
            }
        }
    }

    async function loginWithKey(secretKey) {
        addToast("Restoring identity...", "bi-hourglass-split");
        try {
            const { importIdentityFromKey } = await import('../utils/crypto.js');
            const keys = await importIdentityFromKey(secretKey);

            state.userId = keys.userId;
            
            const anchorRes = await api.get('/auth/anchor');
            state.currentAnchor = anchorRes.data.current_anchor;
            state.isRegistered = true;
            state.currentView = 'feed';
            
            fetchTags();
            fetchMyProfile();
            fetchInbox();
            startPolling();
            loadPushPreferences();
            
            addToast(t('key_imported'), "bi-person-plus");
        } catch (e) {
            await clearIdentity();
            state.userId = null;
            state.currentAnchor = null;
            state.isRegistered = false;
            const detail = e.response?.data?.detail;
            if (detail === "Unknown user") {
                addToast("Account not found for this key.", "bi-x-octagon");
            } else if (detail) {
                addToast(`Login failed: ${detail}`, "bi-exclamation-octagon");
            } else {
                addToast(e.message || "Invalid secret key.", "bi-x-octagon");
            }
        }
    }

    async function rotateKey() {
        if (pollInterval) clearInterval(pollInterval);
        try {
            const identity = await generateUncommittedIdentity();

            try {
                await requestIdentityBackupConfirmation(identity.secretKey, 'rotate');
            } catch (e) {
                startPolling();
                return;
            }

            // Resync current anchor immediately before rotate to guarantee fresh chain continuity
            try {
                const anchorRes = await api.get('/auth/anchor');
                state.currentAnchor = anchorRes.data.current_anchor;
            } catch (anchorErr) {}

            const res = await api.post('/auth/rotate', { 
                new_ed25519_public_pem: identity.edPubPem,
                new_mldsa_public_hex: identity.mldsaPubHex
            });
            
            await commitIdentityVault(identity.vault);

            state.userId = res.data.new_user_id;
            state.currentAnchor = res.data.new_anchor;
            
            startPolling();
            fetchMyProfile();
            fetchInbox();
            persistPushPreferences().catch(() => {});
            syncDevicePush().catch(() => {});
            
            addToast(t('identity_rotated'), "bi-check2-circle");
        } catch (e) {
            startPolling();
            addToast("Failed to rotate identity key", "bi-x-octagon");
            throw e;
        }
    }

    async function logout() {
        if (loggingOut) return;
        loggingOut = true;
        try {
            await removeDevicePush();
            state.isRegistered = false;
            state.isBanned = false;
            state.authErrorNotified = false;
            state.userId = null;
            state.currentAnchor = null;
            state.myProfile = { ...defaultState.myProfile };
            state.inbox = [];
            state.feed = [];
            await clearIdentity();
            if (pollInterval) clearInterval(pollInterval);
        } finally {
            loggingOut = false;
        }
    }

    function deleteAccount() {
        showConfirm(
            t('confirm_delete_title'),
            t('confirm_delete_desc'),
            async () => {
                try {
                    await api.delete('/auth/account');
                    logout();
                    addToast(t('profile_destroyed'), "bi-trash3");
                } catch (e) {
                    addToast("Failed to delete account", "bi-x-circle");
                }
            },
            true,
            t('destroy_profile_btn'),
            t('cancel')
        );
    }

    async function loadDecryptedMedia(mediaItem, keyMaterial, rawKey = false) {
        if (!mediaItem || mediaItem.blobUrl || mediaItem.isUploading || !keyMaterial) return;
        const res = await fetchAndDecryptMedia(mediaItem.url, keyMaterial, mediaItem.media_type, rawKey);
        if (res) {
            mediaItem.blobUrl = res.blobUrl;
            mediaItem.isLegacy = res.isLegacy;
        }
    }

    async function loadProfileMedia(mediaItem, profile) {
        if (!profile) return;
        if (profile.media_key) return loadDecryptedMedia(mediaItem, profile.media_key, true);
        if (profile.media_id) return loadDecryptedMedia(mediaItem, profile.media_id, false);
    }

    async function fetchMyProfile(isSilent = false) {
        if (!isSilent) state.isProfileLoading = true;
        try {
            const res = await api.get('/profile/me');
            const data = res.data;
            const currentContacts = state.myProfile.contacts || [];
            
            data.contacts.forEach(c => {
                const existing = currentContacts.find(oc => oc.type === c.type && oc.value === c.value);
                c._id = existing ? existing._id : (c.type + ':' + c.value);
            });
            
            const currentMedia = state.myProfile.media || [];
            data.media = data.media.map(m => { 
                const old = currentMedia.find(om => om.url === m.url);
                return old && (old.isUploading || old.isDeleting) ? old : { ...m, isLoaded: old ? old.isLoaded : false, isUploading: false, uploadProgress: 0, blobUrl: old ? old.blobUrl : null, isLegacy: old ? old.isLegacy : false };
            });
            const uploadingMedia = currentMedia.filter(m => m.isUploading);
            data.media.push(...uploadingMedia);

            if (data.audio) { 
                const oldA = state.myProfile.audio;
                data.audio = (oldA && (oldA.isUploading || oldA.isDeleting)) ? oldA : { ...data.audio, isLoaded: oldA ? oldA.isLoaded : false, isUploading: false, uploadProgress: 0, blobUrl: oldA ? oldA.blobUrl : null, isLegacy: oldA ? oldA.isLegacy : false };
            } else if (state.myProfile.audio && state.myProfile.audio.isUploading) {
                data.audio = state.myProfile.audio;
            }

            data.forms = data.forms || [];
            if (!data.form) {
                data.form = data.primary_form && data.forms.includes(data.primary_form)
                    ? data.primary_form
                    : (data.forms[data.forms.length - 1] || null);
            }
            state.myProfile = data;
            
        } catch (e) {
            if (e.response?.status === 401 && e.response?.data?.detail === "Unknown user") {
                await logout();
            }
        } finally {
            if (!isSilent) state.isProfileLoading = false;
        }
    }

    async function saveProfile() {
        try {
            const payload = {
                bio: normalizeBio(state.myProfile.bio),
                tags: state.myProfile.tags,
                contacts: state.myProfile.contacts.filter(c => c.value.trim() !== "" && c.type !== 'unknown')
            };
            const res = await api.put('/profile/me', payload);
            const data = res.data;
            
            const currentMedia = state.myProfile.media || [];
            data.media = data.media.map(m => { 
                const old = currentMedia.find(om => om.url === m.url);
                return old && (old.isUploading || old.isDeleting) ? old : { ...m, isLoaded: old ? old.isLoaded : false, isUploading: false, uploadProgress: 0, blobUrl: old ? old.blobUrl : null, isLegacy: old ? old.isLegacy : false };
            });
            const uploadingMedia = currentMedia.filter(m => m.isUploading);
            data.media.push(...uploadingMedia);

            if (data.audio) { 
                const oldA = state.myProfile.audio;
                data.audio = (oldA && (oldA.isUploading || oldA.isDeleting)) ? oldA : { ...data.audio, isLoaded: oldA ? oldA.isLoaded : false, isUploading: false, uploadProgress: 0, blobUrl: oldA ? oldA.blobUrl : null, isLegacy: oldA ? oldA.isLegacy : false };
            } else if (state.myProfile.audio && state.myProfile.audio.isUploading) {
                data.audio = state.myProfile.audio;
            }

            state.myProfile.media = data.media;
            state.myProfile.audio = data.audio;

            addToast(t('vault_synced'), "bi-cloud-check", "minimal");
        } catch (e) {
            addToast("Sync failed", "bi-x-circle");
        }
    }

    async function fetchTags() {
        try {
            const res = await api.get('/tags/search');
            const oldTags = state.availableSearchTags;
            const oldTagsMap = new Map();
            for (let i = 0; i < oldTags.length; i++) {
                oldTagsMap.set(oldTags[i].name, oldTags[i]);
            }
            
            state.availableSearchTags = res.data.map(t => {
                const oldT = oldTagsMap.get(t.name);
                return { 
                    name: t.name, 
                    aliases: t.aliases || [], 
                    hidden: t.hidden, 
                    state: oldT ? oldT.state : 'neutral',
                    pendingState: oldT ? oldT.pendingState : undefined,
                    i18n: t.i18n || {},
                    desc: t.desc || {}
                };
            });
            applyPendingUrlTags();
        } catch (e) {}
    }

    async function fetchInbox(isSilent = false) {
        if (!isSilent) state.isInboxLoading = true;
        try {
            const res = await api.get('/inbox');
            const oldInbox = state.inbox || [];
            const oldInboxMap = new Map();
            for (let i = 0; i < oldInbox.length; i++) {
                oldInboxMap.set(oldInbox[i].id, oldInbox[i]);
            }
            
            state.inbox = res.data.map(r => {
                const oldR = oldInboxMap.get(r.id);
                if (r.profile && r.profile.media) {
                    r.profile.media.forEach(m => {
                        const oldM = oldR?.profile?.media?.find(om => om.url === m.url);
                        m.isLoaded = oldM ? oldM.isLoaded : false;
                        if (oldM && oldM.blobUrl) m.blobUrl = oldM.blobUrl;
                        if (oldM && oldM.isLegacy !== undefined) m.isLegacy = oldM.isLegacy;
                    });
                }
                if (r.profile && r.profile.audio) {
                    const oldA = oldR?.profile?.audio;
                    r.profile.audio.isLoaded = oldA ? oldA.isLoaded : false;
                    if (oldA && oldA.blobUrl) r.profile.audio.blobUrl = oldA.blobUrl;
                    if (oldA && oldA.isLegacy !== undefined) r.profile.audio.isLegacy = oldA.isLegacy;
                }
                return {
                    ...r, 
                    is_read: r.is_read,
                    selectedContacts: oldR ? oldR.selectedContacts : [], 
                    openDropdown: oldR ? oldR.openDropdown : false, 
                    resolving: oldR ? oldR.resolving : false, 
                    isErrorDeleted: oldR ? oldR.isErrorDeleted : false,
                    isDeletingMatch: oldR ? oldR.isDeletingMatch : false
                };
            });
        } catch (e) {} finally {
            if (!isSilent) state.isInboxLoading = false;
        }
    }

    function profileFormUrl(slug) {
        let root;
        if (Capacitor.isNativePlatform()) {
            root = String(import.meta.env.VITE_API_URL || 'https://nargan-projects.hf.space/netlazy/api').replace(/\/api\/?$/, '');
        } else {
            const segments = window.location.pathname.split('/');
            if (segments[segments.length - 1] === '') segments.pop();
            while (segments.length > 0 && ['feed', 'profile', 'inbox', 'privacy', 'config', 'welcome'].includes(segments[segments.length - 1])) {
                segments.pop();
            }
            root = window.location.origin + segments.join('/');
        }
        return `${root}/feed?form=${encodeURIComponent(slug)}`;
    }

    async function persistPushPreferences() {
        if (!state.isRegistered) return;
        await api.put('/push/preferences', {
            enabled: state.pushEnabled,
            share: state.pushShare,
            exchange: state.pushExchange,
            demand: state.pushDemand,
            lang: state.lang,
        });
    }

    async function loadPushPreferences() {
        if (!state.isRegistered || state.isBanned) return;
        try {
            const res = await api.get('/push/preferences');
            const data = res.data || {};
            if (typeof data.enabled === 'boolean') state.pushEnabled = data.enabled;
            if (typeof data.share === 'boolean') state.pushShare = data.share;
            if (typeof data.exchange === 'boolean') state.pushExchange = data.exchange;
            if (typeof data.demand === 'boolean') state.pushDemand = data.demand;
        } catch (e) {}
        if (state.pushEnabled) armPushDelivery();
    }

    function armPushDelivery() {
        if (!state.pushEnabled || !state.isRegistered) return;
        if (Capacitor.getPlatform() === 'android') {
            if (import.meta.env.VITE_FCM_ENABLED === 'true') syncDevicePush().catch(() => {});
            return;
        }
        if (noteIosPushLimit()) return;
        if (typeof Notification === 'undefined' || !('serviceWorker' in navigator) || !('PushManager' in window)) return;
        const reportPush = () => addToast(t('push_unavailable'), 'bi-bell-slash');
        if (Notification.permission === 'granted') {
            syncDevicePush().catch(reportPush);
            return;
        }
        if (Notification.permission !== 'default' || pushPromptArmed) return;
        pushPromptArmed = true;
        const once = () => {
            document.removeEventListener('click', once, true);
            pushPromptArmed = false;
            if (state.pushEnabled && state.isRegistered) syncDevicePush().catch(reportPush);
        };
        document.addEventListener('click', once, true);
    }

    async function togglePushEnabled() {
        const previous = state.pushEnabled;
        state.pushEnabled = !state.pushEnabled;
        try {
            await persistPushPreferences();
        } catch (e) {
            state.pushEnabled = previous;
            addToast(t('push_sync_failed'), 'bi-exclamation-triangle');
            return;
        }
        if (state.pushEnabled) {
            try {
                await syncDevicePush();
            } catch (e) {
                addToast(t('push_sync_failed'), 'bi-exclamation-triangle');
            }
        }
    }

    async function togglePushKind(kind) {
        const key = kind === 'share' ? 'pushShare' : kind === 'exchange' ? 'pushExchange' : kind === 'demand' ? 'pushDemand' : '';
        if (!key || !state.pushEnabled) return;
        const previous = state[key];
        state[key] = !state[key];
        try {
            await persistPushPreferences();
        } catch (e) {
            state[key] = previous;
            addToast(t('push_sync_failed'), 'bi-exclamation-triangle');
        }
    }

    function clearOutgoingMark(profileId) {
        if (!profileId) return;
        const stillOutgoing = state.inbox.some(item => item.is_sender && item.profile && item.profile.id === profileId);
        if (stillOutgoing) return;
        state.feed.forEach(card => {
            if (card && card.id === profileId) {
                card.sent = false;
                card.sentType = null;
            }
        });
        state.clearedHandshakeId = profileId;
        state.clearedHandshakeTick += 1;
    }

    function openFeed() {
        state.formSlug = null;
        if (state.currentView !== 'feed') {
            state.currentView = 'feed';
            return;
        }
        syncViewToUrl();
    }

    loadSavedState();

    instance = {
        state, addToast, toggleTheme, cycleLang, t, showConfirm, createAccount, loginWithKey, logout, saveProfile, fetchTags, deleteAccount, rotateKey, fetchInbox, fetchMyProfile, getLocalizedTag, tagTip, loadDecryptedMedia, loadProfileMedia, syncUrlToView, syncViewToUrl, consumeViewHistorySuppression, applyPendingUrlTags, confirmIdentityBackup, cancelIdentityBackup, profileFormUrl, openFeed, togglePushEnabled, togglePushKind, clearOutgoingMark
    };
    return instance;
}