<template>
  <transition name="lightbox-fade">
    <div class="lightbox" v-if="store.state.lightbox.open" @click="closeLightbox">
      
      <button class="lightbox-close" @click.stop="closeLightbox"><i class="bi bi-x"></i></button>

      <div v-if="currentMedia" class="lightbox-container" @touchstart="handleTouchStart" @touchend="handleTouchEnd">
        
        <div class="lightbox-nav lightbox-nav-left" v-if="hasPrev" @click.stop="prevMedia">
          <i class="bi bi-chevron-left"></i>
        </div>
        
        <div class="lightbox-content-wrapper" @click.stop>
          <transition name="lightbox-slide" mode="out-in">
            <img v-if="currentMedia.media_type === 'image'" 
                 :key="currentMedia.url"
                 :src="currentMedia.url" 
                 class="lightbox-content"
                 :class="{'is-blurred': currentMedia.blur}"
                 alt="media" @click.stop="handleMediaClick(currentMedia)">
                 
            <video v-else-if="currentMedia.media_type === 'video'" 
                   :key="currentMedia.url"
                   :src="currentMedia.url" 
                   class="lightbox-content" 
                   :class="{'is-blurred': currentMedia.blur}"
                   controls autoplay loop playsinline @click.stop="handleMediaClick(currentMedia)"></video>
          </transition>

          <div v-if="store.state.lightbox.isEditable" class="media-remove" @click.stop="!currentMedia.isDeleting && removeMedia(currentMedia)" style="width: 32px; height: 32px; font-size: 1.2rem; top: 8px; right: 8px;">
            <i class="bi" :class="currentMedia.isDeleting ? 'bi-hourglass-split spin' : 'bi-x'"></i>
          </div>
          <div v-if="store.state.lightbox.isEditable" class="media-blur-toggle" @click.stop="toggleBlurMode(currentMedia)" style="width: 32px; height: 32px; font-size: 1.1rem; bottom: 8px; left: 8px;">
            <i class="bi" :class="currentMedia.isUpdatingBlur ? 'bi-hourglass-split spin' : (currentMedia.blur ? 'bi-eye-slash' : 'bi-eye')"></i>
          </div>
        </div>

        <div class="lightbox-nav lightbox-nav-right" v-if="hasNext" @click.stop="nextMedia">
          <i class="bi bi-chevron-right"></i>
        </div>

      </div>
    </div>
  </transition>
</template>

<script setup>
import { computed } from 'vue'
import { useStore } from '../store/state.js'
import api from '../utils/api.js'

const store = useStore()

const hasPrev = computed(() => store.state.lightbox.index > 0)
const hasNext = computed(() => store.state.lightbox.index < store.state.lightbox.mediaList.length - 1)
const currentMedia = computed(() => store.state.lightbox.mediaList[store.state.lightbox.index])

function closeLightbox() {
  store.state.lightbox.open = false
}

function prevMedia() {
  if (hasPrev.value) store.state.lightbox.index--
}

function nextMedia() {
  if (hasNext.value) store.state.lightbox.index++
}

function handleMediaClick(m) {
  if (m.blur) {
    if (!store.state.lightbox.isEditable) {
      m.blur = false
    } else {
      toggleBlurMode(m)
    }
  }
}

async function removeMedia(m) {
  try {
    m.isDeleting = true;
    const completedIdx = store.state.myProfile.media.filter(x => !x.isUploading).findIndex(x => x.url === m.url);
    await api.delete(`/profile/me/media?url=${encodeURIComponent(m.url)}&index=${completedIdx !== -1 ? completedIdx : ''}`);
    
    store.state.myProfile.media = store.state.myProfile.media.filter(x => x.url !== m.url);
    store.state.lightbox.mediaList = store.state.lightbox.mediaList.filter(x => x.url !== m.url);
    
    if (store.state.lightbox.mediaList.length === 0) {
      closeLightbox();
    } else if (store.state.lightbox.index >= store.state.lightbox.mediaList.length) {
      store.state.lightbox.index = store.state.lightbox.mediaList.length - 1;
    }
  } catch (e) {
    store.addToast("Failed to delete media", "bi-x-circle");
  } finally {
    if (m) m.isDeleting = false;
  }
}

async function toggleBlurMode(m) {
  try {
    m.isUpdatingBlur = true;
    const newBlurState = !m.blur;
    const completedIdx = store.state.myProfile.media.filter(x => !x.isUploading).findIndex(x => x.url === m.url);
    await api.patch(`/profile/me/media/blur?url=${encodeURIComponent(m.url)}&blur=${newBlurState}&index=${completedIdx !== -1 ? completedIdx : ''}`);
    
    m.blur = newBlurState;
    const profileMedia = store.state.myProfile.media.find(x => x.url === m.url);
    if (profileMedia) profileMedia.blur = newBlurState;
  } catch (e) {
    store.addToast("Failed to update blur", "bi-x-circle");
  } finally {
    if (m) m.isUpdatingBlur = false;
  }
}

// Touch swipe implementation for mobile users
let touchStartX = 0
let touchEndX = 0

function handleTouchStart(e) {
  if (e.changedTouches.length) {
    touchStartX = e.changedTouches[0].screenX
  }
}

function handleTouchEnd(e) {
  if (e.changedTouches.length) {
    touchEndX = e.changedTouches[0].screenX
    handleSwipe()
  }
}

function handleSwipe() {
  const diff = touchEndX - touchStartX
  if (diff < -50) nextMedia()
  else if (diff > 50) prevMedia()
}
</script>