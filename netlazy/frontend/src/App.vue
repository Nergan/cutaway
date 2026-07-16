<template>
  <div id="app-container">
    
    <div v-if="store.state.isBanned" class="welcome-container">
      <div class="welcome-box">
        <h1 class="welcome-brand" style="color: var(--accent-danger);">banned</h1>
        <p class="welcome-desc">{{ store.t('account_banned') }}</p>
        
        <div class="welcome-footer" style="margin-top: 2rem;">
          <button class="create-btn" @click="checkBanStatus" style="font-size: 0.9rem; padding: 0.6rem 1.2rem;">
            <i class="bi bi-arrow-clockwise"></i> Check Status
          </button>
        </div>

        <div class="welcome-footer">
          <button class="footer-action" @click="store.toggleTheme">
            <i class="bi" :class="store.state.theme === 'dark' ? 'bi-sun' : 'bi-moon'"></i> 
            {{ store.state.theme === 'dark' ? store.t('light_mode') : store.t('dark_mode') }}
          </button>
          <button class="footer-action" @click="store.cycleLang">
            <i class="bi bi-globe"></i> {{ store.t('lang') }}: {{ store.state.lang }}
          </button>
        </div>
      </div>
    </div>

    <div v-else-if="!store.state.isRegistered" class="welcome-container">
      <div class="welcome-box">
        <h1 class="welcome-brand">netlazy</h1>
        <p class="welcome-desc">{{ store.t('welcome_desc') }}</p>
        
        <button class="create-btn" @click="store.createAccount">
          <i class="bi bi-lightning-charge"></i> {{ store.t('create_account') }}
        </button>

        <div class="import-key-wrapper">
          <input :type="importKeyVisible ? 'text' : 'password'" 
                 class="seamless-input import-input" 
                 v-model="importKeyInput" 
                 :placeholder="store.t('import_key_prompt')" 
                 @keyup.enter="handleImport">
          <button class="eye-btn" @click="importKeyVisible = !importKeyVisible" tabindex="-1">
            <i class="bi" :class="importKeyVisible ? 'bi-eye-slash' : 'bi-eye'"></i>
          </button>
        </div>

        <div class="welcome-footer">
          <button class="footer-action" @click="store.toggleTheme">
            <i class="bi" :class="store.state.theme === 'dark' ? 'bi-sun' : 'bi-moon'"></i> 
            {{ store.state.theme === 'dark' ? store.t('light_mode') : store.t('dark_mode') }}
          </button>
          <button class="footer-action" @click="store.cycleLang">
            <i class="bi bi-globe"></i> {{ store.t('lang') }}: {{ store.state.lang }}
          </button>
        </div>
      </div>
    </div>

    <template v-else>
      <nav class="sidebar" :class="{ 'sidebar-collapsed': store.state.isSidebarCollapsed, 'is-resizing': isResizingSidebar }" :style="{ width: store.state.isSidebarCollapsed ? '60px' : store.state.sidebarWidth + 'px' }">
        <div class="resizer-v" @mousedown="startResize"></div>
        <div class="sidebar-content">
          <div class="brand-row">
            <div class="brand" v-if="!store.state.isSidebarCollapsed" @click="reloadPage">netlazy</div>
            <button class="collapse-btn" @click="store.state.isSidebarCollapsed = !store.state.isSidebarCollapsed" :style="{ margin: store.state.isSidebarCollapsed ? '0 auto' : '0' }">
              <i class="bi" :class="store.state.isSidebarCollapsed ? 'bi-list' : 'bi-chevron-left'"></i>
            </button>
          </div>
          
          <div class="nav-section">
            <a class="nav-item" :class="{active: store.state.currentView === 'feed'}" @click="store.state.currentView = 'feed'" :title="store.t('search_profiles')">
              <i class="bi bi-compass"></i> <span v-if="!store.state.isSidebarCollapsed">{{ store.t('search_profiles') }}</span>
            </a>
            <a class="nav-item" :class="{active: store.state.currentView === 'editor'}" @click="store.state.currentView = 'editor'" :title="store.t('my_profile')">
              <i class="bi bi-person-lines-fill"></i> <span v-if="!store.state.isSidebarCollapsed">{{ store.t('my_profile') }}</span>
            </a>
            <a class="nav-item" :class="{active: store.state.currentView === 'inbox'}" @click="store.state.currentView = 'inbox'" :title="store.t('inbox')">
              <i v-if="!store.state.isSidebarCollapsed || pendingInboxCount === 0" class="bi bi-inbox"></i> 
              <span v-else class="badge" style="margin: 0;">{{ pendingInboxCount }}</span>
              <span v-if="!store.state.isSidebarCollapsed">{{ store.t('inbox') }}</span>
              <span class="badge" v-if="pendingInboxCount > 0 && !store.state.isSidebarCollapsed">{{ pendingInboxCount }}</span>
            </a>
          </div>

          <div class="nav-section">
            <a class="nav-item" :class="{active: store.state.currentView === 'vault'}" @click="store.state.currentView = 'vault'" :title="store.t('identity_vault')">
              <i class="bi bi-fingerprint"></i> <span v-if="!store.state.isSidebarCollapsed">{{ store.t('identity_vault') }}</span>
            </a>
          </div>
          
          <div class="sidebar-footer" v-if="!store.state.isSidebarCollapsed">
            <button class="footer-action" @click="store.toggleTheme">
              <i class="bi" :class="store.state.theme === 'dark' ? 'bi-sun' : 'bi-moon'"></i> 
              {{ store.state.theme === 'dark' ? store.t('light_mode') : store.t('dark_mode') }}
            </button>
            <button class="footer-action" @click="store.cycleLang"><i class="bi bi-globe"></i> {{ store.t('lang') }}: {{ store.state.lang }}</button>
          </div>
        </div>
      </nav>
      
      <div class="sidebar-backdrop" :class="{ active: !store.state.isSidebarCollapsed }" @click="store.state.isSidebarCollapsed = true"></div>
      
      <!-- Native Mobile App Bottom Navigation -->
      <nav class="mobile-bottom-nav" v-if="store.state.isRegistered && !store.state.isBanned">
        <a class="nav-item" :class="{active: store.state.currentView === 'feed'}" @click="store.state.currentView = 'feed'">
          <i class="bi bi-compass"></i>
          <span>{{ store.t('feed') }}</span>
        </a>
        <a class="nav-item" :class="{active: store.state.currentView === 'editor'}" @click="store.state.currentView = 'editor'">
          <i class="bi bi-person-lines-fill"></i>
          <span>{{ store.t('editor') }}</span>
        </a>
        <a class="nav-item" :class="{active: store.state.currentView === 'inbox'}" @click="store.state.currentView = 'inbox'" style="position:relative;">
          <i class="bi bi-inbox"></i>
          <span v-if="pendingInboxCount > 0" class="badge" style="position:absolute; top:2px; right:20%; transform:translate(50%, -50%); margin:0;">{{ pendingInboxCount }}</span>
          <span>{{ store.t('inbox') }}</span>
        </a>
        <a class="nav-item" :class="{active: store.state.currentView === 'vault'}" @click="store.state.currentView = 'vault'">
          <i class="bi bi-fingerprint"></i>
          <span>{{ store.t('vault') }}</span>
        </a>
      </nav>

      <main class="main-view">
        <header class="mobile-top-bar">
          <button class="mobile-menu-btn" @click="store.state.isSidebarCollapsed = false" title="Menu">
            <i class="bi bi-list"></i>
          </button>
          <span class="mobile-view-title">{{ store.t(store.state.currentView) }}</span>
          <div style="width: 40px;" class="mobile-menu-btn"></div>
        </header>

        <div style="position:relative; flex-grow:1; display:flex; flex-direction:column; overflow:hidden;">
          <transition name="view-fade" mode="out-in">
            <KeepAlive>
              <Editor v-if="store.state.currentView === 'editor'" key="editor" />
              <Feed v-else-if="store.state.currentView === 'feed'" key="feed" />
              <Inbox v-else-if="store.state.currentView === 'inbox'" key="inbox" />

              <div class="scrollable-content" v-else-if="store.state.currentView === 'vault'" key="vault">
                 <div style="margin-bottom: 2rem; color:var(--text-muted);">
                   {{ store.t('vault_desc') }}
                 </div>
                 
                 <div style="display:flex; gap:1rem; margin-bottom: 2rem; flex-wrap: wrap;">
                    <button class="footer-action" @click="copyKey"><i class="bi bi-clipboard"></i> {{ store.t('copy_raw') }}</button>
                    <button class="footer-action" style="color: var(--accent-earth);" @click="store.logout"><i class="bi bi-box-arrow-right"></i> {{ store.t('log_out') }}</button>
                    <button class="footer-action" style="color: var(--accent-info);" @click="rotateIdentityKey"><i class="bi bi-arrow-repeat"></i> {{ store.t('regenerate_key') }}</button>
                    <button class="footer-action" style="color: var(--accent-danger);" @click="store.deleteAccount"><i class="bi bi-trash3"></i> {{ store.t('delete_account') }}</button>
                 </div>
                 
                 <div class="code-block" :style="{filter: keyVisible ? 'none' : 'blur(5px)'}" @click="keyVisible = !keyVisible" :title="store.t('click_to_reveal')">
                   {{ displayPrivateKey }}
                 </div>
              </div>
            </KeepAlive>
          </transition>
        </div>
      </main>
    </template>

    <Lightbox />

    <div class="toast-container">
      <div class="toast" v-for="toast in store.state.toasts" :key="toast.id" :class="{'toast-minimal': toast.type === 'minimal', 'toast-danger': toast.type === 'danger'}">
        <i class="bi" :class="toast.icon"></i> {{ toast.msg }}
      </div>
    </div>

    <transition name="lightbox-fade">
      <div class="modal-backdrop" v-if="store.state.confirmModal.open" @click="store.state.confirmModal.open = false">
        <div class="modal-box" @click.stop>
          <div class="modal-header">{{ store.state.confirmModal.title }}</div>
          <div class="modal-body">{{ store.state.confirmModal.message }}</div>
          <div class="modal-footer">
            <button class="footer-action" style="color: var(--text-muted);" @click="store.state.confirmModal.open = false">
              {{ store.state.confirmModal.cancelText }}
            </button>
            <button class="footer-action" :style="{ color: store.state.confirmModal.isDanger ? 'var(--accent-danger)' : 'var(--accent-earth)' }" @click="store.state.confirmModal.onConfirm">
              {{ store.state.confirmModal.confirmText }}
            </button>
          </div>
        </div>
      </div>
    </transition>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { useStore } from './store/state.js'
import api from './utils/api.js'
import Lightbox from './components/Lightbox.vue'
import Editor from './components/Editor.vue'
import Feed from './components/Feed.vue'
import Inbox from './components/Inbox.vue'

const store = useStore()
const importKeyInput = ref('')
const keyVisible = ref(false)
const importKeyVisible = ref(false)
const isResizingSidebar = ref(false)

function reloadPage() {
  window.location.reload()
}

const pendingInboxCount = computed(() => {
  return store.state.inbox.filter(r => r.status === 'pending' && !r.is_sender).length
})

const displayPrivateKey = computed(() => {
  if (!store.state.privateKeyPem) return '';
  return store.state.privateKeyPem
    .replace(/-----BEGIN PRIVATE KEY-----/g, '')
    .replace(/-----END PRIVATE KEY-----/g, '')
    .replace(/\r?\n|\r/g, '')
    .trim();
})

async function checkBanStatus() {
  if (!store.state.userId || !store.state.keyPair) {
    store.state.isBanned = false
    store.logout()
    return
  }
  
  try {
    await api.get('/profile/me')
    store.state.isBanned = false
    store.addToast("Account restored", "bi-check-circle")
  } catch (e) {
    if (e.response && (e.response.status === 401 || e.response.status === 404 || e.response.status === 422)) {
      store.state.isBanned = false
      store.logout()
    } else if (store.state.isBanned) {
      store.addToast("Account is still banned", "bi-x-circle")
    }
  }
}

function handleImport() {
  if (importKeyInput.value.trim()) {
    store.loginWithKey(importKeyInput.value.trim())
    importKeyInput.value = ''
  }
}

async function copyKey() {
  await navigator.clipboard.writeText(displayPrivateKey.value)
  store.addToast(store.t('copied'), "bi-check2")
}

function rotateIdentityKey() {
  store.showConfirm(
    store.t('confirm_rotate_title'),
    store.t('confirm_rotate_desc'),
    async () => {
      store.addToast("Regenerating identity...", "bi-hourglass-split")
      try {
        await store.rotateKey()
      } catch (e) {
        store.addToast("Failed to regenerate key", "bi-x-circle")
      }
    },
    false,
    store.t('rotate_key_btn'),
    store.t('cancel')
  )
}

let startX, startW;
function startResize(e) {
  isResizingSidebar.value = true;
  startX = e.clientX;
  startW = store.state.sidebarWidth;
  document.addEventListener('mousemove', doResize);
  document.addEventListener('mouseup', stopResize);
  document.body.style.userSelect = 'none';
}
function doResize(e) {
  const w = startW + (e.clientX - startX);
  if (w > 150 && w < 350) store.state.sidebarWidth = w;
}
function stopResize() {
  isResizingSidebar.value = false;
  document.removeEventListener('mousemove', doResize);
  document.removeEventListener('mouseup', stopResize);
  document.body.style.userSelect = '';
}

watch(() => store.state.currentView, () => {
  if (window.innerWidth <= 768) {
    store.state.isSidebarCollapsed = true;
  }
});
</script>

<style>
#app-container {
  display: flex;
  height: 100vh;
  width: 100vw;
}
</style>