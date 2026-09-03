import path from 'node:path'
import { fileURLToPath } from 'node:url'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

const here = path.dirname(fileURLToPath(import.meta.url))

// The orchestrator mounts this project at /ascii-city and serves the build
// output from <prefix>/static, so every asset URL has to carry that prefix.
export default defineConfig({
  plugins: [react()],
  root: path.resolve(here, 'frontend'),
  base: '/ascii-city/static/',
  build: {
    outDir: path.resolve(here, 'static'),
    emptyOutDir: true,
    target: 'es2022',
    // Shaders and the tile decoder are small; one chunk beats three round trips.
    chunkSizeWarningLimit: 700,
  },
  server: {
    proxy: {
      '/ascii-city': {
        target: 'http://127.0.0.1:8130',
        ws: true,
      },
    },
  },
})
