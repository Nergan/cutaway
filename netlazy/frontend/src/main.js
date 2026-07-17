import { createApp } from 'vue'
import App from './App.vue'
import '../style.css'

const app = createApp(App)

app.directive('intersect', {
  mounted(el, binding) {
    const observer = new IntersectionObserver((entries) => {
      if (entries[0].isIntersecting) {
        // Run binding, but DO NOT disconnect the observer. 
        // This ensures items uploaded dynamically inside the viewport still fire decryption attempts later.
        binding.value();
      }
    }, { rootMargin: '300px' });
    observer.observe(el);
    el._observer = observer;
  },
  unmounted(el) {
    if (el._observer) {
      el._observer.disconnect();
    }
  }
})

app.mount('#app')