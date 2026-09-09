import '@testing-library/jest-dom/vitest';

import {cleanup, configure} from '@testing-library/react';
import {afterAll, afterEach} from 'vitest';

import {server} from './server';

// Booting <App/> costs a lazy route import plus several MSW round trips, which
// can exceed testing-library's 1s default on a loaded machine. Match the
// explicit 10s timeouts the per-component suites already pass.
configure({asyncUtilTimeout: 10_000});

server.listen({onUnhandledRequest: 'error'});
afterEach(() => {
  cleanup();
  server.resetHandlers();
  globalThis.sessionStorage.clear();
  if (typeof globalThis.localStorage?.clear === 'function') {
    globalThis.localStorage.clear();
  }
});
afterAll(() => server.close());
