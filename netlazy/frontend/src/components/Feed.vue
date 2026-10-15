<template>
  <div class="scrollable-content" :class="{ 'feed-single-page': store.state.formSlug }" style="padding-top:0;" ref="feedRoot">
    <div class="feed-header" v-if="!store.state.formSlug">
      <div class="feed-search-bar">
        <div style="position: relative; display: flex; align-items: center; width: 100%;">
          <input type="text" ref="searchInput" class="seamless-input search-header-input" :value="filterText" @input="filterText = $event.target.value" @keydown.down.prevent="navigateTags(1)" @keydown.up.prevent="navigateTags(-1)" @keydown.enter.prevent="selectHighlightedTag" :placeholder="store.t('filter_tags_placeholder')" style="padding-right: 2.2rem !important;">
          <transition name="fade">
            <i v-if="filterText" class="bi bi-x-lg search-clear-btn" @click="filterText = ''"></i>
          </transition>
          
          <transition name="dropdown-fade">
            <div class="glass-menu tag-search-dropdown" v-if="filterText && (visibleSearchTags.length > 0 || isV2)" :style="{ top: isMobile ? 'auto' : '100%', bottom: isMobile ? '100%' : 'auto', left: '0', right: '0', maxHeight: '250px', width: '100%' }">
              <div v-if="isV2 && visibleSearchTags.length === 0" class="glass-option dropdown-empty">{{ store.t('no_tags_found') }}</div>
              <transition-group name="tag-list" tag="div" v-else>
                <div class="glass-option dropdown-tag-row" v-for="(tag, idx) in visibleSearchTags.slice(0, 15)" :key="'ac-'+tag.name" :class="{'highlighted-option': idx === highlightIndex, 'mobile-active': activeMobileTag === tag.name}" @click="handleDropdownTagClick(tag)">
                  <span class="dropdown-tag-name"><span class="animated-underline">{{ store.getLocalizedTag(tag.name) }}</span></span>
                  <div class="dropdown-tag-filters" @click.stop>
                      <button class="inline-filter-btn require" :class="{active: tag.state === 'require'}" @click.stop="setTagStateInline(tag, 'require')">
                          <i class="bi bi-plus-lg"></i>
                          <span v-if="store.state.isUserFriendlyInterface">req</span>
                      </button>
                      <button class="inline-filter-btn exclude" :class="{active: tag.state === 'exclude'}" @click.stop="setTagStateInline(tag, 'exclude')">
                          <i class="bi bi-dash-lg"></i>
                          <span v-if="store.state.isUserFriendlyInterface">exc</span>
                      </button>
                      <button class="inline-filter-btn bonus" :class="{active: tag.state === 'bonus'}" @click.stop="setTagStateInline(tag, 'bonus')">
                          <i class="bi bi-chevron-up"></i>
                          <span v-if="store.state.isUserFriendlyInterface">bon</span>
                      </button>
                      <button class="inline-filter-btn abonus" :class="{active: tag.state === 'abonus'}" @click.stop="setTagStateInline(tag, 'abonus')">
                          <i class="bi bi-chevron-down"></i>
                          <span v-if="store.state.isUserFriendlyInterface">pen</span>
                      </button>
                  </div>
                </div>
              </transition-group>
            </div>
          </transition>
        </div>
      </div>
      
      <div class="tag-scroll-area" @scroll="handleTagScroll" @wheel="handleWheel">
        <div class="marquee-content" :class="{ 'is-paused': tagMenu.visible }">
            <span v-if="hasActiveFilters" class="chip tag-reset-btn" @click.stop="resetFilters">
                <i class="bi bi-x"></i>
            </span>
            
            <template v-if="!hasActiveFilters">
              <div class="marquee-group">
                <span class="chip" 
                      v-for="tag in sortedSearchTags" 
                      :key="tag.name" 
                      :class="getTempTagState(tag)" 
                      @mouseenter="openTagMenu($event, tag)"
                      @mouseleave="closeTagMenu"
                      @click.stop="openTagMenu($event, tag)">
                  {{ store.getLocalizedTag(tag.name) }} <i class="bi" :class="getTagStateIcon(getTempTagState(tag))"></i>
                </span>
              </div>
              <div class="marquee-group" aria-hidden="true">
                <span class="chip" 
                      v-for="tag in sortedSearchTags" 
                      :key="'dup1-'+tag.name" 
                      :class="getTempTagState(tag)" 
                      @mouseenter="openTagMenu($event, tag)"
                      @mouseleave="closeTagMenu"
                      @click.stop="openTagMenu($event, tag)">
                  {{ store.getLocalizedTag(tag.name) }} <i class="bi" :class="getTagStateIcon(getTempTagState(tag))"></i>
                </span>
              </div>
              <div class="marquee-group" aria-hidden="true">
                <span class="chip" 
                      v-for="tag in sortedSearchTags" 
                      :key="'dup2-'+tag.name" 
                      :class="getTempTagState(tag)" 
                      @mouseenter="openTagMenu($event, tag)"
                      @mouseleave="closeTagMenu"
                      @click.stop="openTagMenu($event, tag)">
                  {{ store.getLocalizedTag(tag.name) }} <i class="bi" :class="getTagStateIcon(getTempTagState(tag))"></i>
                </span>
              </div>
            </template>

            <template v-else>
              <span class="chip" 
                    v-for="tag in sortedSearchTags" 
                    :key="tag.name" 
                    :class="getTempTagState(tag)" 
                    @mouseenter="openTagMenu($event, tag)"
                    @mouseleave="closeTagMenu"
                    @click.stop="openTagMenu($event, tag)">
                {{ store.getLocalizedTag(tag.name) }} <i class="bi" :class="getTagStateIcon(getTempTagState(tag))"></i>
              </span>
            </template>
        </div>
      </div>
    </div>

    <Teleport to="body">
      <transition name="popover-fade">
        <div v-if="tagMenu.visible"
             class="glass-menu tag-filter-menu"
             :style="{
               left: tagMenu.x + 'px',
               top: tagMenu.y + 'px',
               position: 'fixed',
               display: 'flex',
               gap: '0.4rem',
               padding: '0.6rem 0.8rem',
               flexDirection: 'row',
               '--popover-translate': tagMenu.isBelow ? 'translate(-50%, 0) translateY(8px)' : 'translate(-50%, -100%) translateY(-8px)',
               transform: 'var(--popover-translate) scale(1)',
               transformOrigin: tagMenu.isBelow ? 'top center' : 'bottom center'
             }"
             @mouseleave="closeTagMenu"
             @mouseenter="keepTagMenu"
             @click.stop>
              <div class="filter-col">
                  <button class="footer-action tag-filter-btn filter-require" 
                          :class="{ 'active': tagMenu.pendingState === 'require' }"
                          @click="setTagFilter('require')">
                      <i class="bi bi-plus-lg"></i>
                  </button>
                  <span v-if="store.state.isUserFriendlyInterface" class="filter-label" style="color: var(--accent-moss);">require</span>
              </div>
              <div class="filter-col">
                  <button class="footer-action tag-filter-btn filter-exclude" 
                          :class="{ 'active': tagMenu.pendingState === 'exclude' }"
                          @click="setTagFilter('exclude')">
                      <i class="bi bi-dash-lg"></i>
                  </button>
                  <span v-if="store.state.isUserFriendlyInterface" class="filter-label" style="color: var(--accent-danger);">exclude</span>
              </div>
              <div class="filter-col">
                  <button class="footer-action tag-filter-btn filter-bonus" 
                          :class="{ 'active': tagMenu.pendingState === 'bonus' }"
                          @click="setTagFilter('bonus')">
                      <i class="bi bi-chevron-up"></i>
                  </button>
                  <span v-if="store.state.isUserFriendlyInterface" class="filter-label" style="color: var(--accent-info);">bonus</span>
              </div>
              <div class="filter-col">
                  <button class="footer-action tag-filter-btn filter-abonus" 
                          :class="{ 'active': tagMenu.pendingState === 'abonus' }"
                          @click="setTagFilter('abonus')">
                      <i class="bi bi-chevron-down"></i>
                  </button>
                  <span v-if="store.state.isUserFriendlyInterface" class="filter-label" style="color: var(--accent-earth);">abonus</span>
              </div>
        </div>
      </transition>
    </Teleport>

    <div v-if="store.state.formSlug && formStatus === 'loading'">
      <div style="text-align: center; padding: 4rem 2rem;">
        <i class="bi bi-arrow-repeat spin" style="font-size: 2rem; color: var(--text-muted);"></i>
      </div>
    </div>

    <div class="empty-state form-missing" v-else-if="store.state.formSlug && formStatus === 'missing'">
      <div class="form-missing-code">404</div>
      <p>{{ store.t('form_missing') }}</p>
      <button class="footer-action" style="margin-top: 1rem;" @click="store.openFeed()">
        {{ store.t('back_to_feed') }}
      </button>
    </div>

    <div class="empty-state" v-else-if="store.state.formSlug && formStatus === 'error'">
      <button class="footer-action icon-btn" @click="loadLinkedForm(store.state.formSlug)" style="font-size: 2.5rem; margin-bottom: 1rem; color: var(--text-muted);">
        <i class="bi bi-arrow-clockwise"></i>
      </button>
      <button class="footer-action" style="margin-top: 1rem;" @click="store.openFeed()">
        {{ store.t('back_to_feed') }}
      </button>
    </div>

    <div v-else-if="!store.state.formSlug && store.state.isFeedLoading && store.state.feed.length === 0 && !selfCard && !guestJoinCard">
      <div style="text-align: center; padding: 4rem 2rem;">
        <i class="bi bi-arrow-repeat spin" style="font-size: 2rem; color: var(--text-muted);"></i>
      </div>
    </div>

    <div class="empty-state" v-else-if="!store.state.formSlug && !isLoading && store.state.feed.length === 0 && !selfCard && !guestJoinCard">
      <button class="footer-action icon-btn" @click="reloadFeed" style="font-size: 2.5rem; margin-bottom: 1rem; color: var(--text-muted);">
        <i class="bi bi-arrow-clockwise"></i>
      </button>
      <h3>{{ store.t('no_profiles_match') }}</h3>
      <button class="footer-action" style="margin-top: 1rem;" @click="resetFilters" v-if="hasActiveFilters">
        <i class="bi bi-arrow-counterclockwise"></i> {{ store.t('reset_tags') }}
      </button>
    </div>

    <div v-else class="feed-results" :class="{ 'feed-results-single': store.state.formSlug }">
    <div class="masonry-grid" @click="closeAllMenus">
      <div class="masonry-col" v-for="(col, colIdx) in masonryColumns" :key="colIdx">
        <div class="card" :class="{ 'card-self': profile.isSelf, 'card-guest': profile.isGuestJoin, 'card-loading': profile.isFeedLoadingMark, 'card-linkable': !!profileSlug(profile) }" v-for="profile in col" :key="profile.id || profile.user_id" :style="{ zIndex: (!isMobile && profile.showContactSelect) ? 100 : 1, position: 'relative' }" @click="copyProfileLink($event, profile)">
          <div v-if="profile.isFeedLoadingMark" class="feed-loading-card">
            <i class="bi bi-arrow-repeat spin"></i>
          </div>
          <div v-else-if="profile.isGuestJoin" class="guest-join">
            <button class="create-btn" @click.stop="store.createAccount">
              <i class="bi bi-lightning-charge"></i> {{ store.t('create_account') }}
            </button>
          </div>
          <template v-else>
          <div v-if="profile.audio" style="display:flex; align-items:center; margin-bottom: 0.5rem; width: 100%;" v-intersect="() => store.loadProfileMedia(profile.audio, profile)">
            <audio v-if="profile.audio.blobUrl" class="audio-minimal" :src="profile.audio.blobUrl" @error="handleMediaError(profile, profile.audio)" controls style="flex-grow:1;"></audio>
            <div v-else class="media-loader skeleton" style="height: 32px; flex-grow: 1; border-radius: var(--radius-sm);"></div>
          </div>

          <div class="feed-media-stack" :data-count="profile.media.length" v-if="profile.media && profile.media.length > 0">
            <div class="feed-media-item" v-for="m in profile.media" :key="m.blobUrl || m.url" @click="handleMediaClick(m, profile.media)" v-intersect="() => store.loadProfileMedia(m, profile)">
               <div v-if="!m.isLoaded" class="media-loader skeleton" style="border-radius: 0;"></div>
               <img v-if="m.media_type === 'image' && m.blobUrl" v-show="m.isLoaded" :src="m.blobUrl" @error="handleMediaError(profile, m)" @load="m.isLoaded = true" :class="{'is-blurred': m.blur, 'cdn-obfuscated': m.isLegacy}">
               <video v-else-if="m.media_type === 'video' && m.blobUrl" v-show="m.isLoaded" :src="m.blobUrl" @error="handleMediaError(profile, m)" @loadeddata="m.isLoaded = true" muted autoplay loop playsinline :class="{'is-blurred': m.blur, 'cdn-obfuscated': m.isLegacy}"></video>
            </div>
          </div>
          
          <div class="chip-group" v-if="profile.tags && profile.tags.length > 0">
            <span class="chip require" style="padding: 0.1rem 0.4rem; font-size: 0.65rem;" v-for="tag in profile.tags" :key="tag">{{ store.getLocalizedTag(tag) }}</span>
          </div>
          <div class="card-bio" v-if="displayBio(profile.bio)">{{ displayBio(profile.bio) }}</div>

          <div v-if="profile.contacts && profile.contacts.some(c => !c.is_private && c.type !== 'unknown')" style="margin-top: 0.5rem; display: flex; flex-direction: column; gap: 0.3rem; width: 100%; min-width: 0;">
            <template v-for="c in profile.contacts" :key="c.value">
              <div v-if="!c.is_private && c.type !== 'unknown'" class="contact-row" style="border-bottom: none; padding: 0; display: flex; align-items: center; gap: 0.5rem; width: 100%; min-width: 0;">
                 <i class="bi contact-icon" :class="getContactIcon(c.type)" style="font-size: 0.85rem; width: 16px; flex-shrink: 0;"></i>
                 <a v-if="contactHref(c)" class="contact-val contact-link" :href="contactHref(c)" target="_blank" rel="noopener noreferrer" @click.stop>{{ c.value }}</a>
                 <span v-else class="contact-val" @click.stop="copyText(c.value)">{{ c.value }}</span>
                 <i class="bi bi-copy contact-action" style="flex-shrink: 0;" @click.stop="copyText(c.value)"></i>
              </div>
            </template>
          </div>
          
          <div v-if="showProfileActions(profile)" class="card-actions">
            <template v-if="!profile.sent">
              <div style="display: flex; justify-content: space-around; width: 100%; align-items: center;">
                <span style="display: inline-flex; flex-direction: column; align-items: center;">
                  <button class="footer-action icon-btn" 
                    style="color: var(--accent-info);"
                    :disabled="validPrivateContacts.length === 0 || profile.isSendingReq"
                    @click.stop="handleContactButtonClick(profile, 'share', $event)">
                    <i class="bi" :class="profile.isSendingReq === 'share' ? 'bi-hourglass-split spin' : 'bi-box-arrow-up'"></i>
                  </button>
                  <span v-if="store.state.isUserFriendlyInterface" style="font-size: 0.65rem; color: var(--accent-info); opacity: 0.8; margin-top: 0.1rem;">{{ store.t('uf_action_share') }}</span>
                </span>
                <span style="display: inline-flex; flex-direction: column; align-items: center;">
                  <button class="footer-action icon-btn" 
                    style="color: var(--accent-moss);"
                    :disabled="validPrivateContacts.length === 0 || profile.isSendingReq"
                    @click.stop="handleContactButtonClick(profile, 'exchange', $event)">
                    <i class="bi" :class="profile.isSendingReq === 'exchange' ? 'bi-hourglass-split spin' : 'bi-arrow-left-right'"></i>
                  </button>
                  <span v-if="store.state.isUserFriendlyInterface" style="font-size: 0.65rem; color: var(--accent-moss); opacity: 0.8; margin-top: 0.1rem;">{{ store.t('uf_action_exchange') }}</span>
                </span>
                <span style="display: inline-flex; flex-direction: column; align-items: center;">
                  <button class="footer-action icon-btn" :disabled="profile.isSendingReq" style="color: var(--accent-danger);" @click.stop="handleContactButtonClick(profile, 'demand', $event)">
                    <i class="bi" :class="profile.isSendingReq === 'demand' ? 'bi-hourglass-split spin' : 'bi-box-arrow-in-down'"></i>
                  </button>
                  <span v-if="store.state.isUserFriendlyInterface" style="font-size: 0.65rem; color: var(--accent-danger); opacity: 0.8; margin-top: 0.1rem;">{{ store.t('uf_action_demand') }}</span>
                </span>
              </div>
            </template>
            <div v-else style="display: flex; flex-direction: column; align-items: center; width: 100%;">
              <button class="footer-action" style="color: var(--text-muted); width: 100%; justify-content: center;" disabled>
                <i class="bi bi-check2"></i> {{ store.t('sent', { type: profile.sentType }) }}
              </button>
            </div>

            <transition name="dropdown-fade">
              <div class="glass-menu" 
                   v-if="!isMobile && profile.showContactSelect" 
                   :style="profile.popoverPosition === 'top' ? { bottom: '100%', top: 'auto', right: 0, left: 'auto', width: 'max-content', minWidth: '260px', maxWidth: 'calc(100vw - 4rem)', marginBottom: '0.5rem' } : { top: '100%', bottom: 'auto', right: 0, left: 'auto', width: 'max-content', minWidth: '260px', maxWidth: 'calc(100vw - 4rem)', marginTop: '0.5rem' }" 
                   @click.stop>
                
                <div class="glass-contacts-list" v-if="profile.pendingReqType !== 'demand'">
                  <div class="glass-option" v-for="c in validPrivateContacts" :key="c.value" @click.stop="toggleProfileContact(profile, c.value)">
                    <span class="animated-underline">{{ c.type }}: {{ c.value }}</span>
                    <i class="bi" :class="profile.selectedContacts && profile.selectedContacts.includes(c.value) ? 'bi-check2' : ''" style="color: var(--accent-moss); width: 16px; display: inline-block; flex-shrink: 0;"></i>
                  </div>
                  <div v-if="validPrivateContacts.length === 0" style="padding: 0.8rem 1rem; text-align: center; color: var(--text-muted); font-style: italic; font-size: 0.85rem;">
                    {{ store.t('no_valid_private') }}
                  </div>
                </div>
                
                <div style="padding: 0.5rem 1rem;" :style="{ borderTop: (profile.pendingReqType !== 'demand' && validPrivateContacts.length > 0) ? '1px dashed rgba(128,128,128,0.2)' : 'none' }">
                  <input type="text" class="seamless-input" v-model="profile.pendingMessage" :placeholder="store.t('message_placeholder')" maxlength="100" style="background: rgba(128,128,128,0.08); padding: 0.6rem; border-radius: var(--radius-pill); font-size: 0.85rem; width: 100%;">
                </div>

                <div style="padding: 0.5rem 1rem; text-align: right;">
                  <button class="icon-btn" 
                    style="background: none; border: none;" 
                    :style="{ color: profile.pendingReqType === 'share' ? 'var(--accent-info)' : (profile.pendingReqType === 'demand' ? 'var(--accent-danger)' : 'var(--accent-moss)') }" 
                    @click.stop="sendRequest(profile, profile.pendingReqType)" 
                    :disabled="(profile.pendingReqType !== 'demand' && (!profile.selectedContacts || profile.selectedContacts.length === 0)) || profile.isSendingReq">
                    <i class="bi" :class="profile.isSendingReq === profile.pendingReqType ? 'bi-hourglass-split spin' : 'bi-send-fill'"></i>
                  </button>
                </div>
              </div>
            </transition>
          </div>
          </template>

        </div>
      </div>
    </div>
      <div v-if="store.state.formSlug && guestJoinCard" class="guest-form-join">
        <button class="create-btn" @click="store.createAccount">
          <i class="bi bi-lightning-charge"></i> {{ store.t('create_account') }}
        </button>
      </div>
    </div>
    
    <div id="feed-bottom" v-show="!store.state.formSlug && (store.state.feed.length > 0 || isLoading)" :style="{'padding-top': '2rem', height: '100px', display:'flex', justifyContent:'center', color:'var(--text-muted)'}">
      <span v-if="isLoading && store.state.feed.length > 0"><i class="bi bi-arrow-repeat spin" style="font-size: 1.5rem;"></i></span>
      <span v-else-if="!hasMore">{{ store.t('end_of_feed') }}</span>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch, onActivated, nextTick } from 'vue'
import { useStore, profileHasContent, tagsMatchingQuery } from '../store/state.js'
import api, { apiWithPoW } from '../utils/api.js'
import { displayBio } from '../utils/bio.js'
import { contactHref } from '../utils/contact.js'

const store = useStore()
const isV2 = computed(() => store.state.interfaceVersion === '2')
const linkedProfile = ref(null)
const formStatus = ref('idle')
let formRequest = 0
const selfCard = computed(() => {
  if (!store.state.isRegistered || !isV2.value || !profileHasContent(store.state.myProfile)) return null
  return {
    ...store.state.myProfile,
    user_id: store.state.myProfile.user_id || store.state.userId || 'self',
    isSelf: true
  }
})
const guestJoinCard = computed(() => {
  if (store.state.isRegistered) return null
  return { user_id: 'guest-join', isGuestJoin: true }
})
const feedRoot = ref(null)
const filterText = ref('')
const isLoading = ref(false)
const hasMore = ref(true)
let observer = null
let feedAbortController = null
let feedRequest = 0

const isMobile = ref(window.innerWidth <= 768)
const highlightIndex = ref(-1)
const columnsCount = ref(1)

const tagMenu = ref({ visible: false, x: 0, y: 0, tagName: null, pendingState: null, isBelow: false });
let tagMenuTimeout = null;

const activeMobileTag = ref(null);

function updateColumnsCount() {
  if (!feedRoot.value) return;
  const width = feedRoot.value.clientWidth;
  const padding = isMobile.value ? 2 * 1.5 * 16 : 2 * 3 * 16; 
  const availableWidth = width - padding;
  let cols = Math.floor((availableWidth + 24) / (280 + 24));
  if (cols < 1) cols = 1;
  columnsCount.value = cols;
}

const masonryColumns = computed(() => {
  const columnTotal = store.state.formSlug ? 1 : columnsCount.value
  const cols = Array.from({length: columnTotal}, () => []);
  const heights = Array.from({length: columnTotal}, () => 0);
  
  const profiles = []
  if (store.state.formSlug) {
    if (linkedProfile.value) profiles.push(linkedProfile.value)
  } else {
    if (guestJoinCard.value) profiles.push(guestJoinCard.value)
    else if (selfCard.value) profiles.push(selfCard.value)
    if (isLoading.value && store.state.feed.length === 0 && (selfCard.value || guestJoinCard.value)) {
      profiles.push({ user_id: 'feed-loading', isFeedLoadingMark: true })
    }
    store.state.feed.forEach(profile => {
      if (!selfCard.value || !profile.id || profile.id !== selfCard.value.id) profiles.push(profile)
    })
  }

  profiles.forEach((profile, index) => {
    let h = 80;
    if (profile.audio) h += 40;
    if (profile.media && profile.media.length > 0) {
      h += profile.media.length === 1 ? 340 : 250;
    }
    if (profile.tags && profile.tags.length > 0) h += 30;
    if (profile.bio) {
      const lines = String(profile.bio).split('\n').length
      h += Math.min(lines * 22 + profile.bio.length * 0.12, 360)
    }
    if (profile.contacts && profile.contacts.length > 0) h += profile.contacts.filter(c => !c.is_private && c.type !== 'unknown').length * 28;
    h += 50;
    
    let minIdx = 0;
    if (!(index === 0 && (profile.isSelf || profile.isGuestJoin))) {
      let minH = heights[0];
      for (let i = 1; i < heights.length; i++) {
          if (heights[i] < minH) {
              minH = heights[i];
              minIdx = i;
          }
      }
    }
    
    cols[minIdx].push(profile);
    heights[minIdx] += h;
  });
  return cols;
});

function getTempTagState(tag) {
    if (tagMenu.value.visible && tagMenu.value.tagName === tag.name && tagMenu.value.pendingState !== undefined) {
        return tagMenu.value.pendingState;
    }
    return tag.state;
}

async function openTagMenu(e, tag) {
    if (tagMenuTimeout) {
        clearTimeout(tagMenuTimeout);
        tagMenuTimeout = null;
    }
    
    if (tagMenu.value.visible && tagMenu.value.tagName === tag.name) {
        return;
    }
    
    if (tagMenu.value.visible && tagMenu.value.tagName && tagMenu.value.tagName !== tag.name) {
        applyTagMenuState();
    }

    const rect = e.currentTarget.getBoundingClientRect();
    const isBelow = !isMobile.value; 
    let x = rect.left + rect.width / 2;
    let y = isBelow ? rect.bottom : rect.top;

    tagMenu.value = {
        visible: true,
        tagName: tag.name,
        pendingState: tag.state,
        x: x,
        y: y,
        isBelow: isBelow
    };
    
    await nextTick();
    const menuEl = document.querySelector('.tag-filter-menu');
    if (menuEl) {
        const menuWidth = menuEl.offsetWidth;
        const padding = 12;
        let clampedX = x;
        if (clampedX - menuWidth / 2 < padding) clampedX = padding + menuWidth / 2;
        else if (clampedX + menuWidth / 2 > window.innerWidth - padding) clampedX = window.innerWidth - padding - menuWidth / 2;
        tagMenu.value.x = clampedX;
    }
}

function keepTagMenu() {
    if (tagMenuTimeout) {
        clearTimeout(tagMenuTimeout);
        tagMenuTimeout = null;
    }
}

function closeTagMenu() {
    if (tagMenuTimeout) clearTimeout(tagMenuTimeout);
    tagMenuTimeout = setTimeout(() => {
        applyTagMenuState();
    }, 250);
}

function applyTagMenuState() {
    if (tagMenu.value.tagName) {
        const tagObj = store.state.availableSearchTags.find(t => t.name === tagMenu.value.tagName);
        if (tagObj && tagObj.state !== tagMenu.value.pendingState) {
            tagObj.state = tagMenu.value.pendingState;
        }
        tagMenu.value.visible = false;
        setTimeout(() => {
            if (!tagMenu.value.visible) tagMenu.value.tagName = null;
        }, 300);
    }
}

function setTagFilter(state) {
    if (!tagMenu.value.tagName) return;
    if (tagMenu.value.pendingState === state) {
        tagMenu.value.pendingState = 'neutral';
    } else {
        tagMenu.value.pendingState = state;
    }
}

function handleGlobalClickForTagMenu(e) {
    if (tagMenu.value.visible) {
        const menuEl = document.querySelector('.tag-filter-menu');
        if (menuEl && menuEl.contains(e.target)) return;
        applyTagMenuState();
    }
    activeMobileTag.value = null;
}

const validPrivateContacts = computed(() => 
  store.state.myProfile.contacts.filter(c => c.is_private && c.type !== 'unknown' && c.value.trim() !== '')
)

const activeFiltersString = computed(() => {
    return store.state.availableSearchTags
        .filter(t => t.state !== 'neutral')
        .map(t => t.name + ':' + t.state)
        .sort()
        .join(',')
})

const hasActiveFilters = computed(() => {
  return store.state.availableSearchTags.some(t => t.state !== 'neutral')
})

const visibleSearchTags = computed(() => tagsMatchingQuery(store.state.availableSearchTags, filterText.value))

const sortedSearchTags = computed(() => {
  const order = { 'require': 1, 'exclude': 2, 'bonus': 3, 'abonus': 4, 'neutral': 5 };
  const activeTags = store.state.availableSearchTags.filter(t => t.state !== 'neutral');
  activeTags.sort((a, b) => order[a.state] - order[b.state]);
  
  const neutralTags = store.state.availableSearchTags.filter(t => t.state === 'neutral' && !t.hidden);
  
  return activeTags.concat(neutralTags);
})

function handleResize() {
  isMobile.value = window.innerWidth <= 768
  updateColumnsCount()
}

function navigateTags(dir) {
    const list = visibleSearchTags.value.slice(0, 15);
    if (!list.length) return;
    highlightIndex.value = (highlightIndex.value + dir + list.length) % list.length;
}

function selectHighlightedTag() {
    const list = visibleSearchTags.value.slice(0, 15);
    if (highlightIndex.value >= 0 && highlightIndex.value < list.length) {
        selectTagFromAutocomplete(list[highlightIndex.value]);
    }
}

watch(filterText, () => { highlightIndex.value = -1; activeMobileTag.value = null; });

function animateAndSelectTag(e, tag) {
  const el = e.currentTarget;
  el.classList.add('clicked');
  setTimeout(() => {
    selectTagFromAutocomplete(tag);
    el.classList.remove('clicked');
  }, 150);
}

function handleDropdownTagClick(tag) {
  if (isMobile.value) {
    if (activeMobileTag.value === tag.name) {
      activeMobileTag.value = null;
    } else {
      activeMobileTag.value = tag.name;
    }
  } else {
    selectTagFromAutocomplete(tag);
  }
}

function selectTagFromAutocomplete(tag) {
  if (tag.state === 'neutral') tag.state = 'require';
  filterText.value = '';
  activeMobileTag.value = null;
}

function setTagStateInline(tag, state) {
  if (tag.state === state) {
    tag.state = 'neutral';
  } else {
    tag.state = state;
  }
  activeMobileTag.value = null;
}

function resetFilters() {
  filterText.value = '';
  store.state.availableSearchTags.forEach(t => t.state = 'neutral');
}

function reloadFeed() {
  fetchFeed(true)
}

async function handleMediaError(profile, m) {
    if (m.isErrorHandled) return;
    m.isErrorHandled = true;
    m.isLoaded = false;
    m.blobUrl = null;
}

async function loadLinkedForm(slug) {
  const requestId = ++formRequest
  if (!slug) {
    formStatus.value = 'idle'
    linkedProfile.value = null
    return
  }
  formStatus.value = 'loading'
  linkedProfile.value = null
  try {
    const res = await api.get(`/feed/form/${encodeURIComponent(slug)}`)
    if (requestId !== formRequest) return
    const profile = res.data
    profile.isSelf = Boolean(profile.id && store.state.myProfile.id && profile.id === store.state.myProfile.id)
    if (profile.media) profile.media.forEach(m => { m.isLoaded = false })
    profile.selectedContacts = []
    profile.showContactSelect = false
    profile.pendingMessage = ''
    profile.popoverPosition = 'bottom'
    linkedProfile.value = profile
    formStatus.value = 'ready'
  } catch (e) {
    if (requestId !== formRequest) return
    linkedProfile.value = null
    formStatus.value = e.response && e.response.status === 404 ? 'missing' : 'error'
  }
}

watch(() => store.state.myProfile.id, (id) => {
  const profile = linkedProfile.value
  if (profile && id) profile.isSelf = profile.id === id
})

watch(() => store.state.formSlug, (slug) => {
  loadLinkedForm(slug)
}, { immediate: true })

function showProfileActions(profile) {
  if (!profile || profile.isGuestJoin || profile.isFeedLoadingMark) return false
  if (store.state.formSlug) return store.state.isRegistered
  return !profile.isSelf
}

function profileSlug(profile) {
  if (profile.form) return profile.form
  if (profile.primary_form) return profile.primary_form
  const forms = profile.forms || []
  return forms.length ? forms[forms.length - 1] : null
}

function blocksProfileCopy(target) {
  return Boolean(target.closest('button, a, input, textarea, audio, video, .feed-media-item, .contact-row, .glass-menu'))
}

async function copyProfileLink(event, profile) {
  if (profile.isGuestJoin || profile.isFeedLoadingMark) return
  if (profile.isSelf) {
    if (blocksProfileCopy(event.target)) return
  } else if (event.target !== event.currentTarget) {
    return
  }
  const slug = profileSlug(profile)
  if (!slug) {
    store.addToast(store.t('form_not_shared'), 'bi-link-45deg')
    return
  }
  await navigator.clipboard.writeText(store.profileFormUrl(slug))
  store.addToast(store.t('link_copied'), 'bi-check2')
}

async function fetchFeed(reset = false) {
  if (store.state.formSlug) return
  if (reset) {
    if (feedAbortController) feedAbortController.abort();
    feedAbortController = new AbortController();
    hasMore.value = true;
  } else if (isLoading.value || !hasMore.value) {
    return;
  }

  const requestId = ++feedRequest
  if (reset || store.state.feed.length === 0) store.state.isFeedLoading = true;
  isLoading.value = true;
  try {
    const requires = store.state.availableSearchTags.filter(t => t.state === 'require').map(t => t.name)
    const excludes = store.state.availableSearchTags.filter(t => t.state === 'exclude').map(t => t.name)
    const bonus = store.state.availableSearchTags.filter(t => t.state === 'bonus').map(t => t.name)
    const abonus = store.state.availableSearchTags.filter(t => t.state === 'abonus').map(t => t.name)
    
    const seen_ids = reset ? [] : store.state.feed.map(p => p.id).filter(Boolean);
    if (!feedAbortController) feedAbortController = new AbortController();
    
    const payload = {
      seen_ids,
      requires,
      excludes,
      bonus,
      abonus
    };

    const res = await api.post(`/feed/search`, payload, { signal: feedAbortController.signal })
    if (requestId !== feedRequest) return
    const batch = res.data
    
    if (batch.length < 20) hasMore.value = false
    batch.forEach(p => {
        if (p.media) p.media.forEach(m => m.isLoaded = false)
        p.selectedContacts = []
        p.showContactSelect = false
        p.pendingMessage = ""
        p.popoverPosition = 'bottom'
    })
    if (reset) store.state.feed = batch
    else if (batch.length > 0) store.state.feed.push(...batch)
  } catch (e) {
    if (requestId !== feedRequest) return
    if (e.name !== 'CanceledError') {
      store.addToast("Failed to fetch feed", "bi-x-circle")
    }
  } finally {
    if (requestId === feedRequest) {
      isLoading.value = false
      store.state.isFeedLoading = false
    }
  }
}

let lastFilterString = null;
watch(activeFiltersString, (newVal) => {
  if (lastFilterString !== null && newVal !== lastFilterString) {
    store.syncViewToUrl(true);
    fetchFeed(true);
  }
  lastFilterString = newVal;
})

function setupObserver() {
  const options = { root: null, rootMargin: '100px', threshold: 0.1 }
  observer = new IntersectionObserver((entries) => {
    if (entries[0].isIntersecting) fetchFeed()
  }, options)
  
  const bottomEl = document.getElementById('feed-bottom')
  if (bottomEl) observer.observe(bottomEl)
}

function handleTagScroll(e) {
    const el = e ? (e.currentTarget || e.target) : document.querySelector('.tag-scroll-area');
    if (!el) return;
    
    const isMarquee = !hasActiveFilters.value;

    if (isMarquee) {
        const groupEl = el.querySelector('.marquee-group');
        if (groupEl) {
            const groupWidth = groupEl.offsetWidth + 8;
            if (el.scrollLeft >= groupWidth * 2) {
                el.scrollLeft -= groupWidth;
            } else if (el.scrollLeft <= 0) {
                el.scrollLeft += groupWidth;
            }
        }
    }
}

watch(hasActiveFilters, () => {
    nextTick(() => {
        const area = document.querySelector('.tag-scroll-area');
        if (area) {
            area.scrollLeft = 0;
            handleTagScroll({ currentTarget: area });
        }
    });
});

function handlePtrRefresh() {
  if (store.state.formSlug) loadLinkedForm(store.state.formSlug)
  else fetchFeed(true)
}

onMounted(() => {
  lastFilterString = activeFiltersString.value;
  if (!store.state.formSlug && store.state.feed.length === 0) {
    fetchFeed(true)
  }
  setTimeout(setupObserver, 500)
  document.addEventListener('click', closeAllMenus)
  document.addEventListener('click', handleGlobalClickForTagMenu)
  window.addEventListener('resize', handleResize)
  window.addEventListener('netlazy:ptr-refresh', handlePtrRefresh)
  setTimeout(updateColumnsCount, 50)
  
  const area = document.querySelector('.tag-scroll-area');
  if (area) handleTagScroll({ currentTarget: area });
})

onUnmounted(() => {
  if (observer) observer.disconnect()
  if (feedAbortController) feedAbortController.abort()
  document.removeEventListener('click', closeAllMenus)
  document.removeEventListener('click', handleGlobalClickForTagMenu)
  window.removeEventListener('resize', handleResize)
  window.removeEventListener('netlazy:ptr-refresh', handlePtrRefresh)
})

onActivated(() => {
  if (feedRoot.value) {
    const videos = feedRoot.value.querySelectorAll('video')
    videos.forEach(v => {
      if (v.paused) v.play().catch(() => {})
    })
  }
})

function getTagStateIcon(state) {
  return { 'require': 'bi-plus-lg', 'exclude': 'bi-dash-lg', 'bonus': 'bi-chevron-up', 'abonus': 'bi-chevron-down', 'neutral': '' }[state]
}

function handleWheel(e) {
  if (Math.abs(e.deltaY) > Math.abs(e.deltaX)) {
    e.preventDefault();
    e.currentTarget.scrollBy({ left: e.deltaY > 0 ? 250 : -250, behavior: 'smooth' });
  }
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

function handleContactButtonClick(profile, type, event) {
  if (!store.state.isRegistered) {
    store.createAccount()
    return
  }
  if (isMobile.value) {
    openContactSelect(profile, type)
  } else {
    if (event && event.currentTarget) {
      const cardEl = event.currentTarget.closest('.card');
      if (cardEl) {
        const cardRect = cardEl.getBoundingClientRect();
        const spaceBelow = window.innerHeight - cardRect.bottom;
        const spaceAbove = cardRect.top;
        profile.popoverPosition = spaceAbove > spaceBelow && spaceBelow < 280 ? 'top' : 'bottom';
      }
    } else {
      profile.popoverPosition = 'bottom';
    }

    const isSameType = profile.pendingReqType === type && profile.showContactSelect;
    closeAllMenus();
    if (!isSameType) {
      profile.selectedContacts = [];
      profile.pendingReqType = type;
      profile.pendingMessage = "";
      profile.showContactSelect = true;
    }
  }
}

function openContactSelect(profile, type) {
  closeAllMenus()
  store.state.contactSelect = {
    open: true,
    profile: profile,
    type: type,
    selectedContacts: [],
    message: '',
    isSending: false
  }
}

function toggleProfileContact(profile, val) {
  if (!profile.selectedContacts) profile.selectedContacts = [];
  const idx = profile.selectedContacts.indexOf(val);
  if (idx === -1) profile.selectedContacts.push(val);
  else profile.selectedContacts.splice(idx, 1);
}

async function sendRequest(profile, type, contactValue = null) {
  closeAllMenus()
  if (type !== 'demand' && !contactValue && profile.selectedContacts) {
     contactValue = profile.selectedContacts.join(', ');
  }
  
  store.addToast("Solving Proof of Work...", "bi-hourglass")
  try {
    profile.isSendingReq = type
    const payload = {
      receiver_id: profile.id,
      type: type,
      offered_contact: type === 'demand' ? null : contactValue,
      message: profile.pendingMessage ? profile.pendingMessage.trim() : null
    }
    
    await apiWithPoW('post', '/inbox/handshakes', payload)
    
    profile.sent = true
    profile.sentType = type
    store.addToast(store.t('sent', { type }), 'bi-send-check')
    store.fetchInbox(true)
    
  } catch (e) {
    if (e.response && e.response.data && e.response.data.detail) {
      store.addToast(e.response.data.detail, "bi-x-circle")
    } else {
      store.addToast("Failed to send handshake", "bi-x-circle")
    }
  } finally {
    profile.isSendingReq = null
    profile.showContactSelect = false
    profile.pendingMessage = ""
  }
}

function closeAllMenus() {
  filterText.value = '';
  store.state.feed.forEach(p => p.showContactSelect = false)
  if (linkedProfile.value) linkedProfile.value.showContactSelect = false
}

const iconMap = { 'email': 'bi-envelope', 'link': 'bi-link-45deg', 'phone': 'bi-telephone', 'unknown': 'bi-question' }
function getContactIcon(type) { return iconMap[type] || 'bi-link-45deg' }

async function copyText(txt) {
  await navigator.clipboard.writeText(txt)
  store.addToast(store.t('copied'), "bi-check2")
}
</script>