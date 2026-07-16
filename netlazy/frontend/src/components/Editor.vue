<template>
  <div class="editor-layout" ref="editorRoot">
    <div class="tag-library-pane">
      <div class="tag-library-header blurred-header" style="position: sticky; top: 0; z-index: 10;">
        <i class="bi bi-search" style="color:var(--text-muted); margin-right: 0.5rem;"></i>
        <div style="position: relative; display: flex; align-items: center; flex-grow: 1;">
          <input type="text" class="seamless-input search-header-input" v-model="store.state.tagSearchQuery" :placeholder="store.t('search_tags')" style="padding-right: 1.5rem;">
          <i v-if="store.state.tagSearchQuery" class="bi bi-x-lg search-clear-btn" @click="store.state.tagSearchQuery = ''"></i>
        </div>
      </div>
      
      <div class="tag-library-list chip-group" id="lib-tags-zone" style="padding: 1.5rem; align-content: flex-start;">
        <div v-if="store.state.availableSearchTags.length === 0" style="width: 100%; text-align: center; color: var(--text-muted);">
          <i class="bi bi-arrow-repeat spin" style="font-size: 1.5rem;"></i>
        </div>
        <span class="chip" 
              :class="{require: store.state.myProfile.tags.includes(tag.name)}" 
              v-for="tag in filteredTags" 
              :key="tag.name" 
              @click="toggleTag(tag.name)">
          {{ store.getLocalizedTag(tag.name) }}
          <i class="bi bi-check2" v-if="store.state.myProfile.tags.includes(tag.name)"></i>
        </span>
        <div v-if="store.state.availableSearchTags.length > 0 && filteredTags.length === 0" class="muted-italic" style="color:var(--text-muted); font-size:0.85rem;">
          {{ store.t('no_tags_found') }}
        </div>
      </div>
    </div>

    <div class="profile-workspace-pane" :class="{collapsed: store.state.isWorkspaceCollapsed, 'is-resizing': isResizingWorkspace}" :style="{width: store.state.isWorkspaceCollapsed ? '0px' : store.state.workspaceWidth + 'px'}" tabindex="0" @paste="handlePaste">
      <div class="resizer-v left" @mousedown="startResize" v-show="!store.state.isWorkspaceCollapsed"></div>
      
      <button class="workspace-toggle-btn" @click="store.state.isWorkspaceCollapsed = !store.state.isWorkspaceCollapsed" :title="store.state.isWorkspaceCollapsed ? store.t('my_profile') : store.t('cancel')">
        <i class="bi" :class="store.state.isWorkspaceCollapsed ? 'bi-chevron-left' : 'bi-chevron-right'"></i>
      </button>
      
      <div class="workspace-scroll-area" v-show="!store.state.isWorkspaceCollapsed"
           :class="{'drag-over-files': isDraggingFiles}"
           @dragenter.prevent="workspaceDragEnter"
           @dragover.prevent="workspaceDragOver"
           @dragleave.prevent="workspaceDragLeave"
           @drop.prevent="workspaceDrop">

        <div v-if="store.state.isProfileLoading" style="text-align: center; padding: 2rem;">
          <i class="bi bi-arrow-repeat spin" style="font-size: 2rem; color: var(--text-muted);"></i>
        </div>
        
        <template v-else>
          <div class="section-header mobile-collapse-header" @click="showMedia = !showMedia">
            <span style="font-size: 0.75rem;">media</span>
            <i class="bi mobile-collapse-icon" :class="showMedia ? 'bi-chevron-up' : 'bi-chevron-down'"></i>
          </div>
          <transition name="collapse">
            <div v-show="showMedia" class="mobile-collapse-content">
              <div v-if="validMedia.length === 0 && !store.state.myProfile.audio" class="media-zone" @click="$refs.fileInput.click()">
                <i class="bi bi-image" style="font-size: 1.5rem;"></i><br>{{ store.t('add_media_placeholder') }}
              </div>
              
              <div v-if="store.state.myProfile.audio" class="audio-player-zone" style="display:flex; align-items:center; gap:1rem; padding-bottom: 0.5rem;">
                 <template v-if="store.state.myProfile.audio.isUploading">
                   <div style="position:relative; overflow:hidden; flex-grow:1; height: 32px; background: var(--bg-elevated); border-radius: var(--radius-sm); display:flex; align-items:center; justify-content:center;">
                     <div class="progress-bar-bg" style="border-radius: 0;">
                       <div class="progress-bar-fill-horizontal" :style="{width: (store.state.myProfile.audio.uploadProgress || 0) + '%'}"></div>
                     </div>
                   </div>
                 </template>
                 
                 <audio v-show="!store.state.myProfile.audio.isUploading" class="audio-minimal" :src="store.state.myProfile.audio.blobUrl || ''" controls style="flex-grow:1;"></audio>
                 
                 <i class="bi contact-action danger" :class="store.state.myProfile.audio.isDeleting ? 'bi-hourglass-split spin' : 'bi-x-circle-fill'" style="font-size:1.2rem; cursor: pointer;" @click="!store.state.myProfile.audio.isDeleting && removeAudio()"></i>
              </div>
              
              <transition-group name="media-list" tag="div" class="media-preview-grid telegram-grid" v-if="validMedia.length > 0">
                <div class="media-thumb" 
                     v-for="(m, idx) in validMedia" 
                     :key="m.url" 
                     :class="{'drag-over': dragOverIdx === idx}" 
                     draggable="true" 
                     @dragstart="!m.isUploading && dragStart(idx)" 
                     @dragover.prevent="!m.isUploading && dragOver(idx)" 
                     @dragleave="dragLeave" 
                     @drop="!m.isUploading && drop(idx)" 
                     @dragend="dragEnd"
                     @click="!m.isUploading && openLightbox(m)">
                  
                  <img v-if="m.media_type === 'image'" :src="m.blobUrl || ''" :class="{'is-blurred': m.blur || m.isUploading}">
                  <video v-else-if="m.media_type === 'video'" :src="m.blobUrl || ''" muted autoplay loop playsinline :class="{'is-blurred': m.blur || m.isUploading}"></video>
                  
                  <div v-if="m.isUploading" class="media-loader">
                    <div class="progress-bar-fill-horizontal" :style="{width: (m.uploadProgress || 0) + '%'}"></div>
                  </div>
                  
                  <div v-if="!m.isUploading" class="media-remove" @click.stop="!m.isDeleting && removeMedia(m, idx)">
                    <i class="bi" :class="m.isDeleting ? 'bi-hourglass-split spin' : 'bi-x'"></i>
                  </div>
                  <div v-if="!m.isUploading" class="media-blur-toggle" @click.stop="toggleBlur(m, idx)" :title="m.blur ? store.t('accept') : store.t('decline')">
                    <i class="bi" :class="m.isUpdatingBlur ? 'bi-hourglass-split spin' : (m.blur ? 'bi-eye-slash' : 'bi-eye')"></i>
                  </div>
                </div>
                
                <div class="media-thumb mini-add" key="mini-add" @click="$refs.fileInput.click()" title="add media" v-if="validMedia.length < 10">
                  <i class="bi bi-plus-lg"></i>
                </div>
              </transition-group>
            </div>
          </transition>
          
          <input type="file" ref="fileInput" hidden multiple accept="image/*,video/*,audio/*" @change="handleFileSelect">

          <div class="section-header mobile-collapse-header" @click="showBio = !showBio" style="margin-top:2rem;">
            <span style="font-size: 0.75rem;">about me</span>
            <div style="display:flex; align-items:center; gap:0.5rem;">
              <span :style="{color: store.state.myProfile.bio.length > 200 ? 'var(--accent-danger)' : 'inherit'}">{{ store.state.myProfile.bio.length }}/200</span>
              <i class="bi mobile-collapse-icon" :class="showBio ? 'bi-chevron-up' : 'bi-chevron-down'"></i>
            </div>
          </div>
          <transition name="collapse">
            <div v-show="showBio" class="mobile-collapse-content">
              <textarea class="seamless-input editor-bio" v-model="store.state.myProfile.bio" placeholder="..." rows="3" @input="triggerAutosave"></textarea>
            </div>
          </transition>

          <div class="section-header mobile-collapse-header" @click="showActiveTags = !showActiveTags">
            <span style="font-size: 0.75rem;">active tags</span>
            <i class="bi mobile-collapse-icon" :class="showActiveTags ? 'bi-chevron-up' : 'bi-chevron-down'"></i>
          </div>
          <transition name="collapse">
            <div v-show="showActiveTags" class="mobile-collapse-content">
              <transition-group name="tag-list" tag="div" class="chip-group" id="active-tags-zone" style="margin-bottom: 2rem; min-height: 25px;">
                <span class="chip require" v-for="tag in store.state.myProfile.tags" :key="tag" @click="toggleTag(tag)">
                  {{ store.getLocalizedTag(tag) }}
                </span>
                <span v-if="store.state.myProfile.tags.length === 0" style="color:var(--text-muted); font-size:0.8rem; font-style:italic;" key="none-placeholder">{{ store.t('none') }}</span>
              </transition-group>
            </div>
          </transition>

          <div class="section-header mobile-collapse-header" @click="showContacts = !showContacts">
            <span style="font-size: 0.75rem;">contacts</span>
            <i class="bi mobile-collapse-icon" :class="showContacts ? 'bi-chevron-up' : 'bi-chevron-down'"></i>
          </div>
          <transition name="collapse">
            <div v-show="showContacts" class="mobile-collapse-content">
              <div class="contact-row" v-for="(c, idx) in store.state.myProfile.contacts" :key="c._id">
                <i class="bi contact-icon" :class="getContactIcon(c.type)"></i>
                <input type="text" class="seamless-input contact-val" v-model="c.value" :placeholder="store.t('contact_placeholder')" @input="handleContactInput(c)" @blur="triggerAutosave">
                <i class="bi bi-copy contact-action" @click="copyText(c.value)" :title="store.t('copy')"></i>
                <i class="bi contact-action" :class="c.is_private ? 'bi-lock' : 'bi-globe'" @click="c.is_private = !c.is_private; triggerAutosave()" :title="store.t('toggle_privacy')"></i>
                <i class="bi bi-x-lg contact-action danger" @click="removeContact(idx)"></i>
              </div>
              <div class="contact-row">
                <i class="bi contact-icon bi-plus-lg"></i>
                <input type="text" class="seamless-input contact-val" v-model="newContact.value" :placeholder="store.t('contact_placeholder')" @input="handleNewContactInput" @blur="commitNewContact" @keyup.enter="commitNewContact">
                <i class="bi contact-action" :class="newContact.is_private ? 'bi-lock' : 'bi-globe'" @click="newContact.is_private = !newContact.is_private" :title="store.t('toggle_privacy')"></i>
              </div>
            </div>
          </transition>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onActivated } from 'vue'
import { useStore } from '../store/state.js'
import api from '../utils/api.js'

const store = useStore()
const editorRoot = ref(null)
const fileInput = ref(null)
const dragOverIdx = ref(null)
const isDraggingFiles = ref(false)
const isResizingWorkspace = ref(false)

const showMedia = ref(true)
const showBio = ref(true)
const showActiveTags = ref(true)
const showContacts = ref(true)

let dragIndex = null
let saveTimeout = null

const filteredTags = computed(() => {
  const query = store.state.tagSearchQuery.toLowerCase().trim()
  if (!query) {
      return store.state.availableSearchTags.filter(t => !t.hidden)
  }
  return store.state.availableSearchTags.filter(t => 
      (t.name && String(t.name).toLowerCase().includes(query)) || 
      (t.aliases && t.aliases.some(a => a && String(a).toLowerCase().includes(query))) ||
      (t.i18n && Object.values(t.i18n).some(v => v && typeof v === 'string' && v.toLowerCase().includes(query)))
  )
})

const validMedia = computed(() => {
  return (store.state.myProfile.media || []).filter(m => m && (m.url || m.blobUrl))
})

onActivated(() => {
  if (editorRoot.value) {
    const videos = editorRoot.value.querySelectorAll('video')
    videos.forEach(v => {
      if (v.paused) v.play().catch(() => {})
    })
  }
})

function triggerAutosave() {
  if (store.state.myProfile.bio.length > 200) {
    store.state.myProfile.bio = store.state.myProfile.bio.substring(0, 200)
  }
  clearTimeout(saveTimeout)
  saveTimeout = setTimeout(() => {
    store.saveProfile()
  }, 1000)
}

function selectTagFromAutocomplete(tagName) {
  if (!store.state.myProfile.tags.includes(tagName)) {
    store.state.myProfile.tags.push(tagName);
    triggerAutosave();
  }
  store.state.tagSearchQuery = '';
}

function toggleTag(tagName) {
  const idx = store.state.myProfile.tags.indexOf(tagName);
  if (idx === -1) {
    store.state.myProfile.tags.push(tagName);
  } else {
    store.state.myProfile.tags.splice(idx, 1);
  }
  triggerAutosave();
}

const iconMap = { 'email': 'bi-envelope', 'link': 'bi-link-45deg', 'phone': 'bi-telephone', 'unknown': 'bi-question' }
function getContactIcon(type) { return iconMap[type] || 'bi-link-45deg' }

const newContact = ref({ type: 'unknown', value: '', is_private: true, _id: Math.random().toString() });

function inferContactType(v) {
  if (v === '') return 'unknown'
  else if (/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v)) return 'email'
  else if (/^(https?:\/\/|[a-zA-Z0-9-]+\.[a-zA-Z0-9-]+)/.test(v)) return 'link'
  else if (/^\+?[0-9\s\-]{7,15}$/.test(v)) return 'phone'
  return 'unknown'
}

function handleContactInput(c) {
  c.type = inferContactType(c.value.trim());
  triggerAutosave();
}

function handleNewContactInput() {
  newContact.value.type = inferContactType(newContact.value.value.trim());
}

function commitNewContact() {
  if (newContact.value.value.trim() !== '') {
    store.state.myProfile.contacts.push({ ...newContact.value });
    newContact.value = { type: 'unknown', value: '', is_private: true, _id: Math.random().toString() };
    triggerAutosave();
  }
}

function removeContact(idx) {
  store.state.myProfile.contacts.splice(idx, 1)
  triggerAutosave()
}

async function copyText(txt) {
  await navigator.clipboard.writeText(txt)
  store.addToast(store.t('copied'), "bi-check2")
}

function updateMediaList(resMedia, remainingTemps) {
    const updated = resMedia.map(newM => {
        const old = store.state.myProfile.media.find(m => m.url === newM.url);
        return old ? { ...newM, isDeleting: old.isDeleting, isUpdatingBlur: old.isUpdatingBlur || false, isLoaded: true, isUploading: false } 
                   : { ...newM, isLoaded: true, isUploading: false }; // It will process dynamically via fetching
    });
    store.state.myProfile.media = [...updated, ...remainingTemps];
}

async function processFiles(files) {
  const tempItems = []
  
  for (let i = 0; i < files.length; i++) {
    const file = files[i]
    if (file.size > 25 * 1024 * 1024) {
      store.addToast("File too large (max 25MB)", "bi-x-octagon")
      continue
    }
    
    const abortCtrl = new AbortController();
    const tempUrl = URL.createObjectURL(file); // Immediately renderable client-side stub
    const media_type = file.type.startsWith('video') ? 'video' : (file.type.startsWith('audio') ? 'audio' : 'image')
    
    if (media_type === 'audio') {
      store.state.myProfile.audio = { url: null, blobUrl: tempUrl, media_type: 'audio', blur: false, isUploading: true, isLoaded: true, isDeleting: false, uploadProgress: 0, file, abortCtrl }
    } else {
      tempItems.push({ url: null, blobUrl: tempUrl, media_type, blur: false, isUploading: true, isLoaded: true, isDeleting: false, uploadProgress: 0, file, abortCtrl })
    }
  }
  
  if (tempItems.length > 0) {
    store.state.myProfile.media.push(...tempItems)
  }
  
  let audioPromise = null
  if (store.state.myProfile.audio && store.state.myProfile.audio.isUploading) {
    const tempAudio = store.state.myProfile.audio
    audioPromise = api.post(`/profile/me/media?blur=${tempAudio.blur}`, tempAudio.file, {
      headers: { 'Content-Type': tempAudio.file.type || 'application/octet-stream' },
      signal: tempAudio.abortCtrl.signal,
      onUploadProgress: (e) => {
        if (e.total && store.state.myProfile.audio) {
          store.state.myProfile.audio.uploadProgress = Math.round((e.loaded * 100) / e.total);
        }
      }
    }).then(async res => {
      const remainingTemps = store.state.myProfile.media.filter(m => m.isUploading)
      updateMediaList(res.data.media, remainingTemps)
      if (res.data.audio) {
          const oldAudio = store.state.myProfile.audio;
          const reactiveAudio = store.state.myProfile.audio;
          const desiredBlur = reactiveAudio ? reactiveAudio.blur : tempAudio.blur;
          
          res.data.audio.blobUrl = tempAudio.blobUrl; // Persist the client side blob to skip re-downloading it instantly

          if (desiredBlur !== res.data.audio.blur) {
              try {
                  const resBlur = await api.patch(`/profile/me/media/blur?url=${encodeURIComponent(res.data.audio.url)}&blur=${desiredBlur}`);
                  store.state.myProfile.audio = { ...resBlur.data.audio, blobUrl: tempAudio.blobUrl, isDeleting: oldAudio?.isDeleting, isLoaded: true };
              } catch (e) {
                  store.state.myProfile.audio = { ...res.data.audio, blobUrl: tempAudio.blobUrl, isDeleting: oldAudio?.isDeleting, isLoaded: true };
              }
          } else {
              store.state.myProfile.audio = { ...res.data.audio, blobUrl: tempAudio.blobUrl, isDeleting: oldAudio?.isDeleting, isLoaded: true };
          }
      } else {
          store.state.myProfile.audio = null;
      }
    }).catch(e => {
      if (e.name === 'CanceledError') return;
      store.addToast("Failed to upload audio", "bi-exclamation-triangle")
      store.state.myProfile.audio = null
    })
  }

  const uploadPromises = tempItems.map(temp => {
    return api.post(`/profile/me/media?blur=${temp.blur}`, temp.file, {
      headers: { 'Content-Type': temp.file.type || 'application/octet-stream' },
      signal: temp.abortCtrl.signal,
      onUploadProgress: (e) => {
        if (e.total) {
          const m = store.state.myProfile.media.find(x => x.blobUrl === temp.blobUrl);
          if (m) m.uploadProgress = Math.round((e.loaded * 100) / e.total);
        }
      }
    }).then(async res => {
      const existingUrls = new Set(store.state.myProfile.media.filter(m => !m.isUploading).map(m => m.url));
      const newItem = res.data.media.find(m => !existingUrls.has(m.url));
      
      const reactiveTemp = store.state.myProfile.media.find(m => m.blobUrl === temp.blobUrl);
      const desiredBlur = reactiveTemp ? reactiveTemp.blur : temp.blur;

      if (newItem) {
        newItem.blur = desiredBlur;
        newItem.blobUrl = temp.blobUrl; // Persist client-side render blob!
      }

      const remainingTemps = store.state.myProfile.media.filter(m => m.isUploading && m.blobUrl !== temp.blobUrl)
      updateMediaList(res.data.media, remainingTemps)

      if (newItem && desiredBlur !== false) {
          try {
              const newIdx = res.data.media.findIndex(m => m.url === newItem.url);
              const resBlur = await api.patch(`/profile/me/media/blur?url=${encodeURIComponent(newItem.url)}&blur=${desiredBlur}&index=${newIdx}`);
              resBlur.data.media.find(m => m.url === newItem.url).blobUrl = temp.blobUrl;
              updateMediaList(resBlur.data.media, remainingTemps);
          } catch (e) {}
      }

      if (!store.state.myProfile.audio?.isUploading) {
        if (res.data.audio) {
            const oldAudio = store.state.myProfile.audio;
            store.state.myProfile.audio = { ...res.data.audio, blobUrl: oldAudio?.blobUrl, isDeleting: oldAudio?.isDeleting, isLoaded: true };
        } else {
            store.state.myProfile.audio = null;
        }
      }
    }).catch(e => {
      if (e.name === 'CanceledError') return;
      store.addToast("Failed to upload media", "bi-exclamation-triangle")
      store.state.myProfile.media = store.state.myProfile.media.filter(m => m.blobUrl !== temp.blobUrl)
    })
  })

  await Promise.all([audioPromise, ...uploadPromises].filter(Boolean))
}

function workspaceDragEnter(e) {
  if (dragIndex === null) isDraggingFiles.value = true
}
function workspaceDragOver(e) {
  if (dragIndex === null) isDraggingFiles.value = true
}
function workspaceDragLeave(e) {
  const rect = e.currentTarget.getBoundingClientRect()
  if (e.clientX <= rect.left || e.clientX >= rect.right || e.clientY <= rect.top || e.clientY >= rect.bottom) {
    isDraggingFiles.value = false
  }
}
function workspaceDrop(e) {
  isDraggingFiles.value = false
  if (dragIndex === null && e.dataTransfer && e.dataTransfer.files.length > 0) {
    processFiles(e.dataTransfer.files)
  }
}

function handleFileSelect(e) { processFiles(e.target.files); e.target.value = null }
function handlePaste(e) {
  if (store.state.currentView !== 'editor') return
  const items = (e.clipboardData || e.originalEvent.clipboardData).items
  const files = []
  for (let i = 0; i < items.length; i++) {
    if (items[i].kind === 'file') files.push(items[i].getAsFile())
  }
  if (files.length > 0) processFiles(files)
}

async function removeMedia(m, idx) {
  if (m.isUploading) {
    if (m.abortCtrl) m.abortCtrl.abort();
    store.state.myProfile.media = store.state.myProfile.media.filter(x => x.blobUrl !== m.blobUrl);
    return;
  }
  
  const realIdx = store.state.myProfile.media.findIndex(x => x.url === m.url);
  if (realIdx !== -1) {
    try {
      m.isDeleting = true
      const completedIdx = store.state.myProfile.media.filter(x => !x.isUploading).findIndex(x => x.url === m.url);
      const idxParam = completedIdx !== -1 ? `&index=${completedIdx}` : '';
      const res = await api.delete(`/profile/me/media?url=${encodeURIComponent(m.url)}${idxParam}`)
      const remainingTemps = store.state.myProfile.media.filter(x => x.isUploading)
      updateMediaList(res.data.media, remainingTemps)
    } catch (e) {
      m.isDeleting = false
    }
  }
}

async function removeAudio() {
  const m = store.state.myProfile.audio;
  if (!m) return;
  if (m.isUploading) {
    if (m.abortCtrl) m.abortCtrl.abort();
    store.state.myProfile.audio = null;
    return;
  }
  try {
    store.state.myProfile.audio.isDeleting = true
    const res = await api.delete('/profile/me/audio')
    store.state.myProfile.audio = res.data.audio ? { ...res.data.audio, isDeleting: false, isLoaded: true } : null
  } catch(e) {
    if (store.state.myProfile.audio) {
      store.state.myProfile.audio.isDeleting = false
    }
  }
}

async function toggleBlur(m, idx) {
  const realIdx = store.state.myProfile.media.findIndex(x => x.url === m.url);
  if (realIdx === -1) return;

  if (m.isUploading) {
    m.blur = !m.blur;
    return;
  }
  try {
    m.isUpdatingBlur = true
    const newBlurState = !m.blur
    const completedIdx = store.state.myProfile.media.filter(x => !x.isUploading).findIndex(x => x.url === m.url);
    const idxParam = completedIdx !== -1 ? `&index=${completedIdx}` : '';
    const res = await api.patch(`/profile/me/media/blur?url=${encodeURIComponent(m.url)}&blur=${newBlurState}${idxParam}`)
    const remainingTemps = store.state.myProfile.media.filter(x => x.isUploading)
    updateMediaList(res.data.media, remainingTemps)
    
    if (!store.state.myProfile.audio?.isUploading) {
      if (res.data.audio) {
          const oldAudio = store.state.myProfile.audio;
          store.state.myProfile.audio = { ...res.data.audio, isDeleting: oldAudio?.isDeleting, isLoaded: true };
      } else {
          store.state.myProfile.audio = null;
      }
    }
  } catch(e) {
    store.addToast("Failed to update blur state", "bi-x-circle")
  } finally {
    const updated = store.state.myProfile.media.find(x => x.url === m.url);
    if (updated) updated.isUpdatingBlur = false;
  }
}

function dragStart(idx) { dragIndex = idx }
function dragOver(idx) { dragOverIdx.value = idx }
function dragLeave() { dragOverIdx.value = null }
function dragEnd() { dragIndex = null; dragOverIdx.value = null; }

async function drop(idx) {
  dragOverIdx.value = null
  if (dragIndex !== null && dragIndex !== idx) {
    const t = store.state.myProfile.media[dragIndex]
    store.state.myProfile.media.splice(dragIndex, 1)
    store.state.myProfile.media.splice(idx, 0, t)
    dragIndex = null
    
    try {
      const urls = store.state.myProfile.media.filter(m => !m.isUploading).map(m => m.url)
      const res = await api.put('/profile/me/media/order', { urls })
      const remainingTemps = store.state.myProfile.media.filter(x => x.isUploading)
      updateMediaList(res.data.media, remainingTemps)
    } catch(e) {
      store.addToast("Failed to save media order", "bi-x-circle")
    }
  }
  dragIndex = null
}

function openLightbox(m) {
  const list = store.state.myProfile.media.filter(x => !x.isUploading);
  const idx = list.findIndex(x => x.url === m.url);
  store.state.lightbox.mediaList = list;
  store.state.lightbox.index = idx !== -1 ? idx : 0;
  store.state.lightbox.isEditable = true;
  store.state.lightbox.open = true;
}

let startX, startW
function startResize(e) {
  isResizingWorkspace.value = true
  startX = e.clientX
  startW = store.state.workspaceWidth
  document.addEventListener('mousemove', doResize)
  document.addEventListener('mouseup', stopResize)
  document.body.style.userSelect = 'none'
}
function doResize(e) {
  const w = startW - (e.clientX - startX)
  if (w > 350 && w < 800) store.state.workspaceWidth = w
}
function stopResize() {
  isResizingWorkspace.value = false
  document.removeEventListener('mousemove', doResize)
  document.removeEventListener('mouseup', stopResize)
  document.body.style.userSelect = ''
}
</script>