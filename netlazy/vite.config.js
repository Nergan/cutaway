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
      const daylight = /daylight_theme:\s*bool\s*=\s*(True|False)/.exec(config);
      const flag = daylight && daylight[1] === 'False' ? '0' : '1';
      const versionAssignment = `window.__NETLAZY_UI_VERSION__="${version}"`;
      const daylightAssignment = `window.__NETLAZY_DAYLIGHT__="${flag}"`;
      let next = html;
      if (next.includes('window.__NETLAZY_UI_VERSION__')) {
        next = next.replace(/window\.__NETLAZY_UI_VERSION__\s*=\s*"[12]"/, versionAssignment);
      } else {
        next = next.replace('</head>', `<script>${versionAssignment};${daylightAssignment};</script></head>`);
        return next;
      }
      if (next.includes('window.__NETLAZY_DAYLIGHT__')) {
        return next.replace(/window\.__NETLAZY_DAYLIGHT__\s*=\s*"[01]"/, daylightAssignment);
      }
      return next.replace(versionAssignment, `${versionAssignment};${daylightAssignment}`);
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