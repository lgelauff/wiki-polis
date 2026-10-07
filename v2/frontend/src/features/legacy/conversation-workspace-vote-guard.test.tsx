/** #505 — double-click protection on the Explore vote buttons.
 *
 * A participant who answers quickly with two clicks sends two votes. The second click lands
 * on the card that replaced the one the first click was meant for, so the next statement is
 * answered without being read. A card that replaces another one therefore ignores vote
 * clicks for VOTE_INPUT_GUARD_MS.
 *
 * Two tests: one against the page on its own, one through the real router of <App/> at the
 * participant's own URL, because a guard added to the card can only be trusted if the page it
 * sits in is reached the way a participant reaches it.
 */
import {QueryClientProvider} from '@tanstack/react-query';
import {fireEvent, render, screen} from '@testing-library/react';
import {http, HttpResponse} from 'msw';
import {MemoryRouter} from 'react-router-dom';
import {afterEach, beforeEach, expect, test, vi} from 'vitest';

import {App} from '../../app';
import {server} from '../../test/server';
import {createQueryClient} from '../../query-client';
import {VOTE_INPUT_GUARD_MS} from './conversation-workspace-page';

const url = (path: string) => new URL(path, globalThis.location.origin).toString();
const WORKSPACE_URL = url('/api/v1/conversations/community-strategy/workspace');
const EXPLORE_URL = url('/api/v1/conversations/community-strategy/explore');
const VOTE_URL = url('/api/v1/conversations/community-strategy/statements/:statementId/vote');

const FIRST_CARD = {id: 12, text: 'Our movement should invest more in shared technical infrastructure.', isMeta: false, isSeed: true};
const SECOND_CARD = {id: 13, text: 'Small wikis should get translation support first.', isMeta: false, isSeed: false};
const THIRD_CARD = {id: 14, text: 'Every tool should publish its source code.', isMeta: false, isSeed: false};
const STATEMENTS = [FIRST_CARD, SECOND_CARD, THIRD_CARD];

const workspace = {
  slug: 'community-strategy',
  title: 'Community strategy',
  space: 'real',
  status: 'open',
  descriptionHtml: '<p>Shape the future together.</p>',
  outroHtml: null,
  viewer: {state: 'participant', pseudonym: 'quiet-otter'},
  spaceWarning: null,
  scheduledTransition: null,
  tabs: [{key: 'vote', label: 'Vote', dataHref: EXPLORE_URL}],
  defaultTab: 'vote',
  reveal: null,
  statementContribution: {unlockAfter: 0, quota: 3, used: 0},
  capabilities: {participate: true, moderate: false},
  links: {
    self: WORKSPACE_URL,
    conversation: '/c/community-strategy',
    about: '/c/community-strategy/about',
    join: '/accept/community-strategy',
    explore: EXPLORE_URL,
  },
};

const exploreState = (index: number, completed: number) => ({
  data: {
    slug: 'community-strategy',
    title: 'Community strategy',
    pseudonym: 'quiet-otter',
    currentStatement: STATEMENTS[index] ?? FIRST_CARD,
    progress: {completed, total: 12, remaining: 12 - completed, allDone: false},
    newStatement: {unlocked: true, unlockAfter: 0, quota: 3, used: 0, remaining: 3},
    capabilities: {vote: true, suggestWording: true, submitNewStatement: true},
    links: {
      self: EXPLORE_URL,
      about: '/c/community-strategy/about',
      conversation: '/c/community-strategy',
      arguments: '/c/community-strategy#tab-arguments',
    },
  },
});

/** A short deck plus a record of every vote request the browser made. */
function serveTwoCards() {
  const votes: {statementId: number; choice: string}[] = [];
  let card = 0;
  server.use(
    http.get(WORKSPACE_URL, () => HttpResponse.json({data: workspace})),
    http.get(EXPLORE_URL, () => HttpResponse.json(exploreState(card, 3 + card))),
    http.put(VOTE_URL, async ({params, request}) => {
      const body = await request.json() as {choice: string};
      votes.push({statementId: Number(params.statementId), choice: body.choice});
      return HttpResponse.json({
        data: {
          statementId: Number(params.statementId),
          choice: body.choice,
          passReason: null,
          links: {explore: EXPLORE_URL},
        },
      });
    }),
  );
  return {
    votes,
    /** What the deck serves next, the way advancing the queue would. */
    answerAndMoveOn: () => {
      card = Math.min(card + 1, STATEMENTS.length - 1);
    },
  };
}

/** A frozen clock, so "within the guard window" is a fact about the test, not about the
 *  machine's speed. Only `Date` is faked, so MSW and React Query keep their real timers. */
beforeEach(() => {
  vi.useFakeTimers({toFake: ['Date']});
  vi.setSystemTime(new Date('2026-07-19T10:00:00Z'));
});
afterEach(() => vi.useRealTimers());

/** Move the participant's clock forward, the way reading a card moves theirs. */
function after(milliseconds: number) {
  vi.setSystemTime(Date.now() + milliseconds);
}

function renderApp(entry: string) {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={[entry]}><App /></MemoryRouter>
    </QueryClientProvider>,
  );
}

test('the guard is half a second, one constant, and the first card is not guarded', async () => {
  const deck = serveTwoCards();
  renderApp('/app/conversations/community-strategy/explore');

  // The card a participant lands on: nothing can have leaked onto it from another card, so
  // the click they make right after reading it counts, guard window or not.
  fireEvent.click(await screen.findByRole('button', {name: 'Agree'}, {timeout: 10_000}));

  expect(await screen.findByText('Your response: Agree', {selector: '#voted-label'})).toBeVisible();
  expect(deck.votes).toEqual([{statementId: 12, choice: 'agree'}]);
  expect(VOTE_INPUT_GUARD_MS).toBe(500);
});

test('a vote click within the guard window of a new card sends nothing, and one after it counts', async () => {
  const deck = serveTwoCards();
  renderApp('/app/conversations/community-strategy/explore');

  fireEvent.click(await screen.findByRole('button', {name: 'Agree'}, {timeout: 10_000}));
  await screen.findByText('Your response: Agree', {selector: '#voted-label'});
  fireEvent.click(screen.getByRole('button', {name: /Move on/}));
  deck.answerAndMoveOn();

  // The second statement is on screen and the buttons are clickable, but this click is the
  // tail of the double click that answered the first one.
  expect(await screen.findByText(SECOND_CARD.text, {selector: '#statement-text'})).toBeVisible();
  fireEvent.click(screen.getByRole('button', {name: 'Agree'}));

  expect(screen.queryByText('Your response: Agree', {selector: '#voted-label'})).toBeNull();
  expect(screen.getByRole('button', {name: 'Agree'})).toBeVisible();

  // Past the window the same button works again, with no reload and no second card.
  after(VOTE_INPUT_GUARD_MS);
  fireEvent.click(screen.getByRole('button', {name: 'Agree'}));

  expect(await screen.findByText('Your response: Agree', {selector: '#voted-label'})).toBeVisible();
  // Two clicks, one vote: the request of the ignored click never reached the server.
  expect(deck.votes).toEqual([
    {statementId: 12, choice: 'agree'},
    {statementId: 13, choice: 'agree'},
  ]);
});

test('the guard covers every statement after the first, not just the second', async () => {
  const deck = serveTwoCards();
  renderApp('/app/conversations/community-strategy/explore');

  fireEvent.click(await screen.findByRole('button', {name: 'Agree'}, {timeout: 10_000}));
  await screen.findByText('Your response: Agree', {selector: '#voted-label'});
  fireEvent.click(screen.getByRole('button', {name: /Move on/}));
  deck.answerAndMoveOn();
  await screen.findByText(SECOND_CARD.text, {selector: '#statement-text'});
  after(VOTE_INPUT_GUARD_MS);
  fireEvent.click(screen.getByRole('button', {name: 'Pass'}));
  await screen.findByText('Your response: Pass', {selector: '#voted-label'});
  fireEvent.click(screen.getByRole('button', {name: /Move on/}));
  deck.answerAndMoveOn();

  // Still guarded: the clock has not moved since the third card appeared.
  expect(await screen.findByText(THIRD_CARD.text, {selector: '#statement-text'})).toBeVisible();
  fireEvent.click(screen.getByRole('button', {name: 'Agree'}));

  expect(screen.queryByText('Your response: Agree', {selector: '#voted-label'})).toBeNull();
  after(VOTE_INPUT_GUARD_MS);
  fireEvent.click(screen.getByRole('button', {name: 'Disagree'}));

  expect(await screen.findByText('Your response: Disagree', {selector: '#voted-label'})).toBeVisible();
  expect(deck.votes).toEqual([
    {statementId: 12, choice: 'agree'},
    {statementId: 13, choice: 'pass'},
    {statementId: 14, choice: 'disagree'},
  ]);
});