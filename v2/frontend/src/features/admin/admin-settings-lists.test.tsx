import {Suspense} from 'react';
import {QueryClientProvider, type QueryClient} from '@tanstack/react-query';
import {fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {http, HttpResponse} from 'msw';
import {MemoryRouter} from 'react-router-dom';
import {expect, test, vi} from 'vitest';

import type {components} from '../../api/schema';
import {AdminInvitationsPage} from './admin-invitations-page';
import {AdminRolesPage} from './admin-roles-page';
import {MessageProvider} from '../../i18n/messages';
import {createQueryClient} from '../../query-client';
import {server} from '../../test/server';

/** Settings › Invitations and Roles: a request on its way cannot be sent twice, a removed
 *  row hands focus on and says what happened, and a status line describes the current
 *  choice only (pr-check #522 items). */

type Settings = components['schemas']['AdminSettings'];

const url = (path: string) => new URL(path, globalThis.location.origin).toString();
const SETTINGS_URL = url('/api/v1/admin/conversations/7/settings');
const INVITATIONS_URL = url('/api/v1/admin/conversations/7/invitations');

const settings: Settings = {
  conversation: {
    id: 7, slug: 'community-strategy', title: 'Community strategy',
    introHtml: '', outroHtml: '', accessPolicy: 'invite_only',
    gated: true, gatingType: 'invite_only', announce: false, information: false,
    resultsShared: false, showUsernames: false, accessRequestText: null,
    phaseRoute: 'default_7', phaseRouteLabel: 'Full consultation',
    polisId: 'polis-community-strategy',
  },
  recommendations: {tier: 'medium', tiers: [
    {key: 'medium', label: 'Medium topic', quantities: {seed_statements: 8}},
  ]},
  eligibility: {configured: false, eventId: '', label: null, configurationMode: 'editable', note: ''},
  capabilities: {edit: true, switchDemo: false},
  locks: {gated: false, gatingType: false, showUsernames: false},
  links: {self: SETTINGS_URL, lifecycle: '/admin/conversations/7'},
};

const invitation = (id: number, username: string) => (
  {id, username, createdAt: '2026-08-01T10:00:00Z', signedIn: false}
);

function serveInvitations(invitations: ReturnType<typeof invitation>[]) {
  server.use(http.get(SETTINGS_URL, () => HttpResponse.json({data: settings})));
  server.use(http.get(INVITATIONS_URL, () => HttpResponse.json({data: {
    conversation: {id: 7, slug: 'community-strategy', title: 'Community strategy', accessPolicy: 'invite_only'},
    invitations,
    capabilities: {manageInvitations: true},
    links: {self: INVITATIONS_URL, conversation: '/admin/conversations/7'},
  }})));
}

function renderPage(page: React.ReactNode, path: string, client: QueryClient = createQueryClient()) {
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Suspense fallback={null}>
          <MessageProvider locale="en">{page}</MessageProvider>
        </Suspense>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const politeRegion = () => document.querySelector('[aria-live="polite"]')!;

test('Add sends one batch however often it is pressed while the first is on its way', async () => {
  serveInvitations([]);
  const sent: unknown[] = [];
  let release: () => void = () => {};
  const held = new Promise<void>((resolve) => { release = resolve; });
  server.use(http.put(INVITATIONS_URL, async ({request}) => {
    sent.push(await request.json());
    await held;
    return HttpResponse.json({data: {
      outcome: {added: 1, alreadyPresent: 0, concurrentConflicts: 0, duplicateInputs: 0},
      invitations: [invitation(52, 'New editor')],
      links: {invitations: INVITATIONS_URL},
    }});
  }));
  renderPage(<AdminInvitationsPage conversationId={7} csrfToken="t" />,
    '/admin/conversations/7/settings/invitations');

  const field = await screen.findByRole('textbox', {}, {timeout: 10_000});
  fireEvent.change(field, {target: {value: 'New editor'}});
  const form = field.closest('form')!;
  const add = within(form).getByRole('button');
  fireEvent.click(add);
  await waitFor(() => expect(add).toBeDisabled());
  // A second submit by Enter, while the first is pending, sends nothing.
  fireEvent.submit(form);
  fireEvent.submit(form);
  release();
  await screen.findByText('New editor');
  expect(sent).toHaveLength(1);
});

test('Remove hands focus to the next row and says which invitation went', async () => {
  serveInvitations([invitation(51, 'First editor'), invitation(52, 'Second editor')]);
  server.use(http.delete(url('/api/v1/admin/conversations/7/invitations/:inviteId'), () => {
    // Re-served without the removed row, as the server would after the delete.
    serveInvitations([invitation(52, 'Second editor')]);
    return HttpResponse.json({data: {
      invitationId: 51, removed: true, invitations: [invitation(52, 'Second editor')],
      links: {invitations: INVITATIONS_URL},
    }});
  }));
  renderPage(<AdminInvitationsPage conversationId={7} csrfToken="t" />,
    '/admin/conversations/7/settings/invitations');

  const first = await screen.findByRole('button', {name: /First editor/}, {timeout: 10_000});
  first.focus();
  fireEvent.click(first);

  const second = screen.getByRole('button', {name: /Second editor/});
  await waitFor(() => expect(second).toHaveFocus());
  expect(screen.queryByText('First editor')).toBeNull();
  expect(politeRegion()).toHaveTextContent('Invitation for First editor removed.');
});

test('removing the last invitation leaves focus on the empty-list line', async () => {
  serveInvitations([invitation(51, 'First editor')]);
  renderPage(<AdminInvitationsPage conversationId={7} csrfToken="t" />,
    '/admin/conversations/7/settings/invitations');

  fireEvent.click(await screen.findByRole('button', {name: /First editor/}, {timeout: 10_000}));
  await waitFor(() => expect(document.activeElement?.textContent).toMatch(/^No invit/));
  expect(politeRegion()).toHaveTextContent('Invitation for First editor removed.');
});

test('a Roles result goes when another person or role is chosen', async () => {
  server.use(http.get(SETTINGS_URL, () => HttpResponse.json({data: settings})));
  renderPage(<AdminRolesPage conversationId={7} csrfToken="t" />,
    '/admin/conversations/7/settings/roles');

  const person = await screen.findByRole('combobox', {}, {timeout: 10_000});
  fireEvent.change(person, {target: {value: '23'}});
  fireEvent.click(screen.getByRole('checkbox', {name: /organizer/i}));
  const form = person.closest('form')!;
  fireEvent.submit(form);
  const status = within(form).getByRole('status');
  await waitFor(() => expect(status).toHaveTextContent(/organizer/));

  fireEvent.change(person, {target: {value: ''}});
  // The region stays mounted for the next result, but no longer speaks about the last one.
  expect(status).toBeEmptyDOMElement();
});

test('a Roles save reads the frame and the settings again', async () => {
  server.use(http.get(SETTINGS_URL, () => HttpResponse.json({data: settings})));
  const client = createQueryClient();
  const invalidate = vi.spyOn(client, 'invalidateQueries');
  renderPage(<AdminRolesPage conversationId={7} csrfToken="t" />,
    '/admin/conversations/7/settings/roles', client);

  const person = await screen.findByRole('combobox', {}, {timeout: 10_000});
  fireEvent.change(person, {target: {value: '23'}});
  fireEvent.submit(person.closest('form')!);

  await waitFor(() => expect(invalidate).toHaveBeenCalledWith(
    expect.objectContaining({queryKey: ['admin-lifecycle', 7]}),
  ));
  expect(invalidate).toHaveBeenCalledWith(expect.objectContaining({queryKey: ['admin-settings', 7]}));
});
