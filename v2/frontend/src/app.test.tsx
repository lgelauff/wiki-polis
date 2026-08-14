import {QueryClientProvider} from '@tanstack/react-query';
import {fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {http, HttpResponse} from 'msw';
import {MemoryRouter} from 'react-router-dom';
import {expect, test, vi} from 'vitest';

import {App} from './app';
import {createQueryClient} from './query-client';
import {server} from './test/server';

test('renders a conversation lane from the API contract', async () => {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={['/app/real']}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );

  expect(screen.getByRole('status')).toHaveTextContent('Loading conversations');
  expect(await screen.findByRole('heading', {name: 'Needs attention'})).toBeVisible();
  expect(await screen.findByRole('link', {name: /Community strategy.*continue/}))
    .toHaveAttribute('href', '/app/conversations/community-strategy/explore');
  expect(screen.getByRole('button', {name: 'Your conversations'})).toHaveAttribute('aria-pressed', 'true');
  fireEvent.click(screen.getByRole('button', {name: 'Browse'}));
  expect(screen.getByText('No consultations open to you right now.')).toBeVisible();
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
          links: {self: '/app/conversations/community-strategy/explore', about: '/c/community-strategy/about'},
        }],
        caughtUp: [], inactive: [], archived: [], available: [], moderating: [],
      },
    }}),
  ));
  render(<QueryClientProvider client={createQueryClient()}><MemoryRouter initialEntries={['/app/real']}><App /></MemoryRouter></QueryClientProvider>);

  const trigger = await screen.findByRole('button', {name: 'After Explore phase: topic and participant clustering'});
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

  expect(await screen.findByRole('heading', {name: 'Admin panel'})).toBeVisible();
  expect(screen.getByRole('link', {name: 'manage'})).toHaveAttribute('href', '/app/admin/conversations/7');
  expect(screen.getByText('Admin')).toHaveClass('header-mode-badge');
  expect(screen.getByRole('heading', {name: 'New conversation'})).toBeVisible();
  fireEvent.change(screen.getByLabelText('Wikimedia username'), {target: {value: 'Example editor'}});
  fireEvent.click(screen.getByRole('button', {name: 'Grant'}));
  expect(await screen.findByRole('status')).toHaveTextContent('Example editor granted site-wide administration');
  expect(screen.getAllByText('Example editor')).toHaveLength(2);
});

test('advances a conversation from the server-described lifecycle console', async () => {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={['/app/admin/conversations/7']}><App /></MemoryRouter>
    </QueryClientProvider>,
  );

  expect(await screen.findByRole('heading', {name: 'Community strategy'})).toBeVisible();
  expect(screen.getByText('not applicable')).toBeVisible();
  expect(screen.getByRole('heading', {name: 'Preparation → Explore'})).toBeVisible();
  const advance = screen.getByRole('button', {name: 'Move to Explore'});
  expect(advance).toBeDisabled();
  fireEvent.click(screen.getByRole('checkbox', {name: /statement set and introduction/}));
  expect(advance).toBeEnabled();
  fireEvent.click(advance);

  expect(await screen.findByRole('status')).toHaveTextContent('Moved to Explore');
  expect(screen.getByRole('heading', {name: 'No guided transition'})).toBeVisible();
  expect(screen.getByRole('link', {name: /Participants/})).toHaveAttribute(
    'href', '/app/admin/conversations/7/participants',
  );
  expect(screen.getByRole('link', {name: /Delete/})).toHaveAttribute(
    'href', '/app/admin/conversations/7/termination',
  );
});

test('schedules and cancels a lifecycle transition', async () => {
  render(<QueryClientProvider client={createQueryClient()}><MemoryRouter initialEntries={['/app/admin/conversations/7']}><App /></MemoryRouter></QueryClientProvider>);
  await screen.findByRole('heading', {name: 'Community strategy'});
  fireEvent.change(screen.getByLabelText(/Move to next phase at/), {target: {value: '2030-01-02T12:30'}});
  fireEvent.click(screen.getByRole('button', {name: 'Schedule'}));
  expect(await screen.findByRole('status')).toHaveTextContent('Schedule updated');
  expect(screen.getByRole('button', {name: 'Freeze'})).toBeVisible();
  fireEvent.click(screen.getByRole('button', {name: 'Cancel'}));
  expect(await screen.findByLabelText(/Move to next phase at/)).toHaveValue('');
});

test('repairs an advanced phase set through route-valid domain keys', async () => {
  vi.spyOn(globalThis, 'confirm').mockReturnValueOnce(true);
  render(<QueryClientProvider client={createQueryClient()}><MemoryRouter initialEntries={['/app/admin/conversations/7']}><App /></MemoryRouter></QueryClientProvider>);
  await screen.findByRole('heading', {name: 'Community strategy'});
  fireEvent.click(screen.getByText('Advanced phase repair'));
  fireEvent.click(screen.getByRole('checkbox', {name: /Arguments/}));
  fireEvent.click(screen.getByRole('checkbox', {name: /Informed vote/}));
  expect(screen.getByText(/Enabled but not initialized/)).toBeVisible();
  fireEvent.click(screen.getByRole('button', {name: 'Save advanced phases'}));
  expect(await screen.findByRole('status')).toHaveTextContent('Advanced phases saved');
  expect(screen.getByText('Advanced phase state')).toBeVisible();
  fireEvent.click(screen.getByRole('button', {name: 'Initialize informed voting'}));
  expect(await screen.findByRole('status')).toHaveTextContent('Informed-voting round initialized');
  expect(screen.getByText('Initialized')).toBeVisible();
});

test('archives and reopens without presenting publication as the outcome', async () => {
  vi.spyOn(globalThis, 'confirm').mockReturnValueOnce(true);
  render(<QueryClientProvider client={createQueryClient()}><MemoryRouter initialEntries={['/app/admin/conversations/7']}><App /></MemoryRouter></QueryClientProvider>);
  await screen.findByRole('heading', {name: 'Community strategy'});
  fireEvent.click(screen.getByRole('button', {name: 'Archive conversation'}));
  expect(await screen.findByRole('status')).toHaveTextContent('Conversation archived');
  expect(screen.getByText('archived')).toBeVisible();
  expect(screen.getByText('not applicable')).toBeVisible();
  fireEvent.click(screen.getByRole('button', {name: 'Reopen conversation'}));
  expect(await screen.findByRole('status')).toHaveTextContent('Conversation reopened');
});

test('edits settings while keeping legacy eligibility observable and read-only', async () => {
  render(<QueryClientProvider client={createQueryClient()}><MemoryRouter initialEntries={['/app/admin/conversations/7/settings']}><App /></MemoryRouter></QueryClientProvider>);
  expect(await screen.findByRole('heading', {name: 'Conversation settings'})).toBeVisible();
  expect(screen.getByText('Extended-confirmed editors')).toBeVisible();
  expect(screen.getByText(/Eligibility changes are unavailable/)).toBeVisible();
  fireEvent.change(screen.getByLabelText('Title'), {target: {value: 'Updated strategy'}});
  fireEvent.click(screen.getByRole('radio', {name: /Complex topic/}));
  fireEvent.click(screen.getByRole('button', {name: 'Save settings'}));
  expect(await screen.findByRole('status')).toHaveTextContent('Settings saved');
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
  expect(screen.getByRole('link', {name: 'Return to admin panel'})).toHaveAttribute('href', '/app/admin');
});

test('moderates statements and imports approved seeds through typed commands', async () => {
  render(<QueryClientProvider client={createQueryClient()}><MemoryRouter initialEntries={['/app/admin/conversations/7/statements']}><App /></MemoryRouter></QueryClientProvider>);

  expect(await screen.findByRole('heading', {name: 'Statements'})).toBeVisible();
  expect(screen.getByText('A participant proposal awaiting review.')).toBeVisible();
  expect(screen.getByRole('button', {name: /Require review/})).toBeDisabled();
  fireEvent.click(screen.getByRole('button', {name: /Auto-approve/}));
  expect(await screen.findByRole('status')).toHaveTextContent('Future participant statements will be approved automatically');
  expect(screen.getByRole('heading', {name: 'Pending review'}).parentElement).toHaveTextContent('1');
  fireEvent.click(screen.getByRole('button', {name: 'Approve'}));
  expect(await screen.findByRole('status')).toHaveTextContent('Statement #11 moved to approved');
  expect(screen.getByRole('heading', {name: 'Approved'}).parentElement).toHaveTextContent('2');

  fireEvent.change(screen.getByLabelText('Seed statements'), {
    target: {value: 'First seed\nSecond seed'},
  });
  expect(screen.getByText('2 / 20 statements')).toBeVisible();
  fireEvent.click(screen.getByRole('button', {name: 'Import approved seeds'}));
  expect(await screen.findByRole('status')).toHaveTextContent('2 imported');
});

test('manages featured statements with transparent vote metrics and argument review', async () => {
  render(<QueryClientProvider client={createQueryClient()}><MemoryRouter initialEntries={['/app/admin/conversations/7/featured']}><App /></MemoryRouter></QueryClientProvider>);

  expect(await screen.findByRole('heading', {name: 'Featured statements'})).toBeVisible();
  expect(screen.getByText('A candidate preserving another viewpoint.')).toBeVisible();
  expect(screen.getByText('Pass').parentElement).toHaveTextContent('2');
  expect(screen.getByText('Agreement').parentElement).toHaveTextContent('75%');
  expect(screen.queryByText(/divisiv/i)).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', {name: 'Select'}));
  expect(await screen.findByRole('status')).toHaveTextContent('Statement #13 selected');

  fireEvent.click(screen.getByRole('button', {name: 'Hide'}));
  expect(await screen.findByRole('status')).toHaveTextContent('Argument hidden');
});

test('manages participant access in the distinct admin workspace', async () => {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={['/app/admin/conversations/7/participants']}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );

  expect(await screen.findByRole('heading', {name: 'Community strategy'})).toBeVisible();
  expect(screen.getByRole('navigation', {name: 'Workspace'})).toHaveTextContent(
    'Admin workspace',
  );
  expect(screen.getByRole('rowheader', {name: /Example editor/})).toHaveTextContent(
    'quiet-otter',
  );
  expect(screen.getByText('8 / 12')).toBeVisible();
  fireEvent.change(screen.getByLabelText('Reason (optional)'), {
    target: {value: 'Repeated disruption'},
  });
  fireEvent.click(screen.getByRole('button', {name: 'Ban Example editor'}));

  expect(await screen.findByRole('button', {
    name: 'Unban Example editor',
  })).toBeVisible();
  expect(screen.getByText('Repeated disruption')).toBeVisible();
  expect(screen.getByRole('status')).toHaveTextContent('Access updated');
});

test('resolves a privacy-safe moderation item through the typed contract', async () => {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={['/app/admin/conversations/7/moderation']}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );

  expect(await screen.findByRole('heading', {name: 'Moderation queue'})).toBeVisible();
  expect(screen.getByText('A statement containing private information.')).toBeVisible();
  expect(screen.getByText('Privacy violation')).toBeVisible();
  expect(screen.getByText(/Reporter identities are intentionally excluded/)).toBeVisible();
  fireEvent.change(screen.getByLabelText('Resolution note (optional)'), {
    target: {value: 'Removed private detail'},
  });
  fireEvent.click(screen.getByRole('button', {name: 'Resolve Statement #12'}));

  expect(await screen.findByText('No open flags.')).toBeVisible();
  expect(screen.getByText('Removed private detail')).toBeVisible();
  expect(screen.getByRole('heading', {name: 'Resolved'}).parentElement).toHaveTextContent('1');
});

test('adds and removes invitations through convergent admin commands', async () => {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={['/app/admin/conversations/7/invitations']}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );

  expect(await screen.findByRole('heading', {name: 'Invites — Community strategy'})).toBeVisible();
  expect(screen.getByText('Existing editor')).toBeVisible();
  fireEvent.change(screen.getByLabelText('Wikimedia usernames (one per line)'), {
    target: {value: 'New editor\nNew editor'},
  });
  fireEvent.click(screen.getByRole('button', {name: 'Add'}));

  expect(await screen.findByText('New editor')).toBeVisible();
  expect(screen.getByRole('status')).toHaveTextContent('Invites: 1 added; 1 duplicate input.');
  const newEditorRow = screen.getByText('New editor').closest('tr');
  expect(newEditorRow).not.toBeNull();
  fireEvent.click(within(newEditorRow!).getByRole('button', {name: 'remove'}));
  expect(await screen.findByText('No invites yet.')).toBeVisible();
});

test('replaces a conversation role set from the admin workspace', async () => {
  render(<QueryClientProvider client={createQueryClient()}><MemoryRouter initialEntries={['/app/admin/conversations/7/roles']}><App /></MemoryRouter></QueryClientProvider>);
  expect(await screen.findByRole('heading', {name: 'Conversation roles'})).toBeVisible();
  expect(screen.getByRole('listitem')).toHaveTextContent('Example editor');
  fireEvent.change(screen.getByLabelText('Participant'), {target: {value: '23'}});
  fireEvent.click(screen.getByRole('checkbox', {name: 'organizer'}));
  fireEvent.click(screen.getByRole('button', {name: 'Save role set'}));
  expect(await screen.findByRole('status')).toHaveTextContent('Added: organizer');
  expect(screen.getByText('moderator + organizer')).toBeVisible();
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
          links: {self: '/api/v1/conversations/community-strategy/identity-reveal', conversation: '/c/community-strategy', about: '/app/conversations/community-strategy/about'},
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
    name: 'Permanently link quiet-otter to your wiki name?',
  })).toBeVisible();
  const submit = screen.getByRole('button', {name: 'Yes, link my identity'});
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
  fireEvent.click(screen.getByRole('checkbox', {name: /I understand my votes/}));
  fireEvent.click(screen.getByRole('button', {name: 'Join consultation as quiet-otter →'}));

  await waitFor(() => expect(joined).toHaveBeenCalledWith({
    pseudonym: 'quiet-otter',
    notifyEmail: false,
    notifyTalkPage: false,
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

  expect(await screen.findByText('AGREE', {selector: '#voted-label'})).toBeVisible();
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

  expect(await screen.findByText('PASS', {selector: '#voted-label'})).toBeVisible();
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
    name: "You've completed informed voting.",
  })).toBeVisible();
  expect(screen.getByText(/votes are recorded under pseudonym/)).toHaveTextContent('quiet-otter');
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
        links: {self: '/api/v1/conversations/community-strategy/results', conversation: '/c/community-strategy', about: '/app/conversations/community-strategy/about'},
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
        links: {self: '/api/v1/conversations/community-strategy/workspace', conversation: '/c/community-strategy', about: '/app/conversations/community-strategy/about', join: '/app/conversations/community-strategy/join', informedVoting: '/api/v1/conversations/community-strategy/informed-voting', results: '/api/v1/conversations/community-strategy/results'},
      }}),
    ),
  );

  render(<QueryClientProvider client={createQueryClient()}><MemoryRouter initialEntries={['/app/conversations/community-strategy/results']}><App /></MemoryRouter></QueryClientProvider>);

  expect(await screen.findByRole('tab', {name: 'Preliminary results'})).toHaveAttribute('aria-selected', 'true');
  expect(screen.getByRole('table', {name: 'Preliminary informed voting results by statement'})).toBeVisible();
  expect(screen.getByText('70.0% agree · 20.0% pass')).toBeVisible();
  expect(screen.getByText('Agree', {selector: '.p6-my-vote'})).toBeVisible();
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

  expect(await screen.findByText('PROPOSED — heading to moderation')).toBeVisible();
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

  expect(await screen.findByText('PROPOSED — heading to moderation')).toBeVisible();
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

  expect(await screen.findByRole('alert')).toHaveTextContent('may have reached the voting service');
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
  expect(screen.getByText('for · against ✓')).toBeVisible();
  expect(screen.getByText('Unlocks after step 1')).toBeVisible();

  fireEvent.click(screen.getByRole('button', {name: 'Add one for-argument'}));
  const forArgument = screen.getByRole('textbox', {name: 'Your for-argument · one sentence, one claim'});
  fireEvent.change(forArgument, {
    target: {value: 'Shared maintenance reduces duplicated work.'},
  });
  fireEvent.click(within(forArgument.closest('form')!).getByRole('button', {name: 'Submit argument'}));

  expect(await screen.findByText('You added one argument for')).toBeVisible();
  expect(screen.getByRole('tab', {name: 'Vote'})).toBeVisible();
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

  expect(await screen.findByText("Thanks for reporting — we'll take a look.")).toBeVisible();
});
