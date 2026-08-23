import { reactive, watch, computed } from 'vue';
import api, { apiWithPoW } from '../utils/api.js';
import { generateIdentity, clearIdentity, hasHybridKeys, generateUncommittedIdentity, commitIdentityVault } from '../utils/crypto.js';
import { fetchAndDecryptMedia } from '../utils/media.js';
import translations from './translations.js';
import { Preferences } from '@capacitor/preferences';
import { Capacitor } from '@capacitor/core';

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
    
    userId: null,
    currentAnchor: null,

    isSidebarCollapsed: window.innerWidth <= 768,
    workspaceWidth: 500,
    isWorkspaceCollapsed: false,
    isInboxSidebarCollapsed: window.innerWidth <= 768,
    toasts: [],
    tagSearchQuery: '',
    lastProfileEditTimestamp: 0,
    pendingUrlTags: null,
    
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
    lightbox: { open: false, mediaList: [], index: 0, isEditable: false }
};

let instance = null;

export function useStore() {
    if (instance) return instance;

    const state = reactive({ ...defaultState });
    let pollInterval = null;

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

    function syncUrlToView() {
        if (Capacitor.isNativePlatform()) return;
        const path = window.location.pathname;
        let view = 'editor';
        if (isBareAppPath(path)) view = 'editor';
        else if (path.match(/\/feed(\/.*)?$/)) view = 'feed';
        else if (path.match(/\/inbox(\/.*)?$/)) view = 'inbox';
        else if (path.match(/\/privacy(\/.*)?$/)) view = 'vault';
        else if (path.match(/\/profile(\/.*)?$/)) view = 'editor';
        
        state.currentView = view;
        if (state.currentView === 'feed') {
            const params = new URLSearchParams(window.location.search);
            if (params.has('tags')) {
                state.pendingUrlTags = params.get('tags');
                applyPendingUrlTags();
            }
        }
        syncViewToUrl(true);
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
            const activeTags = state.availableSearchTags
                .filter(t => t.state !== 'neutral')
                .map(t => `${encodeURIComponent(t.name)}:${t.state}`)
                .join(',');
            if (activeTags) newUrl += `?tags=${activeTags}`;
        }
        
        if (window.location.pathname + window.location.search !== newUrl) {
            if (replace) window.history.replaceState({ view: state.currentView }, '', newUrl);
            else window.history.pushState({ view: state.currentView }, '', newUrl);
        }
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
        try {
            const { value: raw } = await Preferences.get({ key: STORAGE_KEY });
            if (raw) {
                const parsed = JSON.parse(raw);
                
                ['theme', 'lang', 'isUserFriendlyInterface', 'workspaceWidth', 'isWorkspaceCollapsed', 'isInboxSidebarCollapsed'].forEach(k => {
                    if (parsed[k] !== undefined) state[k] = parsed[k];
                });
                
                ['isRegistered', 'isBanned', 'userId', 'currentAnchor'].forEach(k => {
                    if (parsed[k] !== undefined) state[k] = parsed[k];
                });

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
                }
            } else {
                syncUrlToView();
            }
        } catch (e) {
            console.warn("could not read preferences state:", e);
        } finally {
            if (state.theme === 'light') document.body.classList.add('light-theme');
            else document.body.classList.remove('light-theme');
            
            if (state.isUserFriendlyInterface) document.body.classList.add('uf-mode');
            else document.body.classList.remove('uf-mode');
            
            state.isInitialized = true;
        }
    }

    watch(() => state.isUserFriendlyInterface, (val) => {
        if (val) document.body.classList.add('uf-mode');
        else document.body.classList.remove('uf-mode');
    }, { immediate: true });

    watch(() => [
        state.isRegistered, state.isBanned, state.currentView, state.theme, state.lang, state.isUserFriendlyInterface,
        state.workspaceWidth, state.isWorkspaceCollapsed, state.isInboxSidebarCollapsed,
        state.userId, state.currentAnchor
    ], async () => {
        if (!state.isInitialized) return;
        try {
            const saveObj = {
                isRegistered: state.isRegistered, isBanned: state.isBanned, currentView: state.currentView,
                theme: state.theme, lang: state.lang, isUserFriendlyInterface: state.isUserFriendlyInterface,
                workspaceWidth: state.workspaceWidth,
                isWorkspaceCollapsed: state.isWorkspaceCollapsed, isInboxSidebarCollapsed: state.isInboxSidebarCollapsed,
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
            
            addToast(t('identity_rotated'), "bi-check2-circle");
        } catch (e) {
            startPolling();
            addToast("Failed to rotate identity key", "bi-x-octagon");
            throw e;
        }
    }

    async function logout() {
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

    async function loadDecryptedMedia(mediaItem, mediaId) {
        if (!mediaItem || mediaItem.blobUrl || mediaItem.isUploading) return;
        const res = await fetchAndDecryptMedia(mediaItem.url, mediaId, mediaItem.media_type);
        if (res) {
            mediaItem.blobUrl = res.blobUrl;
            mediaItem.isLegacy = res.isLegacy;
        }
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
                bio: state.myProfile.bio,
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
                    i18n: t.i18n || {}
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

    loadSavedState();

    instance = {
        state, addToast, toggleTheme, cycleLang, t, showConfirm, createAccount, loginWithKey, logout, saveProfile, fetchTags, deleteAccount, rotateKey, fetchInbox, fetchMyProfile, getLocalizedTag, loadDecryptedMedia, syncUrlToView, syncViewToUrl, applyPendingUrlTags, confirmIdentityBackup, cancelIdentityBackup
    };
    return instance;
}