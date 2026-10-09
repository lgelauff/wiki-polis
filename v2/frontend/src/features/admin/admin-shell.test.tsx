import {QueryClientProvider} from '@tanstack/react-query';
import {fireEvent, render, screen, within} from '@testing-library/react';
import {http, HttpResponse} from 'msw';
import {MemoryRouter} from 'react-router-dom';
import {afterEach, expect, test} from 'vitest';

import type {components} from '../../api/schema';
import {AdminShell} from './admin-shell';
import {useAnnounce} from './admin-announcer';
import {LegacyToast} from '../legacy/legacy-toast';
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
  counts: {participants: 12, openFlags: 3, featuredStatements: 4},
  capabilities: {advancePhase: true, pause: true, publish: false, editSettings: true, useAdvancedPhases: true, initializePhase6: false, archive: true},
  links: {
    self: '/api/v1/admin/conversations/7', participantView: '/c/community-strategy',
    moderation: '/admin/conversations/7/flags',
    statements: '/admin/conversations/7/statements',
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

function renderShell(options: {
  children?: React.ReactNode;
  data?: Lifecycle;
  gatingType?: 'invite_only' | 'voucher' | 'wiki_based' | null;
  section?: 'overview' | 'settings' | 'moderation' | 'content';
  subPage?: string;
  path?: string;
  toast?: React.ReactNode;
} = {}) {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      {/* Any admin URL: the frame must not read where it is from the address bar. */}
      <MemoryRouter initialEntries={[options.path ?? '/admin/conversations/7/settings/basics']}>
        <MessageProvider>
          <AdminShell
            title="Community strategy"
            data={options.data ?? lifecycle}
            gatingType={options.gatingType ?? null}
            section={options.section ?? 'overview'}
            subPage={options.subPage}
            toast={options.toast ?? null}
            children={options.children ?? null}
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
  })) as typeof globalThis.matchMedia;
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
  // The DTO's links.* cover the other sections, not Overview, so the client builds that
  // one from the conversation id -- the frame is on some other URL and Overview still
  // points at the consultation's own page.
  expect(within(nav).getByRole('link', {name: 'Overview'})).toHaveAttribute('href', '/admin/conversations/7');
  expect(within(nav).getByRole('link', {name: 'Overview'})).toHaveAttribute('aria-current', 'page');
  // No sub-page links: a leaf is reached from the page it belongs to, not from the frame.
  expect(within(nav).queryByRole('link', {name: /Participants|Invitations|Roles|Featured/})).toBeNull();
});

test('the moderation badge counts the open flags', async () => {
  serveSession();
  renderShell();

  const nav = await screen.findByRole('navigation', {name: 'Admin sections'});
  expect(within(nav).getByText('3 open flags')).toBeVisible();
});

test('one open flag reads in the singular', async () => {
  serveSession();
  renderShell({data: {...lifecycle, counts: {...lifecycle.counts, openFlags: 1}}});

  const nav = await screen.findByRole('navigation', {name: 'Admin sections'});
  expect(within(nav).getByText('1 open flag')).toBeVisible();
});

test('a consultation with no open flags carries no badge', async () => {
  // A zero is not worth a badge: an empty counter is noise, not information.
  serveSession();
  renderShell({data: {...lifecycle, counts: {...lifecycle.counts, openFlags: 0}}});

  const nav = await screen.findByRole('navigation', {name: 'Admin sections'});
  expect(within(nav).queryByText(/open flag/)).toBeNull();
});

test('the top bar repeats no section link: the sidebar is the one way in', async () => {
  serveSession();
  const {container} = renderShell();
  await screen.findByRole('navigation', {name: 'Admin breadcrumb'});

  const topbar = container.querySelector('.admin-shell__topbar') as HTMLElement;
  expect(within(topbar).queryByRole('link', {name: 'Overview'})).toBeNull();
  expect(within(topbar).queryByRole('link', {name: 'Moderation'})).toBeNull();
});

test('the breadcrumb ends at the current section', async () => {
  serveSession();
  renderShell({section: 'settings'});

  const crumbs = await screen.findByRole('navigation', {name: 'Admin breadcrumb'});
  const items = within(crumbs).getAllByRole('listitem');
  expect(items).toHaveLength(2);
  expect(items[0]).toHaveTextContent('Community strategy');
  expect(items[1]).toHaveTextContent('Settings');
  expect(items[1]).toHaveAttribute('aria-current', 'page');
  // Only the last crumb is the current page: the section is where the page sits, not
  // the page itself, once the page has a name of its own.
  expect(items[0]).not.toHaveAttribute('aria-current');
});

test('on Overview the breadcrumb is the title and Overview, and Overview is current', async () => {
  serveSession();
  renderShell({section: 'overview'});

  const crumbs = await screen.findByRole('navigation', {name: 'Admin breadcrumb'});
  const items = within(crumbs).getAllByRole('listitem');
  expect(items.map((item) => item.textContent)).toEqual(['Community strategy', 'Overview']);
  expect(items[1]).toHaveAttribute('aria-current', 'page');
});

test('a page with a name of its own adds it as the last crumb', async () => {
  serveSession();
  renderShell({section: 'content', subPage: 'Statements'});

  const crumbs = await screen.findByRole('navigation', {name: 'Admin breadcrumb'});
  const items = within(crumbs).getAllByRole('listitem');
  expect(items.map((item) => item.textContent)).toEqual([
    'Community strategy', 'Content', 'Statements',
  ]);
  expect(items[2]).toHaveAttribute('aria-current', 'page');
  expect(items[1]).not.toHaveAttribute('aria-current');
});

test('each section marks itself in the sidebar and no other', async () => {
  serveSession();
  for (const [section, name] of [
    ['overview', 'Overview'], ['settings', 'Settings'],
    ['moderation', 'Moderation'], ['content', 'Content'],
  ] as const) {
    const {unmount} = renderShell({section});
    const nav = await screen.findByRole('navigation', {name: 'Admin sections'});
    expect(within(nav).getByRole('link', {name: new RegExp(`^${name}`)}))
      .toHaveAttribute('aria-current', 'page');
    // Exactly one section is current, so the sidebar never says "you are here" twice.
    expect(within(nav).getAllByRole('link').filter((link) => link.getAttribute('aria-current') === 'page'))
      .toHaveLength(1);
    unmount();
  }
});

test('the sidebar marks the section the frame is on, whatever the URL says', async () => {
  // The address bar can be anything: the prop is what says which section this is.
  serveSession();
  renderShell({section: 'moderation', path: '/admin/conversations/7/content/statements'});

  const nav = await screen.findByRole('navigation', {name: 'Admin sections'});
  expect(within(nav).getByRole('link', {name: /Moderation/})).toHaveAttribute('aria-current', 'page');
  expect(within(nav).getByRole('link', {name: 'Content'})).not.toHaveAttribute('aria-current');
  // Overview still points at the consultation's own page, not at the URL being rendered.
  expect(within(nav).getByRole('link', {name: 'Overview'})).toHaveAttribute('href', '/admin/conversations/7');
});

test('the session is ended by a form posting the CSRF token to the server link', async () => {
  serveSession();
  const {container} = renderShell();

  // A form has no accessible name here, so it has no role to query by; the logout is the
  // one that posts to the link the session DTO carries.
  await screen.findByRole('button', {name: 'log out'});
  const form = container.querySelector('form[action="/logout"]');
  expect(form).not.toBeNull();
  expect(form!.getAttribute('method')).toBe('post');
  expect(form!.querySelector('input[name="csrf_token"]')).toHaveValue('test-csrf-token');
  // The notification slot is the console's own, not the legacy fixed overlay.
  expect(container.querySelector('#toast-container')).toBeNull();
});

test('the role word comes from the catalogue, not from the server string', async () => {
  serveSession();
  renderShell();

  // The server still sends "Global admin"; the console says "Site admin" (spec: never
  // "Global admin" on screen).
  expect(await screen.findByText('Site admin')).toBeVisible();
  expect(screen.queryByText('Global admin')).toBeNull();
  expect(screen.queryByTitle('Global admin')).toBeNull();
});

test('the role glyph explains itself on hover and to a screen reader', async () => {
  serveSession();
  renderShell();

  // A symbol explains on hover (the SVG <title>) and, since it says what the word beside it
  // is, it carries the same words as its accessible name.
  const glyph = await screen.findByRole('img', {name: 'Your role in this consultation'});
  expect(glyph.querySelector('title')).toHaveTextContent('Your role in this consultation');
  expect(glyph.parentElement).toHaveTextContent('Site admin');
});

test('the footer keeps the CC0 licence line, as quiet text with one link', async () => {
  serveSession();
  const {container} = renderShell();

  await screen.findByRole('navigation', {name: 'Admin sections'});
  const footer = container.querySelector('footer.admin-shell__footer')!;
  expect(footer).toHaveTextContent('All text you write here that is intended for publication is released into the public domain (CC0');
  const link = within(footer as HTMLElement).getByRole('link', {name: /^CC0/});
  expect(link).toHaveAttribute('href', 'https://creativecommons.org/publicdomain/zero/1.0/');
  expect(footer.querySelectorAll('a, button, input, select')).toHaveLength(1);
  // No git version: one line, not the legacy footer's second item.
  expect(footer.querySelector('code')).toBeNull();
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

test('the mark links to Admin home for a site administrator', async () => {
  serveSession({capabilities: {administerSite: true}});
  renderShell();

  expect(await screen.findByRole('link', {name: 'Admin home'})).toHaveAttribute('href', '/admin');
});

test('an organizer\'s mark links to Admin home too, which lists their consultations', async () => {
  serveSession({capabilities: {administerSite: false}});
  renderShell();

  const nav = await screen.findByRole('navigation', {name: 'Admin sections'});
  expect(within(nav).getByRole('link', {name: 'Admin home'})).toHaveAttribute('href', '/admin');
});

/** The frame at site level: Admin home (`home`) or the dashboard. */
function renderSiteShell({home}: {home: boolean}) {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={[home ? '/admin' : '/site-admin']}>
        <MessageProvider>
          <AdminShell title="Page" site="Page" home={home} children={null} />
        </MessageProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

test('on Admin home itself the mark is plain text: a link to where you are goes nowhere', async () => {
  serveSession({capabilities: {administerSite: true}});
  renderSiteShell({home: true});

  const nav = await screen.findByRole('navigation', {name: 'Admin sections'});
  expect(within(nav).queryByRole('link', {name: 'Admin home'})).toBeNull();
  expect(within(nav).getByText('Admin')).toBeVisible();
});

test('a site admin has the dashboard in the sidebar on every console page', async () => {
  serveSession({capabilities: {administerSite: true}});
  renderShell();

  const nav = await screen.findByRole('navigation', {name: 'Admin sections'});
  const link = within(nav).getByRole('link', {name: 'Site admin dashboard'});
  expect(link).toHaveAttribute('href', '/site-admin');
  expect(link).not.toHaveAttribute('aria-current');
});

test('on the dashboard its sidebar link is the current page, and the mark goes home', async () => {
  serveSession({capabilities: {administerSite: true}});
  renderSiteShell({home: false});

  const nav = await screen.findByRole('navigation', {name: 'Admin sections'});
  expect(within(nav).getByRole('link', {name: 'Site admin dashboard'})).toHaveAttribute('aria-current', 'page');
  expect(within(nav).getByRole('link', {name: 'Admin home'})).toHaveAttribute('href', '/admin');
});

test('someone who is not a site admin has no link to the dashboard', async () => {
  serveSession({capabilities: {administerSite: false}});
  renderShell();

  const nav = await screen.findByRole('navigation', {name: 'Admin sections'});
  expect(within(nav).queryByRole('link', {name: 'Site admin dashboard'})).toBeNull();
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

test('the one "also coming" line is muted text, not a control', async () => {
  serveSession();
  const {container} = renderShell();

  // A control whose value nothing reads is not a control: the line says so, in English,
  // and takes no focus, so nobody tabs into a dead end.
  const lines = await screen.findAllByText(/^Also coming:/);
  // Admin home was the other one; it is built now (#538).
  expect(lines).toHaveLength(1);
  for (const line of lines) {
    expect(line.closest('a, button, [tabindex]')).toBeNull();
    expect(line).toHaveClass('admin-shell__coming');
    // Untranslated on purpose, so it says which language it is in (WCAG 3.1.2).
    expect(line).toHaveAttribute('lang', 'en');
  }
  expect(lines[0]).toHaveTextContent('Also coming: switching between consultations — not available yet (#473)');
  // Under the mark; the top bar has none any more.
  const topbar = container.querySelector('.admin-shell__topbar')!;
  expect(topbar.textContent).not.toContain('Also coming');
  const sidebar = container.querySelector('.admin-shell__side')!;
  expect(sidebar.textContent).toContain('switching between consultations');
});

test('the frame has one main, one polite live region and no other landmark', async () => {
  serveSession();
  const {container} = renderShell();

  await screen.findByRole('navigation', {name: 'Admin sections'});
  expect(container.querySelectorAll('main')).toHaveLength(1);
  expect(container.querySelector('main')).toHaveAttribute('id', 'main');
  expect(container.querySelector('main')).toHaveAttribute('tabindex', '-1');
  // One polite and one assertive region announce results, both there (and empty) before
  // the first announcement; the notice slot below them is not a third.
  expect(container.querySelectorAll('[aria-live="polite"]')).toHaveLength(1);
  expect(container.querySelectorAll('[aria-live="assertive"]')).toHaveLength(1);
  expect(container.querySelector('[aria-live="polite"]')).toBeEmptyDOMElement();
  expect(container.querySelector('[aria-live="assertive"]')).toBeEmptyDOMElement();
  // The notice slot is last in <main>, after the page, so a toast's dismiss button comes
  // in tab order where it is drawn (the bottom corner), not before the page's first
  // control. console.css floats it out of the flow, which test_admin_console_css.py guards.
  const notices = container.querySelector('.admin-shell__notices')!;
  expect(notices).toBe(container.querySelector('main')!.lastElementChild);
});

test('under qqx the frame is all keys but the "also coming" line', async () => {
  renderAsQqx();
  serveSession();
  const {container} = renderShell();

  await screen.findByRole('navigation', {name: '(admin-shell-nav-aria)'});
  // The "also coming" line is the exception the issue allows, and the locale
  // autonyms in the switcher are never translated, so both count as content here.
  expect(untranslatedCopy([container.querySelector('.admin-shell')], [
    'Community strategy', 'Example editor', 'English', 'Nederlands',
    'Also coming: switching between consultations — not available yet (#473)',
  ])).toEqual([]);
});

/** A button inside the frame that announces through the shell, as a row action does. */
function AnnounceButton({text, politeness}: {text: string; politeness?: 'polite' | 'assertive'}) {
  const announce = useAnnounce();
  return <button type="button" onClick={() => announce?.(text, politeness)}>Act</button>;
}

test('an announcement from inside the frame is read out, and the same words twice are read twice', async () => {
  serveSession();
  const {container} = renderShell({children: <AnnounceButton text="Statement 12 hidden." />});

  const button = await screen.findByRole('button', {name: 'Act'});
  const region = container.querySelector('[aria-live="polite"]')!;
  fireEvent.click(button);
  expect(region).toHaveTextContent('Statement 12 hidden.');
  const first = region.firstElementChild;
  fireEvent.click(button);
  // Same text, new node: the region gets an addition, so a screen reader reads it again.
  expect(region).toHaveTextContent('Statement 12 hidden.');
  expect(region.firstElementChild).not.toBe(first);
  expect(container.querySelector('[aria-live="assertive"]')).toBeEmptyDOMElement();
});

test('a failure is announced in the assertive region', async () => {
  serveSession();
  const {container} = renderShell({children: <AnnounceButton text="Could not save." politeness="assertive" />});

  fireEvent.click(await screen.findByRole('button', {name: 'Act'}));
  expect(container.querySelector('[aria-live="assertive"]')).toHaveTextContent('Could not save.');
  expect(container.querySelector('[aria-live="polite"]')).toBeEmptyDOMElement();
});

test('a toast in the frame reads out through the shell region, not a role of its own', async () => {
  serveSession();
  const {container} = renderShell({
    toast: <LegacyToast toast={{id: 1, category: 'error', message: 'Could not hide the statement.'}} onDismiss={() => {}} />,
  });

  await screen.findByRole('navigation', {name: 'Admin sections'});
  const toast = container.querySelector('.toast')!;
  expect(toast).toHaveTextContent('Could not hide the statement.');
  expect(toast).not.toHaveAttribute('role');
  expect(container.querySelector('[aria-live="assertive"]')).toHaveTextContent('Could not hide the statement.');
});

test('at site level the role a site admin opens the dashboard with says Site admin', async () => {
  serveSession({capabilities: {administerSite: true}});
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={['/admin']}>
        <MessageProvider>
          <AdminShell title="Site admin dashboard" site="Site admin dashboard" children={null} />
        </MessageProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );

  const identity = (await screen.findByText('Example editor')).closest('.admin-shell__identity')!;
  expect(identity).toHaveTextContent('Site admin');
  expect(identity).not.toHaveTextContent('Global admin');
});
