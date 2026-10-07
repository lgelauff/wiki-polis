import {Suspense} from 'react';
import {QueryClientProvider} from '@tanstack/react-query';
import {fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {http, HttpResponse} from 'msw';
import {MemoryRouter} from 'react-router-dom';
import {expect, test} from 'vitest';

import type {components} from '../../api/schema';
import {AdminModerationFlagsPage} from './admin-moderation-flags-page';
import {AdminModerationPeoplePage} from './admin-moderation-people-page';
import {AdminModerationQueuePage} from './admin-moderation-queue-page';
import {AdminFeaturedPage} from './admin-featured-page';
import {MessageProvider} from '../../i18n/messages';
import {createQueryClient} from '../../query-client';
import {server} from '../../test/server';

type Workspace = components['schemas']['AdminStatementWorkspace'];
type Statement = components['schemas']['AdminStatement'];

const STATEMENTS_URL = new URL(
  '/api/v1/admin/conversations/7/statements', globalThis.location.origin,
).toString();
const FLAGS_URL = new URL('/api/v1/admin/conversations/7/flags', globalThis.location.origin).toString();
const PEOPLE_URL = new URL(
  '/api/v1/admin/conversations/7/participants', globalThis.location.origin,
).toString();

function statement(id: number, overrides: Partial<Statement> = {}): Statement {
  return {
    id, text: `A statement waiting for a decision, number ${id}.`, moderation: 'pending',
    seed: false, featured: false, votes: {agree: 1, pass: 0, disagree: 0}, provenance: null,
    ...overrides,
  };
}

/** Three pending statements, one of them a correction of another, so the lineage sort has
 *  something to group. */
function workspace(rows: {pending?: Statement[]; approved?: Statement[]; hidden?: Statement[]}): Workspace {
  return {
    conversation: {id: 7, slug: 'community-strategy', title: 'Community strategy'},
    statements: {
      pending: rows.pending ?? [
        statement(11),
        statement(14, {text: 'A corrected version of statement 11.', provenance: {
          derivedFromId: 11, scores: [{model: 'sim', value: 1}],
        }}),
        statement(9),
      ],
      approved: rows.approved ?? [statement(12, {moderation: 'approved', featured: true})],
      hidden: rows.hidden ?? [],
    },
    moderationPolicy: {mode: 'moderate', newStatements: 'pending', available: true},
    dataAvailability: {statements: true},
    seeding: {allowed: true, lockReason: null, maxStatementsPerImport: 20, maxCharactersPerStatement: 280},
    capabilities: {moderate: true, seed: true},
    links: {self: STATEMENTS_URL, lifecycle: '/admin/conversations/7'},
  };
}

function serveWorkspace(rows: Parameters<typeof workspace>[0]) {
  server.use(http.get(STATEMENTS_URL, () => HttpResponse.json({data: workspace(rows)})));
}

/** Records every moderation PUT the page makes. */
function recordModeration() {
  const sent: {statementId: number; status: string}[] = [];
  server.use(http.put(
    new URL(
      '/api/v1/admin/conversations/7/statements/:statementId/moderation',
      globalThis.location.origin,
    ).toString(),
    async ({params, request}) => {
      const body = await request.json() as {status: string};
      sent.push({statementId: Number(params.statementId), status: body.status});
      return HttpResponse.json({data: {
        statementId: Number(params.statementId), status: body.status,
        links: {statements: STATEMENTS_URL},
      }});
    },
  ));
  return sent;
}

function renderModeration(element: React.ReactNode, path: string) {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={[path]}>
        <Suspense fallback={null}>
          <MessageProvider locale="en">{element}</MessageProvider>
        </Suspense>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const csrf = 'test-csrf-token';

function strip() {
  return screen.getByRole('navigation', {name: 'Moderation'});
}

/** The page's own content, without the console frame's sidebar and section list. */
function page() {
  return within(screen.getByRole('main'));
}

test('every page of the section carries the strip and marks itself', async () => {
  serveWorkspace({});
  renderModeration(<AdminModerationQueuePage conversationId={7} csrfToken={csrf} />,
    '/admin/conversations/7/moderation/queue');

  expect(await screen.findByRole('heading', {name: 'Queue', level: 1}, {timeout: 10_000}))
    .toBeVisible();
  expect(within(strip()).getAllByRole('link').map((link) => link.textContent))
    .toEqual(['Queue', 'Flags', 'Featured', 'People']);
  expect(within(strip()).getAllByRole('link').map((link) => link.getAttribute('href')))
    .toEqual([
      '/admin/conversations/7/moderation/queue',
      '/admin/conversations/7/moderation/flags',
      '/admin/conversations/7/moderation/featured',
      '/admin/conversations/7/moderation/people',
    ]);
  expect(within(strip()).getByRole('link', {name: 'Queue'}))
    .toHaveAttribute('aria-current', 'page');
  // The frame marks the section in the sidebar as well.
  expect(screen.getByRole('navigation', {name: 'Admin sections'})
    .querySelector('[aria-current="page"]')).toHaveTextContent('Moderation');
});

test('the queue shows the statements waiting, oldest first, by default', async () => {
  serveWorkspace({});
  renderModeration(<AdminModerationQueuePage conversationId={7} csrfToken={csrf} />,
    '/admin/conversations/7/moderation/queue');

  await screen.findByRole('heading', {name: 'Queue', level: 1}, {timeout: 10_000});
  const texts = page().getAllByRole('listitem')
    .map((row) => row.querySelector('.admin-row__text')?.textContent);
  expect(texts[0]).toContain('number 9');
  expect(texts[1]).toContain('number 11');
  // "Based on" is the other sort, not the default.
  expect(screen.getByRole('combobox', {name: 'Sort'})).toHaveValue('oldest');
});

test('a derived statement names its source, and "Based on" puts it under it', async () => {
  serveWorkspace({});
  renderModeration(<AdminModerationQueuePage conversationId={7} csrfToken={csrf} />,
    '/admin/conversations/7/moderation/queue');

  await screen.findByRole('heading', {name: 'Queue', level: 1}, {timeout: 10_000});
  const link = screen.getByRole('link', {name: '↳ #11'});
  expect(link).toHaveAttribute('href', '/admin/conversations/7/statements');
  expect(link.closest('.admin-row__text')).toHaveTextContent('A corrected version');

  fireEvent.change(screen.getByRole('combobox', {name: 'Sort'}), {target: {value: 'based-on'}});
  const texts = page().getAllByRole('listitem')
    .map((row) => row.querySelector('.admin-row__text')?.textContent ?? '');
  // Source, then its correction, then the statement with no lineage at all.
  expect(texts[0]).toContain('number 9');
  expect(texts[1]).toContain('number 11');
  expect(texts[2]).toContain('A corrected version');
});

test('approve and hide are two glyphs that name the statement they act on', async () => {
  serveWorkspace({});
  const sent = recordModeration();
  renderModeration(<AdminModerationQueuePage conversationId={7} csrfToken={csrf} />,
    '/admin/conversations/7/moderation/queue');

  await screen.findByRole('heading', {name: 'Queue', level: 1}, {timeout: 10_000});
  const approve = screen.getByRole('button', {name: 'Approve statement 11'});
  const hide = screen.getByRole('button', {name: 'Hide statement 11'});
  // Icon-only: the glyph is hidden from the accessibility tree and the words are the name.
  expect(approve.querySelector('[aria-hidden="true"]')).toHaveTextContent('✓');
  expect(approve).toHaveAttribute('title', 'Approve statement 11');
  expect(hide.querySelector('[aria-hidden="true"]')).toHaveTextContent('✕');
  // No other button claims this statement, so nothing is ambiguous by position alone.
  expect(screen.getAllByRole('button', {name: /statement 11/})).toHaveLength(2);

  fireEvent.click(approve);
  await waitFor(() => expect(sent).toHaveLength(1));
  expect(sent[0]).toEqual({statementId: 11, status: 'approved'});
  // The row leaves the pending list without a refetch: the receipt named its new state.
  await waitFor(() => expect(screen.queryByRole('button', {name: 'Approve statement 11'})).toBeNull());
});

test('the three-position switch shows which statements are on screen', async () => {
  serveWorkspace({});
  renderModeration(<AdminModerationQueuePage conversationId={7} csrfToken={csrf} />,
    '/admin/conversations/7/moderation/queue');

  await screen.findByRole('heading', {name: 'Queue', level: 1}, {timeout: 10_000});
  const positions = ['Show unmoderated', 'Show approved', 'Show hidden'];
  for (const name of positions) {
    const button = screen.getByRole('button', {name});
    expect(button).toHaveAttribute('title', name);
    expect(button.querySelector('[aria-hidden="true"]')).not.toBeEmptyDOMElement();
  }
  // Unmoderated is the default: what is waiting is what a moderator came for.
  expect(screen.getByRole('button', {name: 'Show unmoderated'}))
    .toHaveAttribute('aria-pressed', 'true');
  expect(screen.getByRole('button', {name: 'Show approved'}))
    .toHaveAttribute('aria-pressed', 'false');

  fireEvent.click(screen.getByRole('button', {name: 'Show approved'}));
  expect(screen.getByText('A statement waiting for a decision, number 12.')).toBeVisible();
  expect(screen.queryByText('number 11')).toBeNull();
});

test('a queue with nothing in it says so in words', async () => {
  serveWorkspace({pending: []});
  renderModeration(<AdminModerationQueuePage conversationId={7} csrfToken={csrf} />,
    '/admin/conversations/7/moderation/queue');

  expect(await screen.findByText('Nothing to moderate.', undefined, {timeout: 10_000}))
    .toBeVisible();
  expect(page().queryByRole('list')).toBeNull();
});

test('the queue names the one thing it cannot show yet', async () => {
  serveWorkspace({});
  renderModeration(<AdminModerationQueuePage conversationId={7} csrfToken={csrf} />,
    '/admin/conversations/7/moderation/queue');

  await screen.findByRole('heading', {name: 'Queue', level: 1}, {timeout: 10_000});
  const lines = page().getAllByText(/^Also coming:/);
  expect(lines).toHaveLength(1);
  expect(lines[0]).toHaveTextContent(
    'Also coming: how long each statement has been waiting — not available yet (#473)',
  );
  expect(lines[0]).toHaveAttribute('lang', 'en');
  expect(lines[0]?.closest('a, button')).toBeNull();
});

test('flags are one row each, with the reason as a suffix and two ways to close one', async () => {
  server.use(http.get(FLAGS_URL, () => HttpResponse.json({data: {
    conversation: {id: 7, slug: 'community-strategy', title: 'Community strategy'},
    open: [{
      id: 41, status: 'open', category: 'privacy', categoryLabel: 'Privacy violation',
      detail: 'Includes a real name.', flaggedAt: '2026-08-13T09:30:00Z',
      target: {type: 'statement', id: 12, label: 'Statement #12', text: 'A statement with a real name in it.', reviewHref: '/admin/conversations/7/statements'},
      resolution: null,
    }],
    resolved: [],
    dataAvailability: {statementText: true},
    capabilities: {resolveFlags: true},
    links: {self: FLAGS_URL, conversation: '/admin/conversations/7'},
  }})));
  const sent: {flagId: number; body: unknown}[] = [];
  server.use(http.put(
    new URL('/api/v1/admin/conversations/7/flags/:flagId/resolution', globalThis.location.origin)
      .toString(),
    async ({params, request}) => {
      const body = await request.json() as unknown;
      sent.push({flagId: Number(params.flagId), body});
      return HttpResponse.json({data: {
        flagId: Number(params.flagId), status: 'resolved', changed: true,
        resolution: {resolvedAt: '2026-08-13T10:00:00Z', note: null},
        links: {flags: FLAGS_URL},
      }});
    },
  ));
  renderModeration(<AdminModerationFlagsPage conversationId={7} csrfToken={csrf} />,
    '/admin/conversations/7/moderation/flags');

  await screen.findByRole('heading', {name: 'Flags', level: 1}, {timeout: 10_000});
  const row = page().getByRole('listitem');
  expect(row).toHaveTextContent('A statement with a real name in it.');
  // The reason qualifies the row; it is not a field of its own and it is muted.
  const suffix = row.querySelector('.admin-row__suffix')!;
  expect(suffix).toHaveTextContent('Privacy violation · Includes a real name.');
  expect(suffix).toHaveClass('admin-row__suffix');
  // Text buttons, not a check: a check beside a flag reads as confirming it.
  expect(within(row).getByRole('button', {name: 'Keep'})).toBeVisible();
  expect(within(row).getByRole('button', {name: 'Remove'})).toBeVisible();

  fireEvent.click(within(row).getByRole('button', {name: 'Keep'}));
  await waitFor(() => expect(sent).toHaveLength(1));
  expect(sent[0]).toEqual({flagId: 41, body: {resolved: true, note: null}});
  await waitFor(() => expect(page().queryByRole('listitem')).toBeNull());
  expect(screen.getByText('No open flags.')).toBeVisible();
});

test('the flags page switches between statements and arguments when the data has both', async () => {
  server.use(http.get(FLAGS_URL, () => HttpResponse.json({data: {
    conversation: {id: 7, slug: 'community-strategy', title: 'Community strategy'},
    open: [
      {
        id: 41, status: 'open', category: 'privacy', categoryLabel: 'Privacy violation',
        detail: null, flaggedAt: '2026-08-13T09:30:00Z',
        target: {type: 'statement', id: 12, label: 'Statement #12', text: 'A flagged statement.', reviewHref: '/admin/conversations/7/statements'},
        resolution: null,
      },
      {
        id: 42, status: 'open', category: 'off_topic', categoryLabel: 'Off topic',
        detail: null, flaggedAt: '2026-08-13T09:40:00Z',
        target: {type: 'argument', id: 71, label: 'Argument #71', text: 'A flagged argument.', reviewHref: '/admin/conversations/7/featured'},
        resolution: null,
      },
    ],
    resolved: [],
    dataAvailability: {statementText: true},
    capabilities: {resolveFlags: true},
    links: {self: FLAGS_URL, conversation: '/admin/conversations/7'},
  }})));
  renderModeration(<AdminModerationFlagsPage conversationId={7} csrfToken={csrf} />,
    '/admin/conversations/7/moderation/flags');

  await screen.findByRole('heading', {name: 'Flags', level: 1}, {timeout: 10_000});
  expect(screen.getByText('A flagged statement.')).toBeVisible();
  expect(screen.queryByText('A flagged argument.')).toBeNull();
  fireEvent.click(screen.getByRole('button', {name: 'Arguments'}));
  expect(screen.getByText('A flagged argument.')).toBeVisible();
  expect(screen.queryByText('A flagged statement.')).toBeNull();
});

test('people are one row each, with their state and the control that changes it', async () => {
  const sent: {participantId: number; body: unknown}[] = [];
  server.use(http.put(
    new URL(
      '/api/v1/admin/conversations/7/participants/:participantId/access',
      globalThis.location.origin,
    ).toString(),
    async ({params, request}) => {
      const body = await request.json() as unknown;
      sent.push({participantId: Number(params.participantId), body});
      return HttpResponse.json({data: {
        participantId: Number(params.participantId), banned: true, changed: true,
        changedAt: '2026-08-14T10:00:00Z', summary: null,
        links: {participants: PEOPLE_URL},
      }});
    },
  ));
  renderModeration(<AdminModerationPeoplePage conversationId={7} csrfToken={csrf} />,
    '/admin/conversations/7/moderation/people');

  await screen.findByRole('heading', {name: 'People', level: 1}, {timeout: 10_000});
  const row = page().getByRole('listitem');
  expect(row).toHaveTextContent('quiet-otter');
  expect(row).toHaveTextContent('Active');
  expect(row).toHaveTextContent('2026-08-13');

  fireEvent.click(within(row).getByRole('button', {name: 'ban'}));
  await waitFor(() => expect(sent).toHaveLength(1));
  expect(sent[0]).toEqual({participantId: 23, body: {banned: true, summary: null}});
  // The row says the new state in place; there is no toast to read past.
  await waitFor(() => expect(page().getByRole('listitem')).toHaveTextContent('Banned'));
  expect(screen.getByRole('button', {name: 'unban'})).toBeVisible();
});

test('Featured is today’s page under the strip, arguments and all', async () => {
  renderModeration(<AdminFeaturedPage conversationId={7} csrfToken={csrf} />,
    '/admin/conversations/7/moderation/featured');

  await screen.findByRole('heading', {name: 'Featured', level: 1}, {timeout: 10_000});
  expect(within(strip()).getByRole('link', {name: 'Featured'}))
    .toHaveAttribute('aria-current', 'page');
  expect(screen.getByRole('heading', {name: 'Confirmed (1)'})).toBeVisible();
  // Argument moderation is served by this endpoint, so it stays here (#473).
  expect(screen.getByText('Arguments')).toBeVisible();
  expect(screen.getByRole('button', {name: 'hide'})).toBeVisible();
});