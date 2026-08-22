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

          <div style="background: var(--bg-surface); border: 1px solid var(--border-subtle); border-radius: var(--radius-md); padding: 1.2rem; margin: 1rem 0;">
            <div style="font-family: monospace; font-size: 0.95rem; word-break: break-all; color: var(--text-main); line-height: 1.6; user-select: text; text-align: center; letter-spacing: 0.5px;">
              {{ phrase }}
            </div>

          </div>

          <label class="custom-checkbox-row" style="display: flex; align-items: center; gap: 0.8rem; cursor: pointer; margin-top: 2rem; padding: 0.8rem 1rem; border-radius: var(--radius-md); border: 1px solid var(--border-subtle); background: var(--bg-elevated); transition: border-color 0.2s;">
            <div style="width: 22px; height: 22px; border-radius: 6px; border: 2px solid var(--border-focus); display: flex; align-items: center; justify-content: center; transition: all 0.2s; flex-shrink: 0;" :style="isConfirmed ? 'background: var(--accent-moss); border-color: var(--accent-moss);' : 'background: transparent;'">
              <i class="bi bi-check" style="color: #000; font-size: 1.2rem; line-height: 1; margin-top: 2px;" v-if="isConfirmed"></i>
            </div>
            <input type="checkbox" v-model="isConfirmed" style="display: none;">
            <span style="font-size: 0.85rem; color: var(--text-main); user-select: none; line-height: 1.4;">{{ store.t('backup_phrase_confirm_checkbox') }}</span>
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
            <i class="bi" :class="isCopied ? 'bi-check2-all' : 'bi-files'"></i> {{ isCopied ? store.t('copied') : store.t('copy_and_continue') }}
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
const isCopied = ref(false);
let copyTimeout = null;

watch(() => props.open, (isOpen) => {
  if (isOpen) {
    isConfirmed.value = false;
    isCopied.value = false;
  }
});

async function copyPhrase(e) {
  if (e) {
    e.preventDefault?.();
    e.stopPropagation?.();
  }
  if (!props.phrase) return;

  let copied = false;
  if (navigator.clipboard && navigator.clipboard.writeText) {
    try {
      await navigator.clipboard.writeText(props.phrase);
      copied = true;
    } catch (e) {}
  }
  if (!copied) {
    try {
      const el = document.createElement('textarea');
      el.value = props.phrase;
      el.setAttribute('readonly', '');
      el.style.position = 'fixed';
      el.style.top = '0';
      el.style.left = '0';
      el.style.opacity = '0';
      document.body.appendChild(el);
      el.focus();
      el.select();
      copied = document.execCommand('copy');
      document.body.removeChild(el);
    } catch (e) {}
  }

  window.getSelection()?.removeAllRanges();

  if (copied) {
    isCopied.value = true;
    store.addToast(store.t('copied'), 'bi-check2');
    if (copyTimeout) clearTimeout(copyTimeout);
    copyTimeout = setTimeout(() => {
      isCopied.value = false;
    }, 2500);
  } else {
    store.addToast("Failed to copy key", 'bi-x-circle');
  }
}

async function handleConfirm() {
  if (isConfirmed.value) {
    await copyPhrase();
    emit('confirm');
  }
}

function handleCancel() {
  emit('cancel');
}
</script>