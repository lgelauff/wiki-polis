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
    id, text: `Statement text ${id}.`, moderation, seed: false, featured: false,
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
