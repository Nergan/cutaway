import path from 'node:path'
import { fileURLToPath } from 'node:url'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

const here = path.dirname(fileURLToPath(import.meta.url))

// The orchestrator mounts this project at /age and serves the build output from
// <prefix>/static, so every asset URL has to carry that prefix.
export default defineConfig({
  plugins: [react()],
  root: path.resolve(here, 'frontend'),
  base: '/age/static/',
  build: {
    outDir: path.resolve(here, 'static'),
    emptyOutDir: true,
    target: 'es2022',
    // Pixi is the bulk of this and splitting it buys nothing: the game cannot start
    // without the renderer, so a second round trip is pure latency.
    chunkSizeWarningLimit: 1400,
    rollupOptions: {
      input: {
        index: path.resolve(here, 'frontend', 'index.html'),
        atelier: path.resolve(here, 'frontend', 'atelier.html'),
      },
    },
  },
  server: {
    proxy: {
      '/age': {
        target: 'http://127.0.0.1:8140',
        ws: true,
      },
    },
  },
})
