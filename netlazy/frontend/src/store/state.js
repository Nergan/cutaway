import { reactive, watch } from 'vue';
import api, { apiWithPoW } from '../utils/api.js';
import { generateIdentity, loadPrivateKey } from '../utils/crypto.js';
import { getRestoredAudioBlobUrl } from '../utils/media.js';
import translations from './translations.js';

const STORAGE_KEY = 'netlazy_state';

const defaultState = {
    isRegistered: false,
    isBanned: false,
    currentView: 'editor',
    theme: 'dark',
    lang: 'en',
    
    userId: null,
    privateKeyPem: null,
    publicKeyPem: null,
    keyPair: null, 

    isSidebarCollapsed: window.innerWidth <= 768,
    sidebarWidth: 220,
    workspaceWidth: 500,
    isWorkspaceCollapsed: false,
    inboxSplit: 50,
    toasts: [],
    tagSearchQuery: '',
    
    confirmModal: {
        open: false,
        title: "",
        message: "",
        confirmText: "confirm",
        cancelText: "cancel",
        onConfirm: null,
        isDanger: false
    },
    
    contactSelect: {
        open: false,
        profile: null,
        type: 'share',
        selectedContacts: [],
        isSending: false
    },
    
    isProfileLoading: false,
    isFeedLoading: false,
    isInboxLoading: false,

    myProfile: {
        bio: "",
        tags: [],
        contacts: [],
        media: [],
        audio: null
    },
    
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

    function startPolling() {
        if (pollInterval) clearInterval(pollInterval);
        pollInterval = setInterval(() => {
            if (state.isRegistered && !state.isBanned) {
                fetchInbox(true);
                fetchMyProfile(true);
            }
        }, 10000);
    }

    async function loadSavedState() {
        try {
            const raw = localStorage.getItem(STORAGE_KEY);
            if (raw) {
                const parsed = JSON.parse(raw);
                
                ['theme', 'lang', 'sidebarWidth', 'workspaceWidth', 'isWorkspaceCollapsed', 'inboxSplit'].forEach(k => {
                    if (parsed[k] !== undefined) state[k] = parsed[k];
                });

                if (parsed.isRegistered && parsed.privateKeyPem) {
                    try {
                        const keys = await loadPrivateKey(parsed.privateKeyPem);
                        state.keyPair = keys.keyPair;
                        
                        ['isRegistered', 'isBanned', 'currentView', 'userId', 'privateKeyPem', 'publicKeyPem'].forEach(k => {
                            if (parsed[k] !== undefined) state[k] = parsed[k];
                        });
                        
                        if (!state.isBanned) {
                            fetchTags(); 
                            fetchMyProfile();
                            fetchInbox();
                            startPolling();
                        }
                    } catch (keyErr) {
                        console.warn("Failed to load private key, logging out:", keyErr);
                        state.isRegistered = false;
                        state.isBanned = false;
                        state.privateKeyPem = null;
                        state.publicKeyPem = null;
                        state.userId = null;
                    }
                } else {
                    ['isRegistered', 'isBanned', 'currentView', 'userId', 'privateKeyPem', 'publicKeyPem'].forEach(k => {
                        if (parsed[k] !== undefined) state[k] = parsed[k];
                    });
                }
            }
        } catch (e) {
            console.warn("could not read local storage state:", e);
        }
    }

    watch(() => [
        state.isRegistered, state.isBanned, state.currentView, state.theme, state.lang,
        state.sidebarWidth, state.workspaceWidth, state.isWorkspaceCollapsed, state.inboxSplit,
        state.userId, state.privateKeyPem, state.publicKeyPem
    ], () => {
        try {
            const saveObj = {
                isRegistered: state.isRegistered, isBanned: state.isBanned, currentView: state.currentView,
                theme: state.theme, lang: state.lang,
                sidebarWidth: state.sidebarWidth, workspaceWidth: state.workspaceWidth,
                isWorkspaceCollapsed: state.isWorkspaceCollapsed, inboxSplit: state.inboxSplit,
                userId: state.userId, privateKeyPem: state.privateKeyPem, publicKeyPem: state.publicKeyPem
            };
            localStorage.setItem(STORAGE_KEY, JSON.stringify(saveObj));
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
        // Trigger a global blur/fade via a CSS class on the body to mask the text swap
        document.body.classList.add('is-translating');
        
        setTimeout(() => {
            const langs = ['en', 'ru', 'pt', 'zh', 'ja', 'ko'];
            const currentIdx = langs.indexOf(state.lang);
            state.lang = langs[(currentIdx + 1) % langs.length];
            
            setTimeout(() => {
                document.body.classList.remove('is-translating');
            }, 50);
        }, 150); // wait for fade out
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
        const tagObj = state.availableSearchTags.find(t => t.name === tagName);
        if (tagObj && tagObj.i18n) {
            return tagObj.i18n[state.lang] || tagObj.i18n['en'] || tagName;
        }
        return tagName;
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

    async function createAccount() {
        addToast("Generating Identity... Solving PoW...", "bi-hourglass-split");
        try {
            const keys = await generateIdentity();
            await apiWithPoW('post', '/auth/register', { public_key: keys.publicKeyPem });
            
            state.privateKeyPem = keys.privateKeyPem;
            state.publicKeyPem = keys.publicKeyPem;
            state.userId = keys.userId;
            state.keyPair = keys.keyPair;
            state.isRegistered = true;
            state.currentView = 'vault';
            
            fetchTags();
            fetchMyProfile();
            fetchInbox();
            startPolling();
            
            addToast(t('new_identity_loaded'), "bi-person-plus");
        } catch (e) {
            addToast("Failed to create account.", "bi-exclamation-octagon");
        }
    }

    async function loginWithKey(rawPrivateKey) {
        try {
            const keys = await loadPrivateKey(rawPrivateKey);
            state.privateKeyPem = keys.privateKeyPem;
            state.publicKeyPem = keys.publicKeyPem;
            state.userId = keys.userId;
            state.keyPair = keys.keyPair;
            state.isRegistered = true;
            
            fetchTags();
            fetchMyProfile();
            fetchInbox();
            startPolling();
            addToast(t('key_imported'), "bi-shield-check");
        } catch (e) {
            addToast("Invalid Private Key format.", "bi-exclamation-triangle");
        }
    }

    async function rotateKey() {
        try {
            const keys = await generateIdentity();
            const res = await api.post('/auth/rotate', { new_public_key: keys.publicKeyPem });
            
            state.privateKeyPem = keys.privateKeyPem;
            state.publicKeyPem = keys.publicKeyPem;
            state.userId = res.data.new_user_id;
            state.keyPair = keys.keyPair;
            
            fetchMyProfile();
            fetchInbox();
            
            addToast(t('identity_rotated'), "bi-check2-circle");
        } catch (e) {
            addToast("Failed to rotate identity key", "bi-x-octagon");
            throw e;
        }
    }

    function logout() {
        state.isRegistered = false;
        state.isBanned = false;
        state.userId = null;
        state.privateKeyPem = null;
        state.publicKeyPem = null;
        state.keyPair = null;
        state.myProfile = { ...defaultState.myProfile };
        state.inbox = [];
        state.feed = [];
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

    async function fetchMyProfile(isSilent = false) {
        if (!isSilent) state.isProfileLoading = true;
        try {
            const res = await api.get('/profile/me');
            const data = res.data;
            data.contacts.forEach(c => c._id = Math.random().toString());
            
            const currentMedia = state.myProfile.media || [];
            data.media = data.media.map(m => { 
                const old = currentMedia.find(om => om.url === m.url);
                return old && (old.isUploading || old.isDeleting) ? old : { ...m, isLoaded: old ? old.isLoaded : false, isUploading: false, uploadProgress: 0 };
            });
            const uploadingMedia = currentMedia.filter(m => m.isUploading);
            data.media.push(...uploadingMedia);

            if (data.audio) { 
                const oldA = state.myProfile.audio;
                data.audio = (oldA && (oldA.isUploading || oldA.isDeleting)) ? oldA : { ...data.audio, isLoaded: oldA ? oldA.isLoaded : false, isUploading: false, uploadProgress: 0 };
                
                if (!data.audio.isLoaded && !data.audio.blobUrl) {
                    getRestoredAudioBlobUrl(data.audio.url).then(bUrl => {
                        if (bUrl === null) api.delete('/profile/me/audio').catch(()=>{}); 
                        else if (bUrl && state.myProfile.audio) {
                            state.myProfile.audio.blobUrl = bUrl;
                            state.myProfile.audio.isLoaded = true;
                        }
                    });
                }
            } else if (state.myProfile.audio && state.myProfile.audio.isUploading) {
                data.audio = state.myProfile.audio;
            }

            state.myProfile = data;
        } catch (e) {
            console.error("Profile sync failed");
        } finally {
            if (!isSilent) state.isProfileLoading = false;
        }
    }

    async function saveProfile() {
        try {
            const payload = {
                bio: state.myProfile.bio,
                tags: state.myProfile.tags,
                contacts: state.myProfile.contacts.filter(c => c.value.trim() !== "")
            };
            await api.put('/profile/me', payload);
            addToast(t('vault_synced'), "bi-cloud-check", "minimal");
        } catch (e) {
            addToast("Sync failed", "bi-x-circle");
        }
    }

    async function fetchTags() {
        try {
            const res = await api.get('/tags/search');
            state.availableSearchTags = res.data.map(t => ({ 
                name: t.name, 
                aliases: t.aliases || [], 
                hidden: t.hidden, 
                state: 'neutral',
                i18n: t.i18n || {}
            }));
        } catch (e) {}
    }

    async function fetchInbox(isSilent = false) {
        if (!isSilent) state.isInboxLoading = true;
        try {
            const res = await api.get('/inbox');
            const oldInbox = state.inbox || [];
            
            state.inbox = res.data.map(r => {
                const oldR = oldInbox.find(old => old.id === r.id);
                if (r.profile && r.profile.media) {
                    r.profile.media.forEach(m => {
                        const oldM = oldR?.profile?.media?.find(om => om.url === m.url);
                        m.isLoaded = oldM ? oldM.isLoaded : false;
                    });
                }
                if (r.profile && r.profile.audio) {
                    const oldA = oldR?.profile?.audio;
                    r.profile.audio.isLoaded = oldA ? oldA.isLoaded : false;
                    if (oldA && oldA.blobUrl) r.profile.audio.blobUrl = oldA.blobUrl;
                    
                    if (!r.profile.audio.isLoaded && !r.profile.audio.blobUrl) {
                        getRestoredAudioBlobUrl(r.profile.audio.url).then(bUrl => {
                            if (bUrl === null) r.profile.audio = null; 
                            else if (bUrl) {
                                r.profile.audio.blobUrl = bUrl;
                                r.profile.audio.isLoaded = true;
                            }
                        });
                    }
                }
                return {
                    ...r, 
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
    if (state.theme === 'light') document.body.classList.add('light-theme');

    instance = {
        state, addToast, toggleTheme, cycleLang, t, showConfirm, createAccount, loginWithKey, logout, saveProfile, fetchTags, deleteAccount, rotateKey, fetchInbox, fetchMyProfile, getLocalizedTag
    };
    return instance;
}