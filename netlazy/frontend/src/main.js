import { createApp } from 'vue'
import App from './App.vue'
import '../style.css'

const app = createApp(App)

app.directive('intersect', {
  mounted(el, binding) {
    const observer = new IntersectionObserver((entries) => {
      if (entries[0].isIntersecting) {
        binding.value();
        observer.disconnect();
      }
    }, { rootMargin: '300px' });
    observer.observe(el);
  }
})

app.mount('#app')