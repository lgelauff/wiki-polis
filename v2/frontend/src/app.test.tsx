import {QueryClientProvider} from '@tanstack/react-query';
import {fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {http, HttpResponse} from 'msw';
import {Link, MemoryRouter, useLocation} from 'react-router-dom';
import {expect, test, vi} from 'vitest';

import {App} from './app';
import {createQueryClient} from './query-client';
import {adminCatalogFixture, testMessages} from './test/handlers';
import {server} from './test/server';

test('renders a conversation lane from the API contract', async () => {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={['/app/real']}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );

  expect(screen.getByRole('status')).toHaveTextContent('Loading…');
  expect(await screen.findByRole('heading', {name: 'Needs attention'})).toBeVisible();
  expect(await screen.findByRole('link', {name: /Community strategy.*continue/}))
    .toHaveAttribute('href', '/c/community-strategy');
  expect(screen.getByRole('button', {name: 'Your consultations'})).toHaveAttribute('aria-pressed', 'true');
  fireEvent.click(screen.getByRole('button', {name: 'New consultations'}));
  expect(screen.getByText('No new consultations are open to you right now. You may still have consultations you joined earlier under Your consultations.')).toBeVisible();
});

test('keeps the current route painted while the next route loads', async () => {
  let releaseAdmin!: () => void;
  const adminReady = new Promise<void>((resolve) => { releaseAdmin = resolve; });
  server.use(http.get(
    new URL('/api/v1/admin', globalThis.location.origin).toString(),
    async () => {
      await adminReady;
      return HttpResponse.json({data: adminCatalogFixture()});
    },
  ));
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={['/consultations']}>
        <Link to="/admin">Open admin</Link>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );

  const currentHeading = await screen.findByRole('heading', {name: 'Needs attention'});
  fireEvent.click(screen.getByRole('link', {name: 'Open admin'}));

  expect(currentHeading).toBeVisible();
  expect(screen.queryByRole('status')).not.toBeInTheDocument();

  releaseAdmin();
  // #479: the page is the site admin dashboard now.
  expect(await screen.findByRole('heading', {name: 'Site admin dashboard'})).toBeVisible();
});

test('matches the legacy pending-output dialog and restores focus', async () => {
  server.use(http.get(
    new URL('/api/v1/conversations', globalThis.location.origin).toString(),
    () => HttpResponse.json({data: {
      space: 'real',
      authenticated: true,
      groups: {
        needsAttention: [{
          slug: 'community-strategy', title: 'Community strategy',
          relationship: 'joined', participantState: 'needs_attention',
          pseudonym: 'quiet-otter', status: 'open', closedAt: null,
          phases: ['submission'], statementsRemaining: 4,
          scheduledTransition: null, reveal: null,
          outputs: [{
            key: 'initial-clustering', label: 'Initial clustering',
            status: 'provisional', symbol: 'initial-clustering',
            tooltip: 'After Explore phase: topic and participant clustering',
            pending: 'Initial clustering becomes available after Explore closes.',
            ready: false, href: '/c/community-strategy/outputs/initial-clustering',
          }],
          capabilities: {join: false, participate: true, moderate: false},
          links: {self: '/c/community-strategy', about: '/c/community-strategy/about'},
        }],
        caughtUp: [], inactive: [], archived: [], available: [], moderating: [],
      },
    }}),
  ));
  render(<QueryClientProvider client={createQueryClient()}><MemoryRouter initialEntries={['/app/real']}><App /></MemoryRouter></QueryClientProvider>);

  const trigger = await screen.findByRole('button', {name: 'After the Explore phase: topic and participant clustering'});
  fireEvent.click(trigger);
  const dialog = screen.getByRole('dialog', {name: 'Initial clustering'});
  expect(dialog).toBeVisible();
  expect(screen.getByRole('button', {name: 'Close output details'})).toHaveFocus();
  fireEvent.keyDown(document, {key: 'Escape'});
  expect(dialog).not.toBeVisible();
  expect(trigger).toHaveFocus();
});

test('runs site-wide administration without falling back to Jinja forms', async () => {
  render(<QueryClientProvider client={createQueryClient()}><MemoryRouter initialEntries={['/app/admin']}><App /></MemoryRouter></QueryClientProvider>);

  expect(await screen.findByRole('heading', {name: 'Site admin dashboard'})).toBeVisible();
  expect(screen.getByRole('link', {name: 'manage'})).toHaveAttribute('href', '/admin/conversations/7');
  // The settings page used to be reachable only by typing its URL.
  expect(screen.getByRole('link', {name: 'settings'})).toHaveAttribute('href', '/admin/conversations/7/settings');
  // The Access column names the stored value in words instead of printing "public".
  expect(screen.getByRole('columnheader', {name: 'Access'})).toBeVisible();
  expect(screen.getByRole('cell', {name: 'Anyone with a Wikimedia account'})).toBeVisible();
  expect(screen.queryByText('invite_only')).not.toBeInTheDocument();
  expect(screen.getByText('Admin')).toHaveClass('header-mode-badge');
  // #479: keyed with `admin-new-conv-heading`, whose English is "New consultation".
  expect(screen.getByRole('heading', {name: 'New consultation'})).toBeVisible();
  fireEvent.change(screen.getByLabelText('Wikimedia username'), {target: {value: 'Example editor'}});
  fireEvent.click(screen.getByRole('button', {name: 'Grant'}));
  await waitFor(() => expect(screen.getAllByText('Example editor')).toHaveLength(2));
  expect(screen.queryByRole('status')).not.toBeInTheDocument();
});

test('matches the legacy catalog error for an unknown global admin', async () => {
  server.use(http.post(
    new URL('/api/v1/admin/global-admin-grants', globalThis.location.origin).toString(),
    () => HttpResponse.json({
      error: {
        code: 'participant_not_found',
        message: 'That account must sign in once before it can be granted access.',
      },
    }, {status: 404}),
  ));
  render(<QueryClientProvider client={createQueryClient()}><MemoryRouter initialEntries={['/app/admin']}><App /></MemoryRouter></QueryClientProvider>);

  const username = await screen.findByLabelText('Wikimedia username');
  fireEvent.change(username, {target: {value: 'MissingEditor'}});
  fireEvent.click(screen.getByRole('button', {name: 'Grant'}));

  expect(await screen.findByRole('alert')).toHaveTextContent(
    'No account found for "MissingEditor". They must log in at least once first.',
  );
  expect(username).toHaveValue('');
});

test('matches the legacy forbidden document for denied admin access', async () => {
  server.use(http.get(
    new URL('/api/v1/admin', globalThis.location.origin).toString(),
    () => HttpResponse.json({
      error: {code: 'forbidden', message: 'You do not have access to this resource.'},
    }, {status: 403}),
  ));
  render(<QueryClientProvider client={createQueryClient()}><MemoryRouter initialEntries={['/app/admin']}><App /></MemoryRouter></QueryClientProvider>);

  expect(await screen.findByRole('heading', {name: 'Forbidden'})).toBeVisible();
  expect(screen.getByText(/read-protected or not readable by the server/)).toBeVisible();
  expect(document.title).toBe('403 Forbidden');
});

test('advances a conversation from the server-described lifecycle console', async () => {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={['/app/admin/conversations/7']}><App /></MemoryRouter>
    </QueryClientProvider>,
  );

  expect(await screen.findByRole('heading', {name: 'Community strategy'})).toBeVisible();
  expect(screen.getByText('You are in phase 1 of 3')).toBeVisible();
  const advance = screen.getByRole('button', {name: 'Move on to Explore →'});
  expect(advance).toBeDisabled();
  fireEvent.click(screen.getByRole('checkbox', {name: /statement set and introduction/}));
  expect(advance).toBeEnabled();
  fireEvent.click(advance);

  expect(await screen.findByText('You are in phase 2 of 3')).toBeVisible();
  expect(screen.getByText('Report phase reached — not yet published.')).toBeVisible();
  expect(screen.getByRole('link', {name: /Participants/})).toHaveAttribute(
    'href', '/admin/conversations/7/participants',
  );
});

test('the lifecycle console writes no setting of its own, and points at the page that does', async () => {
  // This test used to drive the console's own settings and recommendation-tier forms. Both
  // edited fields the settings page edits too, so they were removed; what is pinned now is
  // the absence. Both endpoints are wired to fail, so any surviving writer would be loud.
  let writes = 0;
  const refuse = () => {writes += 1; return HttpResponse.error();};
  server.use(
    http.put(
      new URL('/api/v1/admin/conversations/7/settings', globalThis.location.origin).toString(),
      refuse,
    ),
    http.put(
      new URL('/api/v1/admin/conversations/7/recommendation-tier', globalThis.location.origin).toString(),
      refuse,
    ),
  );
  render(<QueryClientProvider client={createQueryClient()}><MemoryRouter initialEntries={['/app/admin/conversations/7']}><App /></MemoryRouter></QueryClientProvider>);

  await screen.findByRole('heading', {name: 'Community strategy'});
  // #477: the console shell's sidebar carries a Settings link of its own, so the card is
  // named whole (title and description) to tell the two apart.
  expect(screen.getByRole('link', {name: 'Settings Title, introduction and access'})).toHaveAttribute(
    'href', '/admin/conversations/7/settings',
  );
  expect(screen.queryByRole('button', {name: /^Save( settings)?$/})).toBeNull();
  expect(screen.queryByRole('button', {name: 'Save recommendations'})).toBeNull();
  expect(screen.queryByLabelText('Complexity tier')).toBeNull();
  // The tier is still reported, as the fact the readiness checks are measured against.
  expect(screen.getByText(/Complexity tier/)).toBeVisible();
  expect(writes).toBe(0);
});

test('schedules and cancels a lifecycle transition', async () => {
  render(<QueryClientProvider client={createQueryClient()}><MemoryRouter initialEntries={['/app/admin/conversations/7']}><App /></MemoryRouter></QueryClientProvider>);
  await screen.findByRole('heading', {name: 'Community strategy'});
  fireEvent.change(screen.getByLabelText('Scheduled transition time in UTC'), {target: {value: '2030-01-02T12:30'}});
  fireEvent.click(screen.getByRole('button', {name: 'Set'}));
  expect(await screen.findByRole('button', {name: 'Edit'})).toBeVisible();
  expect(screen.getByRole('button', {name: 'Freeze'})).toBeVisible();
  fireEvent.click(screen.getByRole('button', {name: 'Cancel'}));
  expect(await screen.findByRole('button', {name: 'Set'})).toBeVisible();
});

test('repairs an advanced phase set through route-valid domain keys', async () => {
  vi.spyOn(globalThis, 'confirm').mockReturnValueOnce(true);
  render(<QueryClientProvider client={createQueryClient()}><MemoryRouter initialEntries={['/app/admin/conversations/7']}><App /></MemoryRouter></QueryClientProvider>);
  await screen.findByRole('heading', {name: 'Community strategy'});
  fireEvent.click(screen.getByRole('button', {name: 'Advanced'}));
  fireEvent.click(screen.getByRole('checkbox', {name: /Argument mapping/}));
  fireEvent.click(screen.getByRole('checkbox', {name: /Informed opinion/}));
  fireEvent.click(screen.getByRole('button', {name: 'Save phases'}));
  expect(await screen.findByText(/Enabled but not initialised/)).toBeVisible();
  fireEvent.click(screen.getByRole('button', {name: 'Initialise Phase 6'}));
  expect(await screen.findByText(/Phase 6 Polis conversation:/)).toBeVisible();
});

test('pauses and resumes from the legacy lifecycle control', async () => {
  render(<QueryClientProvider client={createQueryClient()}><MemoryRouter initialEntries={['/app/admin/conversations/7']}><App /></MemoryRouter></QueryClientProvider>);
  await screen.findByRole('heading', {name: 'Community strategy'});
  fireEvent.click(screen.getByRole('button', {name: 'Pause'}));
  expect(await screen.findByRole('button', {name: 'Resume'})).toBeVisible();
  expect(screen.getByText(/identity-reveal clock has/)).toBeVisible();
  fireEvent.click(screen.getByRole('button', {name: 'Resume'}));
  expect(await screen.findByRole('button', {name: 'Pause'})).toBeVisible();
});

test('edits settings and legacy eligibility through one typed command', async () => {
  // #478: the bare .../settings path is the old URL and lands on Basics; the eligibility
  // fields are on Access. Both tabs PUT the one complete settings representation.
  const access = render(<QueryClientProvider client={createQueryClient()}><MemoryRouter initialEntries={['/app/admin/conversations/7/settings/access']}><App /></MemoryRouter></QueryClientProvider>);
  expect(await screen.findByRole('heading', {name: 'Settings', level: 1})).toBeVisible();
  expect(screen.queryByRole('heading', {name: 'Access'})).toBeNull();
  expect(screen.getByText('Extended-confirmed editors')).toBeVisible();
  fireEvent.change(screen.getByLabelText('Eligibility event ID'), {target: {value: 'experienced-editors'}});
  fireEvent.change(screen.getByLabelText('Eligibility label'), {target: {value: 'Experienced editors'}});
  fireEvent.click(screen.getByRole('button', {name: 'Save'}));
  await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('Settings saved'));
  access.unmount();

  render(<QueryClientProvider client={createQueryClient()}><MemoryRouter initialEntries={['/app/admin/conversations/7/settings']}><App /></MemoryRouter></QueryClientProvider>);
  expect(await screen.findByRole('heading', {name: 'Settings', level: 1})).toBeVisible();
  expect(screen.queryByRole('heading', {name: 'Basics'})).toBeNull();
  fireEvent.change(screen.getByLabelText('Title'), {target: {value: 'Updated strategy'}});
  fireEvent.click(screen.getByRole('radio', {name: /Complex topic/}));
  fireEvent.click(screen.getByRole('button', {name: 'Save'}));
  await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('Settings saved'));
});

test('deletes a verified empty conversation through a deliberate receipt flow', async () => {
  vi.spyOn(globalThis, 'confirm').mockReturnValueOnce(true);
  render(<QueryClientProvider client={createQueryClient()}><MemoryRouter initialEntries={['/app/admin/conversations/7/termination']}><App /></MemoryRouter></QueryClientProvider>);

  expect(await screen.findByRole('heading', {name: 'Delete conversation'})).toBeVisible();
  expect(screen.getByText('Valid votes').parentElement).toHaveTextContent('0');
  const deletion = screen.getByRole('button', {name: 'Permanently delete conversation'});
  expect(deletion).toBeDisabled();
  fireEvent.change(screen.getByLabelText(/Type Community strategy to confirm/), {
    target: {value: 'Community strategy'},
  });
  expect(deletion).toBeEnabled();
  fireEvent.click(deletion);

  expect(await screen.findByRole('heading', {name: 'Conversation deleted'})).toBeVisible();
  expect(screen.getByRole('link', {name: 'Return to admin panel'})).toHaveAttribute('href', '/admin');
});

test('moderates statements and imports approved seeds through typed commands', async () => {
  render(<QueryClientProvider client={createQueryClient()}><MemoryRouter initialEntries={['/app/admin/conversations/7/statements']}><App /></MemoryRouter></QueryClientProvider>);

  // #473: the old .../statements path redirects to Content > Statements, which is headed
  // like every other page of the section.
  expect(await screen.findByRole('heading', {name: 'Content', level: 1})).toBeVisible();
  expect(screen.queryByRole('heading', {name: 'Statements'})).toBeNull();
  // #473: the list is one row per statement behind the state switch, which opens on the
  // approved ones; the waiting statement is one click away.
  expect(screen.getByRole('button', {name: /^Show unmoderated/})).toBeVisible();
  fireEvent.click(screen.getByRole('button', {name: /^Show unmoderated/}));
  expect(await screen.findByText('A participant proposal awaiting review.')).toBeVisible();
  expect(screen.getByText(
    'Adds a seed-marked statement that appears early in the voting sequence for participants.',
  )).toBeVisible();
  // #478: the Approval control moved to Settings > Basics, so this page no longer owns it.
  expect(screen.queryByRole('checkbox', {name: /Strict moderation/})).toBeNull();
  fireEvent.click(screen.getByRole('button', {name: 'approve'}));
  // Approving takes the row out of the waiting list and into the approved one.
  await waitFor(() => expect(screen.queryByText('A participant proposal awaiting review.')).toBeNull());
  fireEvent.click(screen.getByRole('button', {name: /^Show approved/}));
  await waitFor(() => expect(screen.getByText('A participant proposal awaiting review.')).toBeVisible());

  fireEvent.change(screen.getByLabelText('Statements'), {
    target: {value: 'First seed\nSecond seed'},
  });
  fireEvent.click(screen.getByRole('button', {name: 'Import statements'}));
  expect((await screen.findAllByText('✓ 2 statements imported'))[0]).toBeVisible();

  fireEvent.change(screen.getByLabelText('Statement text (max 280 characters)'), {
    target: {value: 'A corrected seed'},
  });
  fireEvent.change(screen.getByLabelText(/Corrects statement/), {target: {value: '12'}});
  fireEvent.click(screen.getByRole('button', {name: 'Add seed statement'}));
  expect((await screen.findAllByText('Seed statement added (recorded as a correction of #12).'))[0]).toBeVisible();
});

test('matches legacy featured-statement administration and commands', async () => {
  render(<QueryClientProvider client={createQueryClient()}><MemoryRouter initialEntries={['/app/admin/conversations/7/featured']}><App /></MemoryRouter></QueryClientProvider>);

  // #473: the old .../featured path redirects to Moderation > Featured, which is headed
  // like every other page of the section.
  expect(await screen.findByRole('heading', {name: 'Moderation', level: 1})).toBeVisible();
  expect(screen.queryByRole('heading', {name: 'Featured'})).toBeNull();
  expect(screen.getByRole('heading', {name: 'Confirmed (1)'})).toBeVisible();
  expect(screen.getByText('An approved seed statement.')).toBeVisible();
  expect(screen.getByText('A candidate preserving another viewpoint.')).toBeVisible();
  const candidates = screen.getAllByRole('table')[1]!;
  expect(within(candidates).getByText('2')).toBeVisible();
  expect(within(candidates).getByText('6')).toBeVisible();
  expect(screen.queryByText(/divisiv/i)).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', {name: 'confirm'}));
  await waitFor(() => expect(screen.queryByRole('status')).not.toBeInTheDocument());

  fireEvent.click(screen.getByRole('button', {name: 'hide'}));
  await waitFor(() => expect(screen.queryByRole('status')).not.toBeInTheDocument());
});

test('manages participant access in the distinct admin workspace', async () => {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={['/app/admin/conversations/7/participants']}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );

  expect(await screen.findByRole('heading', {name: 'Content', level: 1})).toBeVisible();
  expect(screen.queryByRole('heading', {name: 'Participants'})).toBeNull();
  // The roster is a list of rows now, not a table (#473).
  const roster = within(screen.getByRole('main')).getByRole('listitem').closest('ul')!;
  expect(within(roster).getByText('Example editor')).toBeVisible();
  expect(screen.getByText('8 / 12')).toBeVisible();
  fireEvent.change(screen.getByPlaceholderText('Reason (optional)'), {
    target: {value: 'Repeated disruption'},
  });
  fireEvent.click(screen.getByRole('button', {name: /^ban/}));

  expect(await screen.findByRole('button', {
    name: /^unban/,
  })).toBeVisible();
  expect(screen.getByText('Repeated disruption')).toBeVisible();
  await waitFor(() => expect(document.querySelector('[aria-live="polite"]')).toHaveTextContent(
    'Participant banned from this conversation.',
  ));
});

test('resolves a privacy-safe moderation item through the typed contract', async () => {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={['/app/admin/conversations/7/moderation']}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );

  // #473: the old /moderation path redirects to Moderation > Flags. The page no longer
  // carries the flagger-identity paragraph (quiet screens: no explanatory sentences), and
  // the row is the flagged text with the reason as its suffix, so no target label is
  // printed; one "Mark as handled" closes it, with an optional note.
  expect(await screen.findByRole('heading', {name: 'Moderation', level: 1})).toBeVisible();
  expect(screen.queryByRole('heading', {name: 'Flags'})).toBeNull();
  expect(screen.getByText('A statement containing private information.')).toBeVisible();
  // The reason is a muted suffix on the flagged text, not a field of its own.
  expect(screen.getByText(/Privacy violation/)).toHaveClass('admin-row__suffix');
  fireEvent.click(screen.getByRole('button', {name: /^Mark as handled/}));

  expect(await screen.findByText('No open flags.')).toBeVisible();
  await waitFor(() => expect(document.querySelector('[aria-live="polite"]'))
    .toHaveTextContent('Flag marked as handled.'));
});

/** Serves settings whose answer to who gets in is the invitation list: the Invitations tab
 *  offers its add form only then. */
function serveInvitationListSettings() {
  server.use(http.get(
    new URL('/api/v1/admin/conversations/7/settings', globalThis.location.origin).toString(),
    () => HttpResponse.json({data: {
      conversation: {id: 7, slug: 'community-strategy', title: 'Community strategy', introHtml: '<p>Shape the future.</p>', outroHtml: '', accessPolicy: 'invite_only', gated: true, gatingType: 'invite_only', announce: false, information: false, resultsShared: false, showUsernames: false, accessRequestText: null, phaseRoute: 'default_7', phaseRouteLabel: 'Full consultation', polisId: 'polis-community-strategy'},
      recommendations: {tier: 'medium', tiers: [
        {key: 'medium', label: 'Medium topic', quantities: {seed_statements: 8, featured_statements: 15}},
      ]},
      eligibility: {configured: false, eventId: '', label: null, configurationMode: 'editable', note: 'Leave the event ID blank when no external eligibility check applies.'},
      capabilities: {edit: true, switchDemo: true}, locks: {gated: false, gatingType: false, showUsernames: false}, links: {self: '/api/v1/admin/conversations/7/settings', lifecycle: '/admin/conversations/7'},
    }}),
  ));
}

test('adds and removes invitations through convergent admin commands', async () => {
  serveInvitationListSettings();
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={['/app/admin/conversations/7/invitations']}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );

  // #478: .../invitations is an old path that redirects to the Invitations tab, which is
  // headed by the section like every other Settings tab, and no heading repeats the tab.
  expect(await screen.findByRole('heading', {name: 'Settings', level: 1})).toBeVisible();
  expect(screen.queryByRole('heading', {name: 'Invitations'})).toBeNull();
  expect(screen.getByRole('heading', {name: 'Add invites', level: 2})).toBeVisible();
  // With the invitation list in effect the form works, and there is no reason line.
  expect(screen.getByLabelText('Wikimedia usernames (one per line)')).toBeEnabled();
  expect(screen.queryByText(/^Not available:/)).toBeNull();
  // The access policy reads in words; the stored value never reaches the page.
  expect(screen.getByText('Only people who have been given access')).toBeVisible();
  expect(screen.queryByText('invite_only', {exact: false})).not.toBeInTheDocument();
  expect(screen.getByText('Existing editor')).toBeVisible();
  expect(screen.getByText('1 invited · 1 linked · 0 never logged in')).toBeVisible();
  const existingRow = screen.getByText('Existing editor').closest('tr');
  expect(within(existingRow!).getByText('Linked')).toBeVisible();
  fireEvent.change(screen.getByLabelText('Wikimedia usernames (one per line)'), {
    target: {value: 'New editor\nNew editor'},
  });
  fireEvent.click(screen.getByRole('button', {name: 'Add'}));

  expect(await screen.findByText('New editor')).toBeVisible();
  // The toast inside the console reads out through the shell's polite region.
  expect(screen.getByText('Invites: 1 added; 1 duplicate input.', {selector: '.toast__msg'})).toBeVisible();
  await waitFor(() => expect(document.querySelector('[aria-live="polite"]'))
    .toHaveTextContent('Invites: 1 added; 1 duplicate input.'));
  const newEditorRow = screen.getByText('New editor').closest('tr');
  expect(newEditorRow).not.toBeNull();
  expect(within(newEditorRow!).getByText('Never logged in')).toBeVisible();
  expect(screen.getByText('2 invited · 1 linked · 1 never logged in')).toBeVisible();
  fireEvent.click(within(newEditorRow!).getByRole('button', {
    name: 'Remove invitation for New editor',
  }));
  expect(await screen.findByText('No invites yet.')).toBeVisible();
  expect(screen.getByText('No invites yet.').closest('td')).toHaveAttribute('colspan', '4');
  expect(screen.queryByText(/invited ·/)).not.toBeInTheDocument();
});

test('greys out adding invites while access is not the invitation list, and says why', async () => {
  // With any other answer to who gets in, an added invite would admit nobody: the form is
  // shown disabled, with one line naming the access policy in effect, linked from both of
  // its controls. The stored invitations stay listed, each with its remove button.
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={['/app/admin/conversations/7/invitations']}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );

  expect(await screen.findByText('Existing editor')).toBeVisible();
  expect(screen.getByRole('heading', {name: 'Add invites', level: 2})).toBeVisible();
  const reason = screen.getByText('Not available: access is set to “Anyone with a Wikimedia account”.');
  const textarea = screen.getByLabelText('Wikimedia usernames (one per line)');
  const add = screen.getByRole('button', {name: 'Add'});
  expect(textarea).toBeDisabled();
  expect(add).toBeDisabled();
  expect(textarea).toHaveAttribute('aria-describedby', reason.id);
  expect(add).toHaveAttribute('aria-describedby', reason.id);
  expect(screen.queryByText(/Invites only take effect/)).toBeNull();
  expect(screen.getByRole('button', {name: 'Remove invitation for Existing editor'})).toBeEnabled();
});

test('keeps the typed invitation list and shows a toast after a save error', async () => {
  serveInvitationListSettings();
  server.use(http.put(
    new URL(
      '/api/v1/admin/conversations/7/invitations',
      globalThis.location.origin,
    ).toString(),
    () => HttpResponse.json({
      error: {code: 'save_failed', message: 'The invitations could not be saved safely.'},
    }, {status: 503}),
  ));
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={['/app/admin/conversations/7/invitations']}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );

  const input = await screen.findByLabelText('Wikimedia usernames (one per line)');
  fireEvent.change(input, {target: {value: 'New editor'}});
  fireEvent.click(screen.getByRole('button', {name: 'Add'}));

  expect(await screen.findByText("Couldn't save invites — please review the list and retry.",
    {selector: '.toast__msg'})).toBeVisible();
  // Read out as an alert, through the console's assertive region.
  await waitFor(() => expect(document.querySelector('[aria-live="assertive"]')).toHaveTextContent(
    "Couldn't save invites — please review the list and retry.",
  ));
  expect(input).toHaveValue('New editor');
});

test('replaces a conversation role set from the admin workspace', async () => {
  render(<QueryClientProvider client={createQueryClient()}><MemoryRouter initialEntries={['/app/admin/conversations/7/roles']}><App /></MemoryRouter></QueryClientProvider>);
  // #478: Roles is a Settings tab; its own "Conversation roles" heading went with the old
  // layout, no heading repeats the tab name, and the roster is an h2 under the h1.
  const assigned = await screen.findByRole('heading', {name: 'Assigned', level: 2});
  expect(screen.getByRole('heading', {name: 'Settings', level: 1})).toBeVisible();
  expect(screen.queryByRole('heading', {name: 'Roles'})).toBeNull();
  // The roster's own row, not the username in the console's top bar.
  const roster = assigned.closest('section')!;
  expect(within(roster).getByRole('listitem')).toHaveTextContent('Example editor');
  fireEvent.change(screen.getByLabelText('Participant'), {target: {value: '23'}});
  fireEvent.click(screen.getByRole('checkbox', {name: 'organizer'}));
  fireEvent.click(screen.getByRole('button', {name: 'Save role set'}));
  expect(await screen.findByRole('status')).toHaveTextContent('Added: organizer');
  expect(screen.getByText('moderator + organizer')).toBeVisible();
});

function LocationProbe() {
  const location = useLocation();
  return <output aria-label="client location">{location.pathname}</output>;
}

test.each([
  ['/admin/conversations/7/invites', '/admin/conversations/7/settings/invitations'],
  ['/admin/conversations/7/roles', '/admin/conversations/7/settings/roles'],
  // The /app/admin group redirects into the canonical /admin group.
  ['/app/admin/conversations/7/invitations', '/admin/conversations/7/settings/invitations'],
  ['/app/admin/conversations/7/roles', '/admin/conversations/7/settings/roles'],
])('the old path %s redirects to the Settings tab %s', async (source, target) => {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={[source]}>
        <App />
        <LocationProbe />
      </MemoryRouter>
    </QueryClientProvider>,
  );

  await waitFor(() => expect(screen.getByLabelText('client location')).toHaveTextContent(target));
  expect(screen.getByLabelText('client location').textContent).toBe(target);
});

test.each([
  ['invitations', 'Invitations'],
  ['vouchers', 'Vouchers'],
  ['roles', 'Roles'],
])('the Settings tab …/settings/%s is routed to its page', async (tab, heading) => {
  // Guards the routes themselves: a later change that drops one would fall through to the
  // not-found route instead.
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={[`/admin/conversations/7/settings/${tab}`]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );

  expect(await screen.findByRole('heading', {name: 'Settings', level: 1}, {timeout: 10_000}))
    .toBeVisible();
  // The strip's current tab names the page; no heading repeats it.
  expect(screen.queryByRole('heading', {name: heading})).toBeNull();
  expect(screen.getByRole('navigation', {name: 'Settings'})
    .querySelectorAll('[aria-current="page"]')).toHaveLength(1);
});

test.each([
  ['/admin/conversations/7/flags', '/admin/conversations/7/moderation/flags'],
  ['/admin/conversations/7/featured', '/admin/conversations/7/moderation/featured'],
  // The /app/admin group's flags page was called moderation.
  ['/app/admin/conversations/7/moderation', '/admin/conversations/7/moderation/flags'],
  ['/app/admin/conversations/7/featured', '/admin/conversations/7/moderation/featured'],
])('the old path %s redirects to the Moderation page %s', async (source, target) => {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={[source]}>
        <App />
        <LocationProbe />
      </MemoryRouter>
    </QueryClientProvider>,
  );

  await waitFor(() => expect(screen.getByLabelText('client location')).toHaveTextContent(target));
  expect(screen.getByLabelText('client location').textContent).toBe(target);
});

test.each([
  ['/admin', 'queue', 'Queue'],
  ['/admin', 'flags', 'Flags'],
  ['/admin', 'featured', 'Featured'],
  ['/admin', 'people', 'People'],
  ['/app/admin', 'queue', 'Queue'],
  ['/app/admin', 'flags', 'Flags'],
  ['/app/admin', 'featured', 'Featured'],
  ['/app/admin', 'people', 'People'],
])('%s/conversations/7/moderation/%s is routed to its page', async (group, page, heading) => {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={[`${group}/conversations/7/moderation/${page}`]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );

  expect(await screen.findByRole('heading', {name: 'Moderation', level: 1}, {timeout: 10_000}))
    .toBeVisible();
  expect(screen.queryByRole('heading', {name: heading})).toBeNull();
  expect(within(screen.getByRole('navigation', {name: 'Moderation'})).getByRole('link', {name: heading}))
    .toHaveAttribute('aria-current', 'page');
});

test.each([
  ['/admin/conversations/7/statements', '/admin/conversations/7/content/statements'],
  ['/admin/conversations/7/participants', '/admin/conversations/7/content/participants'],
  // The /app/admin group redirects into the canonical /admin group.
  ['/app/admin/conversations/7/statements', '/admin/conversations/7/content/statements'],
  ['/app/admin/conversations/7/participants', '/admin/conversations/7/content/participants'],
])('the old path %s redirects to the Content page %s', async (source, target) => {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={[source]}>
        <App />
        <LocationProbe />
      </MemoryRouter>
    </QueryClientProvider>,
  );

  await waitFor(() => expect(screen.getByLabelText('client location')).toHaveTextContent(target));
  expect(screen.getByLabelText('client location').textContent).toBe(target);
});

test.each([
  ['/admin', 'statements', 'Statements'],
  ['/admin', 'participants', 'Participants'],
  ['/app/admin', 'statements', 'Statements'],
  ['/app/admin', 'participants', 'Participants'],
])('%s/conversations/7/content/%s is routed to its page', async (group, page, heading) => {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={[`${group}/conversations/7/content/${page}`]}>
        <App />
        <LocationProbe />
      </MemoryRouter>
    </QueryClientProvider>,
  );

  expect(await screen.findByRole('heading', {name: 'Content', level: 1}, {timeout: 10_000}))
    .toBeVisible();
  expect(screen.queryByRole('heading', {name: heading})).toBeNull();
  expect(within(screen.getByRole('navigation', {name: 'Content'})).getByRole('link', {name: heading}))
    .toHaveAttribute('aria-current', 'page');
  // Routed, not redirected: the page renders at the path it was asked for.
  expect(screen.getByLabelText('client location').textContent)
    .toBe(`${group}/conversations/7/content/${page}`);
});

test('renders a conversation record from the generated API contract', async () => {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={['/app/conversations/community-strategy/about']}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );

  expect(await screen.findByRole('heading', {name: 'About Community strategy'})).toBeVisible();
  expect(screen.getByText('Shape the next chapter together.')).toBeVisible();
  expect(screen.getByText('quiet-otter')).toBeVisible();
  expect(screen.getByRole('heading', {name: 'Your contributions'})).toBeVisible();
  expect(screen.getByRole('link', {name: 'Return to conversation'}))
    .toHaveAttribute('href', '/c/community-strategy');
});

test('requires deliberate confirmation before permanently revealing identity', async () => {
  const revealed = vi.fn();
  server.use(http.post(
    new URL('/api/v1/conversations/community-strategy/identity-reveal', globalThis.location.origin).toString(),
    async ({request}) => {
      revealed(await request.json());
      return HttpResponse.json({
        data: {
          slug: 'community-strategy', title: 'Community strategy', state: 'revealed',
          pseudonym: 'quiet-otter', wikimediaUsername: 'Example editor', publicUsername: 'Example editor',
          timeline: {closedAt: '2026-06-01T12:00:00Z', opensAt: '2026-07-01T12:00:00Z', closesAt: '2026-07-31T12:00:00Z', nextBoundaryAt: null, daysRemaining: 0},
          capabilities: {revealIdentity: false},
          links: {self: '/api/v1/conversations/community-strategy/identity-reveal', conversation: '/c/community-strategy', about: '/c/community-strategy/about'},
        },
      }, {status: 201});
    },
  ));
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={['/app/conversations/community-strategy/identity-reveal']}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );

  expect(await screen.findByRole('heading', {
    name: 'Permanently link quiet-otter to your Wikimedia username?',
  })).toBeVisible();
  const submit = screen.getByRole('button', {name: 'Yes, link my identity'});
  expect(submit.closest('form')).not.toHaveAttribute('action');
  expect(submit.closest('form')).not.toHaveAttribute('method');
  fireEvent.click(submit);
  expect(revealed).not.toHaveBeenCalled();

  fireEvent.click(screen.getByRole('checkbox'));
  fireEvent.click(submit);

  await waitFor(() => expect(revealed).toHaveBeenCalledWith({confirm: true}));
});

test('joins a conversation through the typed command', async () => {
  const joined = vi.fn();
  server.use(http.post(
    new URL('/api/v1/conversations/community-strategy/participation', globalThis.location.origin).toString(),
    async ({request}) => {
      joined(await request.json());
      return HttpResponse.json({
        data: {
          pseudonym: 'quiet-otter',
          notifications: {email: false, talkPage: false},
          eligibilityStatus: 'not_required',
          links: {conversation: '/c/community-strategy', about: '/c/community-strategy/about'},
        },
      }, {status: 201});
    },
  ));
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={['/app/conversations/community-strategy/join']}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );

  expect(await screen.findByRole('heading', {name: 'Community strategy'})).toBeVisible();
  const joinButton = screen.getByRole('button', {name: 'Join consultation as quiet-otter →'});
  expect(joinButton.closest('form')).not.toHaveAttribute('action');
  expect(joinButton.closest('form')).not.toHaveAttribute('method');
  fireEvent.click(screen.getByRole('checkbox', {name: /I understand that my responses/}));
  fireEvent.click(joinButton);

  // The tick travels with the join: the server refuses a join without it (#341).
  await waitFor(() => expect(joined).toHaveBeenCalledWith({
    pseudonym: 'quiet-otter',
    notifyEmail: false,
    notifyTalkPage: false,
    consent: true,
  }));
});

test('votes in Explore through the wiki-polis API contract', async () => {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={['/app/conversations/community-strategy/explore']}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );

  fireEvent.click(await screen.findByRole('button', {name: 'Agree'}));

  // text-transform is visual only, so the DOM text -- and what a screen reader reads -- is
  // sentence case. Asserting on it keeps the casing a CSS concern, not a message one.
  expect(await screen.findByText('Your response: Agree', {selector: '#voted-label'})).toBeVisible();
  expect(screen.getByRole('button', {name: /Move on/})).toBeVisible();
});

test('records a pass and opens the legacy post-vote choices', async () => {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={['/app/conversations/community-strategy/explore']}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );

  fireEvent.click(await screen.findByRole('button', {name: 'Pass'}));

  expect(await screen.findByText('Your response: Pass', {selector: '#voted-label'})).toBeVisible();
  expect(screen.getByText('What now?')).toBeVisible();
  expect(screen.getByRole('button', {name: /Suggest different wording/})).toBeVisible();
});

test('renders intermediate results through the typed workspace contract', async () => {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={['/app/conversations/community-strategy/explore']}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );

  fireEvent.click(await screen.findByRole('tab', {name: 'Intermediate results'}));

  expect(await screen.findByRole('heading', {name: /Results.*12 participants/})).toBeVisible();
  expect(screen.getByText(/Small sample:/)).toBeVisible();
  expect(screen.getByText('Areas of broad consensus')).toBeVisible();
  expect(screen.getByText('1 opinion group found')).toBeVisible();
  expect(screen.getByText('82%')).toBeVisible();
});

test('completes informed voting through the legacy workspace panel', async () => {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={['/app/conversations/community-strategy/informed-voting']}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );

  expect(await screen.findByText(
    'Regional communities should share infrastructure funding.',
  )).toHaveClass('p6-statement-text');
  expect(screen.getByText(/reduces duplicated maintenance/)).toBeVisible();
  expect(screen.getByText(/independent budgets/)).toBeVisible();
  fireEvent.click(screen.getByRole('button', {name: 'Agree'}));

  expect(await screen.findByRole('heading', {
    name: "You've given your informed opinion.",
  })).toBeVisible();
  expect(screen.getByText(/responses are recorded under pseudonym/)).toHaveTextContent('quiet-otter');
  expect(screen.getByRole('alert')).toHaveTextContent('Agreed');
});

test('routes preliminary results through the legacy workspace tab', async () => {
  server.use(
    http.get(
      new URL('/api/v1/conversations/community-strategy/results', globalThis.location.origin).toString(),
      () => HttpResponse.json({data: {
        slug: 'community-strategy', title: 'Community strategy',
        publication: 'preliminary', resultsAvailable: true,
        openedAt: '2026-05-01T12:00:00Z', closedAt: null,
        context: {phase: 'Informed voting', status: 'provisional', method: 'Live comparison.'},
        participation: {initialRound: 25, informedRound: 22, matchedRounds: null},
        dataAvailability: {detailedCounts: true, opinionGroups: false},
        moderation: {excludedStatements: 0, excludedParticipants: 0},
        statements: [{
          featuredStatementId: 31,
          statement: 'Regional communities should share infrastructure funding.',
          initial: {counts: {agree: 12, pass: 3, disagree: 5, voters: 20}, percentages: {agree: 60, pass: 15, disagree: 25}},
          informed: {counts: {agree: 14, pass: 4, disagree: 2, voters: 20}, percentages: {agree: 70, pass: 20, disagree: 10}},
          agreementShift: 10,
          viewerChoice: 'agree',
        }],
        opinionGroups: [],
        viewer: {participating: true, pseudonym: 'quiet-otter', revealState: null},
        links: {self: '/api/v1/conversations/community-strategy/results', conversation: '/c/community-strategy', about: '/c/community-strategy/about'},
      }}),
    ),
    http.get(
      new URL('/api/v1/conversations/community-strategy/workspace', globalThis.location.origin).toString(),
      () => HttpResponse.json({data: {
        slug: 'community-strategy', title: 'Community strategy', space: 'real', status: 'open',
        descriptionHtml: null, outroHtml: null,
        viewer: {state: 'participant', pseudonym: 'quiet-otter'},
        spaceWarning: null, scheduledTransition: null,
        tabs: [
          {key: 'informed-voting', label: 'Informed vote', dataHref: '/api/v1/conversations/community-strategy/informed-voting'},
          {key: 'p6-results', label: 'Preliminary results', dataHref: '/api/v1/conversations/community-strategy/results'},
        ],
        defaultTab: 'informed-voting', reveal: null,
        statementContribution: {unlockAfter: 10, quota: 3, used: 0},
        capabilities: {participate: true, moderate: false},
        links: {self: '/api/v1/conversations/community-strategy/workspace', conversation: '/c/community-strategy', about: '/c/community-strategy/about', join: '/accept/community-strategy', informedVoting: '/api/v1/conversations/community-strategy/informed-voting', results: '/api/v1/conversations/community-strategy/results'},
      }}),
    ),
  );

  render(<QueryClientProvider client={createQueryClient()}><MemoryRouter initialEntries={['/app/conversations/community-strategy/results']}><App /></MemoryRouter></QueryClientProvider>);

  expect(await screen.findByRole('tab', {name: 'Preliminary results'})).toHaveAttribute('aria-selected', 'true');
  expect(screen.getByRole('table', {name: 'Preliminary informed opinion results by statement'})).toBeVisible();
  expect(screen.getByText('70.0% agree · 20.0% pass')).toBeVisible();
  // The recorded vote is past tense, and carries the modifier class the stylesheet colours.
  expect(screen.getByText('Agreed', {selector: '.p6-my-vote.p6-my-vote--agreed'})).toBeVisible();
});

test('stays usable when the message catalogue is unavailable', async () => {
  // The catalogue wraps every route. If a failure there could block, a rate-limited or
  // briefly-broken endpoint would take the whole product down rather than degrade it.
  server.use(
    http.get(
      new URL('/api/v1/i18n/:locale', globalThis.location.origin).toString(),
      () => new HttpResponse('rate limited', {status: 429}),
    ),
  );

  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={['/app/conversations']}><App /></MemoryRouter>
    </QueryClientProvider>,
  );

  // The lane still renders from its own contract; its copy degrades to visible keys, which
  // is ugly but usable -- the alternative is a page stuck on a loading state.
  expect(await screen.findByRole('heading', {name: 'home-section-needs-attention'}, {timeout: 5000})).toBeVisible();
  expect(screen.getByRole('link', {name: /Community strategy/})).toHaveAttribute('href', '/c/community-strategy');
  expect(screen.queryByText('Loading…')).not.toBeInTheDocument();
});

test('renders preliminary results from the message catalogue, not from source literals', async () => {
  // The decisive i18n test: serve deliberately different English for two keys. If the
  // component were still holding literals, these assertions could not pass.
  server.use(
    http.get(
      new URL('/api/v1/i18n/:locale', globalThis.location.origin).toString(),
      () => HttpResponse.json({
        ...testMessages,
        'conv-p6-table-aria': 'CATALOGUE TABLE LABEL',
        'conv-bar-label': '$1 in favour and $2 abstaining',
        'conv-participant-count': '$1 {{PLURAL:$1|voter|voters}}',
      }),
    ),
    http.get(
      new URL('/api/v1/conversations/community-strategy/results', globalThis.location.origin).toString(),
      () => HttpResponse.json({data: {
        slug: 'community-strategy', title: 'Community strategy',
        publication: 'preliminary', resultsAvailable: true,
        openedAt: '2026-05-01T12:00:00Z', closedAt: null,
        context: {phase: 'Informed voting', status: 'provisional', method: 'Live comparison.'},
        participation: {initialRound: 25, informedRound: 22, matchedRounds: null},
        dataAvailability: {detailedCounts: true, opinionGroups: false},
        moderation: {excludedStatements: 0, excludedParticipants: 0},
        statements: [{
          featuredStatementId: 31,
          statement: 'Regional communities should share infrastructure funding.',
          initial: {counts: {agree: 12, pass: 3, disagree: 5, voters: 20}, percentages: {agree: 60, pass: 15, disagree: 25}},
          informed: {counts: {agree: 14, pass: 4, disagree: 2, voters: 20}, percentages: {agree: 70, pass: 20, disagree: 10}},
          agreementShift: 10,
          viewerChoice: 'agree',
        }],
        opinionGroups: [],
        viewer: {participating: true, pseudonym: 'quiet-otter', revealState: null},
        links: {self: '/api/v1/conversations/community-strategy/results', conversation: '/c/community-strategy', about: '/c/community-strategy/about'},
      }}),
    ),
    http.get(
      new URL('/api/v1/conversations/community-strategy/workspace', globalThis.location.origin).toString(),
      () => HttpResponse.json({data: {
        slug: 'community-strategy', title: 'Community strategy', space: 'real', status: 'open',
        descriptionHtml: null, outroHtml: null,
        viewer: {state: 'participant', pseudonym: 'quiet-otter'},
        spaceWarning: null, scheduledTransition: null,
        tabs: [
          {key: 'informed-voting', label: 'Informed vote', dataHref: '/api/v1/conversations/community-strategy/informed-voting'},
          {key: 'p6-results', label: 'Preliminary results', dataHref: '/api/v1/conversations/community-strategy/results'},
        ],
        defaultTab: 'informed-voting', reveal: null,
        statementContribution: {unlockAfter: 10, quota: 3, used: 0},
        capabilities: {participate: true, moderate: false},
        links: {self: '/api/v1/conversations/community-strategy/workspace', conversation: '/c/community-strategy', about: '/c/community-strategy/about', join: '/accept/community-strategy', informedVoting: '/api/v1/conversations/community-strategy/informed-voting', results: '/api/v1/conversations/community-strategy/results'},
      }}),
    ),
  );

  render(<QueryClientProvider client={createQueryClient()}><MemoryRouter initialEntries={['/app/conversations/community-strategy/results']}><App /></MemoryRouter></QueryClientProvider>);

  expect(await screen.findByRole('tab', {name: 'Preliminary results'})).toBeVisible();
  // aria-label resolved through the catalogue
  expect(screen.getByRole('table', {name: 'CATALOGUE TABLE LABEL'})).toBeVisible();
  // $1/$2 substitution, and the original English is gone
  expect(screen.getByText('70.0% in favour and 20.0% abstaining')).toBeVisible();
  expect(screen.queryByText('70.0% agree · 20.0% pass')).not.toBeInTheDocument();
  // {{PLURAL:}} selects the plural form for 22 participants
  expect(screen.getByText('22 voters')).toBeVisible();
});

test('renders the legacy final report from the typed results contract', async () => {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={['/app/conversations/community-strategy/results']}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );

  expect(await screen.findByRole('heading', {name: 'Community strategy'})).toBeVisible();
  expect(screen.getByText('Final')).toBeVisible();
  expect(screen.getByText('Final · frozen at publication')).toBeVisible();
  expect(screen.getByText('+10.0%')).toBeVisible();
  expect(screen.getAllByTitle('Agree 60.0% · Disagree 25.0% · Pass 15.0%')).toHaveLength(3);
  expect(screen.getByTitle('Agree 70.0% · Disagree 10.0% · Pass 20.0%')).toBeVisible();
  expect(screen.getByRole('heading', {name: /^Opinion groups/})).toBeVisible();
  expect(screen.getByText(/recorded under pseudonym/)).toHaveTextContent('quiet-otter');
});

test('submits clearer wording through the idempotent statement contract', async () => {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={['/app/conversations/community-strategy/explore']}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );

  fireEvent.click(await screen.findByRole('button', {name: 'Pass'}));
  fireEvent.click(await screen.findByRole('button', {name: /Suggest different wording/}));

  const text = screen.getByRole('textbox', {name: 'Suggest different wording'});
  expect(text).toHaveValue('Our movement should invest more in shared technical infrastructure.');
  fireEvent.change(text, {target: {value: 'Invest together in shared technical infrastructure.'}});
  fireEvent.click(screen.getByRole('button', {name: 'Submit & next'}));

  expect(await screen.findByText('Proposed — heading to moderation')).toBeVisible();
});

test('a rewording identical to an existing statement says it is already in the consultation', async () => {
  server.use(http.post(
    new URL('/api/v1/conversations/community-strategy/statements', globalThis.location.origin).toString(),
    () => HttpResponse.json({
      error: {code: 'statement_exists', message: 'Server-side English that must not reach the page.'},
    }, {status: 409}),
  ));
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={['/app/conversations/community-strategy/explore']}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );

  fireEvent.click(await screen.findByRole('button', {name: 'Pass'}));
  fireEvent.click(await screen.findByRole('button', {name: /Suggest different wording/}));
  // The server refuses it as a duplicate; only the server can know what is already there.
  fireEvent.change(screen.getByRole('textbox', {name: 'Suggest different wording'}), {
    target: {value: 'Invest together in shared technical infrastructure.'},
  });
  fireEvent.click(screen.getByRole('button', {name: 'Submit & next'}));

  // Catches a duplicate refused upstream reaching the participant as "please try again":
  // resending the same wording can never succeed.
  const alert = await screen.findByText(
    'This statement already exists. Duplicates are not allowed.',
  );
  expect(alert).toHaveAttribute('role', 'alert');
  expect(screen.queryByText('Could not submit statement. Please try again.')).toBeNull();
  expect(document.body).not.toHaveTextContent('Server-side English that must not reach the page.');
});

test('submits a new statement from the Explore loop', async () => {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={['/app/conversations/community-strategy/explore']}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );

  fireEvent.click(await screen.findByRole('button', {name: 'Agree'}));
  fireEvent.click(await screen.findByRole('button', {name: /Propose a new statement/}));
  fireEvent.change(screen.getByRole('textbox', {name: 'Propose a new statement'}), {
    target: {value: 'Regional communities should share maintenance funding.'},
  });
  fireEvent.click(screen.getByRole('button', {name: 'Submit & next'}));

  expect(await screen.findByText('Proposed — heading to moderation')).toBeVisible();
});

test('freezes a statement attempt when the upstream outcome is unknown', async () => {
  server.use(http.post(
    new URL('/api/v1/conversations/community-strategy/statements', globalThis.location.origin).toString(),
    ({request}) => {
      expect(request.headers.get('Idempotency-Key')).toMatch(/^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$/);
      expect(request.headers.get('X-CSRFToken')).toBe('test-csrf-token');
      return HttpResponse.json({
        error: {
          code: 'command_outcome_unknown',
          message: 'The statement may have reached the voting service. Do not retry with a new key.',
        },
      }, {status: 502});
    },
  ));
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={['/app/conversations/community-strategy/explore']}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );

  fireEvent.click(await screen.findByRole('button', {name: 'Pass'}));
  fireEvent.click(await screen.findByRole('button', {name: /Propose a new statement/}));
  fireEvent.change(screen.getByRole('textbox', {name: 'Propose a new statement'}), {
    target: {value: 'A statement with an uncertain outcome.'},
  });
  fireEvent.click(screen.getByRole('button', {name: 'Submit & next'}));

  // The catalogue's warning, not the server's developer-facing message (rule 4). It has to
  // say not to start over, since a fresh composer means a fresh key and a possible duplicate.
  const alert = await screen.findByRole('alert');
  expect(alert).toHaveTextContent(testMessages['conv-err-outcome-unknown']!);
  expect(alert).not.toHaveTextContent('may have reached the voting service');
  expect(screen.getByRole('textbox', {name: 'Propose a new statement'})).toBeEnabled();
  expect(screen.getByRole('button', {name: 'Submit & next'})).toBeEnabled();
});

test('renders explicit argument contribution states and submits through the typed API', async () => {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={['/app/conversations/community-strategy/arguments']}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );

  expect(await screen.findByText(
    'Our movement should invest more in shared technical infrastructure.',
  )).toBeVisible();
  expect(screen.getByText('in favour · against ✓')).toBeVisible();
  expect(screen.getByText('Opens after step 1')).toBeVisible();

  fireEvent.click(screen.getByRole('button', {name: 'Add your argument in favour'}));
  const forArgument = screen.getByRole('textbox', {name: 'Your argument in favour · one sentence, one point'});
  fireEvent.change(forArgument, {
    target: {value: 'Shared maintenance reduces duplicated work.'},
  });
  fireEvent.click(within(forArgument.closest('form')!).getByRole('button', {name: 'Submit argument'}));

  expect(await screen.findByText('You added one argument in favour')).toBeVisible();
  expect(screen.getByRole('tab', {name: 'Explore'})).toBeVisible();
});

test('reports a statement through the legacy inline disclosure', async () => {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={['/app/conversations/community-strategy/explore']}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );

  const flagTrigger = await screen.findByLabelText('Flag this statement for moderator review');
  fireEvent.click(flagTrigger);
  fireEvent.change(screen.getByRole('combobox', {name: 'Reason'}), {
    target: {value: 'other'},
  });
  fireEvent.change(screen.getByRole('textbox', {name: 'Details'}), {
    target: {value: 'The wording could be interpreted in two incompatible ways.'},
  });
  fireEvent.click(screen.getByRole('button', {name: 'Send'}));

  expect(await screen.findByText('Thanks for reporting this. A moderator will look at it.')).toBeVisible();
});
