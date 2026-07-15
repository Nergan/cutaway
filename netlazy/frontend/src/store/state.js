import { reactive, watch } from 'vue';
import api, { apiWithPoW } from '../utils/api.js';
import { generateIdentity, loadPrivateKey } from '../utils/crypto.js';
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
    
    myProfile: {
        bio: "",
        tags: [],
        contacts: [{ type: 'unknown', value: '', is_private: true, _id: Math.random().toString() }],
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

    async function loadSavedState() {
        try {
            const raw = localStorage.getItem(STORAGE_KEY);
            if (raw) {
                const parsed = JSON.parse(raw);
                
                // 1. Load non-auth UI states immediately
                ['theme', 'lang', 'sidebarWidth', 'workspaceWidth', 'isWorkspaceCollapsed', 'inboxSplit'].forEach(k => {
                    if (parsed[k] !== undefined) state[k] = parsed[k];
                });

                if (parsed.isRegistered && parsed.privateKeyPem) {
                    try {
                        const keys = await loadPrivateKey(parsed.privateKeyPem);
                        state.keyPair = keys.keyPair;
                        
                        // 2. Only restore auth-dependent variables AFTER the keyPair is initialized.
                        // This prevents child components like <Feed /> from prematurely mounting and
                        // firing API requests lacking cryptographic headers.
                        ['isRegistered', 'isBanned', 'currentView', 'userId', 'privateKeyPem', 'publicKeyPem'].forEach(k => {
                            if (parsed[k] !== undefined) state[k] = parsed[k];
                        });
                        
                        if (!state.isBanned) {
                            await fetchTags(); 
                            await fetchMyProfile();
                            await fetchInbox();
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
                // Fix: ensure the local cache saves the 'privateKeyPem' field correctly,
                // instead of incorrectly overwriting it with the 'publicKeyPem'.
                userId: state.userId, privateKeyPem: state.privateKeyPem, publicKeyPem: state.publicKeyPem
            };
            localStorage.setItem(STORAGE_KEY, JSON.stringify(saveObj));
        } catch (e) {}
    }, { deep: true });

    let toastId = 0;
    function addToast(msg, icon = 'bi-info-circle', type = 'minimal') {
        const id = toastId++;
        // Force the type to 'minimal' internally so that all toasts use the
        // subtle, transparent look originally used by the 'vault synced' alert.
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
        const langs = ['en', 'ru', 'pt', 'zh', 'ja', 'ko'];
        const currentIdx = langs.indexOf(state.lang);
        state.lang = langs[(currentIdx + 1) % langs.length];
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
            
            await fetchTags();
            await fetchMyProfile();
            await fetchInbox();
            
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
            
            await fetchTags();
            await fetchMyProfile();
            await fetchInbox();
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
            
            await fetchMyProfile();
            await fetchInbox();
            
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

    async function fetchMyProfile() {
        try {
            const res = await api.get('/profile/me');
            const data = res.data;
            data.contacts.forEach(c => c._id = Math.random().toString());
            data.media.forEach(m => { m.isLoaded = false; m.isUploading = false; });
            if (data.audio) { data.audio.isLoaded = false; data.audio.isUploading = false; }
            state.myProfile = data;
            
            if (state.myProfile.contacts.length === 0) {
                state.myProfile.contacts.push({ type: 'unknown', value: '', is_private: true, _id: Math.random().toString() });
            }
        } catch (e) {
            console.error("Profile sync failed");
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

    async function fetchInbox() {
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
                }
                return {...r, selectedContact: oldR ? oldR.selectedContact : "", openDropdown: oldR ? oldR.openDropdown : false, resolving: oldR ? oldR.resolving : false, isErrorDeleted: oldR ? oldR.isErrorDeleted : false};
            });
        } catch (e) {}
    }

    loadSavedState();
    if (state.theme === 'light') document.body.classList.add('light-theme');

    instance = {
        state, addToast, toggleTheme, cycleLang, t, showConfirm, createAccount, loginWithKey, logout, saveProfile, fetchTags, deleteAccount, rotateKey, fetchInbox, getLocalizedTag
    };
    return instance;
}