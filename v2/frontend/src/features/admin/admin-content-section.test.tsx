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
import {server} from '../../test/server';

type Statement = components['schemas']['AdminStatement'];
type Workspace = components['schemas']['AdminStatementWorkspace'];

const STATEMENTS_URL = new URL(
  '/api/v1/admin/conversations/7/statements', globalThis.location.origin,
).toString();

function statement(id: number, overrides: Partial<Statement> = {}): Statement {
  return {
    id, text: `Statement number ${id}.`, moderation: 'approved', seed: false, featured: false,
    votes: {agree: 1, pass: 0, disagree: 0}, provenance: null, ...overrides,
  };
}

function serveWorkspace(statements: Workspace['statements'], available = true) {
  const payload: Workspace = {
    conversation: {id: 7, slug: 'community-strategy', title: 'Community strategy'},
    statements,
    moderationPolicy: {mode: 'moderate', newStatements: 'pending', available: true},
    dataAvailability: {statements: available},
    seeding: {allowed: true, lockReason: null, maxStatementsPerImport: 20, maxCharactersPerStatement: 280},
    capabilities: {moderate: true, seed: true},
    links: {self: STATEMENTS_URL, lifecycle: '/admin/conversations/7'},
  };
  server.use(http.get(STATEMENTS_URL, () => HttpResponse.json({data: payload})));
}

function renderContent(element: React.ReactNode, path: string) {
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

function page() {
  return within(screen.getByRole('main'));
}

/** The one-row list, not the page's other lists (the how-to bullets are still here). */
function list() {
  return within(document.querySelector('.admin-rows') as HTMLElement);
}

const csrf = 'test-csrf-token';

test('the Content section is Statements and Participants, each marked in the strip', async () => {
  serveWorkspace({pending: [], approved: [], hidden: []});
  renderContent(<AdminStatementsPage conversationId={7} csrfToken={csrf} />,
    '/admin/conversations/7/content/statements');

  // The h1 names the section; the strip's current tab names the page, so no heading
  // repeats it.
  expect(await screen.findByRole('heading', {name: 'Content', level: 1}, {timeout: 10_000}))
    .toBeVisible();
  expect(screen.queryByRole('heading', {name: 'Statements'})).toBeNull();
  const strip = screen.getByRole('navigation', {name: 'Content'});
  expect(within(strip).getAllByRole('link').map((link) => link.textContent))
    .toEqual(['Statements', 'Participants']);
  expect(within(strip).getAllByRole('link').map((link) => link.getAttribute('href')))
    .toEqual([
      '/admin/conversations/7/content/statements',
      '/admin/conversations/7/content/participants',
    ]);
  expect(within(strip).getByRole('link', {name: 'Statements'}))
    .toHaveAttribute('aria-current', 'page');
});

test('the statement list opens on the approved ones, most responses first', async () => {
  serveWorkspace({
    pending: [statement(20, {moderation: 'pending', votes: {agree: 99, pass: 0, disagree: 0}})],
    approved: [
      statement(11, {votes: {agree: 2, pass: 1, disagree: 1}}),
      statement(12, {votes: {agree: 8, pass: 2, disagree: 1}, featured: true}),
      statement(13, {votes: {agree: 0, pass: 0, disagree: 0}}),
    ],
    hidden: [],
  });
  renderContent(<AdminStatementsPage conversationId={7} csrfToken={csrf} />,
    '/admin/conversations/7/content/statements');

  await screen.findByRole('heading', {name: 'Content', level: 1}, {timeout: 10_000});
  // The state switch defaults to approved here, not to what is waiting: that is the
  // Moderation queue's default.
  expect(screen.getByRole('button', {name: 'Show approved 3'})).toHaveAttribute('aria-pressed', 'true');
  // Each position of the switch carries its count, in its accessible name too.
  expect(screen.getByRole('button', {name: 'Show unmoderated 1'})).toBeVisible();
  expect(screen.getByRole('button', {name: 'Show hidden'})).toBeVisible();
  expect(screen.getByRole('combobox', {name: 'Sort'})).toHaveValue('most-responses');
  expect(screen.getByRole('option', {name: 'Most responses', selected: true})).toBeInTheDocument();
  const rows = list().getAllByRole('listitem')
    .map((row) => row.querySelector('.admin-row__text')?.textContent ?? '');
  expect(rows[0]).toContain('Statement number 12');
  expect(rows[2]).toContain('Statement number 13');
  // A featured statement is starred, the star explains itself, and a waiting one is not in
  // this list at all.
  expect(rows[0]).toContain('★');
  expect(rows[0]).toContain('Featured statement');
  expect(list().getAllByRole('listitem')[0]!.querySelector('[title="Featured statement"]'))
    .toHaveTextContent('★');
  expect(page().queryByText(/Statement number 20/)).toBeNull();
});

test('a statement row carries its votes, muted, and where it came from', async () => {
  serveWorkspace({
    pending: [],
    approved: [statement(14, {text: 'A corrected wording.', provenance: {
      derivedFromId: 11, scores: [{model: 'sim', value: 1}],
    }, votes: {agree: 12, pass: 3, disagree: 5}})],
    hidden: [],
  });
  renderContent(<AdminStatementsPage conversationId={7} csrfToken={csrf} />,
    '/admin/conversations/7/content/statements');

  await screen.findByRole('heading', {name: 'Content', level: 1}, {timeout: 10_000});
  const row = list().getByRole('listitem');
  expect(row).toHaveTextContent('A corrected wording.');
  expect(row.querySelector('.admin-row__counts')).toHaveTextContent('A 12 · P 3 · D 5');
  // The source is not in this list, so there is nothing to jump to: text, not a link.
  expect(within(row).queryByRole('link')).toBeNull();
  const source = row.querySelector('.admin-row__source')!;
  expect(source).toHaveTextContent('derived from statement 11');
  expect(source).toHaveTextContent('↳ #11 · sim 1.00');
  expect(source).toHaveAttribute('title',
    'Derived from statement #11. Similarity 1.00 = identical. sim 1.00.');
});

test('"↳ #N" jumps to the source row when the source is in the list', async () => {
  serveWorkspace({
    pending: [],
    approved: [
      statement(11, {text: 'The original wording.'}),
      statement(14, {text: 'The corrected wording.', provenance: {
        derivedFromId: 11, scores: [{model: 'sim', value: 0.93}],
      }}),
    ],
    hidden: [],
  });
  renderContent(<AdminStatementsPage conversationId={7} csrfToken={csrf} />,
    '/admin/conversations/7/content/statements');

  await screen.findByRole('heading', {name: 'Content', level: 1}, {timeout: 10_000});
  const link = list().getByRole('link', {name: 'derived from statement 11'});
  expect(link).toHaveAttribute('href', '#statement-11');
  expect(link).toHaveTextContent('↳ #11');
  expect(document.getElementById('statement-11')).toHaveTextContent('The original wording.');
  expect(link.closest('.admin-row__source')).toHaveTextContent('· sim 0.93');
});

test('the search box filters the loaded text and says when nothing is left', async () => {
  serveWorkspace({
    pending: [],
    approved: [statement(11, {text: 'Bicycle parking near the station.'}),
      statement(12, {text: 'More trees on the square.'})],
    hidden: [],
  });
  renderContent(<AdminStatementsPage conversationId={7} csrfToken={csrf} />,
    '/admin/conversations/7/content/statements');

  await screen.findByRole('heading', {name: 'Content', level: 1}, {timeout: 10_000});
  fireEvent.change(screen.getByLabelText('Search statements'), {target: {value: 'trees'}});
  expect(list().getByRole('listitem')).toHaveTextContent('More trees on the square.');
  expect(page().queryByText(/Bicycle parking/)).toBeNull();

  fireEvent.change(screen.getByLabelText('Search statements'), {target: {value: 'nothing here'}});
  expect(page().getByText('No statement matches the search.')).toBeVisible();
  expect(page().queryByText('No statements yet.')).toBeNull();
});

test('the empty list says whether there are no statements at all or none in this view', async () => {
  serveWorkspace({pending: [statement(20, {moderation: 'pending'})], approved: [], hidden: []});
  renderContent(<AdminStatementsPage conversationId={7} csrfToken={csrf} />,
    '/admin/conversations/7/content/statements');

  await screen.findByRole('heading', {name: 'Content', level: 1}, {timeout: 10_000});
  expect(page().getByText('No approved statements.')).toBeVisible();
  expect(page().queryByText('No statements yet.')).toBeNull();
  fireEvent.click(screen.getByRole('button', {name: 'Show hidden'}));
  expect(page().getByText('No hidden statements.')).toBeVisible();
});

test('a consultation without statements says so once', async () => {
  serveWorkspace({pending: [], approved: [], hidden: []});
  renderContent(<AdminStatementsPage conversationId={7} csrfToken={csrf} />,
    '/admin/conversations/7/content/statements');

  await screen.findByRole('heading', {name: 'Content', level: 1}, {timeout: 10_000});
  expect(page().getByText('No statements yet.')).toBeVisible();
});

test('statements that could not be loaded are an error, not an empty consultation', async () => {
  // The workspace answers 200 with empty lists when the voting service is unreachable.
  serveWorkspace({pending: [], approved: [], hidden: []}, false);
  renderContent(<AdminStatementsPage conversationId={7} csrfToken={csrf} />,
    '/admin/conversations/7/content/statements');

  await screen.findByRole('heading', {name: 'Content', level: 1}, {timeout: 10_000});
  // The inline error stays on the page, and the toast stays as the old page had it.
  const errors = page().getAllByText('Could not load statements. Check server logs.');
  expect(errors).toHaveLength(2);
  expect(errors.filter((node) => node.closest('.admin-shell__notices'))).toHaveLength(1);
  for (const text of ['No statements yet.', 'No approved statements.',
    'No statement matches the search.']) {
    expect(page().queryByText(text)).toBeNull();
  }
});

test('the switch, sort and search sit directly above the list, seeding below it', async () => {
  serveWorkspace({pending: [], approved: [statement(11)], hidden: []});
  renderContent(<AdminStatementsPage conversationId={7} csrfToken={csrf} />,
    '/admin/conversations/7/content/statements');

  await screen.findByRole('heading', {name: 'Content', level: 1}, {timeout: 10_000});
  const toolbar = document.querySelector('.admin-toolbar')!;
  const rows = document.querySelector('.admin-rows')!;
  expect(toolbar.nextElementSibling).toBe(rows);
  const seed = screen.getByRole('button', {name: 'Add seed statement'});
  expect(rows.compareDocumentPosition(seed) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
});

test('sorting by lineage puts a correction under its source', async () => {
  serveWorkspace({
    pending: [],
    approved: [
      statement(11, {text: 'The original wording.'}),
      statement(14, {text: 'The corrected wording.', provenance: {
        derivedFromId: 11, scores: [{model: 'sim', value: 1}],
      }}),
    ],
    hidden: [],
  });
  renderContent(<AdminStatementsPage conversationId={7} csrfToken={csrf} />,
    '/admin/conversations/7/content/statements');

  await screen.findByRole('heading', {name: 'Content', level: 1}, {timeout: 10_000});
  fireEvent.change(screen.getByRole('combobox', {name: 'Sort'}), {target: {value: 'based-on'}});
  const texts = list().getAllByRole('listitem')
    .map((row) => row.querySelector('.admin-row__text')?.textContent ?? '');
  expect(texts[0]).toContain('The original wording.');
  expect(texts[1]).toContain('The corrected wording.');
});

test('seeding and importing are still on this page', async () => {
  serveWorkspace({pending: [], approved: [], hidden: []});
  renderContent(<AdminStatementsPage conversationId={7} csrfToken={csrf} />,
    '/admin/conversations/7/content/statements');

  await screen.findByRole('heading', {name: 'Content', level: 1}, {timeout: 10_000});
  expect(screen.getByLabelText('Statement text (max 280 characters)')).toBeVisible();
  expect(screen.getByRole('button', {name: 'Add seed statement'})).toBeVisible();
  expect(screen.getByRole('button', {name: 'Import statements'})).toBeVisible();
  // The Approval control is a setting, and lives on Settings > Basics (#478).
  expect(screen.queryByRole('checkbox', {name: /Strict moderation/})).toBeNull();
});

test('the statement page names the one thing it cannot show yet', async () => {
  serveWorkspace({pending: [], approved: [], hidden: []});
  renderContent(<AdminStatementsPage conversationId={7} csrfToken={csrf} />,
    '/admin/conversations/7/content/statements');

  await screen.findByRole('heading', {name: 'Content', level: 1}, {timeout: 10_000});
  const lines = page().getAllByText(/^Also coming:/);
  expect(lines).toHaveLength(1);
  expect(lines[0]).toHaveTextContent(
    'Also coming: the arguments of this consultation as a list of their own'
    + ' — not available yet (#473)',
  );
  expect(lines[0]).toHaveAttribute('lang', 'en');
});

test('participants are one row each, with today’s figures and the access control', async () => {
  renderContent(<AdminParticipantsPage conversationId={7} csrfToken={csrf} />,
    '/admin/conversations/7/content/participants');

  await screen.findByRole('heading', {name: 'Content', level: 1}, {timeout: 10_000});
  expect(screen.getByRole('navigation', {name: 'Content'})
    .querySelector('[aria-current="page"]')).toHaveTextContent('Participants');
  const row = list().getByRole('listitem');
  expect(row).toHaveTextContent('Example editor');
  // Today's columns, as facts about the person.
  expect(row).toHaveTextContent('8 / 12');
  expect(row).toHaveTextContent('Statements remaining');
  expect(row).toHaveTextContent('Arguments submitted');
  expect(row).toHaveTextContent('2026-08-13');
  // The access control is the same one the participants page has always had.
  expect(within(row).getByPlaceholderText('Reason (optional)')).toBeVisible();
  expect(within(row).getByRole('button', {name: 'ban'})).toBeVisible();

  // Once banned, the row says "Banned since …" once, beside the name.
  fireEvent.click(within(row).getByRole('button', {name: 'ban'}));
  await within(row).findByRole('button', {name: 'unban'});
  expect(row).toHaveTextContent('Example editor · Banned since 2026-08-13');
  expect(row.textContent?.match(/since/g)).toHaveLength(1);
});

test('participants says once what the roster cannot answer yet', async () => {
  renderContent(<AdminParticipantsPage conversationId={7} csrfToken={csrf} />,
    '/admin/conversations/7/content/participants');

  await screen.findByRole('heading', {name: 'Content', level: 1}, {timeout: 10_000});
  const lines = page().getAllByText(/^Also coming:/);
  expect(lines).toHaveLength(1);
  expect(lines[0]).toHaveTextContent(
    'Also coming: the moderator and organizer roles per person, their batch,'
    + ' and the day they joined — not available yet (#473)',
  );
  expect(lines[0]).toHaveAttribute('lang', 'en');
});