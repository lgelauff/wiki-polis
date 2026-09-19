import {QueryClientProvider} from '@tanstack/react-query';
import {render, screen} from '@testing-library/react';
import {http, HttpResponse} from 'msw';
import {MemoryRouter} from 'react-router-dom';
import {expect, test} from 'vitest';

import {App} from '../../app';
import {createQueryClient} from '../../query-client';
import {server} from '../../test/server';

function renderRoute(route: string) {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={[route]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

test('renders the entry fork with the legacy shell and card contract', async () => {
  renderRoute('/app/parity/fork');

  expect(await screen.findByRole('heading', {name: 'Where the community finds structure in its opinions.'})).toBeVisible();
  expect(screen.getByRole('link', {name: 'Proto'})).toHaveClass('header-logo');
  expect(screen.getByRole('link', {name: /Try out the platform/})).toHaveClass('fork-card--demo');
  expect(screen.getByRole('link', {name: /Participate in open consultations/})).toHaveClass('fork-card--real');
  expect(screen.getByRole('link', {name: /Open an issue/})).toHaveAttribute('target', '_blank');
  expect(screen.getByText('test-version')).toBeVisible();
  expect(document.querySelector('link[data-react-legacy-styles]')).toBeNull();
});

test('renders server-projected developer login shortcuts without environment logic', async () => {
  server.use(http.get(
    new URL('/api/v1/session', globalThis.location.origin).toString(),
    () => HttpResponse.json({data: {
      state: 'anonymous',
      user: null,
      capabilities: {administerSite: false},
      csrfToken: 'test-csrf-token',
      developerLogins: [
        {username: 'dev-user-1', href: '/dev/login/dev-user-1'},
        {username: 'dev-user-2', href: '/dev/login/dev-user-2'},
      ],
      gitVersion: 'test-version',
      locales: {current: 'en', available: [{code: 'en', name: 'English'}]},
      links: {login: '/login', logout: '/logout'},
    }}),
  ));

  renderRoute('/app/parity/fork');

  expect(await screen.findByTitle('Log in as dev-user-1')).toHaveAttribute(
    'href', '/dev/login/dev-user-1',
  );
  expect(screen.getByTitle('Log in as dev-user-2')).toBeVisible();
});

test('renders the complete statement-writing guide', async () => {
  renderRoute('/app/parity/help/statements');

  expect(await screen.findByRole('heading', {name: 'Writing good statements'})).toBeVisible();
  expect(screen.getByText('statement guide').closest('.header-crumb')).toHaveClass('header-crumb');
  expect(screen.getByText('Make one claim.')).toBeVisible();
  expect(screen.getByRole('heading', {name: 'When to pass'})).toBeVisible();
});

test('renders the complete argument-writing guide', async () => {
  renderRoute('/app/parity/help/arguments');

  expect(await screen.findByRole('heading', {name: 'Writing good arguments'})).toBeVisible();
  expect(screen.getByText('argument guide').closest('.header-crumb')).toHaveClass('header-crumb');
  expect(screen.getByText('State the direction.')).toBeVisible();
  expect(screen.getByRole('heading', {name: 'Moderation baseline'})).toBeVisible();
});

test('the language switcher offers the enabled languages by their own names', async () => {
  server.use(http.get(
    new URL('/api/v1/session', globalThis.location.origin).toString(),
    () => HttpResponse.json({data: {
      state: 'anonymous',
      user: null,
      capabilities: {administerSite: false},
      csrfToken: 'test-csrf-token',
      developerLogins: [],
      gitVersion: 'test-version',
      locales: {current: 'en', available: [
        {code: 'en', name: 'English'},
        {code: 'nl', name: 'Nederlands'},
      ]},
      links: {login: '/login', logout: '/logout'},
    }}),
  ));

  renderRoute('/app/parity/fork');

  // Autonyms, never translated: someone looking for Dutch scans for "Nederlands".
  const select = await screen.findByRole('combobox', {name: 'Language'});
  const options = Array.from(select.querySelectorAll('option'));
  expect(options).toHaveLength(2);
  expect(options.map(o => o.textContent)).toEqual(['English', 'Nederlands']);
  // Each option carries its language code as the value.
  expect(options[0]!.value).toBe('en');
  expect(options[1]!.value).toBe('nl');
  // Options carry the lang attribute for script selection.
  expect(options[0]!.getAttribute('lang')).toBe('en');
  expect(options[1]!.getAttribute('lang')).toBe('nl');
  // The active language is selected.
  expect(options[0]!.selected).toBe(true);
  expect(options[1]!.selected).toBe(false);
});
