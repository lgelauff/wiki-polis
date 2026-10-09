import {Suspense} from 'react';
import {QueryClientProvider, type QueryClient} from '@tanstack/react-query';
import {fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {http, HttpResponse} from 'msw';
import {MemoryRouter, Route, Routes} from 'react-router-dom';
import {expect, test, vi} from 'vitest';

import type {components} from '../../api/schema';
import {AdminSettingsPage} from './admin-settings-page';
import {MessageProvider} from '../../i18n/messages';
import {createQueryClient} from '../../query-client';
import {server} from '../../test/server';

/** Settings › Basics and Access as two tabs of one form: what a Save sends when the page's
 *  copy is older than the server's (pr-check M1), what survives a tab switch (M4), and the
 *  status line's life (usability-3, M5). Kept apart from admin-settings-page.test.tsx, which
 *  pins each tab on its own. */

type Settings = components['schemas']['AdminSettings'];

const SETTINGS_URL = new URL(
  '/api/v1/admin/conversations/7/settings', globalThis.location.origin,
).toString();
const STATEMENTS_URL = new URL(
  '/api/v1/admin/conversations/7/statements', globalThis.location.origin,
).toString();

const settings: Settings = {
  conversation: {
    id: 7, slug: 'community-strategy', title: 'Community strategy',
    introHtml: '<p>Shape the future.</p>', outroHtml: '', accessPolicy: 'public',
    gated: false, gatingType: null, announce: false, information: false,
    resultsShared: false, showUsernames: false, accessRequestText: null,
    phaseRoute: 'default_7', phaseRouteLabel: 'Full consultation',
    polisId: 'polis-community-strategy',
  },
  recommendations: {tier: 'medium', tiers: [
    {key: 'simple', label: 'Simple topic', quantities: {seed_statements: 5}},
    {key: 'medium', label: 'Medium topic', quantities: {seed_statements: 8}},
    {key: 'complex', label: 'Complex topic', quantities: {seed_statements: 12}},
  ]},
  eligibility: {
    configured: false, eventId: '', label: null, configurationMode: 'editable',
    note: 'Leave the event ID blank when no external eligibility check applies.',
  },
  capabilities: {edit: true, switchDemo: false},
  locks: {gated: false, gatingType: false, showUsernames: false},
  links: {self: SETTINGS_URL, lifecycle: '/admin/conversations/7'},
};

function serve(payload: Settings) {
  server.use(http.get(SETTINGS_URL, () => HttpResponse.json({data: payload})));
}

/** Every settings PUT body, answered with the settings as sent. */
function recordPuts() {
  const sent: Record<string, unknown>[] = [];
  server.use(http.put(SETTINGS_URL, async ({request}) => {
    const payload = await request.json() as Record<string, unknown>;
    sent.push(payload);
    return HttpResponse.json({data: {
      changed: true, changedFields: ['title'],
      settings: {...settings, conversation: {...settings.conversation, ...payload}},
    }});
  }));
  return sent;
}

/** The statements workspace the Basics Approval section reads. */
function serveWorkspace() {
  server.use(http.get(STATEMENTS_URL, () => HttpResponse.json({data: {
    conversation: {id: 7, slug: 'community-strategy', title: 'Community strategy'},
    statements: {pending: [], approved: [], hidden: []},
    moderationPolicy: {mode: 'auto_approve', newStatements: 'approved', available: true},
    dataAvailability: {statements: true},
    seeding: {allowed: true, lockReason: null, maxStatementsPerImport: 20, maxCharactersPerStatement: 280},
    capabilities: {moderate: true, seed: true},
    links: {self: '/api/v1/admin/conversations/7/statements', lifecycle: '/admin/conversations/7'},
  }})));
}

function tabs() {
  return screen.getByRole('navigation', {name: 'Settings'});
}

function renderPage(tab: 'basics' | 'access', client: QueryClient = createQueryClient()) {
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[`/admin/conversations/7/settings/${tab}`]}>
        <Suspense fallback={null}>
          <MessageProvider locale="en">
            <AdminSettingsPage conversationId={7} csrfToken="test-csrf-token" tab={tab} />
          </MessageProvider>
        </Suspense>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

/** Both tabs as the app mounts them: each its own route, so switching tabs unmounts the
 *  page, as it does in the app (two route components, not one with a changing prop). */
function BasicsRoute() {
  return <AdminSettingsPage conversationId={7} csrfToken="test-csrf-token" tab="basics" />;
}
function AccessRoute() {
  return <AdminSettingsPage conversationId={7} csrfToken="test-csrf-token" tab="access" />;
}
function renderTabs(start: 'basics' | 'access') {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={[`/admin/conversations/7/settings/${start}`]}>
        <Suspense fallback={null}>
          <MessageProvider locale="en">
            <Routes>
              <Route path="/admin/conversations/7/settings/basics" element={<BasicsRoute />} />
              <Route path="/admin/conversations/7/settings/access" element={<AccessRoute />} />
            </Routes>
          </MessageProvider>
        </Suspense>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

test('a Basics save does not write back an admission answer older than the server\'s', async () => {
  serveWorkspace();
  serve(settings);
  const sent = recordPuts();
  renderPage('basics');

  const title = await screen.findByRole('textbox', {name: 'Title'}, {timeout: 10_000});
  // Meanwhile the consultation was gated (another tab, another organizer): this page's
  // cached copy still says anyone may take part.
  serve({...settings, conversation: {...settings.conversation, gated: true,
    gatingType: 'invite_only', accessPolicy: 'invite_only'}});
  fireEvent.change(title, {target: {value: 'A new title'}});
  fireEvent.click(screen.getByRole('button', {name: 'Save'}));

  await waitFor(() => expect(sent).toHaveLength(1));
  expect(sent[0]).toMatchObject({
    title: 'A new title', gated: true, gatingType: 'invite_only', accessPolicy: 'invite_only',
  });
});

test('an Access save does not write back a title older than the server\'s', async () => {
  serve(settings);
  const sent = recordPuts();
  renderPage('access');

  const eventId = await screen.findByLabelText('Eligibility event ID', {}, {timeout: 10_000});
  serve({...settings, conversation: {...settings.conversation, title: 'Renamed elsewhere'},
    recommendations: {...settings.recommendations, tier: 'complex'}});
  fireEvent.change(eventId, {target: {value: 'event-99'}});
  fireEvent.click(screen.getByRole('button', {name: 'Save'}));

  await waitFor(() => expect(sent).toHaveLength(1));
  expect(sent[0]).toMatchObject({
    eligibilityEventId: 'event-99', title: 'Renamed elsewhere', recommendationTier: 'complex',
  });
});

test('an edit survives a switch to the other tab and back', async () => {
  serveWorkspace();
  serve(settings);
  renderTabs('basics');

  fireEvent.change(await screen.findByRole('textbox', {name: 'Title'}, {timeout: 10_000}),
    {target: {value: 'Not saved yet'}});
  fireEvent.click(within(tabs()).getByRole('link', {name: 'Access'}));
  fireEvent.click(await screen.findByRole('radio', {name: /Anyone with a voucher code/}));
  fireEvent.click(within(tabs()).getByRole('link', {name: 'Basics'}));

  expect(await screen.findByRole('textbox', {name: 'Title'})).toHaveValue('Not saved yet');
  fireEvent.click(within(tabs()).getByRole('link', {name: 'Access'}));
  expect(await screen.findByRole('radio', {name: /Anyone with a voucher code/})).toBeChecked();
});

test('Basics saves only its own fields: an unsaved Access answer is neither sent nor asked about', async () => {
  serveWorkspace();
  serve(settings);
  const sent = recordPuts();
  renderTabs('access');

  // A narrowing answer on Access, not saved.
  fireEvent.click(await screen.findByRole('radio', {name: /Anyone with a voucher code/}, {timeout: 10_000}));
  fireEvent.click(within(tabs()).getByRole('link', {name: 'Basics'}));
  fireEvent.change(await screen.findByRole('textbox', {name: 'Title'}), {target: {value: 'A new title'}});
  fireEvent.click(screen.getByRole('button', {name: 'Save'}));

  // No narrowing question on Basics: it does not show, and does not send, that answer.
  await waitFor(() => expect(sent).toHaveLength(1));
  expect(screen.queryByText('Some people will lose access. Continue?')).toBeNull();
  expect(sent[0]).toMatchObject({title: 'A new title', gated: false, gatingType: null});
  // The Access answer is still there, unsaved, for its own Save.
  fireEvent.click(within(tabs()).getByRole('link', {name: 'Access'}));
  expect(await screen.findByRole('radio', {name: /Anyone with a voucher code/})).toBeChecked();
});

test('"Settings saved." goes as soon as something is edited again', async () => {
  serveWorkspace();
  serve(settings);
  recordPuts();
  renderPage('basics');

  const title = await screen.findByRole('textbox', {name: 'Title'}, {timeout: 10_000});
  fireEvent.change(title, {target: {value: 'A new title'}});
  fireEvent.click(screen.getByRole('button', {name: 'Save'}));
  await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('Settings saved.'));

  fireEvent.change(title, {target: {value: 'A newer title'}});
  // The region stays (so the next message is announced), but says nothing stale.
  expect(screen.getByRole('status')).toBeEmptyDOMElement();
});

test('a second identical "Settings saved." is a new line in the status region', async () => {
  serveWorkspace();
  serve(settings);
  recordPuts();
  renderPage('basics');

  const title = await screen.findByRole('textbox', {name: 'Title'}, {timeout: 10_000});
  const region = screen.getByRole('status');
  fireEvent.change(title, {target: {value: 'A new title'}});
  fireEvent.click(screen.getByRole('button', {name: 'Save'}));
  await waitFor(() => expect(region).toHaveTextContent('Settings saved.'));
  const first = region.firstElementChild;
  fireEvent.click(screen.getByRole('button', {name: 'Save'}));
  await waitFor(() => expect(region.firstElementChild).not.toBe(first));
  expect(region).toHaveTextContent(/Settings (saved|already up to date)\./);
});

test('a Basics save refreshes the frame, whose breadcrumb carries the title', async () => {
  serveWorkspace();
  serve(settings);
  recordPuts();
  const client = createQueryClient();
  const invalidate = vi.spyOn(client, 'invalidateQueries');
  renderPage('basics', client);

  fireEvent.change(await screen.findByRole('textbox', {name: 'Title'}, {timeout: 10_000}),
    {target: {value: 'A new title'}});
  fireEvent.click(screen.getByRole('button', {name: 'Save'}));

  await waitFor(() => expect(invalidate).toHaveBeenCalledWith(
    expect.objectContaining({queryKey: ['admin-lifecycle', 7]}),
  ));
});
