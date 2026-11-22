import {QueryClientProvider} from '@tanstack/react-query';
import {render, screen} from '@testing-library/react';
import {http, HttpResponse} from 'msw';
import {MemoryRouter} from 'react-router-dom';
import {expect, test} from 'vitest';

import {App} from '../../app';
import {createQueryClient} from '../../query-client';
import {adminCatalogFixture} from '../../test/handlers';
import {server} from '../../test/server';

const CATALOG_URL = new URL('/api/v1/admin', globalThis.location.origin).toString();
const SESSION_URL = new URL('/api/v1/session', globalThis.location.origin).toString();

function serveSession(maintenance: boolean) {
  server.use(http.get(SESSION_URL, () => HttpResponse.json({data: {
    state: 'authenticated',
    user: {username: 'Example moderator', emailable: true},
    capabilities: {administerSite: false},
    maintenance,
    csrfToken: 'test-csrf-token',
    developerLogins: [],
    gitVersion: 'test-version',
    locales: {current: 'en', available: [{code: 'en', name: 'English'}]},
    links: {login: '/login', logout: '/logout'},
  }})));
}

test('a console read refused for maintenance shows the maintenance page, and the screen once it is off', async () => {
  // A moderator's console reads are paused while maintenance mode is on (#619). The refusal
  // goes through the router's boundary (`AdminAccessBoundary`), so this goes through the app.
  serveSession(true);
  server.use(http.get(CATALOG_URL, () => HttpResponse.json({
    error: {code: 'maintenance', message: 'Proto is being updated.'},
  }, {status: 503})));
  const client = createQueryClient();
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/app/admin']}><App /></MemoryRouter>
    </QueryClientProvider>,
  );
  expect(await screen.findByRole('heading', {name: 'Proto is being updated', level: 1})).toBeVisible();

  // The switch goes off: the next session read says so, and the screen loads by itself.
  serveSession(false);
  server.use(http.get(CATALOG_URL, () => HttpResponse.json({data: adminCatalogFixture()})));
  await client.invalidateQueries({queryKey: ['session']});
  expect(await screen.findByRole('heading', {name: 'Site admin dashboard', level: 1})).toBeVisible();
  expect(screen.queryByRole('heading', {name: 'Proto is being updated'})).toBeNull();
});
