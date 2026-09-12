import react from '@vitejs/plugin-react';
import {defineConfig} from 'vitest/config';

export default defineConfig({
  plugins: [react()],
  base: '/static/spa/',
  build: {
    outDir: '../static/spa',
    emptyOutDir: true,
    manifest: true,
  },
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:5000',
      '/login': 'http://127.0.0.1:5000',
      '/logout': 'http://127.0.0.1:5000',
      '/c': 'http://127.0.0.1:5000',
      '/admin': 'http://127.0.0.1:5000',
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    restoreMocks: true,
    // Leave room for several sequential 10s findBy* waits (see src/test/setup.ts)
    // before vitest's own timer fires.
    testTimeout: 30_000,
    hookTimeout: 30_000,
    // Pin the timezone. Four components format dates with toLocale*, so any test
    // asserting rendered date text silently depends on the machine's zone -- it
    // passed locally in CEST and failed in CI on UTC, two hours apart. UTC matches
    // what CI runs, so local and CI now agree.
    env: {TZ: 'UTC'},
  },
});
