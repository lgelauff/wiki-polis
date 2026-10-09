import {Suspense} from 'react';
import {QueryClientProvider, type QueryClient} from '@tanstack/react-query';
import {act, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {http, HttpResponse} from 'msw';
import {MemoryRouter} from 'react-router-dom';
import {expect, test, vi} from 'vitest';

import type {components} from '../../api/schema';
import {AdminModerationFlagsPage, FLAG_SETTLE_MS} from './admin-moderation-flags-page';
import {AdminModerationPeoplePage} from './admin-moderation-people-page';
import {AdminModerationQueuePage} from './admin-moderation-queue-page';
import {AdminFeaturedPage} from './admin-featured-page';
import {MessageProvider} from '../../i18n/messages';
import {createQueryClient} from '../../query-client';
import {testMessages} from '../../test/handlers';
import {server} from '../../test/server';

/** Moderation rows (pr-check #523 items): the statement number on the Queue, a result
 *  said for every row action, an empty line per position, controls whose names tell one
 *  row from the next, the sidebar's flag count refreshed, and People by pseudonym only.
 *  Visible words come from the catalogue, so a rewording does not break what is pinned. */

type Statement = components['schemas']['AdminStatement'];
type Flag = components['schemas']['AdminContentFlag'];

const url = (path: string) => new URL(path, globalThis.location.origin).toString();
const STATEMENTS_URL = url('/api/v1/admin/conversations/7/statements');
const FLAGS_URL = url('/api/v1/admin/conversations/7/flags');
const PEOPLE_URL = url('/api/v1/admin/conversations/7/participants');
const m = (key: string) => testMessages[key]!;

function statement(id: number, overrides: Partial<Statement> = {}): Statement {
  return {
    id, text: `Statement text ${id}.`, moderation: 'pending', seed: false, featured: false,
    votes: {agree: 1, pass: 0, disagree: 0}, provenance: null, ...overrides,
  };
}

function serveWorkspace(lists: {pending?: Statement[]; approved?: Statement[]; hidden?: Statement[]}) {
  server.use(http.get(STATEMENTS_URL, () => HttpResponse.json({data: {
    conversation: {id: 7, slug: 'community-strategy', title: 'Community strategy'},
    statements: {pending: lists.pending ?? [], approved: lists.approved ?? [], hidden: lists.hidden ?? []},
    moderationPolicy: {mode: 'moderate', newStatements: 'pending', available: true},
    dataAvailability: {statements: true},
    seeding: {allowed: true, lockReason: null, maxStatementsPerImport: 20, maxCharactersPerStatement: 280},
    capabilities: {moderate: true, seed: true},
    links: {self: STATEMENTS_URL, lifecycle: '/admin/conversations/7'},
  }})));
  server.use(http.put(url('/api/v1/admin/conversations/7/statements/:statementId/moderation'),
    async ({params, request}) => {
      const body = await request.json() as {status: string};
      return HttpResponse.json({data: {
        statementId: Number(params.statementId), status: body.status, links: {statements: STATEMENTS_URL},
      }});
    }));
}

function renderPage(element: React.ReactNode, path: string, client: QueryClient = createQueryClient()) {
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Suspense fallback={null}>
          <MessageProvider locale="en">{element}</MessageProvider>
        </Suspense>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const polite = () => document.querySelector('[aria-live="polite"]');
const main = () => within(screen.getByRole('main'));

test('a Queue row shows its statement number as a muted suffix', async () => {
  serveWorkspace({pending: [statement(12)]});
  renderPage(<AdminModerationQueuePage conversationId={7} csrfToken="t" />,
    '/admin/conversations/7/moderation/queue');

  const row = (await screen.findByText('Statement text 12.', {}, {timeout: 10_000})).closest('li')!;
  const number = within(row).getByText('#12', {exact: false});
  expect(number).toHaveClass('admin-row__suffix');
  expect(number.textContent?.trim()).toBe('#12');
});

test('approving and hiding on the Queue says which statement went where, every time', async () => {
  serveWorkspace({pending: [statement(11), statement(12)]});
  renderPage(<AdminModerationQueuePage conversationId={7} csrfToken="t" />,
    '/admin/conversations/7/moderation/queue');

  const approve = await screen.findByRole('button',
    {name: m('admin-moderation-approve-statement').replace('$1', '11')}, {timeout: 10_000});
  approve.focus();
  fireEvent.click(approve);
  await waitFor(() => expect(polite()).toHaveTextContent(
    m('admin-moderation-statement-approved').replace('$1', '11'),
  ));
  // Focus stays on the list: the next row's first action.
  await waitFor(() => expect(screen.getByRole('button',
    {name: m('admin-moderation-approve-statement').replace('$1', '12')})).toHaveFocus());

  fireEvent.click(screen.getByRole('button', {name: m('admin-moderation-hide-statement').replace('$1', '12')}));
  await waitFor(() => expect(polite()).toHaveTextContent(
    m('admin-moderation-statement-hidden').replace('$1', '12'),
  ));
});

test.each([
  ['approved', 'stmts-approved-empty'],
  ['hidden', 'stmts-hidden-empty'],
  ['unmoderated', 'admin-moderation-queue-empty'],
] as const)('the Queue\'s %s position, when empty, says so in its own words', async (position, key) => {
  serveWorkspace({});
  renderPage(<AdminModerationQueuePage conversationId={7} csrfToken="t" />,
    '/admin/conversations/7/moderation/queue');

  const label = m(`admin-moderation-state-${position}`);
  fireEvent.click(await screen.findByRole('button', {name: label}, {timeout: 10_000}));
  expect(main().getByText(m(key))).toBeVisible();
  const others = ['stmts-approved-empty', 'stmts-hidden-empty', 'admin-moderation-queue-empty']
    .filter((other) => other !== key);
  for (const other of others) expect(main().queryByText(m(other))).toBeNull();
});

function flag(id: number, text: string): Flag {
  return {
    id, status: 'open', category: 'off_topic', categoryLabel: 'Off topic', detail: null,
    flaggedAt: '2026-08-13T09:30:00Z',
    target: {type: 'statement', id, label: `Statement #${id}`, text, reviewHref: '/admin/conversations/7/statements'},
    resolution: null,
  };
}

function serveFlags(open: Flag[]) {
  server.use(http.get(FLAGS_URL, () => HttpResponse.json({data: {
    conversation: {id: 7, slug: 'community-strategy', title: 'Community strategy'},
    open, resolved: [],
    dataAvailability: {statementText: true},
    capabilities: {resolveFlags: true},
    links: {self: FLAGS_URL, conversation: '/admin/conversations/7'},
  }})));
  server.use(http.put(url('/api/v1/admin/conversations/7/flags/:flagId/resolution'), ({params}) => (
    HttpResponse.json({data: {
      flagId: Number(params.flagId), status: 'resolved', changed: true,
      resolution: {resolvedAt: '2026-08-13T10:00:00Z', note: null}, links: {flags: FLAGS_URL},
    }})
  )));
}

test('each flag row\'s note and button are named for that row', async () => {
  serveFlags([flag(41, 'The first flagged text.'), flag(42, 'The second flagged text.')]);
  renderPage(<AdminModerationFlagsPage conversationId={7} csrfToken="t" />,
    '/admin/conversations/7/moderation/flags');

  await screen.findByText('The first flagged text.', {}, {timeout: 10_000});
  const handle = m('admin-moderation-flag-handle');
  const buttons = main().getAllByRole('button', {name: new RegExp(`^${handle}`)});
  expect(buttons.map((button) => button.textContent)).toEqual([
    `${handle} — The first flagged text.`, `${handle} — The second flagged text.`,
  ]);
  const notes = main().getAllByRole('textbox');
  expect(new Set(notes.map((note) => note.closest('label')?.textContent)).size).toBe(2);
});

test('handling a flag reads the frame again, whose sidebar counts the open flags', async () => {
  serveFlags([flag(41, 'The first flagged text.')]);
  const client = createQueryClient();
  const invalidate = vi.spyOn(client, 'invalidateQueries');
  renderPage(<AdminModerationFlagsPage conversationId={7} csrfToken="t" />,
    '/admin/conversations/7/moderation/flags', client);

  fireEvent.click(await screen.findByRole('button',
    {name: new RegExp(`^${m('admin-moderation-flag-handle')}`)}, {timeout: 10_000}));
  await waitFor(() => expect(invalidate).toHaveBeenCalledWith(
    expect.objectContaining({queryKey: ['admin-lifecycle', 7]}),
  ));
});

test('a handled flag stays in place as "Handled ✓" before it moves, so the next button does not slide under the pointer', async () => {
  // Owner, 2026-10-09: removing the row at once moved the next flag's "Mark as handled" into
  // the clicked one's place, and a double click handled two flags.
  serveFlags([flag(41, 'The first flagged text.'), flag(42, 'The second flagged text.')]);
  renderPage(<AdminModerationFlagsPage conversationId={7} csrfToken="t" />,
    '/admin/conversations/7/moderation/flags');
  const handle = m('admin-moderation-flag-handle');
  const first = await screen.findByRole('button', {name: `${handle} — The first flagged text.`}, {timeout: 10_000});
  const second = screen.getByRole('button', {name: `${handle} — The second flagged text.`});
  const openRows = () => [...document.querySelectorAll('[data-row-id]')].map((row) => row.getAttribute('data-row-id'));

  vi.useFakeTimers({shouldAdvanceTime: true});
  try {
    first.focus();
    fireEvent.click(first);
    const settledRow = document.querySelector('[data-row-id="41"]') as HTMLElement;
    await waitFor(() => expect(within(settledRow).getByText(m('admin-moderation-flags-handled-heading'), {exact: false})).toBeVisible());
    await waitFor(() => expect(polite()).toHaveTextContent(m('admin-moderation-flag-marked-handled')));
    // Right after the click: the clicked row is where it was, without controls, and the next
    // row's button is still in its own row, not in the clicked row's place.
    expect(openRows()).toEqual(['41', '42']);
    expect(within(settledRow).queryByRole('button')).toBeNull();
    expect(settledRow).toHaveTextContent(/Handled ✓$/);
    expect(second.closest('[data-row-id]')).toHaveAttribute('data-row-id', '42');
    expect(screen.queryByRole('heading', {name: m('admin-moderation-flags-handled-heading'), level: 2})).toBeNull();
    // Focus is not dropped: it is on the line that replaced the controls.
    expect(document.activeElement).toBe(within(settledRow).getByText(m('admin-moderation-flags-handled-heading'), {exact: false}));

    act(() => { vi.advanceTimersByTime(FLAG_SETTLE_MS); });

    // After the delay: the row is in the Handled list, and focus is on the next flag's button.
    await waitFor(() => expect(openRows()).toEqual(['42']));
    const handledList = screen.getByRole('heading', {name: m('admin-moderation-flags-handled-heading'), level: 2})
      .nextElementSibling as HTMLElement;
    expect(handledList).toHaveTextContent('The first flagged text.');
    await waitFor(() => expect(screen.getByRole('button', {name: `${handle} — The second flagged text.`})).toHaveFocus());
  } finally {
    vi.useRealTimers();
  }
});

test('People shows each person by pseudonym, never by username, and names each row\'s controls', async () => {
  const person = (participantId: number, username: string, pseudonym: string) => ({
    participantId, username, pseudonym, statementProgress: null,
    arguments: {submitted: 0, prioritized: 0}, lastEngagementAt: null,
    access: {banned: false, changedAt: null, summary: null},
  });
  server.use(http.get(PEOPLE_URL, () => HttpResponse.json({data: {
    conversation: {id: 7, slug: 'community-strategy', title: 'Community strategy'},
    participants: [person(31, 'First editor', 'blue-heron'), person(32, 'Second editor', 'grey-badger')],
    dataAvailability: {statementProgress: true},
    capabilities: {setParticipantAccess: true},
    links: {self: PEOPLE_URL, conversation: '/admin/conversations/7'},
  }})));
  renderPage(<AdminModerationPeoplePage conversationId={7} csrfToken="t" />,
    '/admin/conversations/7/moderation/people');

  const block = m('participants-btn-ban');
  await screen.findByRole('button', {name: `${block} — blue-heron`}, {timeout: 10_000});
  expect(main().getAllByRole('listitem')[0]).toHaveTextContent(/^blue-heron/);
  // Moderators know people by the name they take part under (owner decision, 2026-10-08).
  expect(screen.getByRole('main')).not.toHaveTextContent('First editor');
  expect(screen.getByRole('main')).not.toHaveTextContent('Second editor');
  expect(main().getByRole('button', {name: `${block} — blue-heron`})).toBeVisible();
  expect(main().getByRole('button', {name: `${block} — grey-badger`})).toBeVisible();
});

test('Featured\'s row buttons are named for their row', async () => {
  const argument = (id: number, body: string) => ({
    id, side: 'pro' as const, body, proposerPseudonym: 'quiet-otter', hidden: false, createdAt: null,
  });
  server.use(http.get(url('/api/v1/admin/conversations/7/featured-statements'), () => HttpResponse.json({data: {
    conversation: {id: 7, slug: 'community-strategy', title: 'Community strategy'},
    selected: [
      {featuredId: 61, statementId: 12, text: 'First featured.', systemSuggested: true, provenance: null,
        arguments: [argument(71, 'First argument.'), argument(72, 'Second argument.')]},
      {featuredId: 62, statementId: 13, text: 'Second featured.', systemSuggested: true, provenance: null, arguments: []},
    ],
    candidates: [
      {statementId: 14, text: 'First candidate.', seed: false, votes: {agree: 1, pass: 0, disagree: 0, total: 1, agreementPercent: 100}, provenance: null},
      {statementId: 15, text: 'Second candidate.', seed: false, votes: {agree: 1, pass: 0, disagree: 0, total: 1, agreementPercent: 100}, provenance: null},
    ],
    dataAvailability: {candidates: true}, phase: {argumentMappingActive: false, informedVotingLive: false},
    guidance: {recommendedCount: 15, note: ''}, capabilities: {manage: true},
    links: {self: url('/api/v1/admin/conversations/7/featured-statements'), lifecycle: '/admin/conversations/7'},
  }})));
  renderPage(<AdminFeaturedPage conversationId={7} csrfToken="t" />, '/admin/conversations/7/moderation/featured');

  await screen.findByText('First featured.', {exact: false}, {timeout: 10_000});
  const names = (word: string) => main().getAllByRole('button', {name: new RegExp(`^${word}`)})
    .map((button) => button.textContent);
  expect(names(m('admin-btn-remove'))).toEqual([`${m('admin-btn-remove')} — #12`, `${m('admin-btn-remove')} — #13`]);
  expect(names(m('featured-btn-confirm'))).toEqual([`${m('featured-btn-confirm')} — #14`, `${m('featured-btn-confirm')} — #15`]);
  expect(names(m('featured-arg-hide'))).toEqual([
    `${m('featured-arg-hide')} — First argument.`, `${m('featured-arg-hide')} — Second argument.`,
  ]);
  expect(new Set(names(m('featured-arg-delete'))).size).toBe(2);
});
