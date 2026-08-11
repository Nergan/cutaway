import { createApp } from 'vue'
import App from './App.vue'
import '../style.css'

const app = createApp(App)

const intersectionCallbacks = new WeakMap();
let sharedObserver = null;

function getSharedObserver() {
  if (!sharedObserver) {
    sharedObserver = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          const callback = intersectionCallbacks.get(entry.target);
          if (callback) {
            callback();
          }
        }
      });
    }, { rootMargin: '300px' });
  }
  return sharedObserver;
}

app.directive('intersect', {
  mounted(el, binding) {
    intersectionCallbacks.set(el, binding.value);
    getSharedObserver().observe(el);
  },
  unmounted(el) {
    intersectionCallbacks.delete(el);
    if (sharedObserver) {
      sharedObserver.unobserve(el);
    }
  }
})

app.mount('#app')