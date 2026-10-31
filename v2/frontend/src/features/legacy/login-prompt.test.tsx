import {QueryClientProvider} from '@tanstack/react-query';
import {render, screen} from '@testing-library/react';
import {http, HttpResponse} from 'msw';
import {MemoryRouter, useLocation} from 'react-router-dom';
import {afterEach, beforeEach, expect, test, vi, type MockInstance} from 'vitest';

import {introExcerpt} from './login-prompt';

import {App} from '../../app';
import {createQueryClient} from '../../query-client';
import {renderAsQqx, untranslatedCopy} from '../../test/i18n';
import {testMessages} from '../../test/handlers';
import {server} from '../../test/server';

const url = (path: string) => new URL(path, globalThis.location.origin).toString();

type VoucherConsultation = {slug: string; title: string};

function serveSession(state: 'anonymous' | 'demo' | 'voucher', voucherConsultation: VoucherConsultation | null = null) {
  server.use(http.get(url('/api/v1/session'), () => HttpResponse.json({data: {
    state,
    user: null,
    voucherConsultation,
    capabilities: {administerSite: false},
    csrfToken: 'test-csrf-token',
    developerLogins: [],
    gitVersion: 'test-version',
    locales: {current: 'en', available: [{code: 'en', name: 'English'}]},
    links: {login: '/login', logout: '/logout'},
  }})));
}

const unauthorized = () => HttpResponse.json({error: {code: 'unauthorized', message: 'Login required.'}}, {status: 401});

/** The About endpoint's refusal. Its details carry the title, which the prompt must not use. */
function refuseAbout(slug: string, gatingType: string, title = 'Secret board election') {
  server.use(http.get(url(`/api/v1/conversations/${slug}/about`), () => HttpResponse.json({error: {
    code: 'access_required', message: 'Access required.',
    details: {slug, title, gatingType, viewer: 'logged_out', certainty: 'known', reason: null, loginOptions: [], sharedResults: []},
  }}, {status: 403})));
}

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
  // The heading takes focus, so a screen reader announces the page that replaced the one asked for.
  expect(heading).toHaveFocus();
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
  server.use(http.get(url('/api/v1/conversations/test/about'), () => HttpResponse.json({error: {code: 'not_found', message: 'Not found.'}}, {status: 404})));
  renderAt('/c/test');
  await expectPrompt('/c/test');
  expect(document.getElementById('main')).not.toBeEmptyDOMElement();
});

test.each(['anonymous', 'demo'] as const)('a %s visitor on the join page is asked, not sent, to log in', async (state) => {
  serveSession(state);
  renderAt('/accept/community-strategy');
  await expectPrompt('/accept/community-strategy');
});

test('a logged-out visitor on username linking is asked, not sent, to log in', async () => {
  serveSession('anonymous');
  renderAt('/c/community-strategy/reveal');
  await expectPrompt('/c/community-strategy/reveal');
});

test('a public consultation\'s prompt names it, starts its introduction and links its About page', async () => {
  serveSession('anonymous');
  server.use(http.get(url('/api/v1/conversations/:slug/workspace'), unauthorized));
  renderAt('/c/community-strategy');
  await expectPrompt('/c/community-strategy');
  expect(screen.getByText('Community strategy')).toBeVisible();
  expect(screen.getByText('Shape the next chapter together.')).toBeVisible();
  expect(screen.getByRole('link', {name: testMessages['login-prompt-about']!})).toHaveAttribute('href', '/c/community-strategy/about');
});

test('a gated consultation gets the generic prompt and never its name', async () => {
  serveSession('anonymous');
  refuseAbout('community-strategy', 'invite');
  server.use(http.get(url('/api/v1/conversations/:slug/workspace'), unauthorized));
  renderAt('/accept/community-strategy');
  await expectPrompt('/accept/community-strategy');
  expect(screen.queryByText(/Secret board election/)).toBeNull();
  expect(screen.queryByRole('link', {name: testMessages['login-prompt-about']!})).toBeNull();
});

test('a voucher-only consultation points a logged-out (or expired) visitor to the code, not to Wikimedia', async () => {
  serveSession('anonymous');
  refuseAbout('community-strategy', 'voucher');
  renderAt('/c/community-strategy/reveal');
  const heading = await screen.findByRole('heading', {level: 1, name: testMessages['forbidden-voucher-heading']!});
  expect(heading).toHaveFocus();
  // The body says the same code brings them back, rather than repeating the heading.
  expect(screen.getByText(testMessages['login-prompt-voucher-body']!)).toBeVisible();
  expect(screen.queryByText(testMessages['voucher-page-intro']!)).toBeNull();
  expect(screen.getByRole('link', {name: testMessages['forbidden-voucher-link']!})).toHaveAttribute('href', '/c/community-strategy/v');
  expect(screen.queryByRole('link', {name: testMessages['home-login-wikimedia']!})).toBeNull();
  expect(screen.queryByText(/Secret board election/)).toBeNull();
  expect(navigationAttempts()).toEqual([]);
});

test('the introduction excerpt is the first paragraph as text, cut at a word', () => {
  expect(introExcerpt('<p>One <strong>two</strong> &amp; three.</p><p>Second.</p>')).toBe('One two & three.');
  const long = introExcerpt(`<p>${'word '.repeat(100)}</p>`);
  expect(long.endsWith('word…')).toBe(true);
  expect(long.length).toBeLessThanOrEqual(301);
  expect(introExcerpt(null)).toBe('');
});

// ── A single-consultation (voucher) account is asked to log out first (#514) ──

const own = {slug: 'library-hours', title: 'Library opening hours'};

async function expectLogoutChoice(path: string) {
  const heading = await screen.findByRole('heading', {level: 1, name: testMessages['logout-choice-heading']!});
  expect(heading).toHaveFocus();
  expect(screen.getByText(testMessages['logout-choice-body']!)).toBeVisible();
  const confirm = screen.getByRole('button', {name: testMessages['logout-choice-confirm']!});
  const form = confirm.closest('form')!;
  expect(form).toHaveAttribute('method', 'post');
  expect(form).toHaveAttribute('action', '/logout');
  expect(form.querySelector('input[name="csrf_token"]')).toHaveValue('test-csrf-token');
  expect(form.querySelector('input[name="next"]')).toHaveValue(path);
  // "Back" names the consultation the account belongs to, wherever the visitor came from.
  expect(screen.getByRole('link', {name: testMessages['logout-choice-back']!.replace('$1', own.title)}))
    .toHaveAttribute('href', '/c/library-hours');
  // No login is offered while the voucher account is logged in, and nothing moved.
  expect(screen.queryByRole('link', {name: testMessages['home-login-wikimedia']!})).toBeNull();
  expect(screen.queryByText(testMessages['login-prompt-body']!)).toBeNull();
  expect(navigationAttempts()).toEqual([]);
}

test('a voucher account on another consultation\'s username linking is asked to log out of its own first', async () => {
  serveSession('voucher', own);
  refuseAbout('community-strategy', 'invite');
  renderAt('/c/community-strategy/reveal?uselang=en&v=X7F3K9M2ABCD');
  await expectLogoutChoice('/c/community-strategy/reveal?uselang=en');
  expect(screen.queryByText(/Secret board election/)).toBeNull();
});

test('the log-out-first page names no title of the page tried, even a public one', async () => {
  serveSession('voucher', own);
  renderAt('/c/community-strategy/reveal');
  await expectLogoutChoice('/c/community-strategy/reveal');
  expect(screen.queryByText('Community strategy')).toBeNull();
});

test('the header names a voucher session\'s account kind as plain text, never a username', async () => {
  serveSession('voucher', own);
  renderAt('/c/community-strategy/reveal');
  await screen.findByRole('heading', {level: 1, name: testMessages['logout-choice-heading']!});
  const header = document.querySelector('header')!;
  const label = screen.getByText(testMessages['base-single-consultation-account']!);
  expect(header).toContainElement(label);
  // A status, not a name: no chip around it.
  expect(label.closest('.header-user-chip')).toBeNull();
  expect(header).toHaveTextContent(testMessages['base-log-out']!);
});

test('under qqx, the log-out-first page carries no English', async () => {
  renderAsQqx();
  serveSession('voucher', own);
  renderAt('/c/community-strategy/reveal');
  await screen.findByRole('heading', {level: 1, name: '(logout-choice-heading)'});
  // Organizer-written titles are content, not interface copy.
  expect(untranslatedCopy([document.getElementById('main')], [own.title])).toEqual([]);
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
  expect(untranslatedCopy([document.getElementById('main')], ['Community strategy', 'Shape the next chapter together.'])).toEqual([]);
});
