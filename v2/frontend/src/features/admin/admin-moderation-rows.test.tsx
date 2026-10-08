import {Suspense} from 'react';
import {QueryClientProvider, type QueryClient} from '@tanstack/react-query';
import {fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {http, HttpResponse} from 'msw';
import {MemoryRouter} from 'react-router-dom';
import {expect, test, vi} from 'vitest';

import type {components} from '../../api/schema';
import {AdminModerationFlagsPage} from './admin-moderation-flags-page';
import {AdminModerationPeoplePage} from './admin-moderation-people-page';
import {AdminModerationQueuePage} from './admin-moderation-queue-page';
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
