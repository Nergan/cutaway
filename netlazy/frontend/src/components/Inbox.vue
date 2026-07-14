<template>
  <div class="scrollable-content">
    <div class="inbox-layout">
      
      <div class="inbox-col" :style="{width: store.state.inboxSplit + '%'}">
        <div style="color:var(--text-muted); font-size:0.8rem; margin-top:0.5rem; margin-bottom:0.5rem;">{{ store.t('received') }}</div>
        
        <transition-group name="inbox-list" tag="div">
          <div class="inbox-item card" v-for="req in pendingRequests" :key="req.id" :class="{resolving: req.resolving, 'error-deleted': req.isErrorDeleted}">
            
            <div v-if="req.profile && req.profile.audio" style="display:flex; align-items:center; margin-bottom: 0.5rem; width: 100%;">
              <audio class="audio-minimal" :src="req.profile.audio.url" controls style="flex-grow:1;"></audio>
            </div>

            <div class="telegram-grid" v-if="req.profile && req.profile.media && filterMedia(req.profile.media).length > 0">
              <div class="media-thumb" v-for="m in filterMedia(req.profile.media)" :key="m.url" @click="handleMediaClick(m)">
                 <div v-if="!m.isLoaded" class="media-loader">
                   <i class="bi bi-arrow-repeat spin" style="font-size: 1.5rem; color: var(--text-muted);"></i>
                 </div>
                 <img v-if="m.media_type === 'image'" v-show="m.isLoaded" :src="m.url" @load="m.isLoaded = true" @error="m.isLoaded = true" :class="{'is-blurred': m.blur}">
                 <video v-else-if="m.media_type === 'video'" v-show="m.isLoaded" :src="m.url" @loadeddata="m.isLoaded = true" @error="m.isLoaded = true" muted autoplay loop :class="{'is-blurred': m.blur}"></video>
              </div>
            </div>

            <div class="chip-group" v-if="req.profile && req.profile.tags && req.profile.tags.length > 0">
              <span class="chip require" style="padding: 0.1rem 0.4rem; font-size: 0.65rem;" v-for="tag in req.profile.tags" :key="tag">{{ tag }}</span>
            </div>
            <div style="font-size: 0.85rem;" v-if="req.profile && req.profile.bio">{{ req.profile.bio }}</div>

            <div v-if="req.profile && req.profile.contacts && req.profile.contacts.some(c => !c.is_private && c.type !== 'unknown')" style="margin-top: 0.5rem; display: flex; flex-direction: column; gap: 0.3rem;">
              <div v-for="c in req.profile.contacts.filter(c => !c.is_private && c.type !== 'unknown')" :key="c.value" class="contact-row" style="border-bottom: none; padding: 0;">
                 <i class="bi contact-icon" :class="getContactIcon(c.type)" style="font-size: 0.85rem; width: 16px;"></i>
                 <span class="contact-val" style="font-size: 0.85rem;">{{ c.value }}</span>
                 <i class="bi bi-copy contact-action" @click.stop="copyText(c.value)" :title="store.t('copy')"></i>
              </div>
            </div>
            
            <div style="border-top: 1px solid var(--border-subtle); padding-top: 0.5rem; margin-top: auto;">
              <div style="font-size: 0.75rem; color: var(--accent-info); margin-bottom: 0.2rem;">{{ req.type }}</div>
              
              <div style="font-size: 0.95rem; margin-bottom: 0.5rem;" v-if="req.offered_contact">
                <span v-if="req.status === 'pending' && ['exchange', 'mutual'].includes(req.type)" style="color: var(--text-muted); font-style: italic;">
                  {{ store.t('contact_hidden_exchange') }}
                </span>
                <span v-else>
                  "{{ req.offered_contact }}"
                </span>
              </div>
              
              <div v-if="['mutual', 'demand', 'exchange'].includes(req.type)" style="margin-bottom:0.5rem;">
                 <div class="custom-select" @click.stop="toggleDropdown(req)">
                   {{ req.selectedContact || store.t('select_contact_share') }}
                   <div class="custom-select-menu" v-if="req.openDropdown" @click.stop>
                     <div class="custom-select-option" v-for="c in validPrivateContacts" :key="c.value" @click="req.selectedContact = c.value; req.openDropdown = false">
                       {{ c.type }}: {{ c.value }}
                     </div>
                   </div>
                 </div>
              </div>

              <div style="display:flex; gap:1rem; align-items:center; justify-content:flex-end;">
                <template v-if="req.type === 'share'">
                  <button class="footer-action" style="color:var(--accent-moss);" @click="resolveRequest(req, 'accepted')">
                    <i class="bi bi-eye"></i> {{ store.t('viewed') }}
                  </button>
                </template>
                <template v-else>
                  <button class="footer-action" style="color:var(--accent-danger);" @click="resolveRequest(req, 'declined')">
                    <i class="bi bi-x-lg"></i> {{ store.t('decline') }}
                  </button>
                  <button class="footer-action" style="color:var(--accent-moss);" @click="resolveRequest(req, 'accepted')" 
                    :disabled="['mutual', 'demand', 'exchange'].includes(req.type) && !req.selectedContact" 
                    :style="{opacity: (['mutual', 'demand', 'exchange'].includes(req.type) && !req.selectedContact) ? 0.3 : 1}">
                    <i class="bi bi-check-lg"></i> {{ store.t('accept') }}
                  </button>
                </template>
              </div>
            </div>

          </div>
        </transition-group>
        <div v-if="pendingRequests.length === 0" style="color:var(--text-muted); font-size:0.85rem; margin-bottom: 1.5rem;">
          {{ store.t('no_pending') }}
        </div>

        <div v-if="acceptedRequests.length > 0" style="color:var(--text-muted); font-size:0.8rem; margin-top:1.5rem; margin-bottom:0.5rem;">{{ store.t('matches') }}</div>
        <transition-group name="inbox-list" tag="div">
          <div class="inbox-item card" v-for="req in acceptedRequests" :key="'acc'+req.id">
            
            <div v-if="req.profile && req.profile.audio" style="display:flex; align-items:center; margin-bottom: 0.5rem; width: 100%;">
              <audio class="audio-minimal" :src="req.profile.audio.url" controls style="flex-grow:1;"></audio>
            </div>

            <div class="telegram-grid" v-if="req.profile && req.profile.media && filterMedia(req.profile.media).length > 0">
              <div class="media-thumb" v-for="m in filterMedia(req.profile.media)" :key="m.url" @click="handleMediaClick(m)">
                 <div v-if="!m.isLoaded" class="media-loader">
                   <i class="bi bi-arrow-repeat spin" style="font-size: 1.5rem; color: var(--text-muted);"></i>
                 </div>
                 <img v-if="m.media_type === 'image'" v-show="m.isLoaded" :src="m.url" @load="m.isLoaded = true" @error="m.isLoaded = true" :class="{'is-blurred': m.blur}">
                 <video v-else-if="m.media_type === 'video'" v-show="m.isLoaded" :src="m.url" @loadeddata="m.isLoaded = true" @error="m.isLoaded = true" muted autoplay loop :class="{'is-blurred': m.blur}"></video>
              </div>
            </div>

            <div class="chip-group" v-if="req.profile && req.profile.tags && req.profile.tags.length > 0">
              <span class="chip require" style="padding: 0.1rem 0.4rem; font-size: 0.65rem;" v-for="tag in req.profile.tags" :key="tag">{{ tag }}</span>
            </div>
            <div style="font-size: 0.85rem;" v-if="req.profile && req.profile.bio">{{ req.profile.bio }}</div>

            <div v-if="req.profile && req.profile.contacts && req.profile.contacts.some(c => !c.is_private && c.type !== 'unknown')" style="margin-top: 0.5rem; display: flex; flex-direction: column; gap: 0.3rem;">
              <div v-for="c in req.profile.contacts.filter(c => !c.is_private && c.type !== 'unknown')" :key="c.value" class="contact-row" style="border-bottom: none; padding: 0;">
                 <i class="bi contact-icon" :class="getContactIcon(c.type)" style="font-size: 0.85rem; width: 16px;"></i>
                 <span class="contact-val" style="font-size: 0.85rem;">{{ c.value }}</span>
                 <i class="bi bi-copy contact-action" @click.stop="copyText(c.value)" :title="store.t('copy')"></i>
              </div>
            </div>

            <div style="border-top: 1px solid var(--border-subtle); padding-top: 0.5rem; margin-top: auto;">
              <div style="font-size: 0.75rem; margin-bottom: 0.2rem; color: var(--accent-moss);">
                {{ req.is_sender ? 'Sent' : 'Received' }} • {{ req.type }} • accepted
              </div>
              
              <div>
                <div style="font-size:0.75rem; color:var(--text-muted); margin-bottom:0.2rem;">Shared Details:</div>
                <div class="offered-item" v-if="req.offered_contact">Offered: {{ req.offered_contact }}</div>
                <div class="offered-item" v-if="req.returned_contact">Returned: {{ req.returned_contact }}</div>
              </div>

              <div style="display:flex; justify-content:flex-end; margin-top: 0.5rem;">
                <button class="footer-action icon-btn" style="color: var(--accent-danger);" @click.stop="deleteMatch(req)" title="Delete Match">
                  <i class="bi bi-trash3"></i>
                </button>
              </div>
            </div>

          </div>
        </transition-group>
      </div>
      
      <div class="resizer-v left" style="position:relative; left:0; width:4px; height:100%; cursor:col-resize; background:var(--border-subtle);" @mousedown="startResize"></div>
      
      <div class="inbox-col" :style="{width: (100 - store.state.inboxSplit) + '%'}">
        <div style="color:var(--text-muted); font-size:0.8rem; margin-top:0.5rem; margin-bottom:0.5rem;">{{ store.t('sent_resolved') }}</div>
        
        <transition-group name="inbox-list" tag="div">
          <div class="inbox-item card" v-for="req in sentRequests" :key="'s'+req.id">
            
            <div v-if="req.profile && req.profile.audio" style="display:flex; align-items:center; margin-bottom: 0.5rem; width: 100%;">
              <audio class="audio-minimal" :src="req.profile.audio.url" controls style="flex-grow:1;"></audio>
            </div>

            <div class="telegram-grid" v-if="req.profile && req.profile.media && filterMedia(req.profile.media).length > 0">
              <div class="media-thumb" v-for="m in filterMedia(req.profile.media)" :key="m.url" @click="handleMediaClick(m)">
                 <div v-if="!m.isLoaded" class="media-loader">
                   <i class="bi bi-arrow-repeat spin" style="font-size: 1.5rem; color: var(--text-muted);"></i>
                 </div>
                 <img v-if="m.media_type === 'image'" v-show="m.isLoaded" :src="m.url" @load="m.isLoaded = true" @error="m.isLoaded = true" :class="{'is-blurred': m.blur}">
                 <video v-else-if="m.media_type === 'video'" v-show="m.isLoaded" :src="m.url" @loadeddata="m.isLoaded = true" @error="m.isLoaded = true" muted autoplay loop :class="{'is-blurred': m.blur}"></video>
              </div>
            </div>

            <div class="chip-group" v-if="req.profile && req.profile.tags && req.profile.tags.length > 0">
              <span class="chip require" style="padding: 0.1rem 0.4rem; font-size: 0.65rem;" v-for="tag in req.profile.tags" :key="tag">{{ tag }}</span>
            </div>
            <div style="font-size: 0.85rem;" v-if="req.profile && req.profile.bio">{{ req.profile.bio }}</div>

            <div v-if="req.profile && req.profile.contacts && req.profile.contacts.some(c => !c.is_private && c.type !== 'unknown')" style="margin-top: 0.5rem; display: flex; flex-direction: column; gap: 0.3rem;">
              <div v-for="c in req.profile.contacts.filter(c => !c.is_private && c.type !== 'unknown')" :key="c.value" class="contact-row" style="border-bottom: none; padding: 0;">
                 <i class="bi contact-icon" :class="getContactIcon(c.type)" style="font-size: 0.85rem; width: 16px;"></i>
                 <span class="contact-val" style="font-size: 0.85rem;">{{ c.value }}</span>
                 <i class="bi bi-copy contact-action" @click.stop="copyText(c.value)" :title="store.t('copy')"></i>
              </div>
            </div>

            <div style="border-top: 1px solid var(--border-subtle); padding-top: 0.5rem; margin-top: auto;">
              <div style="font-size: 0.75rem; margin-bottom: 0.2rem; color: var(--text-muted);">
                Sent • {{ req.type }} • pending
              </div>
            </div>

          </div>
        </transition-group>
        <div v-if="sentRequests.length === 0" style="color:var(--text-muted); font-size:0.85rem; margin-bottom: 1.5rem;">
          {{ store.t('no_pending') }}
        </div>

        <div v-if="declinedRequests.length > 0" style="color:var(--text-muted); font-size:0.8rem; margin-top:1.5rem; margin-bottom:0.5rem;">{{ store.t('no_matches') }}</div>
        <transition-group name="inbox-list" tag="div">
          <div class="inbox-item card" v-for="req in declinedRequests" :key="'d'+req.id">
            
            <div v-if="req.profile && req.profile.audio" style="display:flex; align-items:center; margin-bottom: 0.5rem; width: 100%;">
              <audio class="audio-minimal" :src="req.profile.audio.url" controls style="flex-grow:1;"></audio>
            </div>

            <div class="telegram-grid" v-if="req.profile && req.profile.media && filterMedia(req.profile.media).length > 0">
              <div class="media-thumb" v-for="m in filterMedia(req.profile.media)" :key="m.url" @click="handleMediaClick(m)">
                 <div v-if="!m.isLoaded" class="media-loader">
                   <i class="bi bi-arrow-repeat spin" style="font-size: 1.5rem; color: var(--text-muted);"></i>
                 </div>
                 <img v-if="m.media_type === 'image'" v-show="m.isLoaded" :src="m.url" @load="m.isLoaded = true" @error="m.isLoaded = true" :class="{'is-blurred': m.blur}">
                 <video v-else-if="m.media_type === 'video'" v-show="m.isLoaded" :src="m.url" @loadeddata="m.isLoaded = true" @error="m.isLoaded = true" muted autoplay loop :class="{'is-blurred': m.blur}"></video>
              </div>
            </div>

            <div class="chip-group" v-if="req.profile && req.profile.tags && req.profile.tags.length > 0">
              <span class="chip require" style="padding: 0.1rem 0.4rem; font-size: 0.65rem;" v-for="tag in req.profile.tags" :key="tag">{{ tag }}</span>
            </div>
            <div style="font-size: 0.85rem;" v-if="req.profile && req.profile.bio">{{ req.profile.bio }}</div>

            <div v-if="req.profile && req.profile.contacts && req.profile.contacts.some(c => !c.is_private && c.type !== 'unknown')" style="margin-top: 0.5rem; display: flex; flex-direction: column; gap: 0.3rem;">
              <div v-for="c in req.profile.contacts.filter(c => !c.is_private && c.type !== 'unknown')" :key="c.value" class="contact-row" style="border-bottom: none; padding: 0;">
                 <i class="bi contact-icon" :class="getContactIcon(c.type)" style="font-size: 0.85rem; width: 16px;"></i>
                 <span class="contact-val" style="font-size: 0.85rem;">{{ c.value }}</span>
                 <i class="bi bi-copy contact-action" @click.stop="copyText(c.value)" :title="store.t('copy')"></i>
              </div>
            </div>

            <div style="border-top: 1px solid var(--border-subtle); padding-top: 0.5rem; margin-top: auto;">
              <div style="font-size: 0.75rem; margin-bottom: 0.2rem; color: var(--accent-danger);">
                Sent • {{ req.type }} • {{ store.t('declined') }}
              </div>
              <div style="display:flex; justify-content:flex-end; margin-top: 0.5rem;">
                <button class="footer-action icon-btn" style="color: var(--accent-danger);" @click.stop="deleteMatch(req)" title="Remove">
                  <i class="bi bi-trash3"></i>
                </button>
              </div>
            </div>

          </div>
        </transition-group>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted } from 'vue'
import { useStore } from '../store/state.js'
import api from '../utils/api.js'

const store = useStore()

const validPrivateContacts = computed(() => store.state.myProfile.contacts.filter(c => c.is_private && c.type !== 'unknown' && c.value.trim() !== ''))

const pendingRequests = computed(() => store.state.inbox.filter(r => r.status === 'pending' && !r.is_sender))
const sentRequests = computed(() => store.state.inbox.filter(r => r.status === 'pending' && r.is_sender))
const acceptedRequests = computed(() => store.state.inbox.filter(r => r.status === 'accepted'))
const declinedRequests = computed(() => store.state.inbox.filter(r => r.status === 'declined' && r.is_sender))

function filterMedia(mediaArr) {
  return (mediaArr || []).filter(m => m && m.url);
}

onMounted(() => {
  store.fetchInbox()
  document.addEventListener('click', closeAllDropdowns)
})
onUnmounted(() => document.removeEventListener('click', closeAllDropdowns))

function handleMediaClick(mediaObj) {
  if (mediaObj.blur) mediaObj.blur = false
  else {
    store.state.lightbox.media = mediaObj
    store.state.lightbox.open = true
  }
}

function toggleDropdown(req) {
  const stateBefore = req.openDropdown
  closeAllDropdowns()
  req.openDropdown = !stateBefore
}

function closeAllDropdowns() {
  store.state.inbox.forEach(r => r.openDropdown = false)
}

async function resolveRequest(req, status) {
  req.resolving = true
  req.openDropdown = false
  
  try {
    const payload = {
      status: status,
      returned_contact: req.selectedContact || null
    }
    await api.post(`/inbox/handshakes/${req.id}/resolve`, payload)
    
    setTimeout(async () => {
      req.status = status
      req.resolving = false
      if (status === 'accepted') req.returned_contact = req.selectedContact
      await store.fetchInbox()
    }, 300)
    store.addToast(`Handshake ${status}`, "bi-check2")
  } catch (e) {
    req.resolving = false
    if (e.response && e.response.status === 404) {
      const isBanned = e.response.data.detail && e.response.data.detail.includes('banned')
      store.addToast(e.response.data.detail || "user account has been deleted", isBanned ? "bi-slash-circle" : "bi-info-circle", "danger")
      req.isErrorDeleted = true
      setTimeout(() => {
        store.state.inbox = store.state.inbox.filter(r => r.id !== req.id)
      }, 600)
    } else {
      store.addToast("Failed to resolve handshake", "bi-x-circle")
    }
  }
}

async function deleteMatch(req) {
  try {
    await api.delete(`/inbox/handshakes/${req.id}`)
    store.state.inbox = store.state.inbox.filter(r => r.id !== req.id)
    store.addToast(store.t('match_deleted'), "bi-trash")
  } catch (e) {
    store.addToast("Failed to delete match", "bi-x-circle")
  }
}

let startX, startW
function startResize(e) {
  startX = e.clientX
  startW = store.state.inboxSplit
  document.addEventListener('mousemove', doResize)
  document.addEventListener('mouseup', stopResize)
  document.body.style.userSelect = 'none'
}
function doResize(e) {
  const p = startW + ((e.clientX - startX) / window.innerWidth) * 100
  if (p > 20 && p < 80) store.state.inboxSplit = p
}
function stopResize() {
  document.removeEventListener('mousemove', doResize)
  document.removeEventListener('mouseup', stopResize)
  document.body.style.userSelect = ''
}

const iconMap = { 'email': 'bi-envelope', 'link': 'bi-link-45deg', 'phone': 'bi-telephone', 'unknown': 'bi-question' }
function getContactIcon(type) { return iconMap[type] || 'bi-link-45deg' }

async function copyText(txt) {
  await navigator.clipboard.writeText(txt)
  store.addToast(store.t('copied'), "bi-check2")
}
</script>