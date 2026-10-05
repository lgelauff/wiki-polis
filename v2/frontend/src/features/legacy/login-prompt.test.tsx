import {QueryClientProvider} from '@tanstack/react-query';
import {render, screen} from '@testing-library/react';
import {http, HttpResponse} from 'msw';
import {MemoryRouter, useLocation} from 'react-router-dom';
import {afterEach, beforeEach, expect, test, vi, type MockInstance} from 'vitest';

import {App} from '../../app';
import {createQueryClient} from '../../query-client';
import {renderAsQqx, untranslatedCopy} from '../../test/i18n';
import {testMessages} from '../../test/handlers';
import {server} from '../../test/server';

const url = (path: string) => new URL(path, globalThis.location.origin).toString();

function serveSession(state: 'anonymous' | 'demo' | 'voucher') {
  server.use(http.get(url('/api/v1/session'), () => HttpResponse.json({data: {
    state,
    user: null,
    capabilities: {administerSite: false},
    csrfToken: 'test-csrf-token',
    developerLogins: [],
    gitVersion: 'test-version',
    locales: {current: 'en', available: [{code: 'en', name: 'English'}]},
    links: {login: '/login', logout: '/logout'},
  }})));
}

const unauthorized = () => HttpResponse.json({error: {code: 'unauthorized', message: 'Login required.'}}, {status: 401});

/** Where the router is: a redirect inside the SPA would move it. */
function RouterLocation() {
  const location = useLocation();
  return <output data-testid="router-location">{`${location.pathname}${location.search}`}</output>;
}

function renderAt(path: string) {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={[path]}><App /><RouterLocation /></MemoryRouter>
    </QueryClientProvider>,
  );
}

// jsdom cannot leave the document: location.assign('/login…') — what the old redirect did —
// reports "Not implemented: navigation" through console.error. Location's methods are
// unforgeable in jsdom, so this report is the observable trace of a full-page navigation.
let consoleError: MockInstance;
beforeEach(() => { consoleError = vi.spyOn(console, 'error'); });
afterEach(() => consoleError.mockRestore());

function navigationAttempts() {
  return consoleError.mock.calls.filter((args) => args.some((arg) => String(arg instanceof Error ? arg.message : arg).includes('navigation')));
}

async function expectPrompt(path: string) {
  const heading = await screen.findByRole('heading', {level: 1, name: testMessages['login-prompt-heading']!});
  expect(heading).toBeVisible();
  expect(screen.getByText(testMessages['login-prompt-body']!)).toBeVisible();
  // The button returns to this very page, query included, after the login (#441).
  expect(screen.getByRole('link', {name: testMessages['home-login-wikimedia']!}))
    .toHaveAttribute('href', `/login?next=${encodeURIComponent(path)}`);
  expect(screen.getByRole('link', {name: testMessages['login-prompt-back']!})).toHaveAttribute('href', '/consultations');
  // Nothing moved without a click: not the router, not the document.
  expect(screen.getByTestId('router-location')).toHaveTextContent(path);
  expect(navigationAttempts()).toEqual([]);
}

test('a logged-out visitor to a consultation is asked, not sent, to log in', async () => {
  serveSession('anonymous');
  server.use(http.get(url('/api/v1/conversations/:slug/workspace'), unauthorized));
  renderAt('/c/community-strategy?uselang=en');
  await expectPrompt('/c/community-strategy?uselang=en');
  expect(document.title).toBe(testMessages['login-prompt-doc-title']);
});

test('the first logged-out load of a consultation paints the prompt, not a blank page', async () => {
  // A private window: no cookie, so the session is anonymous and the workspace refuses. The
  // old redirect rendered nothing while the browser left for the login (#510).
  serveSession('anonymous');
  server.use(http.get(url('/api/v1/conversations/:slug/workspace'), unauthorized));
  renderAt('/c/test');
  await expectPrompt('/c/test');
  expect(document.getElementById('main')).not.toBeEmptyDOMElement();
});

test.each(['anonymous', 'demo'] as const)('a %s visitor on the join page is asked, not sent, to log in', async (state) => {
  serveSession(state);
  renderAt('/accept/community-strategy');
  await expectPrompt('/accept/community-strategy');
});

test.each(['anonymous', 'voucher'] as const)('a %s visitor on username linking is asked, not sent, to log in', async (state) => {
  serveSession(state);
  renderAt('/c/community-strategy/reveal');
  await expectPrompt('/c/community-strategy/reveal');
});

test('a logged-out visitor to members-only results is asked, not sent, to log in', async () => {
  serveSession('anonymous');
  server.use(http.get(url('/api/v1/conversations/:slug/results'), unauthorized));
  renderAt('/c/community-strategy/report?uselang=en');
  await expectPrompt('/c/community-strategy/report?uselang=en');
});

test('a voucher code in the address never rides along to the login', async () => {
  serveSession('anonymous');
  renderAt('/accept/community-strategy?v=X7F3K9M2ABCD');
  expect(await screen.findByRole('link', {name: testMessages['home-login-wikimedia']!}))
    .toHaveAttribute('href', `/login?next=${encodeURIComponent('/accept/community-strategy')}`);
});

test('under qqx, the login prompt carries no English', async () => {
  renderAsQqx();
  serveSession('anonymous');
  server.use(http.get(url('/api/v1/conversations/:slug/workspace'), unauthorized));
  renderAt('/c/community-strategy');
  await screen.findByRole('heading', {level: 1, name: '(login-prompt-heading)'});
  expect(untranslatedCopy([document.getElementById('main')])).toEqual([]);
});
