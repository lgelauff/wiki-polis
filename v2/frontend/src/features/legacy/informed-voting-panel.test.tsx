import {QueryClientProvider} from '@tanstack/react-query';
import {fireEvent, render, screen, within} from '@testing-library/react';
import {http, HttpResponse} from 'msw';
import {MemoryRouter} from 'react-router-dom';
import {expect, test} from 'vitest';

import type {components} from '../../api/schema';
import {App} from '../../app';
import {createQueryClient} from '../../query-client';
import {renderAsQqx, untranslatedCopy} from '../../test/i18n';
import {server} from '../../test/server';

type Workspace = components['schemas']['ConversationWorkspace'];
type Card = components['schemas']['InformedVotingCard'];

const url = (path: string) => new URL(path, globalThis.location.origin).toString();

const STATEMENT = 'Regional communities should share infrastructure funding.';
const EARLIER = 'Small wikis should get translation support first.';
const ARGUMENTS = ['Shared funding reduces duplicated maintenance.', 'Pooling lowers hosting costs.', 'One team can be on call.', 'Fewer contracts to negotiate.'];
const CONTENT = [STATEMENT, EARLIER, ...ARGUMENTS, 'quiet-otter', 'Community strategy'];

function workspace(overrides: Partial<Workspace> = {}): Workspace {
  return {
    slug: 'community-strategy', title: 'Community strategy', space: 'real', status: 'open',
    descriptionHtml: '', outroHtml: null,
    viewer: {state: 'participant', pseudonym: 'quiet-otter'}, spaceWarning: null, scheduledTransition: null,
    tabs: [{key: 'informed-voting', label: 'Informed vote', dataHref: '/api/v1/conversations/community-strategy/informed-voting'}],
    defaultTab: 'informed-voting', reveal: null,
    statementContribution: {unlockAfter: 0, quota: 3, used: 0},
    capabilities: {participate: true, moderate: false},
    links: {self: '/api/v1/conversations/community-strategy/workspace', conversation: '/c/community-strategy', about: '/c/community-strategy/about', join: '/accept/community-strategy', results: '/c/community-strategy/report'},
    ...overrides,
  } as Workspace;
}

function deck(cards: Card[]) {
  return http.get(url('/api/v1/conversations/community-strategy/informed-voting'), () => HttpResponse.json({data: {
    slug: 'community-strategy', title: 'Community strategy', pseudonym: 'quiet-otter', cards,
    progress: {completed: cards.filter((c) => c.voted).length, total: cards.length, remaining: cards.filter((c) => !c.voted).length, allDone: cards.every((c) => c.voted)},
    capabilities: {vote: true},
    links: {self: '/api/v1/conversations/community-strategy/informed-voting', about: '/c/community-strategy/about', conversation: '/c/community-strategy', explore: '/c/community-strategy', arguments: '/c/community-strategy#tab-arguments'},
  }}));
}

const unanswered: Card = {
  featuredStatementId: 31, statement: STATEMENT, canVote: true, voted: false,
  // Four for, none against: reaches the "N more" disclosure and the empty side.
  arguments: {for: ARGUMENTS.map((body, index) => ({id: 80 + index, body, helpfulVotes: 1})), against: []},
};
const answered: Card = {featuredStatementId: 32, statement: EARLIER, canVote: true, voted: true, arguments: {for: [], against: []}};

const reveal = (state: 'open' | 'pending') => ({
  state, pseudonym: 'quiet-otter', closedAt: '2026-09-01T00:00:00Z', opensAt: '2026-10-01T00:00:00Z',
  closesAt: '2026-11-01T00:00:00Z', daysRemaining: 20, cooldownDays: 30, windowDays: 30, countdownTargetAt: null,
});

function renderPanel(ws: Workspace, cards: Card[]) {
  server.use(http.get(url('/api/v1/conversations/community-strategy/workspace'), () => HttpResponse.json({data: ws})), deck(cards));
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={['/app/conversations/community-strategy/informed-voting']}><App /></MemoryRouter>
    </QueryClientProvider>,
  );
}

const panel = () => document.getElementById('tab-informed-voting');

test('under qqx, a deck mid-way through carries no English but the statements and arguments', async () => {
  renderAsQqx();
  renderPanel(workspace(), [unanswered, answered]);
  await screen.findByText(STATEMENT);

  expect(untranslatedCopy([panel()], CONTENT)).toEqual([]);
  // The earlier card is present, hidden, and must be translated too.
  expect(screen.getByText(EARLIER, {selector: '.p6-statement-text'})).toBeInTheDocument();
});

test('under qqx, a failed vote carries no English either', async () => {
  server.use(http.put(url('/api/v1/conversations/community-strategy/featured-statements/31/informed-vote'),
    () => HttpResponse.json({error: {code: 'conflict', message: 'The round is paused.'}}, {status: 409})));
  renderAsQqx();
  renderPanel(workspace(), [unanswered]);
  fireEvent.click(await screen.findByRole('button', {name: '(conv-vote-agree)'}));

  expect(await screen.findByText('(conv-p6-vote-failed)')).toBeVisible();
  expect(untranslatedCopy([panel()], CONTENT)).toEqual([]);
});

test.each([
  ['preliminary results out, reveal window open', workspace({
    tabs: [
      {key: 'informed-voting', label: 'Informed vote', dataHref: ''},
      {key: 'p6-results', label: 'Preliminary results', dataHref: ''},
    ],
    reveal: reveal('open'),
  } as Partial<Workspace>)],
  ['deliberation still open, reveal pending', workspace({
    tabs: [
      {key: 'arguments', label: 'Arguments', dataHref: ''},
      {key: 'informed-voting', label: 'Informed vote', dataHref: ''},
    ],
  } as Partial<Workspace>)],
  ['waiting for the report', workspace()],
  // No 'closed' case: a closed workspace renders ClosedWorkspace instead of the tabs, so the
  // panel's closed branch (conv-p6-done-closed) is unreachable today.
])('under qqx, the completion panel carries no English: %s', async (_name, ws) => {
  renderAsQqx();
  renderPanel(ws, [answered]);
  await screen.findByRole('heading', {name: '(conv-p6-done-heading)'});

  expect(untranslatedCopy([document.querySelector('.p6-done')], CONTENT)).toEqual([]);
});

test('the pointer to preliminary results is one sentence, and its link still switches tab', async () => {
  renderPanel(workspace({
    tabs: [
      {key: 'informed-voting', label: 'Informed vote', dataHref: ''},
      {key: 'p6-results', label: 'Preliminary results', dataHref: ''},
    ],
  } as Partial<Workspace>), [answered]);

  // conv-p6-done-see is one message with the link passed in as an element, so the link keeps
  // its onClick handler.
  const done = await screen.findByText(/to compare the first round with this one/);
  expect(done).toHaveTextContent('See the Preliminary results tab to compare the first round with this one.');
  fireEvent.click(within(done).getByRole('link', {name: 'Preliminary results'}));
  expect(await screen.findByRole('tab', {name: 'Preliminary results'})).toHaveAttribute('aria-selected', 'true');
});

test('the identity note names the pseudonym in bold and links to the reveal page', async () => {
  renderPanel(workspace({reveal: reveal('open')} as Partial<Workspace>), [answered]);

  const note = await screen.findByText(/recorded under pseudonym/);
  expect(note).toHaveTextContent('Your responses are recorded under pseudonym quiet-otter. You can link your Wikimedia username to this pseudonym now. Open the linking page →');
  expect(within(note).getByText('quiet-otter').tagName).toBe('STRONG');
  expect(within(note).getByRole('link', {name: /Open the linking page/})).toHaveAttribute('href', '/c/community-strategy/reveal');
});

test('each card counts its position, and a rejected vote says so', async () => {
  server.use(http.put(url('/api/v1/conversations/community-strategy/featured-statements/31/informed-vote'),
    () => HttpResponse.json({error: {code: 'conflict', message: 'The round is paused.'}}, {status: 409})));
  renderPanel(workspace(), [unanswered, answered]);

  await screen.findByText(STATEMENT);
  expect(screen.getAllByText(/Informed opinion · 1 of 2/)[0]).toBeInTheDocument();
  expect(screen.getByText('1 more')).toBeInTheDocument();
  expect(screen.getAllByText('No arguments yet.', {selector: '.p6-args-side--con .p6-args-empty'})[0]).toBeInTheDocument();

  fireEvent.click(screen.getAllByRole('button', {name: 'Disagree'})[0]!);
  expect(await screen.findByText('Response not saved — try again')).toBeVisible();
  // The server's English never reaches the participant.
  expect(screen.queryByText(/round is paused/)).not.toBeInTheDocument();
});

test('a saved vote is confirmed in the past tense, while the buttons keep the present', async () => {
  renderPanel(workspace(), [unanswered, answered]);
  await screen.findByText(STATEMENT);

  fireEvent.click(screen.getAllByRole('button', {name: 'Disagree'})[0]!);
  // "Disagreed" is its own message, not the button's "Disagree" reused: a confirmation reports
  // a vote already recorded, and a language may need a different form for that.
  expect(await screen.findByText('Disagreed')).toBeVisible();
  expect(screen.getAllByRole('button', {name: 'Disagree'})[0]).toHaveAttribute('aria-pressed', 'true');
});

test('a pass is confirmed as "Passed"', async () => {
  renderPanel(workspace(), [unanswered, answered]);
  await screen.findByText(STATEMENT);

  // Catches the pass branch falling back to another choice's message.
  fireEvent.click(screen.getAllByRole('button', {name: 'Pass'})[0]!);
  expect(await screen.findByText('Passed')).toBeVisible();
});

test('a participant coming back mid-deck resumes at the first card still to answer', async () => {
  // Answered first, so a panel that starts at the first card lands on the wrong one.
  renderPanel(workspace(), [answered, unanswered]);
  await screen.findByText(STATEMENT);

  const card = (id: number) => panel()!.querySelector(`.p6-card[data-fs-id="${id}"]`)!;
  expect(card(31)).not.toHaveClass('p6-card--hidden');
  expect(card(32)).toHaveClass('p6-card--hidden');
  expect(card(32)).toHaveClass('p6-card--done');
});

test('the card navigation is named for the statements it moves between', async () => {
  renderPanel(workspace(), [unanswered, answered]);
  await screen.findByText(STATEMENT);

  // Catches the arrows being read out as the buttons' names.
  expect(screen.getAllByRole('button', {name: 'Next statement'})[0]).toHaveTextContent('Next →');
  expect(screen.getAllByRole('button', {name: 'Previous statement'})[0]).toHaveTextContent('← Previous');
});

