import '@testing-library/jest-dom/vitest';

import {cleanup} from '@testing-library/react';
import {afterAll, afterEach} from 'vitest';

import {server} from './server';

server.listen({onUnhandledRequest: 'error'});
afterEach(() => {
  cleanup();
  server.resetHandlers();
  globalThis.sessionStorage.clear();
});
afterAll(() => server.close());
