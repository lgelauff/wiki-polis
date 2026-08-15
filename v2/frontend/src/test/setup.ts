import '@testing-library/jest-dom/vitest';

import {cleanup} from '@testing-library/react';
import {afterAll, afterEach} from 'vitest';

import {server} from './server';

server.listen({onUnhandledRequest: 'error'});
afterEach(() => {
  cleanup();
  server.resetHandlers();
  globalThis.sessionStorage.clear();
  if (typeof globalThis.localStorage?.clear === 'function') {
    globalThis.localStorage.clear();
  }
  document.cookie = 'wiki-polis-spa-only=; Path=/; Max-Age=0; SameSite=Lax';
});
afterAll(() => server.close());
