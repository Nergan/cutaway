<template>
  <div style="display: flex; height: 100%; width: 100%; overflow: hidden;" ref="inboxRoot">
    <div class="inbox-main-pane" v-show="!isMobile || selectedChat">
      <div v-if="isMobile && selectedChat" style="padding-bottom: 1rem;">
        <button class="footer-action icon-btn" @click="selectedChat = null"><i class="bi bi-chevron-left"></i> back</button>
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

            <div class="chat-actions" style="display:flex; gap:1rem; margin-top: 1rem; justify-content: flex-end;">
              <template v-if="selectedChat.chatState === 'received'">
                <template v-if="selectedChat.type === 'share'">
                   <button class="footer-action icon-btn" style="color: var(--accent-danger);" @click="deleteMatch(selectedChat)"><i class="bi bi-trash3"></i></button>
                </template>
                <template v-else-if="selectedChat.type === 'exchange' || selectedChat.type === 'demand'">
                   <button class="footer-action" style="color: var(--accent-danger);" @click="resolveRequest(selectedChat, 'declined')"><i class="bi bi-x-lg"></i> {{ store.t('decline') }}</button>
                   <button class="footer-action" style="color: var(--accent-moss);" @click="openResolveModal(selectedChat)"><i class="bi bi-check-lg"></i> {{ selectedChat.type === 'exchange' ? store.t('uf_action_exchange') : store.t('send') }}</button>
                </template>
              </template>
              <template v-else-if="['matched', 'declined'].includes(selectedChat.chatState)">
                 <button class="footer-action icon-btn" style="color: var(--accent-danger);" @click="deleteMatch(selectedChat)"><i class="bi bi-trash3"></i></button>
              </template>
            </div>
          </div>
        </div>
      </div>
      <div v-else class="empty-state">
        <i class="bi bi-chat-dots empty-icon"></i>
        <h3>select a chat...</h3>
      </div>
    </div>

    <!-- RIGHT SIDEBAR -->
    <div class="inbox-sidebar" :class="{ 'collapsed': store.state.isInboxSidebarCollapsed, 'non-uf': !store.state.isUserFriendlyInterface }" @click="handleInboxBgClick" v-show="!isMobile || !selectedChat">
      
      <div class="brand-row" v-if="store.state.isUserFriendlyInterface" style="padding: 1.5rem 1rem; border-bottom: 1px solid var(--border-subtle); display: flex; align-items: center; justify-content: space-between; min-height: 70px;">
        <div class="brand" v-if="!store.state.isInboxSidebarCollapsed" style="font-size: 1.1rem; cursor: default;">{{ store.t('inbox') }}</div>
        <button class="collapse-btn" @click.stop="store.state.isInboxSidebarCollapsed = !store.state.isInboxSidebarCollapsed" :style="store.state.isInboxSidebarCollapsed ? 'margin: 0 auto;' : 'margin: 0;'">
          <i class="bi" :class="store.state.isInboxSidebarCollapsed ? 'bi-chat-left-dots' : 'bi-chevron-right'"></i>
        </button>
      </div>

      <div class="inbox-filters" v-show="!store.state.isInboxSidebarCollapsed" :class="{ 'mobile-bottom': isMobile }" @click.stop>
        <div class="filter-group">
          <i class="bi bi-envelope-arrow-down filter-icon" :class="{active: filters.state.received}" @click="filters.state.received = !filters.state.received"></i>
          <i class="bi bi-envelope-arrow-up filter-icon" :class="{active: filters.state.sent}" @click="filters.state.sent = !filters.state.sent"></i>
          <i class="bi bi-heart filter-icon" :class="{active: filters.state.matched}" @click="filters.state.matched = !filters.state.matched"></i>
          <i class="bi bi-heartbreak filter-icon" :class="{active: filters.state.declined}" @click="filters.state.declined = !filters.state.declined"></i>
        </div>
        <div class="filter-group">
          <i class="bi bi-box-arrow-up filter-icon type-share" :class="{active: filters.type.share}" @click="filters.type.share = !filters.type.share"></i>
          <i class="bi bi-arrow-left-right filter-icon type-exchange" :class="{active: filters.type.exchange}" @click="filters.type.exchange = !filters.type.exchange"></i>
          <i class="bi bi-box-arrow-in-down filter-icon type-demand" :class="{active: filters.type.demand}" @click="filters.type.demand = !filters.type.demand"></i>
        </div>
      </div>

      <div class="inbox-chat-list scrollable-content" style="padding: 0; flex-grow: 1;">
        <div class="chat-preview" v-for="chat in filteredChats" :key="chat.id" @click.stop="selectChat(chat)" :class="{ unread: isUnread(chat), active: selectedChat?.id === chat.id, 'uf-unread': store.state.isUserFriendlyInterface, 'nonuf-unread': !store.state.isUserFriendlyInterface }">
          <div class="chat-avatar-container">
            <template v-if="chat.avatarUrl">
               <img v-if="chat.avatarType === 'image'" :src="chat.avatarUrl" class="chat-avatar" />
               <video v-else-if="chat.avatarType === 'video'" :src="chat.avatarUrl" class="chat-avatar" muted autoplay loop playsinline></video>
            </template>
            <i v-else class="bi bi-person chat-avatar-icon"></i>
            
            <div class="chat-icons-badge" v-if="store.state.isInboxSidebarCollapsed">
               <i class="bi" :class="getStateIcon(chat)"></i>
               <i class="bi" :class="getTypeIcon(chat)" :style="{ color: getTypeColor(chat.type) }"></i>
               <div class="unread-dot" v-if="isUnread(chat)"></div>
            </div>
          </div>
          
          <div class="chat-preview-content" v-if="!store.state.isInboxSidebarCollapsed">
             <div class="chat-preview-header">
               <div style="display:flex; align-items:center; gap: 0.3rem;">
                 <i class="bi" :class="getStateIcon(chat)" style="font-size: 0.75rem; color: var(--text-muted);"></i>
                 <i class="bi" :class="getTypeIcon(chat)" :style="{ color: getTypeColor(chat.type), fontSize: '0.75rem' }"></i>
               </div>
               <span class="chat-time">{{ formatTime(chat.updated_at) }}</span>
             </div>
             <div class="chat-preview-message" :class="{'italic-muted': !chat.message}">
               {{ chat.message || (store.state.isUserFriendlyInterface ? 'no message' : '') }}
             </div>
          </div>
          <div class="unread-dot" v-if="isUnread(chat) && !store.state.isInboxSidebarCollapsed && store.state.isUserFriendlyInterface"></div>
        </div>
        
        <div v-if="filteredChats.length === 0" style="padding: 2rem; text-align: center; color: var(--text-muted); font-size: 0.85rem; font-style: italic;">
          no chats...
        </div>
      </div>
    </div>
    
    <transition name="sheet-fade">
      <div class="bottom-sheet-backdrop" v-if="resolveReq" @click="resolveReq = null">
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
            <button class="footer-action icon-btn" @click="confirmResolve(resolveReq)" style="font-size: 1.5rem; color: var(--accent-moss);">
              <i class="bi bi-send-fill"></i>
            </button>
          </div>
        </div>
      </div>
    </transition>
  </div>
</template>

<script setup>
import { computed, ref, reactive, onMounted, onUnmounted, onActivated } from 'vue'
import { useStore } from '../store/state.js'
import api from '../utils/api.js'

const store = useStore()
const inboxRoot = ref(null)

const isMobile = ref(window.innerWidth <= 768)
const selectedChat = ref(null)
const resolveReq = ref(null)

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
  return chats.value.filter(c => filters.state[c.chatState] && filters.type[c.type]);
});

function handleInboxBgClick(e) {
  if (!store.state.isUserFriendlyInterface && !store.state.isInboxSidebarCollapsed) {
    if (e.target.classList.contains('inbox-sidebar') || e.target.classList.contains('inbox-chat-list')) {
      store.state.isInboxSidebarCollapsed = true;
    }
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
  return { 'received': 'received', 'sent': 'sent', 'matched': 'matched', 'declined': 'declined' }[state] || state;
}

function isUnread(chat) {
  return !chat.is_read;
}

async function markAsRead(req) {
  if (req.is_read) return;
  if ((req.status === 'pending' && !req.is_sender) || 
      (req.status !== 'pending' && req.is_sender)) {
    req.is_read = true;
    try {
      await api.post(`/inbox/handshakes/${req.id}/read`);
    } catch (e) {
      req.is_read = false;
    }
  }
}

function selectChat(chat) {
  selectedChat.value = chat;
  markAsRead(chat);
}

function formatTime(isoString) {
  const d = new Date(isoString);
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function handleResize() {
  isMobile.value = window.innerWidth <= 768;
}

const validPrivateContacts = computed(() => store.state.myProfile.contacts.filter(c => c.is_private && c.type !== 'unknown' && c.value.trim() !== ''))

onMounted(() => {
  if (store.state.inbox.length === 0) store.fetchInbox()
  window.addEventListener('resize', handleResize)
})
onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
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
  resolveReq.value = { ...chat, selectedContacts: [] };
}

function toggleReqContact(req, val) {
  const idx = req.selectedContacts.indexOf(val);
  if (idx === -1) req.selectedContacts.push(val);
  else req.selectedContacts.splice(idx, 1);
}

async function confirmResolve(req) {
  if (req.selectedContacts.length === 0) return;
  await resolveRequest(selectedChat.value, 'accepted', req.selectedContacts.join(', '));
  resolveReq.value = null;
}

async function resolveRequest(req, status, returned_contact = null) {
  try {
    const payload = { status, returned_contact };
    await api.post(`/inbox/handshakes/${req.id}/resolve`, payload);
    
    req.status = status;
    if (status === 'accepted') req.returned_contact = returned_contact;
    store.addToast(`Handshake ${status}`, "bi-check2");
    
    await store.fetchInbox(true);
    const updated = store.state.inbox.find(c => c.id === req.id);
    if (updated) {
        selectedChat.value = chats.value.find(c => c.id === req.id) || null;
    }
  } catch (e) {
    store.addToast("Failed to resolve handshake", "bi-x-circle");
  }
}

async function deleteMatch(req) {
  try {
    await api.delete(`/inbox/handshakes/${req.id}`)
    store.state.inbox = store.state.inbox.filter(r => r.id !== req.id)
    if (selectedChat.value?.id === req.id) selectedChat.value = null;
    store.addToast(store.t('match_deleted'), "bi-trash")
  } catch (e) {
    store.addToast(store.t('failed_delete_chat'), "bi-x-circle")
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
.inbox-sidebar {
  width: 320px;
  flex-shrink: 0;
  border-left: 1px solid var(--border-subtle);
  background: var(--bg-surface);
  display: flex;
  flex-direction: column;
  transition: width 0.3s cubic-bezier(0.16, 1, 0.3, 1), background-color 0.2s;
  position: relative;
  z-index: 10;
}
.inbox-sidebar.collapsed { width: 80px; }

/* Force pointer on everything in non-UF mode inbox sidebar to indicate clickability */
body:not(.uf-mode) .inbox-sidebar.non-uf,
body:not(.uf-mode) .inbox-sidebar.non-uf * { 
  cursor: pointer; 
}
body:not(.uf-mode) .inbox-sidebar.non-uf:hover { 
  background: var(--bg-elevated); 
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
  padding: 1rem;
  border-bottom: 1px solid var(--border-subtle);
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.inbox-filters.mobile-bottom {
  order: 3;
  border-bottom: none;
  border-top: 1px solid var(--border-subtle);
}
.filter-group {
  display: flex;
  justify-content: space-around;
}
.filter-icon {
  font-size: 1.2rem;
  color: var(--text-muted);
  cursor: pointer;
  transition: color 0.2s, transform 0.2s;
  padding: 0.2rem;
}
.filter-icon:hover { transform: scale(1.1); }
.filter-icon.active { color: var(--accent-moss); }
.filter-icon.type-share.active { color: var(--accent-info); }
.filter-icon.type-exchange.active { color: var(--accent-moss); }
.filter-icon.type-demand.active { color: var(--accent-danger); }

.chat-preview {
  display: flex;
  align-items: center;
  padding: 0.8rem 1rem;
  gap: 1rem;
  border-bottom: 1px solid var(--border-subtle);
  transition: background 0.2s;
  cursor: pointer;
}
.chat-preview:hover, .chat-preview.active { background: rgba(128,128,128,0.05); }
.chat-preview.unread.nonuf-unread { background: rgba(141, 169, 112, 0.1); }

.chat-avatar-container {
  width: 45px; height: 45px;
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
.chat-avatar-icon { font-size: 1.5rem; color: var(--text-muted); }
.chat-icons-badge {
  position: absolute;
  top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0,0,0,0.6);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.1rem;
  color: white;
  font-size: 0.65rem;
}

.chat-preview-content {
  flex-grow: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}
.chat-preview-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.chat-time { font-size: 0.7rem; color: var(--text-muted); }
.chat-preview-message {
  font-size: 0.8rem;
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
  width: 10px; height: 10px;
  background: var(--accent-moss);
  border-radius: 50%;
  box-shadow: 0 0 8px var(--accent-moss);
  flex-shrink: 0;
}
</style>
