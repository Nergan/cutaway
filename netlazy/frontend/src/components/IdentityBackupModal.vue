<template>
  <transition name="lightbox-fade">
    <div class="modal-backdrop" v-if="open" @click="handleCancel">
      <div class="modal-box" @click.stop style="max-width: 480px;">
        <div class="modal-header">
          <i class="bi bi-shield-lock" style="color: var(--accent-moss); margin-right: 0.5rem;"></i>
          {{ store.t('backup_phrase_title') }}
        </div>
        
        <div class="modal-body">
          <p style="margin-bottom: 1rem;">
            {{ store.t('backup_phrase_warning') }}
          </p>

          <div class="code-block" @click="copyPhrase" style="user-select: all; word-break: break-word; font-size: 0.9rem; padding: 1rem; position: relative;">
            {{ phrase }}
            <div style="margin-top: 0.5rem; text-align: right; font-size: 0.75rem; color: var(--accent-moss);">
              <i class="bi bi-copy"></i> {{ store.t('copy') }}
            </div>
          </div>

          <label style="display: flex; align-items: center; gap: 0.6rem; cursor: pointer; margin-top: 1rem; font-size: 0.85rem; color: var(--text-main);">
            <input type="checkbox" v-model="isConfirmed" style="accent-color: var(--accent-moss); width: 16px; height: 16px;">
            <span>{{ store.t('backup_phrase_confirm_checkbox') }}</span>
          </label>
        </div>

        <div class="modal-footer">
          <button class="footer-action" style="color: var(--text-muted);" @click="handleCancel">
            {{ store.t('backup_phrase_cancel_btn') }}
          </button>
          <button class="footer-action" 
                  :disabled="!isConfirmed"
                  :style="{ 
                    color: isConfirmed ? 'var(--accent-moss)' : 'var(--text-muted)',
                    opacity: isConfirmed ? 1 : 0.4,
                    cursor: isConfirmed ? 'pointer' : 'not-allowed'
                  }" 
                  @click="handleConfirm">
            <i class="bi bi-check2"></i> {{ store.t('backup_phrase_confirm_btn') }}
          </button>
        </div>
      </div>
    </div>
  </transition>
</template>

<script setup>
import { ref, watch } from 'vue';
import { useStore } from '../store/state.js';

const props = defineProps({
  open: {
    type: Boolean,
    default: false
  },
  phrase: {
    type: String,
    default: ''
  }
});

const emit = defineEmits(['confirm', 'cancel']);
const store = useStore();
const isConfirmed = ref(false);

// Сбрасываем чекбокс при каждом открытии модального окна
watch(() => props.open, (isOpen) => {
  if (isOpen) {
    isConfirmed.value = false;
  }
});

async function copyPhrase() {
  if (props.phrase) {
    await navigator.clipboard.writeText(props.phrase);
    store.addToast(store.t('copied'), 'bi-check2');
  }
}

function handleConfirm() {
  if (isConfirmed.value) {
    emit('confirm');
  }
}

function handleCancel() {
  emit('cancel');
}
</script>