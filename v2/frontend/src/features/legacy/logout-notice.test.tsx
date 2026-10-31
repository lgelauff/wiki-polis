import {QueryClientProvider} from '@tanstack/react-query';
import {act, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {http, HttpResponse} from 'msw';
import {MemoryRouter, useLocation, useNavigate} from 'react-router-dom';
import {afterEach, expect, test, vi} from 'vitest';

import {App} from '../../app';
import {createQueryClient} from '../../query-client';
import {renderAsQqx, untranslatedCopy} from '../../test/i18n';
import {testMessages} from '../../test/handlers';
import {server} from '../../test/server';

// The one-time note on the page a logout lands on (#514). The server hands it out once, in
// the session response, and forgets it (tests/test_voucher.py); here: the SPA shows it on
// that page only.

const url = (path: string) => new URL(path, globalThis.location.origin).toString();

type Notice = 'logged-out' | 'voucher' | 'revoked' | null;
type Session = {state: 'anonymous' | 'voucher'; logoutNotice: Notice};

function sessionBody({state, logoutNotice}: Session) {
  return {data: {
    state,
    user: null,
    voucherConsultation: state === 'voucher' ? {slug: 'community-strategy', title: 'Community strategy'} : null,
    logoutNotice,
    capabilities: {administerSite: false},
    csrfToken: 'test-csrf-token',
    developerLogins: [],
    gitVersion: 'test-version',
    locales: {current: 'en', available: [{code: 'en', name: 'English'}]},
    links: {login: '/login', logout: '/logout'},
  }};
}

/** Serves each session in turn, then the last one for every later request, as the server
 *  does: the note is in the first response after the logout only. */
function serveSessions(...sessions: Session[]) {
  let call = 0;
  server.use(http.get(url('/api/v1/session'), () => {
    const next = sessions[Math.min(call, sessions.length - 1)]!;
    call += 1;
    return HttpResponse.json(sessionBody(next));
  }));
}

function renderAt(path: string) {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={[path]}><App /></MemoryRouter>
    </QueryClientProvider>,
  );
}

/** Lets a test navigate the router as a page would: a redirect is `replace`. */
let navigateTo: ((to: string, replace: boolean) => void) | null = null;
function CaptureNavigate() {
  const navigate = useNavigate();
  navigateTo = (to, replace) => { void navigate(to, {replace}); };
  return null;
}

function RouterPath() {
  return <output data-testid="router-path">{useLocation().pathname}</output>;
}

const reminder = testMessages['logout-notice-voucher']!;

/** The logout note: a toast in the top-right container of the shell. */
function note() {
  return document.querySelector('.toast-container-top .toast');
}

test('after a Wikimedia logout from the header, home says "You are logged out." once', async () => {
  serveSessions({state: 'anonymous', logoutNotice: 'logged-out'}, {state: 'anonymous', logoutNotice: null});
  renderAt('/');
  const text = await screen.findByText(testMessages['logout-notice']!, {}, {timeout: 10_000});
  expect(text).toBeVisible();
  expect(note()).toHaveAttribute('role', 'status');
  expect(note()).toHaveClass('toast', 'toast--info');
  // Not a voucher account: no reminder about a code.
  expect(screen.queryByText(reminder, {exact: false})).toBeNull();
});

afterEach(() => { vi.useRealTimers(); });

test('"You are logged out." closes itself after 5 seconds, like any info toast', async () => {
  vi.useFakeTimers({shouldAdvanceTime: true});
  serveSessions({state: 'anonymous', logoutNotice: 'logged-out'}, {state: 'anonymous', logoutNotice: null});
  renderAt('/c/community-strategy/reveal');
  await screen.findByText(testMessages['logout-notice']!, {}, {timeout: 10_000});
  act(() => { vi.advanceTimersByTime(4_000); });
  expect(note()).not.toBeNull();
  // Generous: a late re-render (session refetch under a loaded runner) re-arms the timer.
  act(() => { vi.advanceTimersByTime(10_000); });
  await waitFor(() => expect(note()).toBeNull());
});

test.each([
  ['voucher', 'logout-notice-voucher'],
  ['revoked', 'logout-notice-revoked'],
] as const)('the %s note stays until closed with ×', async (kind, key) => {
  vi.useFakeTimers({shouldAdvanceTime: true});
  serveSessions({state: 'anonymous', logoutNotice: kind}, {state: 'anonymous', logoutNotice: null});
  renderAt('/c/community-strategy/reveal');
  await screen.findByText(testMessages[key]!, {exact: false}, {timeout: 10_000});
  act(() => { vi.advanceTimersByTime(60_000); });
  expect(note()).toHaveTextContent(testMessages[key]!);
  fireEvent.click(screen.getByRole('button', {name: testMessages['base-dismiss']!}));
  expect(note()).toBeNull();
});

test('a voucher logout adds how to come back to the account, and is gone on the next page', async () => {
  serveSessions({state: 'anonymous', logoutNotice: 'voucher'}, {state: 'anonymous', logoutNotice: null});
  server.use(http.get(url('/api/v1/conversations/:slug/workspace'), () => HttpResponse.json({error: {code: 'unauthorized', message: 'Login required.'}}, {status: 401})));
  renderAt('/c/community-strategy/reveal');
  await screen.findByRole('heading', {level: 1, name: testMessages['login-prompt-heading']!});
  const toast = note()!;
  expect(toast).toHaveAttribute('role', 'status');
  expect(toast).toHaveClass('toast--info');
  expect(toast).toHaveTextContent(`${testMessages['logout-notice']!} ${reminder}`);
  // Never a code or a link in it.
  expect(toast.querySelector('a')).toBeNull();

  fireEvent.click(screen.getByRole('link', {name: testMessages['login-prompt-back']!}));
  await waitFor(() => expect(note()).toBeNull());
});

test.each([
  ['follows a redirect, such as a consultation sending a newcomer to its join page', true],
  ['is dropped by an ordinary navigation', false],
])('the note %s', async (_, replace) => {
  serveSessions({state: 'voucher', logoutNotice: 'voucher'}, {state: 'voucher', logoutNotice: null});
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={['/app/real']}><App /><CaptureNavigate /><RouterPath /></MemoryRouter>
    </QueryClientProvider>,
  );
  await waitFor(() => expect(note()).not.toBeNull(), {timeout: 10_000});
  act(() => navigateTo!('/consultations', replace));
  await waitFor(() => expect(screen.getByTestId('router-path')).toHaveTextContent('/consultations'));
  await screen.findAllByText(testMessages['base-log-out']!);
  if (replace) expect(note()).toHaveTextContent(testMessages['logout-notice']!);
  else expect(note()).toBeNull();
});

test('no note when the session carries none', async () => {
  serveSessions({state: 'anonymous', logoutNotice: null});
  renderAt('/c/community-strategy/reveal');
  await screen.findByRole('heading', {level: 1, name: testMessages['login-prompt-heading']!});
  expect(note()).toBeNull();
});

test('a withdrawn code logs the voucher account out where it is found, with its own note', async () => {
  // The workspace finds the code revoked; the server has logged the session out and the
  // next session response carries the note.
  serveSessions(
    {state: 'voucher', logoutNotice: null},
    {state: 'anonymous', logoutNotice: 'revoked'},
    {state: 'anonymous', logoutNotice: null},
  );
  server.use(http.get(url('/api/v1/conversations/:slug/workspace'), () => HttpResponse.json({error: {
    code: 'access_required',
    message: 'Access to this consultation is required.',
    details: {
      slug: 'community-strategy', title: 'Community strategy', gatingType: 'voucher',
      viewer: 'access_lost', certainty: 'known', reason: 'access-voucher-revoked', loginOptions: [], sharedResults: [],
    },
  }}, {status: 403})));
  renderAt('/c/community-strategy');
  expect(await screen.findByText(testMessages['logout-notice-revoked']!, {}, {timeout: 10_000})).toBeVisible();
  expect(screen.queryByText(testMessages['logout-notice']!)).toBeNull();
  // The header no longer shows the voucher account.
  expect(document.querySelector('header')).not.toHaveTextContent(testMessages['base-single-consultation-account']!);
});

test('under qqx, the note carries no English', async () => {
  renderAsQqx();
  serveSessions({state: 'anonymous', logoutNotice: 'voucher'}, {state: 'anonymous', logoutNotice: null});
  renderAt('/c/community-strategy/reveal');
  await screen.findByRole('heading', {level: 1, name: '(login-prompt-heading)'});
  expect(untranslatedCopy([note()])).toEqual([]);
});
