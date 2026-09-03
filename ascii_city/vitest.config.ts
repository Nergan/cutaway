import { defineConfig } from 'vitest/config'

// Kept separate from vite.config.ts because Vitest ships its own Vite, and
// mixing the two type trees in one file makes the build config unresolvable.
// Nothing under test needs the React plugin: these are pure logic suites.
export default defineConfig({
  test: {
    include: ['frontend/src/**/*.test.ts'],
    environment: 'node',
  },
})
