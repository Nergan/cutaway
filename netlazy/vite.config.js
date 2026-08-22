import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'
import { fileURLToPath } from 'url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)

export default defineConfig(() => {
  const isMobile = process.env.CAPACITOR_BUILD === 'true';
  return {
    plugins: [vue()],
    root: path.resolve(__dirname, 'frontend'),
    base: isMobile ? './' : '/netlazy/static/',
    build: {
      outDir: path.resolve(__dirname, 'static'),
      emptyOutDir: true,
      rollupOptions: {
        input: {
          main: path.resolve(__dirname, 'frontend/index.html'),
          ...(isMobile ? {} : { welcome: path.resolve(__dirname, 'welcome.html') })
        }
      }
    }
  }
})