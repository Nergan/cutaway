<template>
  <div id="app-container">
    
    <!-- Native Mobile Pull To Refresh Visual Indicator -->
    <div class="ptr-indicator" :style="{ transform: `translateY(${ptrOffset}px)`, opacity: ptrOffset > -60 ? 1 : 0 }">
      <div class="ptr-icon">
        <i class="bi bi-arrow-repeat" 
           :class="{ spin: isPtrRefreshing }"
           :style="{ transform: !isPtrRefreshing ? `rotate(${ptrRotation}deg)` : 'none' }"></i>
      </div>
    </div>

    <!-- Neutral app-wide splash screen to block structural pop-in during async hydration -->
    <div v-if="!store.state.isInitialized" class="welcome-container" style="justify-content: center; align-items: center; min-height: 100vh; flex-direction: column; gap: 1.5rem;">
      <h1 class="welcome-brand" style="cursor: default;">netlazy</h1>
      <i class="bi bi-arrow-repeat spin" style="font-size: 2.2rem; color: var(--accent-moss);"></i>
    </div>

    <div v-else-if="store.state.isBanned" class="welcome-container">
      <div style="position: absolute; top: 1.5rem; right: 1.5rem; display: flex; gap: 1rem; z-index: 100;">
        <button class="footer-action icon-btn" @click="store.toggleTheme">
          <transition name="fade" mode="out-in">
            <i class="bi" :class="store.state.theme === 'dark' ? 'bi-sun' : 'bi-moon'" :key="store.state.theme"></i>
          </transition>
        </button>
        <button class="footer-action lang-btn icon-btn" @click.stop="toggleLangMenu">
          <i class="bi bi-translate"></i>
        </button>
      </div>

      <div class="welcome-box">
        <h1 class="welcome-brand" style="color: var(--accent-danger);">banned</h1>
        <p class="welcome-desc">{{ store.t('account_banned') }}</p>
        
        <div class="welcome-footer" style="margin-top: 2rem;">
          <button class="create-btn" @click="checkBanStatus" style="font-size: 0.9rem; padding: 0.6rem 1.2rem; text-transform: lowercase;">
            <i class="bi bi-arrow-clockwise"></i> {{ store.t('check_status') }}
          </button>
        </div>
      </div>
    </div>

    <div v-else-if="!store.state.isRegistered" class="welcome-container">
      <div style="position: absolute; top: 1.5rem; right: 1.5rem; display: flex; gap: 1rem; z-index: 100;">
        <button class="footer-action icon-btn" @click="store.toggleTheme">
          <transition name="fade" mode="out-in">
            <i class="bi" :class="store.state.theme === 'dark' ? 'bi-sun' : 'bi-moon'" :key="store.state.theme"></i>
          </transition>
        </button>
        <button class="footer-action lang-btn icon-btn" @click.stop="toggleLangMenu">
          <i class="bi bi-translate"></i>
        </button>
      </div>

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
      </div>
    </div>

    <template v-else>
      <nav class="sidebar" :class="{ 'sidebar-collapsed': store.state.isSidebarCollapsed }">
        <div class="sidebar-content">
          <div class="brand-row">
            <div class="brand" v-if="!store.state.isSidebarCollapsed" @click="reloadPage">netlazy</div>
            <button class="collapse-btn" @click="store.state.isSidebarCollapsed = !store.state.isSidebarCollapsed">
              <i class="bi" :class="store.state.isSidebarCollapsed ? 'bi-list' : 'bi-chevron-left'"></i>
            </button>
          </div>
          
          <div class="nav-section">
            <a class="nav-item" :class="{active: store.state.currentView === 'feed'}" @click="store.state.currentView = 'feed'" :title="store.t('search_profiles')">
              <i class="bi bi-compass"></i> 
              <span v-if="!store.state.isSidebarCollapsed" class="animated-underline">{{ store.t('search_profiles') }}</span>
            </a>
            <a class="nav-item" :class="{active: store.state.currentView === 'editor'}" @click="store.state.currentView = 'editor'" :title="store.t('my_profile')">
              <i class="bi bi-person-lines-fill"></i> 
              <span v-if="!store.state.isSidebarCollapsed" class="animated-underline">{{ store.t('my_profile') }}</span>
            </a>
            <a class="nav-item" :class="{active: store.state.currentView === 'inbox'}" @click="store.state.currentView = 'inbox'" :title="store.t('inbox')">
              <i v-if="!store.state.isSidebarCollapsed || pendingInboxCount === 0" class="bi bi-envelope"></i> 
              <span v-else class="badge" style="margin: 0;">{{ pendingInboxCount }}</span>
              <span v-if="!store.state.isSidebarCollapsed" class="animated-underline">{{ store.t('inbox') }}</span>
              <span class="badge" v-if="pendingInboxCount > 0 && !store.state.isSidebarCollapsed">{{ pendingInboxCount }}</span>
            </a>
          </div>
          
          <div class="sidebar-footer">
            <div class="sidebar-controls-row">
              <button class="footer-action icon-btn" @click="store.toggleTheme" :title="store.state.theme === 'dark' ? store.t('light_mode') : store.t('dark_mode')">
                <transition name="fade" mode="out-in">
                  <i class="bi" :class="store.state.theme === 'dark' ? 'bi-sun' : 'bi-moon'" :key="store.state.theme"></i>
                </transition>
              </button>
              <button class="footer-action lang-btn icon-btn" @click.stop="toggleLangMenu" :title="store.t('lang')">
                <i class="bi bi-translate"></i>
              </button>
            </div>
            
            <a class="nav-item vault-item" :class="{active: store.state.currentView === 'vault'}" @click="store.state.currentView = 'vault'" :title="store.t('identity_vault')">
              <i class="bi bi-shield-lock"></i> 
              <span v-if="!store.state.isSidebarCollapsed" class="animated-underline">{{ store.t('identity_vault') }}</span>
            </a>
          </div>
        </div>
      </nav>
      
      <!-- Native Mobile App Bottom Navigation -->
      <nav class="mobile-bottom-nav" v-if="store.state.isRegistered && !store.state.isBanned">
        <a class="nav-item" :class="{active: store.state.currentView === 'feed'}" @click="store.state.currentView = 'feed'">
          <i class="bi bi-compass"></i>
        </a>
        <a class="nav-item" :class="{active: store.state.currentView === 'editor'}" @click="store.state.currentView = 'editor'">
          <i class="bi bi-person-lines-fill"></i>
        </a>
        <a class="nav-item" :class="{active: store.state.currentView === 'inbox'}" @click="store.state.currentView = 'inbox'">
          <i v-if="pendingInboxCount === 0" class="bi bi-envelope"></i>
          <span v-else class="badge" style="margin: 0; font-size: 0.8rem; width: 22px; height: 22px; display: inline-flex; align-items: center; justify-content: center; border-radius: 50%;">{{ pendingInboxCount }}</span>
        </a>
        <a class="nav-item" :class="{active: store.state.currentView === 'vault'}" @click="store.state.currentView = 'vault'">
          <i class="bi bi-shield-lock"></i>
        </a>
      </nav>

      <main class="main-view">
        <div style="position:relative; flex-grow:1; display:flex; flex-direction:column; overflow:hidden;">
          <transition name="view-fade" mode="out-in">
            <KeepAlive>
              <Editor v-if="store.state.currentView === 'editor'" key="editor" />
              <Feed v-else-if="store.state.currentView === 'feed'" key="feed" />
              <Inbox v-else-if="store.state.currentView === 'inbox'" key="inbox" />

              <div class="scrollable-content" v-else-if="store.state.currentView === 'vault'" key="vault">
                 
                 <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 2rem; border-bottom: 1px solid var(--border-subtle); padding-bottom: 1rem;" class="mobile-only-settings">
                   <h2 style="margin: 0; font-size: 1.2rem; color: var(--text-main); font-weight: 600;">{{ store.t('identity_vault') }}</h2>
                   <div style="display: flex; gap: 1.5rem;">
                       <button class="footer-action icon-btn" @click="store.toggleTheme">
                         <transition name="fade" mode="out-in">
                           <i class="bi" :class="store.state.theme === 'dark' ? 'bi-sun' : 'bi-moon'" :key="store.state.theme"></i>
                         </transition>
                       </button>
                       <button class="footer-action lang-btn icon-btn" @click.stop="toggleLangMenu">
                         <i class="bi bi-translate"></i>
                       </button>
                   </div>
                 </div>

                 <div style="margin-bottom: 2rem; color:var(--text-muted);" v-html="store.state.isUserFriendlyInterface ? store.t('vault_desc_uf') : store.t('vault_desc')"></div>
                 
                 <div style="display:flex; gap:1rem; margin-bottom: 2rem; flex-wrap: wrap;">
                    <button class="footer-action" @click="copyKey">
                      <i class="bi bi-clipboard"></i> <span class="animated-underline">{{ store.t('copy_raw') }}</span>
                    </button>
                    <button class="footer-action" style="color: var(--accent-earth);" @click="store.logout">
                      <i class="bi bi-box-arrow-right"></i> <span class="animated-underline">{{ store.t('log_out') }}</span>
                    </button>
                    <button class="footer-action" style="color: var(--accent-info);" @click="rotateIdentityKey">
                      <i class="bi bi-arrow-repeat"></i> <span class="animated-underline">{{ store.t('regenerate_key') }}</span>
                    </button>
                    <button class="footer-action" style="color: var(--accent-danger);" @click="store.deleteAccount">
                      <i class="bi bi-trash3"></i> <span class="animated-underline">{{ store.t('delete_account') }}</span>
                    </button>
                 </div>
                 
                 <div class="code-block" :style="{filter: keyVisible ? 'none' : 'blur(5px)'}" @click="keyVisible = !keyVisible" :title="store.t('click_to_reveal')">
                   {{ displayPrivateKey }}
                 </div>

                 <div style="margin-top: 3rem; border-top: 1px solid var(--border-subtle); padding-top: 1.5rem;">
                   <h3 v-if="store.state.isUserFriendlyInterface" style="font-size: 1.1rem; color: var(--text-main); font-weight: 600; margin-bottom: 1rem;">
                     {{ store.t('uf_settings') }}
                   </h3>

                   <!-- Mobile Only Update App Button -->
                   <button v-if="Capacitor.isNativePlatform()" 
                           class="footer-action" 
                           style="color: var(--accent-moss); margin-bottom: 1rem; width: max-content; display: flex; align-items: center;" 
                           @click="handleUpdateApp"
                           :disabled="isCheckingUpdate">
                      <i class="bi" :class="isCheckingUpdate ? 'bi-arrow-repeat spin' : (updateAvailable ? 'bi-cloud-download-fill' : 'bi-cloud-download')" style="margin-right: 0.5rem;"></i> 
                      <span class="animated-underline">{{ store.t('update_app') }}</span>
                      <span v-if="updateAvailable" style="margin-left: 0.5rem; background: var(--accent-moss); color: var(--bg-base); font-size: 0.65rem; padding: 0.1rem 0.4rem; border-radius: var(--radius-pill); font-weight: bold;">NEW</span>
                   </button>

                   <div class="glass-option" @click="store.state.isUserFriendlyInterface = !store.state.isUserFriendlyInterface" style="padding: 0.5rem 0; width: max-content;">
                     <i class="bi bi-flower3 uf-icon" style="margin-right: 0.5rem; transition: color 0.2s;"></i>
                     <span class="animated-underline">{{ store.t('userfriendly_interface') }}</span>
                     <i class="bi" :class="store.state.isUserFriendlyInterface ? 'bi-check2' : ''" style="color: var(--accent-moss); width: 16px; display: inline-block; margin-left: 0.5rem;"></i>
                   </div>
                 </div>

                 <!-- In-App Version Label (Injected by CI, Mobile Only) -->
                 <div v-if="Capacitor.isNativePlatform()" style="margin-top: 2.5rem; text-align: center; color: var(--text-muted); font-size: 0.8rem; font-family: monospace;">
                    netlazy v{{ CURRENT_VERSION }}
                 </div>

              </div>
            </KeepAlive>
          </transition>
        </div>
      </main>
    </template>

    <Lightbox />

    <!-- Minimalist Global Sliding Bottom Sheet Overlay for Handshake Contact Selection (Mobile) -->
    <transition name="sheet-fade">
      <div class="bottom-sheet-backdrop" v-if="store.state.contactSelect.open" @click="store.state.contactSelect.open = false">
        <div class="bottom-sheet-box" @click.stop>
          <div class="bottom-sheet-body">
            <template v-if="store.state.contactSelect.type !== 'demand'">
              <div class="sheet-contact-row" 
                   v-for="c in validPrivateContacts" 
                   :key="c.value" 
                   :class="{ 'is-selected': store.state.contactSelect.selectedContacts.includes(c.value) }"
                   @click="toggleGlobalContact(c.value)">
                <span class="sheet-contact-val">{{ c.value }}</span>
              </div>
              
              <div v-if="validPrivateContacts.length === 0" style="text-align: center; color: var(--text-muted); padding: 1.5rem 0;">
                {{ store.t('no_valid_private') }}
              </div>
            </template>

            <div style="margin-top: 0.5rem;" v-if="store.state.contactSelect.profile">
                <input type="text" 
                       class="seamless-input" 
                       v-model="store.state.contactSelect.message" 
                       :placeholder="store.t('message_placeholder')" 
                       maxlength="100" 
                       style="background: rgba(128, 128, 128, 0.08); padding: 0.8rem 1.2rem; border-radius: var(--radius-pill); border: 1px solid var(--border-subtle); width: 100%; font-size: 0.9rem;">
            </div>
          </div>
          
          <div class="bottom-sheet-footer">
            <button class="footer-action icon-btn search-clear-btn" style="position: static; font-size: 1.5rem;" @click="store.state.contactSelect.open = false">
              <i class="bi bi-x-lg"></i>
            </button>
            <button class="footer-action icon-btn" 
                    :disabled="(store.state.contactSelect.type !== 'demand' && store.state.contactSelect.selectedContacts.length === 0) || store.state.contactSelect.isSending" 
                    @click="submitGlobalHandshake" 
                    style="font-size: 1.5rem;"
                    :style="{ 
                      color: store.state.contactSelect.type === 'share' ? 'var(--accent-info)' : (store.state.contactSelect.type === 'demand' ? 'var(--accent-danger)' : 'var(--accent-moss)'),
                      opacity: (store.state.contactSelect.isSending || (store.state.contactSelect.type !== 'demand' && store.state.contactSelect.selectedContacts.length === 0)) ? 0.4 : 1,
                      cursor: (store.state.contactSelect.isSending || (store.state.contactSelect.type !== 'demand' && store.state.contactSelect.selectedContacts.length === 0)) ? 'not-allowed' : 'pointer'
                    }">
              <i class="bi" :class="store.state.contactSelect.isSending ? 'bi-hourglass-split spin' : 'bi-send-fill'"></i>
            </button>
          </div>
        </div>
      </div>
    </transition>

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

    <!-- Language Selection Bottom Sheet (Mobile Only) -->
    <transition name="sheet-fade">
      <div class="bottom-sheet-backdrop" v-if="langMenu.open && isMobile" @click="langMenu.open = false">
        <div class="bottom-sheet-box" @click.stop>
          <div class="bottom-sheet-body">
             <div class="sheet-contact-row" v-for="l in availableLangs" :key="'mob'+l.code" @click="selectLang(l.code)" :class="{'is-selected': store.state.lang === l.code}">
                 <span class="sheet-contact-val" style="text-transform: lowercase;">{{ l.name }}</span>
             </div>
          </div>
        </div>
      </div>
    </transition>

    <!-- Language Selection Popover (Desktop Only) -->
    <Teleport to="body">
      <transition name="popover-fade">
        <div v-if="langMenu.open && !isMobile" 
             class="glass-menu lang-dropdown" 
             :style="{
               position: 'fixed',
               left: langMenu.x + 'px',
               top: langMenu.y + 'px',
               '--popover-translate': langMenu.isBelow ? 'translate(-50%, 0) translateY(8px)' : 'translate(-50%, -100%) translateY(-8px)',
               transform: 'var(--popover-translate) scale(1)',
               transformOrigin: langMenu.isBelow ? 'top center' : 'bottom center'
             }"
             @click.stop>
             <div class="glass-option" v-for="l in availableLangs" :key="'desk'+l.code" @click="selectLang(l.code)" :class="{'highlighted-option': store.state.lang === l.code}">
                 <span class="animated-underline">{{ l.name }}</span>
             </div>
        </div>
      </transition>
    </Teleport>

    <!-- Invisible Global Hardware Decoder for Media Obfuscation -->
    <svg style="width:0; height:0; position:absolute;" aria-hidden="true" focusable="false">
      <filter id="channel-restore">
        <feColorMatrix type="matrix" values="
          0 1 0 0 0
          0 0 1 0 0
          1 0 0 0 0
          0 0 0 1 0
        "/>
      </filter>
    </svg>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useStore } from './store/state.js'
import api, { apiWithPoW } from './utils/api.js'
import Lightbox from './components/Lightbox.vue'
import Editor from './components/Editor.vue'
import Feed from './components/Feed.vue'
import Inbox from './components/Inbox.vue'
import { App as CapacitorApp } from '@capacitor/app';
import { Capacitor } from '@capacitor/core';

const store = useStore()
const importKeyInput = ref('')
const keyVisible = ref(false)
const importKeyVisible = ref(false)

const ptrOffset = ref(-60)
const ptrRotation = ref(0)
const isPtrRefreshing = ref(false)

const SECTIONS = ['feed', 'editor', 'inbox', 'vault'];

let touchStartPos = { x: 0, y: 0 };
let touchCurrentPos = { x: 0, y: 0 };
let canPullToRefresh = false;

const isMobile = ref(window.innerWidth <= 768);
function handleResize() { isMobile.value = window.innerWidth <= 768; }

// Language Menu Logic
const langMenu = ref({ open: false, x: 0, y: 0, isBelow: false });
const availableLangs = [
    { code: 'en', name: 'english' },
    { code: 'ru', name: 'russian' },
    { code: 'pt', name: 'portuguese' },
    { code: 'zh', name: 'chinese' },
    { code: 'ja', name: 'japanese' },
    { code: 'ko', name: 'korean' }
];

function toggleLangMenu(e) {
    if (langMenu.value.open) {
        langMenu.value.open = false;
    } else {
        const rect = e.currentTarget.getBoundingClientRect();
        const isBelow = rect.top < window.innerHeight / 2; 
        
        let x = rect.left + rect.width / 2;
        if (!store.state.isSidebarCollapsed && !isMobile.value) {
            // Position over the main view content area when sidebar is open so backdrop blur has page content to process
            x = Math.max(x, 240);
        } else {
            if (x < 100) x = 100; // clamp to prevent off-screen left
        }
        
        langMenu.value = {
            open: true,
            x: x,
            y: isBelow ? rect.bottom : rect.top,
            isBelow
        };
    }
}

function selectLang(code) {
    if (store.state.lang !== code) {
        document.body.classList.add('is-translating');
        setTimeout(() => {
            store.state.lang = code;
            setTimeout(() => document.body.classList.remove('is-translating'), 50);
        }, 150);
    }
    langMenu.value.open = false;
}

function handleGlobalClick(e) {
    if (langMenu.value.open) {
        const el = document.querySelector('.lang-dropdown');
        if (el && el.contains(e.target)) return;
        langMenu.value.open = false;
    }
}

function isInsideHorizontalScroll(target) {
  let el = target;
  while (el && el !== document.body && el !== document.documentElement) {
    const style = window.getComputedStyle(el);
    const overflowX = style.overflowX;
    const isScrollable = (overflowX === 'auto' || overflowX === 'scroll') && (el.scrollWidth > el.clientWidth + 5);
    
    if (isScrollable || el.tagName === 'INPUT' || el.classList.contains('lightbox-container') || el.classList.contains('feed-media-item')) {
      return true;
    }
    el = el.parentElement;
  }
  return false;
}

function isViewAtVeryTop(target) {
  let el = target;
  while (el && el !== document.body && el !== document.documentElement) {
    const style = window.getComputedStyle(el);
    const overflowY = style.overflowY;
    const isScrollable = (overflowY === 'auto' || overflowY === 'scroll') && (el.scrollHeight > el.clientHeight + 5);
    
    if (isScrollable && el.scrollTop > 2) {
      return false;
    }
    el = el.parentElement;
  }
  return true;
}

function handleGlobalTouchStart(e) {
  if (e.touches.length !== 1 || window.innerWidth > 768) {
    canPullToRefresh = false;
    return;
  }
  const touch = e.touches[0];
  touchStartPos = { x: touch.clientX, y: touch.clientY };
  touchCurrentPos = { x: touch.clientX, y: touch.clientY };
  canPullToRefresh = isViewAtVeryTop(e.target);
}

function handleGlobalTouchMove(e) {
  if (e.touches.length !== 1) return;
  const touch = e.touches[0];
  touchCurrentPos = { x: touch.clientX, y: touch.clientY };

  if (!canPullToRefresh) return;
  const deltaY = touchCurrentPos.y - touchStartPos.y;
  if (deltaY < 0 || !isViewAtVeryTop(e.target)) {
    canPullToRefresh = false;
    ptrOffset.value = -60;
    ptrRotation.value = 0;
  } else {
    ptrOffset.value = Math.min(deltaY * 0.4, 80) - 60;
    ptrRotation.value = Math.min(deltaY * 2.5, 360);
  }
}

function handleGlobalTouchEnd(e) {
  if (window.innerWidth > 768) {
    canPullToRefresh = false;
    ptrOffset.value = -60;
    ptrRotation.value = 0;
    return;
  }

  if (e.changedTouches && e.changedTouches.length > 0) {
    const touch = e.changedTouches[0];
    touchCurrentPos = { x: touch.clientX, y: touch.clientY };
  }

  const deltaY = touchCurrentPos.y - touchStartPos.y;
  const deltaX = touchCurrentPos.x - touchStartPos.x;
  const absDeltaX = Math.abs(deltaX);
  const absDeltaY = Math.abs(deltaY);

  if (absDeltaX > 80 && absDeltaX > absDeltaY * 1.5) {
      if (!store.state.lightbox.open && !store.state.contactSelect.open && !store.state.confirmModal.open && !langMenu.value.open) {
          if (!isInsideHorizontalScroll(e.target)) {
              const currentIndex = SECTIONS.indexOf(store.state.currentView);
              if (currentIndex !== -1) {
                  if (deltaX < 0 && currentIndex < SECTIONS.length - 1) {
                      store.state.currentView = SECTIONS[currentIndex + 1];
                  } else if (deltaX > 0 && currentIndex > 0) {
                      store.state.currentView = SECTIONS[currentIndex - 1];
                  }
              }
          }
      }
  }

  if (canPullToRefresh) {
    if (deltaY > 140 && deltaY > absDeltaX * 1.5 && isViewAtVeryTop(e.target)) {
      isPtrRefreshing.value = true;
      ptrOffset.value = 20;
      setTimeout(() => window.location.reload(), 500);
    } else {
      ptrOffset.value = -60;
      ptrRotation.value = 0;
    }
    canPullToRefresh = false;
  }
}

function handleGlobalTouchCancel() {
  canPullToRefresh = false;
  ptrOffset.value = -60;
  ptrRotation.value = 0;
}

// CAPACITOR AUTO-UPDATE MECHANISM
const CURRENT_VERSION = import.meta.env.VITE_APP_VERSION || "0.0.1";
const updateAvailable = ref(false);
const updateData = ref(null);
const isCheckingUpdate = ref(false);

function isNewerVersion(oldVer, newVer) {
  const oldParts = oldVer.split('.').map(Number);
  const newParts = newVer.split('.').map(Number);
  for (let i = 0; i < Math.max(oldParts.length, newParts.length); i++) {
    const a = newParts[i] || 0;
    const b = oldParts[i] || 0;
    if (a > b) return true;
    if (a < b) return false;
  }
  return false;
}

async function fetchLatestReleaseData() {
  try {
    const res = await fetch("https://api.github.com/repos/Nergan/cdn/contents/netlazy/apk?t=" + Date.now());
    if (res.ok) {
        const files = await res.json();
        const apkFile = files.find(f => f.name.endsWith('.apk') && f.name.startsWith('netlazy-'));
        if (apkFile) {
            const match = apkFile.name.match(/netlazy-v?([\d\.]+)\.apk/i);
            if (match) {
                return {
                    version: match[1],
                    url: `https://cdn.jsdelivr.net/gh/Nergan/cdn@main/netlazy/apk/${apkFile.name}`
                };
            }
        }
    }
  } catch (e) {
    console.warn("GitHub API check failed", e);
  }
  return null;
}

async function checkForUpdates() {
  if (!Capacitor.isNativePlatform()) return;
  try {
    const data = await fetchLatestReleaseData();
    if (data && isNewerVersion(CURRENT_VERSION, data.version)) {
        updateAvailable.value = true;
        updateData.value = data;
    }
  } catch (e) {}
}

async function handleUpdateApp() {
  if (!Capacitor.isNativePlatform()) return;

  if (updateAvailable.value && updateData.value && updateData.value.url) {
    window.open(updateData.value.url, '_system');
    return;
  }

  isCheckingUpdate.value = true;
  store.addToast("Checking for updates...", "bi-hourglass-split");

  try {
    const data = await fetchLatestReleaseData();
    if (data) {
      if (isNewerVersion(CURRENT_VERSION, data.version)) {
        updateAvailable.value = true;
        updateData.value = data;
        window.open(data.url, '_system');
      } else {
        store.addToast("App is up to date (v" + CURRENT_VERSION + ")", "bi-check-circle");
      }
    } else {
        store.addToast("Could not find latest APK", "bi-exclamation-triangle");
    }
  } catch (e) {
    store.addToast("Failed to check for updates", "bi-x-circle");
  } finally {
    isCheckingUpdate.value = false;
  }
}

onMounted(() => {
  window.addEventListener('resize', handleResize);
  document.addEventListener('touchstart', handleGlobalTouchStart, { passive: true });
  document.addEventListener('touchmove', handleGlobalTouchMove, { passive: true });
  document.addEventListener('touchend', handleGlobalTouchEnd, { passive: true });
  document.addEventListener('touchcancel', handleGlobalTouchCancel, { passive: true });
  document.addEventListener('click', handleGlobalClick);

  setTimeout(checkForUpdates, 3000);

  if (Capacitor.isNativePlatform()) {
    CapacitorApp.addListener('backButton', ({ canGoBack }) => {
      if (store.state.lightbox.open) {
        store.state.lightbox.open = false;
      } else if (store.state.contactSelect.open) {
        store.state.contactSelect.open = false;
      } else if (store.state.confirmModal.open) {
        store.state.confirmModal.open = false;
      } else if (langMenu.value.open) {
        langMenu.value.open = false;
      } else if (store.state.currentView !== 'feed') {
        store.state.currentView = 'feed';
      } else {
        if (canGoBack) {
          window.history.back();
        } else {
          CapacitorApp.exitApp();
        }
      }
    });
  } else {
    // Web browser popstate sync for client-side routing illusion
    window.addEventListener('popstate', (e) => {
        store.syncUrlToView();
    });
  }
});

onUnmounted(() => {
  window.removeEventListener('resize', handleResize);
  document.removeEventListener('touchstart', handleGlobalTouchStart);
  document.removeEventListener('touchmove', handleGlobalTouchMove);
  document.removeEventListener('touchend', handleGlobalTouchEnd);
  document.removeEventListener('touchcancel', handleGlobalTouchCancel);
  document.removeEventListener('click', handleGlobalClick);
});

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

const validPrivateContacts = computed(() => 
  store.state.myProfile.contacts.filter(c => c.is_private && c.type !== 'unknown' && c.value.trim() !== '')
)

function toggleGlobalContact(val) {
  const idx = store.state.contactSelect.selectedContacts.indexOf(val);
  if (idx === -1) {
    store.state.contactSelect.selectedContacts.push(val);
  } else {
    store.state.contactSelect.selectedContacts.splice(idx, 1);
  }
}

async function submitGlobalHandshake() {
  const cs = store.state.contactSelect;
  if (!cs.profile) return;
  
  cs.isSending = true;
  store.addToast("Solving Proof of Work...", "bi-hourglass");
  
  try {
    const contactValue = cs.selectedContacts.join(', ');
    const payload = {
      receiver_id: cs.profile.user_id,
      type: cs.type,
      offered_contact: contactValue,
      message: cs.message ? cs.message.trim() : null
    };
    
    const feedProfile = store.state.feed.find(p => p.user_id === cs.profile.user_id);
    if (feedProfile) {
      feedProfile.isSendingReq = cs.type;
    }
    
    await apiWithPoW('post', '/inbox/handshakes', payload);
    
    if (feedProfile) {
      feedProfile.sent = true;
      feedProfile.sentType = cs.type;
    }
    
    store.addToast(store.t('sent', { type: cs.type }), 'bi-send-check');
    cs.open = false;
    cs.message = ''; 
  } catch (e) {
    if (e.response && e.response.data && e.response.data.detail) {
      store.addToast(e.response.data.detail, "bi-x-circle");
    } else {
      store.addToast("Failed to send handshake", "bi-x-circle");
    }
  } finally {
    cs.isSending = false;
    const feedProfile = store.state.feed.find(p => p.user_id === cs.profile.user_id);
    if (feedProfile) {
      feedProfile.isSendingReq = null;
    }
  }
}

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

watch(() => store.state.currentView, (newVal, oldVal) => {
  if (newVal !== oldVal) {
      store.syncViewToUrl();
  }
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
@media (min-width: 769px) {
  .mobile-only-settings { display: none !important; }
}

.ptr-indicator {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 99999;
  pointer-events: none;
  transition: transform 0.2s cubic-bezier(0.16, 1, 0.3, 1), opacity 0.2s;
}
.ptr-icon {
  background: var(--bg-surface);
  border: 1px solid var(--border-subtle);
  color: var(--accent-moss);
  border-radius: 50%;
  width: 42px;
  height: 42px;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: var(--shadow-md);
}
.ptr-icon i {
  font-size: 1.35rem;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 1em;
  height: 1em;
  line-height: 1;
  transform-origin: center center;
}
</style>