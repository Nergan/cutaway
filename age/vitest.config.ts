import { defineConfig } from 'vitest/config'

// Kept separate from vite.config.ts because Vitest ships its own Vite, and mixing the
// two type trees in one file makes the build config unresolvable. Nothing under test
// needs the React plugin or a DOM: these are pure logic suites, which is deliberate —
// the parity-critical code is all free of browser dependencies so it can be tested
// against the Python reference without a headless browser.
export default defineConfig({
  test: {
    include: ['frontend/src/**/*.test.ts'],
    environment: 'node',
  },
})
