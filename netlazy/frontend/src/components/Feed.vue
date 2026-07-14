<template>
  <div class="scrollable-content" style="padding-top:0;">
    <div class="feed-header blurred-header">
      <div style="position: relative; display: flex; align-items: center; width: 100%;">
        <input type="text" class="seamless-input search-header-input" v-model="filterText" :placeholder="store.t('filter_tags_placeholder')" style="padding-right: 2.2rem !important;">
        <i v-if="filterText" class="bi bi-x-lg" style="position: absolute; right: 0.8rem; cursor: pointer; color: var(--text-muted);" @click="filterText = ''"></i>
      </div>
      <div class="tag-scroll-area" @wheel="handleWheel">
        <span class="chip" v-for="tag in visibleSearchTags" :key="tag.name" :class="tag.state" @click="cycleTagState(tag)">
          {{ tag.name }} <i class="bi" :class="getTagStateIcon(tag.state)"></i>
        </span>
      </div>
    </div>

    <div class="grid" @click="closeAllMenus">
      <div class="card" v-for="profile in store.state.feed" :key="profile.user_id">
        
        <div v-if="profile.audio" style="display:flex; align-items:center; margin-bottom: 0.5rem; width: 100%;">
          <audio class="audio-minimal" :src="profile.audio.url" controls style="flex-grow:1;"></audio>
        </div>

        <div class="telegram-grid" v-if="profile.media && profile.media.length > 0">
          <div class="media-thumb" v-for="m in profile.media" :key="m.url" @click="handleMediaClick(m, profile.media)">
             <div v-if="!m.isLoaded" class="media-loader">
               <i class="bi bi-arrow-repeat spin" style="font-size: 1.5rem; color: var(--text-muted);"></i>
             </div>
             <img v-if="m.media_type === 'image'" v-show="m.isLoaded" :src="m.url" @load="m.isLoaded = true" @error="m.isLoaded = true" :class="{'is-blurred': m.blur}">
             <video v-else-if="m.media_type === 'video'" v-show="m.isLoaded" :src="m.url" @loadeddata="m.isLoaded = true" @error="m.isLoaded = true" muted autoplay loop :class="{'is-blurred': m.blur}"></video>
          </div>
        </div>
        
        <div class="chip-group" v-if="profile.tags && profile.tags.length > 0">
          <span class="chip require" style="padding: 0.1rem 0.4rem; font-size: 0.65rem;" v-for="tag in profile.tags" :key="tag">{{ tag }}</span>
        </div>
        <div style="font-size: 0.85rem;" v-if="profile.bio">{{ profile.bio }}</div>

        <div v-if="profile.contacts && profile.contacts.some(c => !c.is_private && c.type !== 'unknown')" style="margin-top: 0.5rem; display: flex; flex-direction: column; gap: 0.3rem; width: 100%; min-width: 0;">
          <div v-for="c in profile.contacts.filter(c => !c.is_private && c.type !== 'unknown')" :key="c.value" class="contact-row" style="border-bottom: none; padding: 0; display: flex; align-items: center; gap: 0.5rem; width: 100%; min-width: 0;">
             <i class="bi contact-icon" :class="getContactIcon(c.type)" style="font-size: 0.85rem; width: 16px; flex-shrink: 0;"></i>
             <span class="contact-val" style="font-size: 0.85rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; cursor: pointer; flex-grow: 1; min-width: 0;" :title="c.value" @click.stop="copyText(c.value)">{{ c.value }}</span>
             <i class="bi bi-copy contact-action" style="flex-shrink: 0;" @click.stop="copyText(c.value)" :title="store.t('copy')"></i>
          </div>
        </div>
        
        <div style="margin-top: auto; display: flex; width: 100%; border-top: 1px solid var(--border-subtle); padding-top: 0.5rem; position: relative;">
          <template v-if="!profile.sent">
            <div style="display: flex; justify-content: space-around; width: 100%; align-items: center;">
              <span :title="validPrivateContacts.length === 0 ? store.t('add_private_contact_tooltip') : 'share'" style="display: inline-flex;">
                <button class="footer-action icon-btn" 
                  :disabled="validPrivateContacts.length === 0 || profile.isSendingReq"
                  :style="{ color: 'var(--accent-info)', opacity: validPrivateContacts.length === 0 ? 0.3 : 1, cursor: validPrivateContacts.length === 0 ? 'not-allowed' : 'pointer' }"
                  @click.stop="openContactSelect(profile, 'share')">
                  <i class="bi" :class="profile.isSendingReq === 'share' ? 'bi-hourglass-split spin' : 'bi-box-arrow-up'"></i>
                </button>
              </span>
              <span :title="validPrivateContacts.length === 0 ? store.t('add_private_contact_tooltip') : 'exchange'" style="display: inline-flex;">
                <button class="footer-action icon-btn" 
                  :disabled="validPrivateContacts.length === 0 || profile.isSendingReq"
                  :style="{ color: 'var(--accent-moss)', opacity: validPrivateContacts.length === 0 ? 0.3 : 1, cursor: validPrivateContacts.length === 0 ? 'not-allowed' : 'pointer' }"
                  @click.stop="openContactSelect(profile, 'exchange')">
                  <i class="bi" :class="profile.isSendingReq === 'exchange' ? 'bi-hourglass-split spin' : 'bi-arrow-left-right'"></i>
                </button>
              </span>
              <button class="footer-action icon-btn" :disabled="profile.isSendingReq" style="color: var(--accent-danger);" @click.stop="sendRequest(profile, 'demand')" title="demand">
                <i class="bi" :class="profile.isSendingReq === 'demand' ? 'bi-hourglass-split spin' : 'bi-box-arrow-in-down'"></i>
              </button>
            </div>
          </template>
          <button v-else class="footer-action" style="color: var(--text-muted); width: 100%; justify-content: center;" disabled>
            <i class="bi bi-check2"></i> {{ store.t('sent', { type: profile.sentType }) }}
          </button>

          <div class="custom-select-menu" v-if="profile.showContactSelect" style="bottom: 100%; top: auto; right: 0; left: auto; min-width: 180px; margin-bottom: 0.5rem;" @click.stop>
            <div style="padding: 0.5rem; font-size: 0.75rem; color:var(--text-muted); border-bottom: 1px solid var(--border-subtle);">
              {{ store.t('select_contact_to', { type: profile.pendingReqType }) }}
            </div>
            <div class="custom-select-option" v-for="c in validPrivateContacts" :key="c.value" @click="sendRequest(profile, profile.pendingReqType, c.value)">
              {{ c.type }}: {{ c.value }}
            </div>
          </div>
        </div>

      </div>
    </div>
    
    <div id="feed-bottom" :style="{'padding-top': store.state.feed.length === 0 ? '4rem' : '2rem', height: '100px', display:'flex', justifyContent:'center', color:'var(--text-muted)'}">
      <span v-if="isLoading"><i class="bi bi-arrow-repeat spin" style="font-size: 1.5rem;"></i></span>
      <span v-else-if="store.state.feed.length === 0">{{ store.t('no_profiles_match') }}</span>
      <span v-else-if="!hasMore">End of feed.</span>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useStore } from '../store/state.js'
import api, { apiWithPoW } from '../utils/api.js'

const store = useStore()
const filterText = ref('')
const isLoading = ref(false)
const hasMore = ref(true)
let currentCursor = null
let observer = null

const validPrivateContacts = computed(() => 
  store.state.myProfile.contacts.filter(c => c.is_private && c.type !== 'unknown' && c.value.trim() !== '')
)

const visibleSearchTags = computed(() => {
  const query = filterText.value.toLowerCase().trim()
  if (!query) {
      return store.state.availableSearchTags.filter(t => !t.hidden)
  }
  return store.state.availableSearchTags.filter(t => t.name.includes(query) || t.aliases.some(a => a.includes(query)))
})

async function fetchFeed(reset = false) {
  if (isLoading.value || (!hasMore.value && !reset)) return
  if (reset) {
    store.state.feed = []
    currentCursor = null
    hasMore.value = true
  }
  
  isLoading.value = true
  try {
    const requires = store.state.availableSearchTags.filter(t => t.state === 'require').map(t => t.name)
    const excludes = store.state.availableSearchTags.filter(t => t.state === 'exclude').map(t => t.name)
    
    const params = new URLSearchParams()
    if (currentCursor) params.append('cursor', currentCursor)
    requires.forEach(r => params.append('requires', r))
    excludes.forEach(e => params.append('excludes', e))

    const res = await api.get(`/feed?${params.toString()}`)
    const batch = res.data
    
    if (batch.length < 20) hasMore.value = false
    if (batch.length > 0) {
      currentCursor = batch[batch.length - 1].created_at
      batch.forEach(p => {
          if (p.media) p.media.forEach(m => m.isLoaded = false)
      })
      store.state.feed.push(...batch)
    }
  } catch (e) {
    store.addToast("Failed to fetch feed", "bi-x-circle")
  } finally {
    isLoading.value = false
  }
}

watch(() => store.state.availableSearchTags, () => {
  fetchFeed(true)
}, { deep: true })

function setupObserver() {
  const options = { root: null, rootMargin: '100px', threshold: 0.1 }
  observer = new IntersectionObserver((entries) => {
    if (entries[0].isIntersecting) fetchFeed()
  }, options)
  
  const bottomEl = document.getElementById('feed-bottom')
  if (bottomEl) observer.observe(bottomEl)
}

onMounted(() => {
  fetchFeed(true)
  setTimeout(setupObserver, 500)
  document.addEventListener('click', closeAllMenus)
})

onUnmounted(() => {
  if (observer) observer.disconnect()
  document.removeEventListener('click', closeAllMenus)
})

function cycleTagState(tagObj) {
  const states = ['neutral', 'require', 'exclude', 'bonus']
  tagObj.state = states[(states.indexOf(tagObj.state) + 1) % states.length]
}

function getTagStateIcon(state) {
  return { 'require': 'bi-plus-lg', 'exclude': 'bi-dash-lg', 'bonus': 'bi-star', 'neutral': '' }[state]
}

function handleWheel(e) {
  e.preventDefault()
  e.currentTarget.scrollLeft += e.deltaY
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

function openContactSelect(profile, type) {
  closeAllMenus()
  profile.pendingReqType = type
  profile.showContactSelect = true
}

async function sendRequest(profile, type, contactValue = null) {
  closeAllMenus()
  store.addToast("Solving Proof of Work...", "bi-hourglass")
  
  try {
    profile.isSendingReq = type
    const payload = {
      receiver_id: profile.user_id,
      type: type,
      offered_contact: contactValue
    }
    
    await apiWithPoW('post', '/inbox/handshakes', payload)
    
    profile.sent = true
    profile.sentType = type
    store.addToast(store.t('sent', { type }), 'bi-send-check')
    
  } catch (e) {
    if (e.response && e.response.data && e.response.data.detail) {
      store.addToast(e.response.data.detail, "bi-x-circle")
    } else {
      store.addToast("Failed to send handshake", "bi-x-circle")
    }
  } finally {
    profile.isSendingReq = null
  }
}

function closeAllMenus() {
  store.state.feed.forEach(p => p.showContactSelect = false)
}

const iconMap = { 'email': 'bi-envelope', 'link': 'bi-link-45deg', 'phone': 'bi-telephone', 'unknown': 'bi-question' }
function getContactIcon(type) { return iconMap[type] || 'bi-link-45deg' }

async function copyText(txt) {
  await navigator.clipboard.writeText(txt)
  store.addToast(store.t('copied'), "bi-check2")
}
</script>