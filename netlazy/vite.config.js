import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import fs from 'fs'
import path from 'path'
import { fileURLToPath } from 'url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)

function interfaceVersionPlugin() {
  return {
    name: 'netlazy-interface-version',
    transformIndexHtml(html) {
      const configPath = path.resolve(__dirname, 'config.py');
      const config = fs.readFileSync(configPath, 'utf8');
      const match = config.match(/interface_version:\s*Literal\["1",\s*"2"\]\s*=\s*"([12])"/);
      const version = match ? match[1] : '1';
      const assignment = `window.__NETLAZY_UI_VERSION__="${version}"`;
      if (html.includes('window.__NETLAZY_UI_VERSION__')) {
        return html.replace(/window\.__NETLAZY_UI_VERSION__\s*=\s*"[12]"/, assignment);
      }
      return html.replace('</head>', `<script>${assignment};</script></head>`);
    }
  };
}

export default defineConfig(() => {
  const isMobile = process.env.CAPACITOR_BUILD === 'true';
  return {
    plugins: [vue(), interfaceVersionPlugin()],
    root: path.resolve(__dirname, 'frontend'),
    base: isMobile ? './' : '/netlazy/static/',
    build: {
      outDir: path.resolve(__dirname, 'static'),
      emptyOutDir: true,
    }
  }
})