import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig(() => {
  const isMobile = process.env.CAPACITOR_BUILD === 'true';
  return {
    plugins: [vue()],
    root: 'frontend',
    base: isMobile ? './' : '/netlazy/static/',
    build: {
      outDir: '../static',
      emptyOutDir: true,
    }
  }
})