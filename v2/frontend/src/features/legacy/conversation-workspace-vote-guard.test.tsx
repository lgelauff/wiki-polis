/** #505 — double-click protection on the Explore vote buttons.
 *
 * A participant who answers quickly with two clicks sends two votes. The second click lands
 * on the card that replaced the one the first click was meant for, so the next statement is
 * answered without being read. So: while the next card loads the old card keeps its receipt
 * and no vote counts; then a card that replaced another one ignores a pointer click for
 * VOTE_INPUT_GUARD_MS and a keyboard activation (Enter or Space: a keydown, then a click with
 * `detail === 0`) for VOTE_KEY_GUARD_MS. An assistive-technology click (`detail === 0` with
 * no keydown) gets the pointer window.
 *
 * Every test goes through the real router of <App/> at the participant's own URL, because a
 * guard added to the card can only be trusted if the page it sits in is reached the way a
 * participant reaches it.
 */
import {QueryClientProvider} from '@tanstack/react-query';
import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import {http, HttpResponse} from 'msw';
import {MemoryRouter} from 'react-router-dom';
import {afterEach, beforeEach, expect, test, vi} from 'vitest';

import {App} from '../../app';
import {server} from '../../test/server';
import {createQueryClient} from '../../query-client';
import {VOTE_INPUT_GUARD_MS, VOTE_KEY_GUARD_MS} from './conversation-workspace-page';

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
  const reads = {count: 0};
  let card = 0;
  let failing = false;
  let held: Promise<void> | null = null;
  let release = () => {};
  server.use(
    http.get(WORKSPACE_URL, () => HttpResponse.json({data: workspace})),
    http.get(EXPLORE_URL, async () => {
      reads.count += 1;
      if (held) await held;
      if (failing) {
        return HttpResponse.json({
          error: {code: 'upstream_unavailable', message: 'The voting service is unavailable.'},
        }, {status: 503});
      }
      return HttpResponse.json(exploreState(card, 3 + card));
    }),
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
    reads,
    /** Every deck reload from now on fails with a 503. */
    failDeck: () => {
      failing = true;
    },
    /** What the deck serves next, the way advancing the queue would. */
    answerAndMoveOn: () => {
      card = Math.min(card + 1, STATEMENTS.length - 1);
    },
    /** Hold every deck reload until `releaseDeck()`: the next card is still loading. */
    holdDeck: () => {
      held = new Promise((resolve) => {
        release = () => {
          held = null;
          resolve();
        };
      });
    },
    releaseDeck: () => release(),
  };
}

/** A pointer click or tap: the browser reports a click count of at least 1. */
const tap = (element: HTMLElement) => fireEvent.click(element, {detail: 1});
/** Enter on a focused button: a keydown, then a click with `detail === 0`. */
const press = (element: HTMLElement) => {
  fireEvent.keyDown(element, {key: 'Enter'});
  fireEvent.click(element, {detail: 0});
};
/** Assistive technology activating a button: a click with `detail === 0` and no keydown. */
const activateWithAssistiveTech = (element: HTMLElement) => fireEvent.click(element, {detail: 0});

/** A frozen monotonic clock, so "within the guard window" is a fact about the test, not about
 *  the machine's speed. Only `performance.now()` is replaced; MSW and React Query keep their
 *  real timers. */
let clock = 0;
beforeEach(() => {
  clock = 1_000_000;
  vi.spyOn(performance, 'now').mockImplementation(() => clock);
});
afterEach(() => vi.restoreAllMocks());

/** Move the participant's clock forward, the way reading a card moves theirs. */
function after(milliseconds: number) {
  clock += milliseconds;
}

/** The page the way a participant meets it: the SPA router, at its own URL. A failed deck
 *  reload is not retried, so a 503 surfaces at once. */
function renderApp() {
  const client = createQueryClient();
  client.setQueryDefaults(['explore-state'], {retry: false});
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/app/conversations/community-strategy/explore']}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

test('the guards are half a second for a tap and 1.5 s for a key, and the first card is not guarded', async () => {
  const deck = serveTwoCards();
  renderApp();

  // The card a participant lands on: nothing can have leaked onto it from another card, so
  // the key press they make right after reading it counts, guard window or not.
  press(await screen.findByRole('button', {name: 'Agree'}, {timeout: 10_000}));

  expect(await screen.findByText('Your response: Agree', {selector: '#voted-label'})).toBeVisible();
  expect(deck.votes).toEqual([{statementId: 12, choice: 'agree'}]);
  expect(VOTE_INPUT_GUARD_MS).toBe(500);
  expect(VOTE_KEY_GUARD_MS).toBe(1500);
});

test('while the next card loads the old card keeps its receipt, and Move on twice or a vote sends nothing more', async () => {
  const deck = serveTwoCards();
  renderApp();

  tap(await screen.findByRole('button', {name: 'Agree'}, {timeout: 10_000}));
  await screen.findByText('Your response: Agree', {selector: '#voted-label'});
  deck.answerAndMoveOn();
  deck.holdDeck();
  const readsBefore = deck.reads.count;
  const moveOn = screen.getByRole('button', {name: /Move on/});
  press(moveOn);
  press(moveOn);

  // The next card is still loading: the old card keeps its receipt, so there are no vote
  // buttons for the second click of a double click, or a repeated Enter, to land on.
  await waitFor(() => expect(document.getElementById('particiapi-client')).toHaveAttribute('aria-busy', 'true'));
  expect(screen.getByText('Your response: Agree', {selector: '#voted-label'})).toBeVisible();
  expect(screen.queryByRole('button', {name: 'Agree'})).toBeNull();
  // "Change" brings the old card's buttons back, but no vote counts until the next card.
  fireEvent.click(screen.getByRole('button', {name: 'change'}));
  after(5_000);
  tap(screen.getByRole('button', {name: 'Agree'}));
  press(screen.getByRole('button', {name: 'Disagree'}));
  expect(screen.queryByText(/Your response:/, {selector: '#voted-label'})).toBeNull();

  deck.releaseDeck();
  expect(await screen.findByText(SECOND_CARD.text, {selector: '#statement-text'})).toBeVisible();
  expect(document.getElementById('particiapi-client')).toHaveAttribute('aria-busy', 'false');
  // Two presses of Move on, one reload.
  expect(deck.reads.count).toBe(readsBefore + 1);
  after(VOTE_INPUT_GUARD_MS);
  tap(screen.getByRole('button', {name: 'Pass'}));

  expect(await screen.findByText('Your response: Pass', {selector: '#voted-label'})).toBeVisible();
  // Asserted after the second receipt, so a stray request for the old card would have been
  // served (and recorded) before it.
  expect(deck.votes).toEqual([
    {statementId: 12, choice: 'agree'},
    {statementId: 13, choice: 'pass'},
  ]);
});

test('when the reload brings the same card back, the block is lifted and a vote counts', async () => {
  const deck = serveTwoCards();
  renderApp();

  tap(await screen.findByRole('button', {name: 'Agree'}, {timeout: 10_000}));
  await screen.findByText('Your response: Agree', {selector: '#voted-label'});
  // The deck does not advance: the reload serves the first card again.
  tap(screen.getByRole('button', {name: /Move on/}));

  await screen.findByRole('button', {name: 'Agree'});
  expect(screen.getByText(FIRST_CARD.text, {selector: '#statement-text'})).toBeVisible();
  expect(document.getElementById('particiapi-client')).toHaveAttribute('aria-busy', 'false');
  // No new card was shown, so no guard window either: the tap counts at once.
  tap(screen.getByRole('button', {name: 'Disagree'}));

  expect(await screen.findByText('Your response: Disagree', {selector: '#voted-label'})).toBeVisible();
  expect(deck.votes).toEqual([
    {statementId: 12, choice: 'agree'},
    {statementId: 12, choice: 'disagree'},
  ]);
});

test('when the reload fails, the error is shown, the block is lifted and a vote counts', async () => {
  const deck = serveTwoCards();
  renderApp();

  tap(await screen.findByRole('button', {name: 'Agree'}, {timeout: 10_000}));
  await screen.findByText('Your response: Agree', {selector: '#voted-label'});
  deck.failDeck();
  tap(screen.getByRole('button', {name: /Move on/}));

  expect(await screen.findByText('This consultation could not be loaded. Try again in a moment.', {selector: '#conv-next-error p'})).toBeVisible();
  expect(document.getElementById('particiapi-client')).toHaveAttribute('aria-busy', 'false');
  // The old card keeps its receipt, with Move on right there to try again.
  expect(screen.getByText('Your response: Agree', {selector: '#voted-label'})).toBeVisible();
  expect(screen.getByRole('button', {name: /Move on/})).toBeVisible();

  fireEvent.click(screen.getByRole('button', {name: 'change'}));
  tap(screen.getByRole('button', {name: 'Disagree'}));

  expect(await screen.findByText('Your response: Disagree', {selector: '#voted-label'})).toBeVisible();
  expect(deck.votes).toEqual([
    {statementId: 12, choice: 'agree'},
    {statementId: 12, choice: 'disagree'},
  ]);
});

test('a keyboard activation within 1.5 s of a new card is ignored, and one after it counts', async () => {
  const deck = serveTwoCards();
  renderApp();

  press(await screen.findByRole('button', {name: 'Agree'}, {timeout: 10_000}));
  await screen.findByText('Your response: Agree', {selector: '#voted-label'});
  press(screen.getByRole('button', {name: /Move on/}));
  deck.answerAndMoveOn();
  await screen.findByText(SECOND_CARD.text, {selector: '#statement-text'});

  // Past the pointer window, still inside the key window.
  after(1000);
  press(screen.getByRole('button', {name: 'Agree'}));
  expect(screen.queryByText(/Your response:/, {selector: '#voted-label'})).toBeNull();

  after(VOTE_KEY_GUARD_MS - 1000);
  press(screen.getByRole('button', {name: 'Disagree'}));

  expect(await screen.findByText('Your response: Disagree', {selector: '#voted-label'})).toBeVisible();
  expect(deck.votes).toEqual([
    {statementId: 12, choice: 'agree'},
    {statementId: 13, choice: 'disagree'},
  ]);
});

test('a vote tap within the guard window of a new card sends nothing, and one after it counts', async () => {
  const deck = serveTwoCards();
  renderApp();

  tap(await screen.findByRole('button', {name: 'Agree'}, {timeout: 10_000}));
  await screen.findByText('Your response: Agree', {selector: '#voted-label'});
  tap(screen.getByRole('button', {name: /Move on/}));
  deck.answerAndMoveOn();

  // The second statement is on screen and the buttons are clickable, but this tap is the
  // tail of the double click that answered the first one.
  expect(await screen.findByText(SECOND_CARD.text, {selector: '#statement-text'})).toBeVisible();
  tap(screen.getByRole('button', {name: 'Agree'}));
  after(VOTE_INPUT_GUARD_MS - 1);
  tap(screen.getByRole('button', {name: 'Agree'}));

  expect(screen.queryByText(/Your response:/, {selector: '#voted-label'})).toBeNull();
  expect(screen.getByRole('button', {name: 'Agree'})).toBeVisible();

  // Past the window a tap counts, with no reload and no second card. A different choice
  // from the dropped ones, so the receipt can only come from this tap.
  after(1);
  tap(screen.getByRole('button', {name: 'Disagree'}));

  expect(await screen.findByText('Your response: Disagree', {selector: '#voted-label'})).toBeVisible();
  // Three taps, one vote: the requests of the ignored taps never reached the server.
  expect(deck.votes).toEqual([
    {statementId: 12, choice: 'agree'},
    {statementId: 13, choice: 'disagree'},
  ]);
});

test('the guard covers every statement after the first, not just the second', async () => {
  const deck = serveTwoCards();
  renderApp();

  tap(await screen.findByRole('button', {name: 'Agree'}, {timeout: 10_000}));
  await screen.findByText('Your response: Agree', {selector: '#voted-label'});
  tap(screen.getByRole('button', {name: /Move on/}));
  deck.answerAndMoveOn();
  await screen.findByText(SECOND_CARD.text, {selector: '#statement-text'});
  after(VOTE_INPUT_GUARD_MS);
  tap(screen.getByRole('button', {name: 'Pass'}));
  await screen.findByText('Your response: Pass', {selector: '#voted-label'});
  tap(screen.getByRole('button', {name: /Move on/}));
  deck.answerAndMoveOn();

  // Still guarded: the clock has not moved since the third card appeared.
  expect(await screen.findByText(THIRD_CARD.text, {selector: '#statement-text'})).toBeVisible();
  tap(screen.getByRole('button', {name: 'Agree'}));

  expect(screen.queryByText('Your response: Agree', {selector: '#voted-label'})).toBeNull();
  after(VOTE_INPUT_GUARD_MS);
  tap(screen.getByRole('button', {name: 'Disagree'}));

  expect(await screen.findByText('Your response: Disagree', {selector: '#voted-label'})).toBeVisible();
  expect(deck.votes).toEqual([
    {statementId: 12, choice: 'agree'},
    {statementId: 13, choice: 'pass'},
    {statementId: 14, choice: 'disagree'},
  ]);
});

test('an assistive-technology click on a new card gets the pointer window, not the key window', async () => {
  const deck = serveTwoCards();
  renderApp();

  tap(await screen.findByRole('button', {name: 'Agree'}, {timeout: 10_000}));
  await screen.findByText('Your response: Agree', {selector: '#voted-label'});
  tap(screen.getByRole('button', {name: /Move on/}));
  deck.answerAndMoveOn();
  await screen.findByText(SECOND_CARD.text, {selector: '#statement-text'});

  // Inside the pointer window: ignored, like a tap.
  activateWithAssistiveTech(screen.getByRole('button', {name: 'Agree'}));
  expect(screen.queryByText(/Your response:/, {selector: '#voted-label'})).toBeNull();

  // Past the pointer window, inside the key window: no keydown came first, so it counts.
  after(VOTE_INPUT_GUARD_MS);
  activateWithAssistiveTech(screen.getByRole('button', {name: 'Disagree'}));

  expect(await screen.findByText('Your response: Disagree', {selector: '#voted-label'})).toBeVisible();
  expect(deck.votes).toEqual([
    {statementId: 12, choice: 'agree'},
    {statementId: 13, choice: 'disagree'},
  ]);
});
