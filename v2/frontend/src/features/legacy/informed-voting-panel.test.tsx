import {QueryClientProvider} from '@tanstack/react-query';
import {fireEvent, render, screen, waitFor, within} from '@testing-library/react';
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
    viewer: {state: 'participant', pseudonym: 'quiet-otter'}, spaceWarning: null, scheduledTransition: null, cleanup: false,
    tabs: [{key: 'informed-voting', label: 'Informed vote', dataHref: '/api/v1/conversations/community-strategy/informed-voting'}],
    defaultTab: 'informed-voting', reveal: null,
    statementContribution: {unlockAfter: 0, quota: 3, used: 0},
    capabilities: {participate: true, moderate: false},
    links: {self: '/api/v1/conversations/community-strategy/workspace', conversation: '/c/community-strategy', about: '/c/community-strategy/about', join: '/accept/community-strategy', results: '/c/community-strategy/report'},
    ...overrides,
  } as Workspace;
}

function deck(cards: Card[]) {
  return http.get(url('/api/v1/conversations/community-strategy/informed-voting'), () => deckResponse(cards));
}

function deckResponse(cards: Card[]) {
  return HttpResponse.json({data: {
    slug: 'community-strategy', title: 'Community strategy', pseudonym: 'quiet-otter', cards,
    progress: {completed: cards.filter((c) => c.voted).length, total: cards.length, remaining: cards.filter((c) => !c.voted).length, allDone: cards.every((c) => c.voted)},
    capabilities: {vote: true},
    links: {self: '/api/v1/conversations/community-strategy/informed-voting', about: '/c/community-strategy/about', conversation: '/c/community-strategy', explore: '/c/community-strategy', arguments: '/c/community-strategy#tab-arguments'},
  }});
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
  // No 'closed' case: a closed workspace renders ClosedWorkspace instead of the tabs (#402).
])('under qqx, the completion panel carries no English: %s', async (_name, ws) => {
  renderAsQqx();
  renderPanel(ws, [answered]);
  await screen.findByRole('heading', {name: '(conv-p6-done-heading)'});

  expect(untranslatedCopy([document.querySelector('.p6-done')], CONTENT)).toEqual([]);
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

test('leaving the tab and coming back does not forget a vote just cast', async () => {
  // The server's deck follows the vote, as the real one does.
  let voted = false;
  let reads = 0;
  server.use(
    http.get(url('/api/v1/conversations/community-strategy/workspace'), () => HttpResponse.json({data: workspace()})),
    http.get(url('/api/v1/conversations/community-strategy/informed-voting'), () => {
      reads += 1;
      // A third card still open, so the deck stays up after this vote (a finished one gives
      // way to its completion panel).
      return deckResponse([{...unanswered, voted}, answered, {...unanswered, featuredStatementId: 35, statement: 'Wikis should publish their budgets.', voted: false}]);
    }),
    http.put(url('/api/v1/conversations/community-strategy/featured-statements/31/informed-vote'), () => {
      voted = true;
      return HttpResponse.json({data: {featuredStatementId: 31, choice: 'agree', links: {informedVoting: '/api/v1/conversations/community-strategy/informed-voting'}}});
    }),
  );
  const client = createQueryClient();
  const mount = () => render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/app/conversations/community-strategy/informed-voting']}><App /></MemoryRouter>
    </QueryClientProvider>,
  );

  const first = mount();
  await screen.findByText(STATEMENT);
  fireEvent.click(screen.getAllByRole('button', {name: 'Agree'})[0]!);
  expect(await screen.findByText('Agreed')).toBeVisible();
  // Leave at once: the cache must already know, whether or not the refetch has landed.
  first.unmount();

  // Same query client, as a tab switch keeps it: the first render must already know.
  mount();
  await screen.findByText(STATEMENT);
  expect(panel()!.querySelector('.p6-card[data-fs-id="31"]')).toHaveClass('p6-card--done');
  // And the server still gets the last word.
  await waitFor(() => expect(reads).toBeGreaterThanOrEqual(2));
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

test('the heading outline of the deck skips no level', async () => {
  renderPanel(workspace(), [unanswered, answered]);
  await screen.findByText(STATEMENT);

  // What a screen-reader user tabs through: the card on screen, not the hidden ones.
  const card = panel()!.querySelector('.p6-card:not(.p6-card--hidden)')!;
  const levels = [...card.querySelectorAll('h1, h2, h3, h4, h5, h6')].map((h) => Number(h.tagName[1]));
  expect(levels[0]).toBe(2);
  expect(within(card as HTMLElement).getByRole('heading', {level: 2})).toHaveTextContent(STATEMENT);
  levels.slice(1).forEach((level, i) => expect(level - (levels[i] ?? level)).toBeLessThanOrEqual(1));
  expect(within(card as HTMLElement).getAllByRole('heading', {level: 3}).length).toBeGreaterThan(0);
});

test('the card navigation is named for the statements it moves between', async () => {
  renderPanel(workspace(), [unanswered, answered]);
  await screen.findByText(STATEMENT);

  // Catches the arrows being read out as the buttons' names.
  expect(screen.getAllByRole('button', {name: 'Next statement'})[0]).toHaveTextContent('Next →');
  expect(screen.getAllByRole('button', {name: 'Previous statement'})[0]).toHaveTextContent('← Previous');
});


// #319: a card whose phase-6 statement does not exist yet renders without vote controls and
// can never be answered. No seek may stop on it, and it must not keep the deck from finishing.
const unvotable: Card = {featuredStatementId: 33, statement: 'Awaiting its phase-6 statement.', canVote: false, voted: false, arguments: {for: [], against: []}};
const later: Card = {featuredStatementId: 34, statement: 'Wikis should publish their budgets.', canVote: true, voted: false, arguments: {for: [], against: []}};
const cardButton = (id: number, name: string) => within(panel()!.querySelector<HTMLElement>(`.p6-card[data-fs-id="${id}"]`)!).getByRole('button', {name});
const shown = () => [...panel()!.querySelectorAll('.p6-card:not(.p6-card--hidden)')].map((card) => Number(card.getAttribute('data-fs-id')));

function acceptVote(id: number) {
  return http.put(url(`/api/v1/conversations/community-strategy/featured-statements/${id}/informed-vote`),
    () => HttpResponse.json({data: {featuredStatementId: id, choice: 'agree', links: {informedVoting: '/api/v1/conversations/community-strategy/informed-voting'}}}));
}

test('a returning participant does not resume on a card that cannot be voted', async () => {
  renderPanel(workspace(), [unvotable, unanswered]);
  await screen.findByText(STATEMENT);

  expect(shown()).toEqual([31]);
  // Skipped, but not claimed as answered: it was never voted.
  const card = panel()!.querySelector('.p6-card[data-fs-id="33"]')!;
  expect(card).not.toHaveClass('p6-card--done');
  expect(card.querySelector('.p6-answered-note')).not.toBeVisible();
});

test('a deck whose only open card cannot be voted counts as finished', async () => {
  renderPanel(workspace(), [answered, unvotable]);

  expect(await screen.findByRole('heading', {name: "You've given your informed opinion."})).toBeVisible();
  expect(panel()!.querySelector('.p6-card')).toBeNull();
});

test('after a vote the card stays in view for its confirmation, then the deck skips a card that cannot be voted', async () => {
  server.use(acceptVote(31));
  renderPanel(workspace(), [unanswered, unvotable, later]);
  await screen.findByText(STATEMENT);

  fireEvent.click(screen.getAllByRole('button', {name: 'Agree'})[0]!);
  expect(await screen.findByText('Agreed')).toBeVisible();
  // Inside the pause before the advance, the card just answered is still the one shown.
  await new Promise((resolve) => setTimeout(resolve, 100));
  expect(shown()).toEqual([31]);
  await waitFor(() => expect(shown()).toEqual([34]));
});

test('the last answer gives way to the completion panel, after the confirmation is seen', async () => {
  server.use(acceptVote(31));
  renderPanel(workspace(), [answered, unanswered, unvotable]);
  await screen.findByText(STATEMENT);

  fireEvent.click(cardButton(31, 'Agree'));
  expect(await screen.findByText('Agreed')).toBeVisible();
  expect(shown()).toEqual([31]);
  const heading = await screen.findByRole('heading', {name: "You've given your informed opinion."});
  expect(heading).toBeVisible();
  expect(panel()!.querySelector('.p6-card')).toBeNull();
  // The button that had focus went with the deck; focus lands on the completion heading.
  await waitFor(() => expect(heading).toHaveFocus());
});

test('the card counter counts the cards that can be answered, as the progress does', async () => {
  renderPanel(workspace(), [unanswered, unvotable, later]);
  await screen.findByText(STATEMENT);

  const counter = () => panel()!.querySelector('.p6-card:not(.p6-card--hidden) .p6-nav-counter')!;
  expect(counter()).toHaveTextContent('1 of 2');
  // Next steps over the card without vote controls, as the advance after a vote does.
  fireEvent.click(cardButton(31, 'Next statement'));
  await waitFor(() => expect(shown()).toEqual([34]));
  expect(counter()).toHaveTextContent('2 of 2');
  expect(cardButton(34, 'Next statement')).toBeDisabled();
  fireEvent.click(cardButton(34, 'Previous statement'));
  await waitFor(() => expect(shown()).toEqual([31]));
});

for (const [name, cards, next] of [
  ['an advance', [unanswered, later], 34],
  ['the completion panel', [unanswered, answered], null],
] as const) {
  test(`${name} after a vote leaves focus alone once the participant has moved it`, async () => {
    server.use(acceptVote(31));
    renderPanel(workspace(), [...cards]);
    await screen.findByText(STATEMENT);
    const elsewhere = document.createElement('button');
    document.body.append(elsewhere);

    fireEvent.click(cardButton(31, 'Agree'));
    expect(await screen.findByText('Agreed')).toBeVisible();
    elsewhere.focus();
    if (next === null) await screen.findByRole('heading', {name: "You've given your informed opinion."});
    else await waitFor(() => expect(shown()).toEqual([next]));
    await new Promise((resolve) => setTimeout(resolve, 100));
    expect(elsewhere).toHaveFocus();
    elsewhere.remove();
  });
}

test('Previous during the pause stays on the chosen card, focus inside the shown card', async () => {
  server.use(acceptVote(31));
  renderPanel(workspace(), [answered, unanswered, later]);
  await screen.findByText(STATEMENT);

  fireEvent.click(cardButton(31, 'Agree'));
  expect(await screen.findByText('Agreed')).toBeVisible();
  // Within the 400 ms pause before the advance to card 34.
  fireEvent.click(cardButton(31, 'Previous statement'));
  await waitFor(() => expect(shown()).toEqual([32]));
  // Past the moment the cancelled advance would have fired.
  await new Promise((resolve) => setTimeout(resolve, 500));
  expect(shown()).toEqual([32]);
  expect(document.activeElement).not.toBe(document.body);
  expect(document.activeElement!.closest('.p6-card')).toBe(panel()!.querySelector('.p6-card[data-fs-id="32"]'));
});

test('Previous during the pause after the last answer keeps focus when the deck gives way', async () => {
  server.use(acceptVote(31));
  renderPanel(workspace(), [answered, unanswered, {...later, voted: true}]);
  await screen.findByText(STATEMENT);

  fireEvent.click(cardButton(31, 'Agree'));
  expect(await screen.findByText('Agreed')).toBeVisible();
  fireEvent.click(cardButton(31, 'Previous statement'));
  await waitFor(() => expect(shown()).toEqual([32]));
  await waitFor(() => expect(document.activeElement!.closest('.p6-card')).toBe(panel()!.querySelector('.p6-card[data-fs-id="32"]')));
  // The deck is answered, so it still gives way to the completion panel, and focus,
  // which was on a card that went with the deck, follows to its heading.
  const heading = await screen.findByRole('heading', {name: "You've given your informed opinion."});
  await waitFor(() => expect(heading).toHaveFocus());
});

test('a finished deck shows a card again when a refetch makes one votable', async () => {
  // A statement initialised after the participant finished: its card becomes votable.
  let reads = 0;
  const client = createQueryClient();
  server.use(
    http.get(url('/api/v1/conversations/community-strategy/workspace'), () => HttpResponse.json({data: workspace()})),
    http.get(url('/api/v1/conversations/community-strategy/informed-voting'), () => {
      reads += 1;
      return deckResponse([answered, {...unvotable, canVote: reads > 1}]);
    }),
  );
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/app/conversations/community-strategy/informed-voting']}><App /></MemoryRouter>
    </QueryClientProvider>,
  );
  await screen.findByRole('heading', {name: "You've given your informed opinion."});

  await client.invalidateQueries({queryKey: ['informed-voting']});
  await client.refetchQueries();
  await waitFor(() => expect(panel()!.querySelector('.p6-card[data-fs-id="33"]')).not.toBeNull());
  expect(screen.queryByRole('heading', {name: "You've given your informed opinion."})).toBeNull();
  // The card shown is the one that reopened the deck, not the one answered earlier.
  expect(shown()).toEqual([33]);
});

test('a deck that loses a card before the current one stays on the current card', async () => {
  // On the second of three open cards; a refetch drops the first (a statement unfeatured
  // mid-session). The participant stays where they were instead of skipping ahead.
  let reads = 0;
  const client = createQueryClient();
  const third: Card = {...later, featuredStatementId: 35, statement: 'Budgets should be reviewed yearly.'};
  server.use(
    http.get(url('/api/v1/conversations/community-strategy/workspace'), () => HttpResponse.json({data: workspace()})),
    http.get(url('/api/v1/conversations/community-strategy/informed-voting'), () => {
      reads += 1;
      return deckResponse(reads === 1 ? [unanswered, later, third] : [later, third]);
    }),
  );
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/app/conversations/community-strategy/informed-voting']}><App /></MemoryRouter>
    </QueryClientProvider>,
  );
  await screen.findByText(STATEMENT);
  fireEvent.click(cardButton(31, 'Next statement'));
  await waitFor(() => expect(shown()).toEqual([34]));

  await client.invalidateQueries({queryKey: ['informed-voting']});
  await client.refetchQueries();
  await waitFor(() => expect(reads).toBeGreaterThanOrEqual(2));
  await waitFor(() => expect(panel()!.querySelector('.p6-card[data-fs-id="31"]')).toBeNull());
  expect(shown()).toEqual([34]);
});

test('a deck that shrinks under the current card still shows a card and its navigation', async () => {
  // The advance after the vote heads for the third card; the refetch the vote triggers has
  // lost the card before it, so the deck is one shorter (a statement unfeatured mid-session).
  let reads = 0;
  server.use(
    http.get(url('/api/v1/conversations/community-strategy/workspace'), () => HttpResponse.json({data: workspace()})),
    http.get(url('/api/v1/conversations/community-strategy/informed-voting'), () => {
      reads += 1;
      return deckResponse(reads === 1 ? [answered, unanswered, later] : [answered, later]);
    }),
    acceptVote(31),
  );
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={['/app/conversations/community-strategy/informed-voting']}><App /></MemoryRouter>
    </QueryClientProvider>,
  );
  await screen.findByText(STATEMENT);

  fireEvent.click(cardButton(31, 'Agree'));
  await waitFor(() => expect(reads).toBeGreaterThanOrEqual(2));
  // Past the advance, which targeted index 2 of a deck that now has two cards.
  await new Promise((resolve) => setTimeout(resolve, 600));
  expect(shown()).toEqual([34]);
  expect(cardButton(34, 'Previous statement')).toBeEnabled();
});
