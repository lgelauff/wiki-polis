import {Suspense} from 'react';
import {QueryClientProvider} from '@tanstack/react-query';
import {fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {http, HttpResponse} from 'msw';
import {MemoryRouter} from 'react-router-dom';
import {expect, test} from 'vitest';

import type {components} from '../../api/schema';
import {AdminParticipantsPage} from './admin-participants-page';
import {AdminStatementsPage} from './admin-statements-page';
import {MessageProvider} from '../../i18n/messages';
import {createQueryClient} from '../../query-client';
import {testMessages} from '../../test/handlers';
import {server} from '../../test/server';

/** Content rows (pr-check #524 items): the statement number on every row, a moderation
 *  action that keeps keyboard focus on the list and says what it did, an import that does
 *  not call a failure "skipped" nor throw the failed lines away, and Participants by
 *  pseudonym for a viewer the roster sends no username. */

type Statement = components['schemas']['AdminStatement'];

const url = (path: string) => new URL(path, globalThis.location.origin).toString();
const STATEMENTS_URL = url('/api/v1/admin/conversations/7/statements');
const PEOPLE_URL = url('/api/v1/admin/conversations/7/participants');
const m = (key: string, ...params: (string | number)[]) => params.reduce<string>(
  (text, value, index) => text.replace(`$${index + 1}`, String(value)), testMessages[key]!,
);

function statement(id: number, moderation: Statement['moderation']): Statement {
  return {
    id, text: `Statement text ${id}.`, moderation, seed: false, meta: false, hasResponses: false, featured: false,
    votes: {agree: 1, pass: 0, disagree: 0}, provenance: null,
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

function renderPage(element: React.ReactNode, path: string) {
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

const polite = () => document.querySelector('[aria-live="polite"]');
const rowOf = (id: number) => document.querySelector<HTMLElement>(`[data-row-id="${id}"]`)!;

test('a Statements row shows its number as a muted suffix', async () => {
  serveWorkspace({approved: [statement(12, 'approved')]});
  renderPage(<AdminStatementsPage conversationId={7} csrfToken="t" />, '/admin/conversations/7/content/statements');

  await screen.findByText('Statement text 12.', {}, {timeout: 10_000});
  const number = within(rowOf(12)).getByText('#12', {exact: false});
  expect(number).toHaveClass('admin-row__suffix');
  expect(number.textContent?.trim()).toBe('#12');
});

test('a moderation action keeps focus on the list and says what it did', async () => {
  serveWorkspace({pending: [statement(11, 'pending'), statement(12, 'pending')]});
  renderPage(<AdminStatementsPage conversationId={7} csrfToken="t" />, '/admin/conversations/7/content/statements');

  fireEvent.click(await screen.findByRole('button',
    {name: new RegExp(m('admin-moderation-state-unmoderated'))}, {timeout: 10_000}));
  const approve = within(rowOf(11)).getByRole('button', {name: /approve/i});
  approve.focus();
  fireEvent.click(approve);

  // The row has left the Unmoderated list: focus is on the next row's first action, not on
  // the document, and the result is read out.
  await waitFor(() => expect(rowOf(11)).toBeNull());
  await waitFor(() => expect(rowOf(12).contains(document.activeElement)).toBe(true));
  expect(document.activeElement?.tagName).toBe('BUTTON');
  expect(polite()).toHaveTextContent(m('admin-moderation-statement-approved', 11));

  // The last row going leaves focus on the empty-list line, and says so too.
  fireEvent.click(within(rowOf(12)).getByRole('button', {name: /hide/i}));
  await waitFor(() => expect(document.activeElement).toHaveClass('admin-empty'));
  expect(polite()).toHaveTextContent(m('admin-moderation-statement-hidden', 12));
});

test('an import the voting service partly refused keeps the text and does not call it skipped', async () => {
  serveWorkspace({});
  server.use(http.post(url('/api/v1/admin/conversations/7/statement-imports'), () => HttpResponse.json({data: {
    outcome: {imported: 1, skippedExisting: 0, skippedDuplicateInput: 0, failedUpstream: 2},
    links: {statements: STATEMENTS_URL},
  }})));
  renderPage(<AdminStatementsPage conversationId={7} csrfToken="t" />, '/admin/conversations/7/content/statements');

  const box = (await screen.findAllByRole('textbox', {}, {timeout: 10_000}))
    .find((field) => field.getAttribute('name') === 'statement_texts')!;
  const text = 'First line\nSecond line\nThird line';
  fireEvent.change(box, {target: {value: text}});
  fireEvent.submit(box.closest('form')!);

  await waitFor(() => expect(screen.getAllByText(/not added|could not be added/i).length).toBeGreaterThan(0));
  expect(box).toHaveValue(text);
  const main = screen.getByRole('main');
  expect(main.textContent).not.toMatch(/2 skipped/);
});

test('Participants names a person by pseudonym when the roster sends no username', async () => {
  server.use(http.get(PEOPLE_URL, () => HttpResponse.json({data: {
    conversation: {id: 7, slug: 'community-strategy', title: 'Community strategy'},
    participants: [{
      participantId: 31, username: null, pseudonym: 'blue-heron', statementProgress: null,
      arguments: {submitted: 0, prioritized: 0}, lastEngagementAt: null,
      access: {banned: false, changedAt: null, summary: null},
    }],
    dataAvailability: {statementProgress: true},
    capabilities: {setParticipantAccess: true},
    links: {self: PEOPLE_URL, conversation: '/admin/conversations/7'},
  }})));
  renderPage(<AdminParticipantsPage conversationId={7} csrfToken="t" />, '/admin/conversations/7/content/participants');

  const button = await screen.findByRole('button', {name: /— blue-heron$/}, {timeout: 10_000});
  expect(button.closest('li')).toHaveTextContent(/^blue-heron/);
});

test('a link to one statement opens Statements on the list that holds it', async () => {
  serveWorkspace({pending: [statement(14, 'pending')], approved: [statement(12, 'approved')]});
  renderPage(<AdminStatementsPage conversationId={7} csrfToken="t" />,
    '/admin/conversations/7/content/statements#statement-14');

  // Statement 14 waits for moderation, so the page opens on Unmoderated, not on Approved.
  expect(await screen.findByText('Statement text 14.', {}, {timeout: 10_000})).toBeVisible();
  expect(screen.getByRole('button', {name: new RegExp(m('admin-moderation-state-unmoderated'))}))
    .toHaveAttribute('aria-pressed', 'true');
  expect(screen.queryByText('Statement text 12.')).toBeNull();
});

test('moving a statement back to unmoderated is said too', async () => {
  serveWorkspace({approved: [statement(21, 'approved')]});
  renderPage(<AdminStatementsPage conversationId={7} csrfToken="t" />, '/admin/conversations/7/content/statements');

  await screen.findByText('Statement text 21.', {}, {timeout: 10_000});
  fireEvent.click(within(rowOf(21)).getByRole('button', {name: /unmoderated|pending/i}));
  await waitFor(() => expect(polite()).toHaveTextContent(m('admin-moderation-statement-unmoderated', 21)));
});

/** Meta statements (#415): seeds only, a warning before changing one people answered. */
function seedRow(id: number, extra: Partial<Statement> = {}): Statement {
  return {...statement(id, 'approved'), seed: true, ...extra};
}

function serveMeta(onPut: (body: {meta: boolean; acknowledgeResponses?: boolean}) => Response) {
  server.use(http.put(url('/api/v1/admin/conversations/7/statements/:statementId/meta'),
    async ({request}) => onPut(await request.json() as {meta: boolean; acknowledgeResponses?: boolean})));
}

test('only a seed statement offers the meta toggle, and a meta row says so', async () => {
  serveWorkspace({approved: [seedRow(12), statement(13, 'approved'), seedRow(14, {meta: true})]});
  renderPage(<AdminStatementsPage conversationId={7} csrfToken="t" />, '/admin/conversations/7/content/statements');

  await screen.findByText('Statement text 12.', {}, {timeout: 10_000});
  expect(within(rowOf(12)).getByRole('button', {name: m('stmts-meta-mark')})).toBeVisible();
  expect(within(rowOf(13)).queryByRole('button', {name: m('stmts-meta-mark')})).toBeNull();
  expect(within(rowOf(14)).getByRole('button', {name: m('stmts-meta-unmark')})).toBeVisible();
  expect(within(rowOf(14)).getByText(m('meta-statement-label'), {exact: false})).toBeVisible();
  expect(within(rowOf(12)).queryByText(m('meta-statement-label'), {exact: false})).toBeNull();
});

test('a featured seed cannot be marked meta', async () => {
  serveWorkspace({approved: [seedRow(12, {featured: true})]});
  renderPage(<AdminStatementsPage conversationId={7} csrfToken="t" />, '/admin/conversations/7/content/statements');

  await screen.findByText('Statement text 12.', {}, {timeout: 10_000});
  expect(within(rowOf(12)).queryByRole('button', {name: m('stmts-meta-mark')})).toBeNull();
});

test('marking a seed nobody answered yet goes through at once and is said', async () => {
  const bodies: unknown[] = [];
  serveWorkspace({approved: [seedRow(12)]});
  serveMeta((body) => {
    bodies.push(body);
    return HttpResponse.json({data: {statementId: 12, meta: true, changed: true, links: {statements: STATEMENTS_URL}}});
  });
  renderPage(<AdminStatementsPage conversationId={7} csrfToken="t" />, '/admin/conversations/7/content/statements');

  fireEvent.click(await screen.findByRole('button', {name: m('stmts-meta-mark')}, {timeout: 10_000}));
  await waitFor(() => expect(polite()).toHaveTextContent(m('flash-meta-marked', 12)));
  expect(bodies).toEqual([{meta: true, acknowledgeResponses: false}]);
  expect(within(rowOf(12)).getByRole('button', {name: m('stmts-meta-unmark')})).toBeVisible();
});

test('a seed with responses warns first, and changes only when confirmed', async () => {
  const bodies: unknown[] = [];
  serveWorkspace({approved: [seedRow(12, {hasResponses: true})]});
  serveMeta((body) => {
    bodies.push(body);
    return HttpResponse.json({data: {statementId: 12, meta: true, changed: true, links: {statements: STATEMENTS_URL}}});
  });
  renderPage(<AdminStatementsPage conversationId={7} csrfToken="t" />, '/admin/conversations/7/content/statements');

  fireEvent.click(await screen.findByRole('button', {name: m('stmts-meta-mark')}, {timeout: 10_000}));
  const warning = within(rowOf(12)).getByRole('alert');
  expect(warning).toHaveTextContent(m('stmts-meta-warn-responses', 12));
  expect(bodies).toEqual([]);

  fireEvent.click(within(warning).getByRole('button', {name: m('common-cancel')}));
  expect(within(rowOf(12)).queryByRole('alert')).toBeNull();
  expect(bodies).toEqual([]);

  fireEvent.click(within(rowOf(12)).getByRole('button', {name: m('stmts-meta-mark')}));
  fireEvent.click(within(within(rowOf(12)).getByRole('alert')).getByRole('button', {name: m('stmts-meta-mark')}));
  await waitFor(() => expect(bodies).toEqual([{meta: true, acknowledgeResponses: true}]));
});

test('the seed form can add a meta statement, and says when the mark failed', async () => {
  const bodies: unknown[] = [];
  serveWorkspace({});
  server.use(http.post(STATEMENTS_URL, async ({request}) => {
    bodies.push(await request.json());
    return HttpResponse.json({data: {
      statementId: 42, derivedFromId: null, provenanceRecorded: null, metaRecorded: false,
      links: {statements: STATEMENTS_URL},
    }}, {status: 201});
  }));
  renderPage(<AdminStatementsPage conversationId={7} csrfToken="t" />, '/admin/conversations/7/content/statements');

  const text = await screen.findByLabelText(m('stmts-seed-label'), {}, {timeout: 10_000});
  fireEvent.change(text, {target: {value: 'I would stand as a candidate'}});
  fireEvent.click(screen.getByRole('checkbox', {name: m('stmts-seed-meta-label')}));
  fireEvent.submit(text.closest('form')!);

  await waitFor(() => expect(bodies).toEqual([
    {text: 'I would stand as a candidate', derivedFromId: null, isMeta: true},
  ]));
  expect(await screen.findByText(m('flash-seed-added-meta-failed', 42))).toBeVisible();
});

test('from the 4th meta statement on, the list warns once', async () => {
  serveWorkspace({approved: [11, 12, 13].map((id) => seedRow(id, {meta: true}))});
  const {unmount} = renderPage(<AdminStatementsPage conversationId={7} csrfToken="t" />, '/admin/conversations/7/content/statements');
  await screen.findByText('Statement text 12.', {}, {timeout: 10_000});
  expect(screen.queryByText(/meta statements: each one/)).toBeNull();
  unmount();

  serveWorkspace({approved: [11, 12, 13, 14].map((id) => seedRow(id, {meta: true}))});
  renderPage(<AdminStatementsPage conversationId={7} csrfToken="t" />, '/admin/conversations/7/content/statements');
  expect(await screen.findByText('4 meta statements: each one asks every participant for one more response.',
    {}, {timeout: 10_000})).toBeVisible();
});
