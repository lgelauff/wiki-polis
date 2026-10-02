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

const FIRST = 'Regional communities should share infrastructure funding.';
const SECOND = 'Small wikis should get translation support first.';

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

/** Both cards answered, which is how a participant who returns to a finished deck finds it:
 *  the panel seeds `done` at mount and the deck opens on card 1. */
const deck: Card[] = [
  {featuredStatementId: 31, statement: FIRST, canVote: true, voted: true, arguments: {for: [], against: []}},
  {featuredStatementId: 32, statement: SECOND, canVote: true, voted: true, arguments: {for: [], against: []}},
];

function renderPanel() {
  server.use(
    http.get(url('/api/v1/conversations/community-strategy/workspace'), () => HttpResponse.json({data: workspace()})),
    http.get(url('/api/v1/conversations/community-strategy/informed-voting'), () => HttpResponse.json({data: {
      slug: 'community-strategy', title: 'Community strategy', pseudonym: 'quiet-otter', cards: deck,
      progress: {completed: deck.length, total: deck.length, remaining: 0, allDone: true},
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

test.fails("#361: on a deck that is already finished, the 'you are done' message comes before the card", async () => {
  renderPanel();
  const done = await screen.findByRole('heading', {name: "You've given your informed opinion."});

  // Nothing to present as live is allowed to sit between the reader and the message that says
  // there is nothing left to do. Either the message leads, or the deck is collapsed behind it:
  // both are acceptable, a fully interactive card above the message is not.
  const firstLive = document.querySelector('.p6-card .vote-choice');
  const doneLeads = firstLive === null
    || Boolean(done.parentElement!.compareDocumentPosition(firstLive) & Node.DOCUMENT_POSITION_FOLLOWING);

  expect(doneLeads, '#361: a participant returning to a deck they already finished should read "you have given your informed opinion" BEFORE a live vote card, not find a card with three unselected vote buttons above it; the interactive card was rendered ahead of the completion message')
    .toBe(true);
});

test("#361: a deck that is already finished still says so on arrival", async () => {
  renderPanel();

  expect(await screen.findByRole('heading', {name: "You've given your informed opinion."}),
    '#361: a participant returning to a finished deck must be told they are done when the tab opens, without having to vote or navigate first')
    .toBeVisible();
});
