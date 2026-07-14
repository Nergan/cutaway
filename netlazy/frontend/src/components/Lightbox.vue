<template>
  <transition name="lightbox-fade">
    <div class="lightbox" v-if="store.state.lightbox.open" @click="store.state.lightbox.open = false">
      <button class="lightbox-close"><i class="bi bi-x"></i></button>
      <img v-if="store.state.lightbox.media.type?.startsWith('image') || store.state.lightbox.media.media_type === 'image'" 
           :src="store.state.lightbox.media.url" 
           class="lightbox-content" 
           @click.stop>
      <video v-else-if="store.state.lightbox.media.type?.startsWith('video') || store.state.lightbox.media.media_type === 'video'" 
             :src="store.state.lightbox.media.url" 
             class="lightbox-content" controls autoplay 
             @click.stop></video>
    </div>
  </transition>
</template>

<script setup>
import { useStore } from '../store/state.js'

const store = useStore()
</script>