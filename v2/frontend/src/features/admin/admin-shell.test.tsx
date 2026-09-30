import {QueryClientProvider} from '@tanstack/react-query';
import {fireEvent, render, screen, within} from '@testing-library/react';
import {http, HttpResponse} from 'msw';
import {MemoryRouter} from 'react-router-dom';
import {afterEach, expect, test} from 'vitest';

import type {components} from '../../api/schema';
import {AdminShell} from './admin-shell';
import {MessageProvider} from '../../i18n/messages';
import {createQueryClient} from '../../query-client';
import {server} from '../../test/server';
import {renderAsQqx, untranslatedCopy} from '../../test/i18n';

type Lifecycle = components['schemas']['AdminLifecycle'];
type Session = components['schemas']['Session'];

const SESSION_URL = new URL('/api/v1/session', globalThis.location.origin).toString();

/** Three open flags, a site-admin operator and every link the shell reads. The shell is
 *  handed the lifecycle DTO directly, so this file never boots the page: the assertions
 *  below are about the frame, not about what is inside it. */
const lifecycle: Lifecycle = {
  conversation: {id: 7, slug: 'community-strategy', title: 'Community strategy', accessPolicy: 'public', status: 'active', publication: 'not_applicable', closedAt: null, identityReveal: null},
  operator: {roleLabel: 'Global admin'},
  phase: {linear: true, currentIndex: 0, activeKeys: ['preparation'], steps: [
    {key: 'preparation', label: 'Preparation', effect: 'Configure and seed the conversation.', state: 'current'},
  ], transition: null, phase6Setup: null, advancedControls: []},
  schedule: {canSchedule: false, scheduledAt: null, targetKey: null, targetLabel: null, frozen: false},
  publicationReadiness: {windowOpen: false, preconditions: []},
  statistics: {upstreamUnavailable: false, groups: [], informedVoting: null},
  counts: {participants: 12, invitations: 1, openFlags: 3, featuredStatements: 4},
  capabilities: {advancePhase: true, pause: true, publish: false, editSettings: true, useAdvancedPhases: true, initializePhase6: false, archive: true},
  links: {
    self: '/api/v1/admin/conversations/7', participantView: '/c/community-strategy',
    participants: '/admin/conversations/7/participants', moderation: '/admin/conversations/7/flags',
    invitations: '/admin/conversations/7/invites', roles: '/admin/conversations/7/roles',
    statements: '/admin/conversations/7/statements', featuredStatements: '/admin/conversations/7/featured',
    settings: '/admin/conversations/7/settings', termination: '/admin/conversations/7/termination',
  },
};

/** Two locales, because the switcher is deliberately invisible while only one exists --
 *  a dead control on every page would be worse than no control. */
function serveSession(overrides: Partial<Session> = {}) {
  const data: Session = {
    state: 'authenticated',
    user: {username: 'Example editor', emailable: true},
    capabilities: {administerSite: false},
    csrfToken: 'test-csrf-token',
    developerLogins: [],
    gitVersion: 'test-version',
    locales: {current: 'en', available: [{code: 'en', name: 'English'}, {code: 'nl', name: 'Nederlands'}]},
    links: {login: '/login', logout: '/logout'},
    ...overrides,
  };
  server.use(http.get(SESSION_URL, () => HttpResponse.json({data})));
}

function renderShell(options: {data?: Lifecycle; gatingType?: 'invite_only' | 'voucher' | 'wiki_based' | null; toast?: React.ReactNode} = {}) {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={['/admin/conversations/7']}>
        <MessageProvider locale="en">
          <AdminShell
            title="Community strategy"
            data={options.data ?? lifecycle}
            gatingType={options.gatingType ?? null}
            toast={options.toast ?? null}
          />
        </MessageProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

/** The 1024px breakpoint, decided in JS as well as CSS: a disclosure that only CSS could
 *  open would be unreachable by keyboard and would not exist at all without a stylesheet. */
function stubNarrowViewport(narrow: boolean) {
  const original = globalThis.matchMedia;
  globalThis.matchMedia = ((query: string) => ({
    media: query, matches: narrow, onchange: null,
    addEventListener() {}, removeEventListener() {},
    addListener() {}, removeListener() {}, dispatchEvent: () => false,
  })) as MediaQueryList['matchMedia'];
  return () => { globalThis.matchMedia = original; };
}

let restoreViewport: (() => void) | null = null;
afterEach(() => {
  restoreViewport?.();
  restoreViewport = null;
});

test('the sidebar names the four sections and points each at the fixture href', async () => {
  serveSession();
  renderShell();

  const nav = await screen.findByRole('navigation', {name: 'Admin sections'});
  expect(within(nav).getByRole('link', {name: 'Settings'})).toHaveAttribute('href', '/admin/conversations/7/settings');
  expect(within(nav).getByRole('link', {name: /^Moderation/})).toHaveAttribute('href', '/admin/conversations/7/flags');
  expect(within(nav).getByRole('link', {name: 'Content'})).toHaveAttribute('href', '/admin/conversations/7/statements');
  // Overview is the page the frame is on, so it is marked as the current one.
  expect(within(nav).getByRole('link', {name: 'Overview'})).toHaveAttribute('aria-current', 'page');
  // No sub-page links: a leaf is reached from the page it belongs to, not from the frame.
  expect(within(nav).queryByRole('link', {name: /Participants|Invitations|Roles|Featured/})).toBeNull();
});

test('the moderation badge counts open flags and disappears when there are none', async () => {
  serveSession();
  renderShell();

  const nav = await screen.findByRole('navigation', {name: 'Admin sections'});
  expect(within(nav).getByText('3 open flags')).toBeVisible();

  // A zero is not worth a badge: an empty counter is noise, not information.
  screen.getByRole('link', {name: 'Log out'});
  const quiet = renderShell({data: {...lifecycle, counts: {...lifecycle.counts, openFlags: 0}}});
  const quietNav = within(quiet.container).getByRole('navigation', {name: 'Admin sections'});
  expect(within(quietNav).queryByText(/open flag/)).toBeNull();
});

test('the breadcrumb ends at the current section', async () => {
  serveSession();
  renderShell();

  const crumbs = await screen.findByRole('navigation', {name: 'Admin breadcrumb'});
  const items = within(crumbs).getAllByRole('listitem');
  expect(items).toHaveLength(2);
  expect(items[0]).toHaveTextContent('Community strategy');
  expect(items[1]).toHaveTextContent('Overview');
  expect(items[1]).toHaveAttribute('aria-current', 'page');
});

test('the session is ended by a form posting the CSRF token to the server link', async () => {
  serveSession();
  const {container} = renderShell();

  const form = (await screen.findAllByRole('form')).find((node) => node.getAttribute('action') === '/logout');
  expect(form).toBeDefined();
  expect(form!.querySelector('input[name="csrf_token"]')).toHaveValue('test-csrf-token');
  expect(within(form!).getByRole('button', {name: 'Log out'})).toBeVisible();
  expect(container.querySelector('#toast-container')).toBeNull();
});

test('the role word comes from the catalogue, not from the server string', async () => {
  serveSession();
  renderShell();

  // The server still sends "Global admin"; the console says "Site admin" (spec: never
  // "Global admin" on screen). A glyph explains itself through the word beside it, so
  // the glyph itself carries nothing for a screen reader.
  expect(await screen.findByText('Site admin')).toBeVisible();
  expect(screen.queryByText('Global admin')).toBeNull();
  expect(screen.queryByTitle('Global admin')).toBeNull();
});

test('the language switcher moves with the shell', async () => {
  serveSession();
  renderShell();

  const select = await screen.findByLabelText('Language');
  expect(select).toHaveValue('en');
  expect(within(select).getByRole('option', {name: 'Nederlands'})).toBeVisible();
});

test('a voucher consultation labels the participant view a preview', async () => {
  serveSession();
  renderShell({gatingType: 'voucher'});

  // Organizers cannot take part in a voucher consultation, so the switch shows them
  // what a visitor without a code sees rather than pretending they can join.
  expect(await screen.findByRole('link', {name: 'Participant (preview)'})).toHaveAttribute('href', '/c/community-strategy');
});

test('the participant view is labelled plainly when the consultation is not gated', async () => {
  serveSession();
  renderShell({gatingType: 'invite_only'});

  expect(await screen.findByRole('link', {name: 'Participant'})).toHaveAttribute('href', '/c/community-strategy');
  expect(screen.queryByRole('link', {name: 'Participant (preview)'})).toBeNull();
});

test('the mark links to Admin home only for a site administrator', async () => {
  serveSession({capabilities: {administerSite: true}});
  const admin = renderShell();

  // Today's crumb sends an organizer to a 403, so the frame only offers the link to
  // someone who can open the page behind it.
  expect(await screen.findByRole('link', {name: 'Admin'})).toHaveAttribute('href', '/admin');

  serveSession({capabilities: {administerSite: false}});
  const organizer = renderShell();
  await screen.findAllByRole('navigation', {name: 'Admin sections'});
  const nav = within(organizer.container).getByRole('navigation', {name: 'Admin sections'});
  expect(within(nav).queryByRole('link', {name: 'Admin'})).toBeNull();
  expect(within(nav).getByText('Admin')).toBeVisible();
});

test('below 1024px the sections collapse behind a disclosure', async () => {
  restoreViewport = stubNarrowViewport(true);
  serveSession();
  renderShell();

  // A link hidden by CSS alone is still in the accessibility tree and still tabbable,
  // so the collapsed state has to remove the links, not dim them.
  const toggle = await screen.findByRole('button', {name: 'Sections'});
  expect(toggle).toHaveAttribute('aria-expanded', 'false');
  expect(screen.queryByRole('link', {name: 'Settings'})).toBeNull();

  fireEvent.click(toggle);
  expect(toggle).toHaveAttribute('aria-expanded', 'true');
  expect(screen.getByRole('link', {name: 'Settings'})).toBeVisible();
});

test('at desktop width there is no disclosure and every section is reachable', async () => {
  restoreViewport = stubNarrowViewport(false);
  serveSession();
  renderShell();

  await screen.findByRole('link', {name: 'Settings'});
  expect(screen.queryByRole('button', {name: 'Sections'})).toBeNull();
});

test('the two "also coming" lines are muted text, not controls', async () => {
  serveSession();
  const {container} = renderShell();

  // A control whose value nothing reads is not a control: the line says so, in English,
  // and takes no focus, so nobody tabs into a dead end.
  const lines = screen.getAllByText(/^Also coming:/);
  expect(lines).toHaveLength(2);
  for (const line of lines) {
    expect(line.closest('a, button, [tabindex]')).toBeNull();
    expect(line).toHaveClass('admin-shell__coming');
  }
  expect(lines[0]).toHaveTextContent('Also coming: Admin home — not available yet (#473)');
  expect(lines[1]).toHaveTextContent('Also coming: switching between consultations — not available yet (#473)');
  // The first sits far left of the top bar, before the breadcrumb; the second under the mark.
  const topbar = container.querySelector('.admin-shell__topbar')!;
  expect(topbar.firstElementChild).toBe(lines[0]);
  const sidebar = container.querySelector('.admin-shell__side')!;
  expect(sidebar.textContent).toContain('switching between consultations');
});

test('the frame has one main, one polite live region and no other landmark', async () => {
  serveSession();
  const {container} = renderShell();

  expect(container.querySelectorAll('main')).toHaveLength(1);
  expect(container.querySelector('main')).toHaveAttribute('id', 'main');
  expect(container.querySelector('main')).toHaveAttribute('tabindex', '-1');
  // One region announces results; the notice slot below it is not a second one.
  expect(container.querySelectorAll('[aria-live="polite"]')).toHaveLength(1);
  expect(container.querySelector('[aria-live="polite"]')).toBeEmptyDOMElement();
  // The notice slot is a non-fixed area at the top of <main>, not a floating overlay.
  const notices = container.querySelector('.admin-shell__notices')!;
  expect(notices).toBe(container.querySelector('main')!.firstElementChild);
});

test('under qqx the frame is all keys but the two "also coming" lines', async () => {
  renderAsQqx();
  serveSession();
  const {container} = renderShell();

  await screen.findByRole('navigation', {name: '(admin-shell-nav-aria)'});
  expect(untranslatedCopy([container.querySelector('.admin-shell')], [
    'Community strategy', 'Example editor',
    'Also coming: Admin home — not available yet (#473)',
    'Also coming: switching between consultations — not available yet (#473)',
  ])).toEqual([]);
});
