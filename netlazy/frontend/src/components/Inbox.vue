<template>
  <div style="display: flex; height: 100%; width: 100%; overflow: hidden;" ref="inboxRoot">
    <div class="inbox-main-pane" :class="{ 'mobile-chat-open': isMobile && selectedChat }" v-show="!isMobile || selectedChat">
      <div v-if="isMobile && selectedChat" class="inbox-back-bar">
        <button class="footer-action inbox-back-btn" @click="selectedChatId = null"><i class="bi bi-chevron-left"></i> {{ store.t('back') }}</button>
      </div>
      <div v-if="selectedChat" class="inbox-chat-detail">
        <div class="card">
          <!-- Audio -->
          <div v-if="selectedChat.profile && selectedChat.profile.audio" style="display:flex; align-items:center; margin-bottom: 0.5rem; width: 100%;" v-intersect="() => store.loadDecryptedMedia(selectedChat.profile.audio, selectedChat.profile.media_id)">
            <audio v-if="selectedChat.profile.audio.blobUrl" class="audio-minimal" :src="selectedChat.profile.audio.blobUrl" @error="handleMediaError(selectedChat.profile, selectedChat.profile.audio)" controls style="flex-grow:1;"></audio>
            <div v-else class="media-loader skeleton" style="height: 32px; flex-grow: 1; border-radius: var(--radius-sm);"></div>
          </div>

          <!-- Media Stack -->
          <div class="feed-media-stack" :data-count="selectedChat.profile.media.length" v-if="selectedChat.profile && selectedChat.profile.media && selectedChat.profile.media.length > 0">
            <div class="feed-media-item" v-for="m in selectedChat.profile.media" :key="m.blobUrl || m.url" @click="handleMediaClick(m, selectedChat.profile.media)" v-intersect="() => store.loadDecryptedMedia(m, selectedChat.profile.media_id)">
               <div v-if="!m.isLoaded" class="media-loader skeleton" style="border-radius: 0;"></div>
               <img v-if="m.media_type === 'image' && m.blobUrl" v-show="m.isLoaded" :src="m.blobUrl" @error="handleMediaError(selectedChat.profile, m)" @load="m.isLoaded = true" :class="{'is-blurred': m.blur, 'cdn-obfuscated': m.isLegacy}">
               <video v-else-if="m.media_type === 'video' && m.blobUrl" v-show="m.isLoaded" :src="m.blobUrl" @error="handleMediaError(selectedChat.profile, m)" @loadeddata="m.isLoaded = true" muted autoplay loop playsinline :class="{'is-blurred': m.blur, 'cdn-obfuscated': m.isLegacy}"></video>
            </div>
          </div>

          <!-- Tags & Bio -->
          <div class="chip-group" v-if="selectedChat.profile && selectedChat.profile.tags && selectedChat.profile.tags.length > 0">
            <span class="chip require" style="padding: 0.1rem 0.4rem; font-size: 0.65rem;" v-for="tag in selectedChat.profile.tags" :key="tag">{{ store.getLocalizedTag(tag) }}</span>
          </div>
          <div style="font-size: 0.85rem;" v-if="selectedChat.profile && selectedChat.profile.bio">{{ selectedChat.profile.bio }}</div>

          <!-- Public Contacts -->
          <div v-if="selectedChat.profile && selectedChat.profile.contacts && selectedChat.profile.contacts.some(c => !c.is_private && c.type !== 'unknown')" style="margin-top: 0.5rem; display: flex; flex-direction: column; gap: 0.3rem; width: 100%; min-width: 0;">
            <template v-for="c in selectedChat.profile.contacts" :key="c.value">
              <div v-if="!c.is_private && c.type !== 'unknown'" class="contact-row" style="border-bottom: none; padding: 0; display: flex; align-items: center; gap: 0.5rem; width: 100%; min-width: 0;">
                 <i class="bi contact-icon" :class="getContactIcon(c.type)" style="font-size: 0.85rem; width: 16px; flex-shrink: 0;"></i>
                 <span class="contact-val" style="font-size: 0.85rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; cursor: pointer; flex-grow: 1; min-width: 0;" @click.stop="copyText(c.value)">{{ c.value }}</span>
                 <i class="bi bi-copy contact-action" style="flex-shrink: 0;" @click.stop="copyText(c.value)"></i>
              </div>
            </template>
          </div>

          <!-- Chat Info -->
          <div style="border-top: 1px solid var(--border-subtle); padding-top: 0.5rem; margin-top: 1rem;">
            <div style="display: flex; align-items: center; gap: 0.5rem; font-size: 0.8rem; color: var(--text-muted); margin-bottom: 0.5rem;">
               <i class="bi" :class="getStateIcon(selectedChat)"></i>
               <span>{{ getChatStateLabel(selectedChat.chatState) }}</span>
               <span>•</span>
               <i class="bi" :class="getTypeIcon(selectedChat)" :style="{ color: getTypeColor(selectedChat.type) }"></i>
               <span :style="{ color: getTypeColor(selectedChat.type) }">{{ selectedChat.type }}</span>
            </div>

            <!-- Contacts Info -->
            <div v-if="selectedChat.offered_contact || selectedChat.returned_contact" style="font-size: 0.85rem; margin-bottom: 0.8rem;">
              <div v-if="selectedChat.offered_contact">
                <span v-if="selectedChat.chatState === 'received' && ['exchange'].includes(selectedChat.type)" style="color: var(--text-muted); font-style: italic;">
                  {{ store.t('contact_hidden_exchange') }}
                </span>
                <div v-else>
                  <div class="offered-item" v-for="contact in selectedChat.offered_contact.split(', ')" :key="contact">{{ store.t(selectedChat.is_sender ? 'my_shared' : 'they_revealed', {value: ''}) }} {{ contact }}</div>
                </div>
              </div>
              <div v-if="selectedChat.returned_contact">
                <div class="offered-item" v-for="contact in selectedChat.returned_contact.split(', ')" :key="contact">{{ store.t(!selectedChat.is_sender ? 'my_shared' : 'they_revealed', {value: ''}) }} {{ contact }}</div>
              </div>
            </div>

            <div v-if="selectedChat.message" style="margin-bottom: 0.8rem; padding: 0.6rem 0.8rem; background: rgba(128,128,128,0.05); border-left: 2px solid var(--accent-moss); font-size: 0.85rem; font-style: italic; color: var(--text-main); border-radius: 0 var(--radius-sm) var(--radius-sm) 0; word-break: break-word;">
              {{ selectedChat.message }}
            </div>

            <div class="chat-actions">
              <template v-if="selectedChat.chatState === 'received'">
                <template v-if="selectedChat.type === 'share'">
                   <button class="footer-action icon-btn" style="color: var(--accent-danger);" :disabled="isBusy(selectedChat)" @click="deleteMatch(selectedChat)">
                     <i class="bi" :class="actionIcon(selectedChat, 'delete', 'bi-trash3')"></i>
                   </button>
                </template>
                <template v-else-if="selectedChat.type === 'exchange' || selectedChat.type === 'demand'">
                   <button class="footer-action" style="color: var(--accent-danger);" :disabled="isBusy(selectedChat)" @click="resolveRequest(selectedChat, 'declined')">
                     <i class="bi" :class="actionIcon(selectedChat, 'decline', 'bi-x-lg')"></i> {{ store.t('decline') }}
                   </button>
                   <button class="footer-action"
                           :disabled="isBusy(selectedChat) || validPrivateContacts.length === 0"
                           :style="{ color: 'var(--accent-moss)', opacity: (isBusy(selectedChat) || validPrivateContacts.length === 0) ? 0.35 : 1, cursor: (isBusy(selectedChat) || validPrivateContacts.length === 0) ? 'not-allowed' : 'pointer' }"
                           @click.stop="openResolveModal(selectedChat)">
                     <i class="bi" :class="actionIcon(selectedChat, 'accept', 'bi-check-lg')"></i> {{ selectedChat.type === 'exchange' ? store.t('uf_action_exchange') : store.t('send') }}
                   </button>
                </template>
              </template>
              <template v-else-if="selectedChat.chatState === 'sent' || ['matched', 'declined'].includes(selectedChat.chatState)">
                 <button class="footer-action icon-btn" style="color: var(--accent-danger);" :disabled="isBusy(selectedChat)" @click="deleteMatch(selectedChat)">
                   <i class="bi" :class="actionIcon(selectedChat, 'delete', 'bi-trash3')"></i>
                 </button>
              </template>

              <transition name="dropdown-fade">
                <div class="glass-menu inbox-resolve-menu" v-if="resolveReq && !isMobile" @click.stop>
                  <div class="glass-contacts-list">
                    <div class="glass-option" v-for="c in validPrivateContacts" :key="c.value" @click="toggleReqContact(resolveReq, c.value)">
                      <span class="animated-underline">{{ c.type }}: {{ c.value }}</span>
                      <i class="bi" :class="resolveReq.selectedContacts && resolveReq.selectedContacts.includes(c.value) ? 'bi-check2' : ''" style="color: var(--accent-moss); width: 16px; display: inline-block; flex-shrink: 0;"></i>
                    </div>
                    <div v-if="validPrivateContacts.length === 0" style="padding: 0.8rem 1rem; text-align: center; color: var(--text-muted); font-style: italic; font-size: 0.85rem;">
                      {{ store.t('no_valid_private') }}
                    </div>
                  </div>
                  <div v-if="validPrivateContacts.length > 0" style="padding: 0.5rem 1rem; text-align: right;">
                    <button class="icon-btn" style="background: none; border: none; color: var(--accent-moss);" :disabled="!resolveReq.selectedContacts.length || !!pendingAction" @click="confirmResolve(resolveReq)">
                      <i class="bi" :class="pendingAction && pendingAction.type === 'accept' ? 'bi-hourglass-split spin' : 'bi-send-fill'"></i>
                    </button>
                  </div>
                </div>
              </transition>
            </div>
          </div>
        </div>
      </div>
      <div v-else class="empty-state">
        <i class="bi bi-chat-dots empty-icon"></i>
        <h3>{{ store.t('select_chat_prompt') }}</h3>
      </div>
    </div>

    <!-- RIGHT SIDEBAR -->
    <div class="inbox-sidebar" :class="{ 'collapsed': isSidebarCollapsed, 'non-uf': !store.state.isUserFriendlyInterface }" @click="handleInboxBgClick" v-show="!isMobile || !selectedChat">
      
      <div class="inbox-brand-row" v-if="store.state.isUserFriendlyInterface">
        <div class="brand" v-if="!isSidebarCollapsed">{{ store.t('inbox') }}</div>
        <button class="collapse-btn" @click.stop="store.state.isInboxSidebarCollapsed = !store.state.isInboxSidebarCollapsed">
          <i class="bi" :class="isSidebarCollapsed ? 'bi-chevron-left' : 'bi-chevron-right'"></i>
        </button>
      </div>

      <div class="inbox-filters" @click.stop>
        <i class="bi bi-envelope-arrow-down filter-icon" :class="{active: filters.state.received}" @click="filters.state.received = !filters.state.received"></i>
        <i class="bi bi-envelope-arrow-up filter-icon" :class="{active: filters.state.sent}" @click="filters.state.sent = !filters.state.sent"></i>
        <i class="bi bi-heart filter-icon filter-match" :class="{active: filters.state.matched}" @click="filters.state.matched = !filters.state.matched"></i>
        <i class="bi bi-heartbreak filter-icon filter-nomatch" :class="{active: filters.state.declined}" @click="filters.state.declined = !filters.state.declined"></i>
        <i class="bi bi-box-arrow-up filter-icon type-share" :class="{active: filters.type.share}" @click="filters.type.share = !filters.type.share"></i>
        <i class="bi bi-arrow-left-right filter-icon type-exchange" :class="{active: filters.type.exchange}" @click="filters.type.exchange = !filters.type.exchange"></i>
        <i class="bi bi-box-arrow-in-down filter-icon type-demand" :class="{active: filters.type.demand}" @click="filters.type.demand = !filters.type.demand"></i>
      </div>

      <div class="inbox-chat-list scrollable-content">
        <transition-group name="chat-item" tag="div" class="inbox-chat-list-inner">
          <div class="chat-preview" v-for="chat in filteredChats" :key="chat.id" @click.stop="selectChat(chat)" :class="{ unread: isUnread(chat), active: selectedChat?.id === chat.id, 'uf-unread': store.state.isUserFriendlyInterface, 'nonuf-unread': !store.state.isUserFriendlyInterface }">
            <div class="chat-avatar-container" v-intersect="() => loadChatAvatar(chat)">
              <template v-if="chat.avatarUrl">
                 <img v-if="chat.avatarType === 'image'" :src="chat.avatarUrl" class="chat-avatar" />
                 <video v-else-if="chat.avatarType === 'video'" :src="chat.avatarUrl" class="chat-avatar" muted autoplay loop playsinline></video>
              </template>
              <i v-else class="bi bi-person chat-avatar-icon"></i>
              
              <div class="chat-icons-badge" v-if="isSidebarCollapsed">
                 <i class="bi" :class="getStateIcon(chat)"></i>
                 <i class="bi" :class="getTypeIcon(chat)" :style="{ color: getTypeColor(chat.type) }"></i>
                 <div class="unread-dot" v-if="isUnread(chat)"></div>
              </div>
            </div>
            
            <div class="chat-preview-content" v-if="!isSidebarCollapsed">
               <div class="chat-preview-header">
                 <div class="chat-preview-icons">
                   <i class="bi" :class="getStateIcon(chat)"></i>
                   <i class="bi" :class="getTypeIcon(chat)" :style="{ color: getTypeColor(chat.type) }"></i>
                 </div>
               </div>
               <div class="chat-preview-message" :class="{'italic-muted': !chat.message}">
                 {{ chat.message || (store.state.isUserFriendlyInterface ? store.t('no_message') : '') }}
               </div>
            </div>
            <div class="unread-dot" v-if="isUnread(chat) && !isSidebarCollapsed && store.state.isUserFriendlyInterface"></div>
          </div>
        </transition-group>
        
        <div v-if="filteredChats.length === 0 && !isSidebarCollapsed" class="inbox-empty-label">
          {{ store.t('no_chats') }}
        </div>
      </div>
    </div>
    
    <transition name="sheet-fade">
      <div class="bottom-sheet-backdrop" v-if="resolveReq && isMobile" @click="resolveReq = null">
        <div class="bottom-sheet-box" @click.stop>
          <div class="bottom-sheet-body">
            <div class="sheet-contact-row" 
                 v-for="c in validPrivateContacts" 
                 :key="c.value" 
                 :class="{ 'is-selected': resolveReq.selectedContacts && resolveReq.selectedContacts.includes(c.value) }"
                 @click="toggleReqContact(resolveReq, c.value)">
              <span class="sheet-contact-val">{{ c.type }}: {{ c.value }}</span>
            </div>
            <div v-if="validPrivateContacts.length === 0" style="text-align: center; color: var(--text-muted); padding: 1.5rem 0; font-style: italic;">
              {{ store.t('no_valid_private') }}
            </div>
          </div>
          <div class="bottom-sheet-footer" v-if="validPrivateContacts.length > 0">
            <button class="footer-action icon-btn" @click="confirmResolve(resolveReq)" :disabled="!!pendingAction" style="font-size: 1.5rem; color: var(--accent-moss);">
              <i class="bi" :class="pendingAction && pendingAction.type === 'accept' ? 'bi-hourglass-split spin' : 'bi-send-fill'"></i>
            </button>
          </div>
        </div>
      </div>
    </transition>
  </div>
</template>

<script setup>
import { computed, ref, reactive, onMounted, onUnmounted, onActivated, watch, nextTick } from 'vue'
import { useStore } from '../store/state.js'
import api from '../utils/api.js'

const store = useStore()
const inboxRoot = ref(null)

const isMobile = ref(window.innerWidth <= 768)
const selectedChatId = ref(null)
const resolveReq = ref(null)
const pendingAction = ref(null)

const filters = reactive({
  state: { received: true, sent: true, matched: true, declined: true },
  type: { share: true, exchange: true, demand: true }
});

const chats = computed(() => {
    return store.state.inbox.map(req => {
        let state = 'unknown';
        if (req.status === 'pending' && !req.is_sender) state = 'received';
        else if (req.status === 'pending' && req.is_sender) state = 'sent';
        else if (req.status === 'accepted') state = 'matched';
        else if (req.status === 'declined') state = 'declined';
        
        let avatarUrl = null;
        let avatarType = null;
        if (req.profile && req.profile.media && req.profile.media.length > 0) {
            avatarUrl = req.profile.media[0].blobUrl;
            avatarType = req.profile.media[0].media_type;
        }
        
        return { ...req, chatState: state, avatarUrl, avatarType };
    }).sort((a, b) => new Date(b.updated_at) - new Date(a.updated_at));
});

const filteredChats = computed(() => {
  return chats.value.filter(c => filters.state[c.chatState] || filters.type[c.type]);
});

function handleInboxBgClick(e) {
  if (store.state.isUserFriendlyInterface || isMobile.value) return;
  if (e.target.closest('.chat-preview') || e.target.closest('.filter-icon') || e.target.closest('.collapse-btn') || e.target.closest('.inbox-brand-row')) return;
  store.state.isInboxSidebarCollapsed = !store.state.isInboxSidebarCollapsed;
}

const selectedChat = computed(() => chats.value.find(c => c.id === selectedChatId.value) || null)
const isSidebarCollapsed = computed(() => store.state.isInboxSidebarCollapsed && !isMobile.value)

function patchInbox(id, patch) {
  const item = store.state.inbox.find(r => r.id === id)
  if (item) Object.assign(item, patch)
}

function isBusy(chat) {
  return !!(pendingAction.value && pendingAction.value.id === chat.id)
}

function actionIcon(chat, type, idleIcon) {
  if (pendingAction.value && pendingAction.value.id === chat.id && pendingAction.value.type === type) {
    return 'bi-hourglass-split spin'
  }
  return idleIcon
}

function loadChatAvatar(chat) {
  const media = chat.profile?.media?.[0]
  if (media && chat.profile?.media_id) {
    store.loadDecryptedMedia(media, chat.profile.media_id)
  }
}

function getStateIcon(chat) {
  if (chat.chatState === 'received') return 'bi-envelope-arrow-down';
  if (chat.chatState === 'sent') return 'bi-envelope-arrow-up';
  if (chat.chatState === 'matched') return 'bi-heart';
  return 'bi-heartbreak';
}

function getTypeIcon(chat) {
  if (chat.type === 'share') return 'bi-box-arrow-up';
  if (chat.type === 'exchange') return 'bi-arrow-left-right';
  return 'bi-box-arrow-in-down';
}

function getTypeColor(type) {
  if (type === 'share') return 'var(--accent-info)';
  if (type === 'exchange') return 'var(--accent-moss)';
  return 'var(--accent-danger)';
}

function getChatStateLabel(state) {
  return {
    received: store.t('received'),
    sent: store.t('sent_resolved'),
    matched: store.t('matched_label'),
    declined: store.t('declined')
  }[state] || state
}

function isUnread(chat) {
  if (chat.status === 'pending' && !chat.is_sender) return !chat.is_read
  if (chat.status !== 'pending' && chat.is_sender) return !chat.is_read
  return false
}

async function markAsRead(req) {
  if (!isUnread(req)) return
  patchInbox(req.id, { is_read: true })
  try {
    await api.post(`/inbox/handshakes/${req.id}/read`)
  } catch (e) {
    patchInbox(req.id, { is_read: false })
  }
}

function selectChat(chat) {
  selectedChatId.value = chat.id
  markAsRead(chat)
  nextTick(() => {
    const pane = inboxRoot.value && inboxRoot.value.querySelector('.inbox-main-pane')
    if (pane) pane.scrollTop = 0
  })
}

function handleResize() {
  isMobile.value = window.innerWidth <= 768;
}

const validPrivateContacts = computed(() => store.state.myProfile.contacts.filter(c => c.is_private && c.type !== 'unknown' && c.value.trim() !== ''))

watch(filteredChats, (list) => {
  list.forEach(loadChatAvatar)
}, { immediate: true })

onMounted(() => {
  store.fetchInbox(store.state.inbox.length > 0)
  window.addEventListener('resize', handleResize)
  document.addEventListener('click', handleResolveOutsideClick)
})
onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  document.removeEventListener('click', handleResolveOutsideClick)
})

onActivated(() => {
  if (inboxRoot.value) {
    const videos = inboxRoot.value.querySelectorAll('video')
    videos.forEach(v => {
      if (v.paused) v.play().catch(() => {})
    })
  }
})

async function handleMediaError(profile, m) {
    if (m.isErrorHandled) return;
    m.isErrorHandled = true;
    m.isLoaded = false;
    m.blobUrl = null;
}

function handleMediaClick(mediaObj, mediaList) {
  if (mediaObj.blur) mediaObj.blur = false
  else {
    const idx = mediaList.findIndex(x => x.url === mediaObj.url);
    store.state.lightbox.mediaList = mediaList;
    store.state.lightbox.index = idx !== -1 ? idx : 0;
    store.state.lightbox.isEditable = false;
    store.state.lightbox.open = true;
  }
}

function openResolveModal(chat) {
  if (validPrivateContacts.value.length === 0) return;
  if (resolveReq.value && resolveReq.value.id === chat.id) {
    resolveReq.value = null;
    return;
  }
  resolveReq.value = { ...chat, selectedContacts: [] };
}

function handleResolveOutsideClick(e) {
  if (!resolveReq.value) return;
  if (e.target.closest('.inbox-resolve-menu') || e.target.closest('.bottom-sheet-box') || e.target.closest('.chat-actions')) return;
  resolveReq.value = null;
}

function toggleReqContact(req, val) {
  const idx = req.selectedContacts.indexOf(val);
  if (idx === -1) req.selectedContacts.push(val);
  else req.selectedContacts.splice(idx, 1);
}

async function confirmResolve(req) {
  if (!req.selectedContacts || req.selectedContacts.length === 0) return
  const target = selectedChat.value
  if (!target) return
  const ok = await resolveRequest(target, 'accepted', req.selectedContacts.join(', '))
  if (ok) resolveReq.value = null
}

async function resolveRequest(req, status, returned_contact = null) {
  if (pendingAction.value) return false
  pendingAction.value = { id: req.id, type: status === 'accepted' ? 'accept' : 'decline' }
  try {
    const payload = { status, returned_contact }
    await api.post(`/inbox/handshakes/${req.id}/resolve`, payload)

    if (status === 'declined') {
      store.state.inbox = store.state.inbox.filter(r => r.id !== req.id)
      if (selectedChatId.value === req.id) selectedChatId.value = null
    } else {
      patchInbox(req.id, { status, returned_contact, is_read: true })
    }
    store.addToast(`Handshake ${status}`, "bi-check2")
    await store.fetchInbox(true)
    return true
  } catch (e) {
    const detail = e.response && e.response.data && e.response.data.detail
    store.addToast(detail || "Failed to resolve handshake", "bi-x-circle")
    return false
  } finally {
    pendingAction.value = null
  }
}

async function deleteMatch(req) {
  if (pendingAction.value) return
  pendingAction.value = { id: req.id, type: 'delete' }
  try {
    await api.delete(`/inbox/handshakes/${req.id}`)
    store.state.inbox = store.state.inbox.filter(r => r.id !== req.id)
    if (selectedChatId.value === req.id) selectedChatId.value = null
    store.addToast(store.t('match_deleted'), "bi-trash")
  } catch (e) {
    store.addToast(store.t('failed_delete_chat'), "bi-x-circle")
  } finally {
    pendingAction.value = null
  }
}

const iconMap = { 'email': 'bi-envelope', 'link': 'bi-link-45deg', 'phone': 'bi-telephone', 'unknown': 'bi-question' }
function getContactIcon(type) { return iconMap[type] || 'bi-link-45deg' }

async function copyText(txt) {
  await navigator.clipboard.writeText(txt)
  store.addToast(store.t('copied'), "bi-check2")
}
</script>

<style scoped>
.inbox-main-pane {
  flex-grow: 1;
  position: relative;
  overflow-y: auto;
  padding: 1.5rem;
}

.inbox-sidebar {
  width: 220px;
  flex-shrink: 0;
  border-left: 1px solid var(--border-subtle);
  background: var(--bg-surface);
  display: flex;
  flex-direction: column;
  transition: width 0.3s cubic-bezier(0.16, 1, 0.3, 1), background-color 0.2s;
  position: relative;
  z-index: 10;
  overflow-x: hidden;
}
body:not(.uf-mode) .inbox-sidebar.non-uf,
body:not(.uf-mode) .inbox-sidebar.non-uf * {
  cursor: pointer;
}
body:not(.uf-mode) .inbox-sidebar.non-uf:hover {
  background: var(--bg-elevated);
}
.inbox-sidebar.collapsed {
  width: 60px;
  overflow-x: hidden;
}
.inbox-sidebar.collapsed .inbox-chat-list,
.inbox-sidebar.collapsed .inbox-chat-list-inner,
.inbox-sidebar.collapsed .chat-preview {
  overflow-x: hidden;
  max-width: 100%;
}

.inbox-brand-row {
  padding: 1rem 0.7rem;
  border-bottom: 1px solid var(--border-subtle);
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 56px;
  flex-shrink: 0;
}
.inbox-brand-row .brand {
  font-size: 1.05rem;
  cursor: default;
}
.inbox-sidebar.collapsed .inbox-brand-row {
  padding: 1rem 0;
  justify-content: center;
}
.inbox-sidebar.collapsed .inbox-brand-row .collapse-btn {
  margin: 0 auto;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  width: 100%;
  color: var(--text-muted);
}

.inbox-filters {
  padding: 0.25rem 0.4rem;
  border: none;
  display: flex;
  flex-direction: row;
  flex-wrap: nowrap;
  justify-content: center;
  align-items: center;
  gap: 0.05rem;
  flex-shrink: 0;
}
.inbox-sidebar.collapsed .inbox-brand-row { order: 1; }
.inbox-sidebar.collapsed .inbox-chat-list { order: 2; }
.inbox-sidebar.collapsed .inbox-filters {
  order: 3;
  margin-top: auto;
  flex-direction: column;
  padding: 0.35rem 0 0.6rem;
  gap: 0;
}
.filter-icon {
  font-size: 0.9rem;
  color: var(--text-muted);
  cursor: pointer;
  transition: color 0.2s, transform 0.2s;
  padding: 0.12rem 0.18rem;
  border: none;
  background: none;
}
.filter-icon:hover { transform: scale(1.1); }
.filter-icon.active { color: var(--accent-moss); }
.filter-icon.filter-match.active,
.filter-icon.filter-nomatch.active { color: #fff; }
body.light-theme .filter-icon.filter-match.active,
body.light-theme .filter-icon.filter-nomatch.active { color: var(--text-main); }
.filter-icon.type-share.active { color: var(--accent-info); }
.filter-icon.type-exchange.active { color: var(--accent-moss); }
.filter-icon.type-demand.active { color: var(--accent-danger); }

.chat-actions {
  display: flex;
  gap: 1rem;
  margin-top: 1rem;
  justify-content: flex-end;
  position: relative;
}
.inbox-resolve-menu {
  right: 0;
  left: auto;
  bottom: calc(100% + 0.4rem);
  top: auto;
  width: max-content;
  min-width: 260px;
  max-width: min(360px, calc(100vw - 4rem));
  margin-top: 0;
}
.chat-preview {
  display: flex;
  align-items: center;
  padding: 0.75rem 0.9rem;
  gap: 0.7rem;
  border-bottom: 1px solid var(--border-subtle);
  transition: background 0.2s;
  cursor: pointer;
  max-width: 100%;
  box-sizing: border-box;
}
.inbox-sidebar.collapsed .chat-preview {
  padding: 0.4rem 0;
  justify-content: center;
  gap: 0;
}
.chat-preview:hover, .chat-preview.active { background: rgba(128,128,128,0.05); }
.chat-preview.unread.nonuf-unread { background: rgba(141, 169, 112, 0.1); }

.chat-avatar-container {
  width: 48px; height: 48px;
  border-radius: 50%;
  background: var(--bg-elevated);
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  flex-shrink: 0;
  overflow: hidden;
}
.chat-avatar { width: 100%; height: 100%; object-fit: cover; }
.chat-avatar-icon { font-size: 1.2rem; color: var(--text-muted); }
.chat-icons-badge {
  position: absolute;
  top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0,0,0,0.6);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.05rem;
  color: white;
  font-size: 0.58rem;
}

.chat-preview-content {
  flex-grow: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0.12rem;
}
.chat-preview-header {
  display: flex;
  align-items: center;
}
.chat-preview-icons {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  font-size: 0.72rem;
  color: var(--text-muted);
}
.inbox-sidebar.collapsed .chat-avatar-container {
  width: 36px; height: 36px;
}
.chat-preview-message {
  font-size: 0.85rem;
  color: var(--text-main);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.chat-preview-message.italic-muted {
  font-style: italic;
  color: var(--text-muted);
}
.unread-dot {
  width: 8px; height: 8px;
  background: var(--accent-moss);
  border-radius: 50%;
  box-shadow: 0 0 8px var(--accent-moss);
  flex-shrink: 0;
}

.inbox-chat-list {
  position: relative;
  overflow-x: hidden;
  flex-grow: 1;
  padding: 0;
  min-width: 0;
}
.inbox-chat-list-inner {
  position: relative;
  overflow-x: hidden;
  min-width: 0;
}
.inbox-empty-label {
  padding: 1rem 0.6rem;
  text-align: center;
  color: var(--text-muted);
  font-size: 0.8rem;
  font-style: italic;
}

.chat-item-enter-active,
.chat-item-leave-active {
  transition: opacity 0.25s cubic-bezier(0.16, 1, 0.3, 1), transform 0.25s cubic-bezier(0.16, 1, 0.3, 1);
}
.chat-item-enter-from,
.chat-item-leave-to {
  opacity: 0;
  transform: translateX(16px);
}
.chat-item-leave-active {
  position: absolute;
  width: 100%;
}
.chat-item-move {
  transition: transform 0.25s cubic-bezier(0.16, 1, 0.3, 1);
}

@media (max-width: 768px) {
  .inbox-sidebar,
  .inbox-sidebar.collapsed {
    width: 100% !important;
  }
  .inbox-filters {
    flex-direction: row;
    flex-wrap: nowrap;
    justify-content: space-evenly;
    padding: 0.25rem 0.5rem;
    gap: 0.05rem;
  }
  .inbox-brand-row .collapse-btn { display: none; }
  .inbox-chat-list {
    padding-bottom: calc(72px + env(safe-area-inset-bottom));
  }
  .inbox-main-pane {
    padding-bottom: calc(88px + env(safe-area-inset-bottom));
  }
  .inbox-main-pane.mobile-chat-open {
    padding-top: 0;
    padding-left: 1.2rem;
    padding-right: 1.2rem;
  }
  .inbox-back-bar {
    position: sticky;
    top: 0;
    z-index: 20;
    margin: 0 -1.2rem 0.4rem;
    padding: calc(0.2rem + env(safe-area-inset-top, 0px)) 1.2rem 0.35rem;
    background: linear-gradient(to bottom, rgba(0, 0, 0, 0.18) 0%, transparent 100%);
    backdrop-filter: blur(4px);
    -webkit-backdrop-filter: blur(4px);
  }
  body.light-theme .inbox-back-bar {
    background: linear-gradient(to bottom, rgba(254, 252, 245, 0.72) 0%, transparent 100%);
  }
  .inbox-back-btn {
    font-size: 0.72rem;
    opacity: 0.45;
    gap: 0.25rem;
    padding: 0.1rem 0.35rem;
    height: auto;
    width: auto;
    background: none;
    border: none;
    color: var(--text-muted);
  }
  .inbox-back-btn:hover,
  .inbox-back-btn:active {
    opacity: 0.7;
    background: none;
  }
}
</style>
