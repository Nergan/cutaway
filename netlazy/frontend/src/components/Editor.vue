<template>
  <div class="editor-layout">
    <div class="tag-library-pane">
      <div class="tag-library-header blurred-header">
        <i class="bi bi-search" style="color:var(--text-muted); margin-right: 0.5rem;"></i>
        <div style="position: relative; display: flex; align-items: center; flex-grow: 1;">
          <input type="text" class="seamless-input" v-model="store.state.tagSearchQuery" :placeholder="store.t('search_tags')" style="padding-right: 1.5rem;">
          <i v-if="store.state.tagSearchQuery" class="bi bi-x-lg" style="position: absolute; right: 0; cursor: pointer; color: var(--text-muted);" @click="store.state.tagSearchQuery = ''"></i>
        </div>
      </div>
      
      <div class="tag-library-list chip-group" id="lib-tags-zone" style="padding: 1.5rem; align-content: flex-start;">
        <span class="chip" 
              :class="{require: store.state.myProfile.tags.includes(tag.name)}" 
              :id="'lib-tag-'+tag.name" 
              v-for="tag in filteredTags" 
              :key="tag.name" 
              @click="flyTag($event, tag.name, !store.state.myProfile.tags.includes(tag.name), true)">
          {{ tag.name }}
          <i class="bi bi-check2" v-if="store.state.myProfile.tags.includes(tag.name)"></i>
        </span>
        <div v-if="filteredTags.length === 0" class="muted-italic" style="color:var(--text-muted); font-size:0.85rem;">
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
        
        <div v-if="validMedia.length === 0 && !store.state.myProfile.audio" class="media-zone" @click="$refs.fileInput.click()">
          <i class="bi bi-image" style="font-size: 1.5rem;"></i><br>{{ store.t('add_media_placeholder') }}
        </div>
        
        <div v-if="store.state.myProfile.audio" class="audio-player-zone" style="display:flex; align-items:center; gap:1rem; padding-bottom: 0.5rem;">
           <template v-if="store.state.myProfile.audio.isUploading || !store.state.myProfile.audio.isLoaded">
             <i class="bi bi-arrow-repeat spin" style="font-size: 1.5rem; color: var(--text-muted);"></i>
             <span style="color:var(--text-muted); font-size:0.85rem;">Uploading audio...</span>
           </template>
           
           <audio v-show="!store.state.myProfile.audio.isUploading" class="audio-minimal" :src="store.state.myProfile.audio.url" @loadeddata="store.state.myProfile.audio.isLoaded = true" controls style="flex-grow:1;"></audio>
           
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
            
            <div v-if="m.isUploading || !m.isLoaded" class="media-loader">
              <i class="bi bi-arrow-repeat spin" style="font-size: 2rem; color: var(--text-muted);"></i>
            </div>
            
            <img v-if="m.media_type === 'image'" v-show="!m.isUploading && m.isLoaded" @load="m.isLoaded = true" @error="m.isLoaded = true" :src="m.url" :class="{'is-blurred': m.blur}">
            <video v-else-if="m.media_type === 'video'" v-show="!m.isUploading && m.isLoaded" @loadeddata="m.isLoaded = true" @error="m.isLoaded = true" :src="m.url" muted autoplay loop :class="{'is-blurred': m.blur}"></video>
            
            <div class="media-remove" @click.stop="!m.isDeleting && removeMedia(m, idx)">
              <i class="bi" :class="m.isDeleting ? 'bi-hourglass-split spin' : 'bi-x'"></i>
            </div>
            <div class="media-blur-toggle" @click.stop="toggleBlur(m, idx)" :title="m.blur ? store.t('accept') : store.t('decline')">
              <i class="bi" :class="m.isUpdatingBlur ? 'bi-hourglass-split spin' : (m.blur ? 'bi-eye-slash' : 'bi-eye')"></i>
            </div>
            
          </div>
          
          <div class="media-thumb mini-add" key="mini-add" @click="$refs.fileInput.click()" title="add media" v-if="validMedia.length < 10">
            <i class="bi bi-plus-lg"></i>
          </div>
        </transition-group>
        
        <input type="file" ref="fileInput" hidden multiple accept="image/*,video/*,audio/*" @change="handleFileSelect">

        <div style="margin-top:2rem; margin-bottom: 0.5rem; display:flex; justify-content:space-between; color:var(--text-muted); font-size: 0.75rem;">
          <span>{{ store.t('about_me') }}</span>
          <span :style="{color: store.state.myProfile.bio.length > 200 ? 'var(--accent-danger)' : 'inherit'}">{{ store.state.myProfile.bio.length }}/200</span>
        </div>
        <textarea class="seamless-input editor-bio" v-model="store.state.myProfile.bio" placeholder="..." rows="3" @input="triggerAutosave"></textarea>

        <div style="color:var(--text-muted); font-size:0.75rem; margin-bottom:0.5rem;">{{ store.t('active_tags') }}</div>
        <div class="chip-group" id="active-tags-zone" style="margin-bottom: 2rem; min-height: 25px;">
          <span class="chip require" :id="'act-tag-'+tag" v-for="tag in store.state.myProfile.tags" :key="tag" @click="flyTag($event, tag, false, false)">
            {{ tag }}
          </span>
          <span v-if="store.state.myProfile.tags.length === 0" style="color:var(--text-muted); font-size:0.8rem; font-style:italic;">{{ store.t('none') }}</span>
        </div>

        <div style="color:var(--text-muted); font-size:0.75rem; margin-bottom:0.5rem;">{{ store.t('contacts') }}</div>
        <div>
          <div class="contact-row" v-for="(c, idx) in store.state.myProfile.contacts" :key="c._id">
            <i class="bi contact-icon" :class="getContactIcon(c.type)"></i>
            <input type="text" class="seamless-input contact-val" v-model="c.value" :placeholder="store.t('contact_placeholder')" @input="handleContactInput(idx)" @blur="handleContactBlur">
            <i class="bi bi-copy contact-action" @click="copyText(c.value)" :title="store.t('copy')"></i>
            <i class="bi contact-action" :class="c.is_private ? 'bi-lock' : 'bi-globe'" @click="c.is_private = !c.is_private; triggerAutosave()" :title="store.t('toggle_privacy')"></i>
            <i class="bi bi-x-lg contact-action danger" v-if="idx < store.state.myProfile.contacts.length - 1 || store.state.myProfile.contacts.length > 1" @click="removeContact(idx)"></i>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useStore } from '../store/state.js'
import api from '../utils/api.js'

const store = useStore()
const fileInput = ref(null)
const dragOverIdx = ref(null)
const isDraggingFiles = ref(false)
const isResizingWorkspace = ref(false)

let dragIndex = null
let saveTimeout = null
let isAnimating = false

const filteredTags = computed(() => {
  const query = store.state.tagSearchQuery.toLowerCase().trim()
  if (!query) {
      return store.state.availableSearchTags.filter(t => !t.hidden)
  }
  return store.state.availableSearchTags.filter(t => t.name.includes(query) || t.aliases.some(a => a.includes(query)))
})

const validMedia = computed(() => {
  return (store.state.myProfile.media || []).filter(m => m && m.url)
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

function flyTag(e, tag, isAdding, fromLibrary) {
  if (isAnimating) return
  if (fromLibrary && !isAdding) {
    store.state.myProfile.tags = store.state.myProfile.tags.filter(t => t !== tag)
    triggerAutosave()
    return
  }

  isAnimating = true
  if (isAdding && store.state.isWorkspaceCollapsed) {
    store.state.isWorkspaceCollapsed = false
  }

  const srcEl = e.target.closest('span') || e.target
  const rect = srcEl.getBoundingClientRect()
  const clone = srcEl.cloneNode(true)
  clone.classList.add('flying-tag')
  clone.style.position = 'fixed'
  clone.style.left = rect.left + 'px'
  clone.style.top = rect.top + 'px'
  clone.style.transition = 'all 0.4s cubic-bezier(0.2, 0.8, 0.2, 1)'
  document.body.appendChild(clone)
  
  if (isAdding && !store.state.myProfile.tags.includes(tag)) {
    store.state.myProfile.tags.push(tag)
  }
  
  setTimeout(() => {
    const destZone = document.getElementById('active-tags-zone')
    if (destZone) {
      const destRect = destZone.getBoundingClientRect()
      clone.style.left = (destRect.left + 20) + 'px'
      clone.style.top = (destRect.top + 20) + 'px'
      clone.style.transform = 'scale(0.8)'
      clone.style.opacity = '0'
    }
  }, 10)

  setTimeout(() => {
    clone.remove()
    if (!isAdding) {
      store.state.myProfile.tags = store.state.myProfile.tags.filter(t => t !== tag)
    }
    triggerAutosave()
    isAnimating = false
  }, 400)
}

const iconMap = { 'email': 'bi-envelope', 'link': 'bi-link-45deg', 'phone': 'bi-telephone', 'unknown': 'bi-question' }
function getContactIcon(type) { return iconMap[type] || 'bi-link-45deg' }

function handleContactInput(idx) {
  const c = store.state.myProfile.contacts[idx]
  const v = c.value.trim()
  
  if (v === '') c.type = 'unknown'
  else if (/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v)) c.type = 'email'
  else if (/^(https?:\/\/|[a-zA-Z0-9-]+\.[a-zA-Z0-9-]+)/.test(v)) c.type = 'link'
  else if (/^\+?[0-9\s\-]{7,15}$/.test(v)) c.type = 'phone'
  else c.type = 'unknown'

  const contacts = store.state.myProfile.contacts
  if (idx === contacts.length - 1 && c.type !== 'unknown' && v !== '') {
    contacts.push({ type: 'unknown', value: '', is_private: true, _id: Math.random().toString() })
  }

  if (c.type !== 'unknown' || v === '') {
    triggerAutosave()
  }
}

function handleContactBlur() {
  const contacts = store.state.myProfile.contacts
  for (let i = contacts.length - 2; i >= 0; i--) {
    if (contacts[i].value.trim() === '') contacts.splice(i, 1)
  }
  if (contacts.length === 0) {
    contacts.push({ type: 'unknown', value: '', is_private: true, _id: Math.random().toString() })
  }
  triggerAutosave()
}

function removeContact(idx) {
  store.state.myProfile.contacts.splice(idx, 1)
  if (store.state.myProfile.contacts.length === 0) {
    store.state.myProfile.contacts.push({ type: 'unknown', value: '', is_private: true, _id: Math.random().toString() })
  }
  triggerAutosave()
}

async function copyText(txt) {
  await navigator.clipboard.writeText(txt)
  store.addToast(store.t('copied'), "bi-check2")
}

function updateMediaList(resMedia, remainingTemps) {
    const updated = resMedia.map(newM => {
        const old = store.state.myProfile.media.find(m => m.url === newM.url);
        return old ? { ...newM, isDeleting: old.isDeleting, isUpdatingBlur: old.isUpdatingBlur || false, isLoaded: old.isLoaded, isUploading: false } 
                   : { ...newM, isLoaded: false, isUploading: false };
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
    const tempId = Math.random().toString()
    const media_type = file.type.startsWith('video') ? 'video' : (file.type.startsWith('audio') ? 'audio' : 'image')
    
    if (media_type === 'audio') {
      store.state.myProfile.audio = { url: tempId, media_type: 'audio', blur: false, isUploading: true, isLoaded: false, isDeleting: false, file, abortCtrl }
    } else {
      tempItems.push({ url: tempId, media_type, blur: false, isUploading: true, isLoaded: false, isDeleting: false, file, abortCtrl })
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
      signal: tempAudio.abortCtrl.signal
    }).then(async res => {
      const remainingTemps = store.state.myProfile.media.filter(m => m.isUploading)
      updateMediaList(res.data.media, remainingTemps)
      if (res.data.audio) {
          const oldAudio = store.state.myProfile.audio;
          const reactiveAudio = store.state.myProfile.audio;
          const desiredBlur = reactiveAudio ? reactiveAudio.blur : tempAudio.blur;

          if (desiredBlur !== res.data.audio.blur) {
              try {
                  const resBlur = await api.patch(`/profile/me/media/blur?url=${encodeURIComponent(res.data.audio.url)}&blur=${desiredBlur}`);
                  store.state.myProfile.audio = { ...resBlur.data.audio, isDeleting: oldAudio?.isDeleting, isLoaded: false };
              } catch (e) {
                  console.error("Failed to sync audio blur state after upload:", e);
                  store.state.myProfile.audio = { ...res.data.audio, isDeleting: oldAudio?.isDeleting, isLoaded: false };
              }
          } else {
              store.state.myProfile.audio = { ...res.data.audio, isDeleting: oldAudio?.isDeleting, isLoaded: false };
          }
      } else {
          store.state.myProfile.audio = null;
      }
    }).catch(e => {
      if (e.name === 'CanceledError') return;
      if (e.response && e.response.data && e.response.data.detail) {
          store.addToast(e.response.data.detail, "bi-exclamation-triangle")
      } else {
          store.addToast("Failed to upload audio", "bi-exclamation-triangle")
      }
      store.state.myProfile.audio = null
    })
  }

  const uploadPromises = tempItems.map(temp => {
    return api.post(`/profile/me/media?blur=${temp.blur}`, temp.file, {
      headers: { 'Content-Type': temp.file.type || 'application/octet-stream' },
      signal: temp.abortCtrl.signal
    }).then(async res => {
      const existingUrls = new Set(store.state.myProfile.media.filter(m => !m.isUploading).map(m => m.url));
      const newItem = res.data.media.find(m => !existingUrls.has(m.url));
      
      const reactiveTemp = store.state.myProfile.media.find(m => m.url === temp.url);
      const desiredBlur = reactiveTemp ? reactiveTemp.blur : temp.blur;

      if (newItem) {
          newItem.blur = desiredBlur;
      }

      const remainingTemps = store.state.myProfile.media.filter(m => m.isUploading && m.url !== temp.url)
      updateMediaList(res.data.media, remainingTemps)

      if (newItem && desiredBlur !== false) {
          try {
              const newIdx = res.data.media.findIndex(m => m.url === newItem.url);
              const resBlur = await api.patch(`/profile/me/media/blur?url=${encodeURIComponent(newItem.url)}&blur=${desiredBlur}&index=${newIdx}`);
              updateMediaList(resBlur.data.media, remainingTemps);
          } catch (e) {
              console.error("Failed to sync blur state after upload:", e);
          }
      }

      if (!store.state.myProfile.audio?.isUploading) {
        if (res.data.audio) {
            const oldAudio = store.state.myProfile.audio;
            store.state.myProfile.audio = { ...res.data.audio, isDeleting: oldAudio?.isDeleting, isLoaded: oldAudio?.isLoaded };
        } else {
            store.state.myProfile.audio = null;
        }
      }
    }).catch(e => {
      if (e.name === 'CanceledError') return;
      if (e.response && e.response.data && e.response.data.detail) {
          store.addToast(e.response.data.detail, "bi-exclamation-triangle")
      } else {
          store.addToast("Failed to upload media", "bi-exclamation-triangle")
      }
      store.state.myProfile.media = store.state.myProfile.media.filter(m => m.url !== temp.url)
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
  const realIdx = store.state.myProfile.media.findIndex(x => x.url === m.url);
  if (realIdx !== -1) {
    if (m.isUploading) {
      if (m.abortCtrl) m.abortCtrl.abort();
      store.state.myProfile.media.splice(realIdx, 1);
      return;
    }
    try {
      m.isDeleting = true
      const completedIdx = store.state.myProfile.media.filter(x => !x.isUploading).findIndex(x => x.url === m.url);
      const res = await api.delete(`/profile/me/media?url=${encodeURIComponent(m.url)}&index=${completedIdx !== -1 ? completedIdx : ''}`)
      const remainingTemps = store.state.myProfile.media.filter(x => x.isUploading)
      updateMediaList(res.data.media, remainingTemps)
    } catch (e) {
      m.isDeleting = false
      store.addToast("Failed to delete media", "bi-x-circle")
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
    store.state.myProfile.audio = res.data.audio ? { ...res.data.audio, isDeleting: false, isLoaded: false } : null
  } catch(e) {
    if (store.state.myProfile.audio) {
      store.state.myProfile.audio.isDeleting = false
    }
    store.addToast("Failed to delete audio", "bi-x-circle")
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
    const res = await api.patch(`/profile/me/media/blur?url=${encodeURIComponent(m.url)}&blur=${newBlurState}&index=${completedIdx !== -1 ? completedIdx : ''}`)
    const remainingTemps = store.state.myProfile.media.filter(x => x.isUploading)
    updateMediaList(res.data.media, remainingTemps)
    
    if (!store.state.myProfile.audio?.isUploading) {
      if (res.data.audio) {
          const oldAudio = store.state.myProfile.audio;
          store.state.myProfile.audio = { ...res.data.audio, isDeleting: oldAudio?.isDeleting, isLoaded: oldAudio?.isLoaded };
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
  store.state.lightbox.media = m
  store.state.lightbox.open = true
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