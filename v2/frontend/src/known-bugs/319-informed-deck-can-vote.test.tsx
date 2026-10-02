// Known bug: the failing tests use test.fails. When the fix lands they pass, vitest reports
// that as a failure, and the fix turns them back into plain test().
import {QueryClientProvider} from '@tanstack/react-query';
import {render, screen} from '@testing-library/react';
import {http, HttpResponse} from 'msw';
import {MemoryRouter} from 'react-router-dom';
import {expect, test} from 'vitest';

import type {components} from '../api/schema';
import {App} from '../app';
import {createQueryClient} from '../query-client';
import {server} from '../test/server';

type Workspace = components['schemas']['ConversationWorkspace'];
type Card = components['schemas']['InformedVotingCard'];

const url = (path: string) => new URL(path, globalThis.location.origin).toString();

const NOT_LIVE = 'A statement confirmed after the round opened.';
const VOTABLE = 'Regional communities should share infrastructure funding.';

function workspace(): Workspace {
  return {
    slug: 'community-strategy', title: 'Community strategy', space: 'real', status: 'open',
    descriptionHtml: '', outroHtml: null,
    viewer: {state: 'participant', pseudonym: 'quiet-otter'}, spaceWarning: null, scheduledTransition: null,
    tabs: [{key: 'informed-voting', label: 'Informed vote', dataHref: '/api/v1/conversations/community-strategy/informed-voting'}],
    defaultTab: 'informed-voting', reveal: null,
    statementContribution: {unlockAfter: 0, quota: 3, used: 0},
    capabilities: {participate: true, moderate: false},
    links: {self: '/api/v1/conversations/community-strategy/workspace', conversation: '/c/community-strategy', about: '/c/community-strategy/about', join: '/accept/community-strategy', results: '/c/community-strategy/report'},
  } as Workspace;
}

/** Card 1 is a featured statement an admin confirmed after the round was initialised, so
 *  `phase6_polis_statement_id` is still null: the server sends canVote=false and, because
 *  `voted` needs that same id, voted=false too. It can never become answered. */
const notLive: Card = {
  featuredStatementId: 41, statement: NOT_LIVE, canVote: false, voted: false,
  arguments: {for: [], against: []},
};
const votable: Card = {
  featuredStatementId: 42, statement: VOTABLE, canVote: true, voted: false,
  arguments: {for: [], against: []},
};

function renderPanel(cards: Card[]) {
  server.use(
    http.get(url('/api/v1/conversations/community-strategy/workspace'), () => HttpResponse.json({data: workspace()})),
    http.get(url('/api/v1/conversations/community-strategy/informed-voting'), () => HttpResponse.json({data: {
      slug: 'community-strategy', title: 'Community strategy', pseudonym: 'quiet-otter', cards,
      progress: {completed: 0, total: cards.length, remaining: cards.length, allDone: false},
      capabilities: {vote: true},
      links: {self: '/api/v1/conversations/community-strategy/informed-voting', about: '/c/community-strategy/about', conversation: '/c/community-strategy', explore: '/c/community-strategy', arguments: '/c/community-strategy#tab-arguments'},
    }})),
  );
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={['/app/conversations/community-strategy/informed-voting']}><App /></MemoryRouter>
    </QueryClientProvider>,
  );
}

const card = (id: number) => document.querySelector<HTMLElement>(`.p6-card[data-fs-id="${id}"]`)!;

test.fails('#319: a deck opens on the first card the participant can actually answer', async () => {
  renderPanel([notLive, votable]);
  await screen.findByText(VOTABLE);

  expect(card(42), '#319: opening the deck should skip the card with no vote controls and land on the first card that can be answered, so the participant is not parked on a card they can do nothing with')
    .not.toHaveClass('p6-card--hidden');
  expect(card(41)).toHaveClass('p6-card--hidden');
});

test.fails('#319: answering every votable card finishes the deck even when a card has no vote controls', async () => {
  renderPanel([{...votable, voted: true}, notLive]);
  await screen.findByText(NOT_LIVE);

  expect(await screen.findByRole('heading', {name: "You've given your informed opinion."}),
    '#319: a participant who has answered every card that can be answered has finished the round, so the completion panel must be reachable; a card with canVote=false can never be answered and must not count against completion')
    .toBeVisible();
});

test('#319 (canary): the deck renders both cards from this mock', async () => {
  // A plain test, so that drift in the mock data or the selectors fails loudly instead of
  // being absorbed by the expected failures above.
  renderPanel([notLive, votable]);
  await screen.findByText(VOTABLE);

  expect(card(41)).not.toBeNull();
  expect(card(42)).not.toBeNull();
  expect(screen.getByText(NOT_LIVE)).toBeInTheDocument();
});
