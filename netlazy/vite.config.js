import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'

export default defineConfig({
  plugins: [vue()],
  root: 'frontend',
  base: '/netlazy/static/',
  build: {
    outDir: '../static',
    emptyOutDir: true,
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './frontend/src')
    }
  }
})