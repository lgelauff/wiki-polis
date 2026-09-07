import {QueryClientProvider} from '@tanstack/react-query';
import {render, screen} from '@testing-library/react';
import {http, HttpResponse} from 'msw';
import {MemoryRouter} from 'react-router-dom';
import {expect, test} from 'vitest';

import {App} from '../../app';
import {createQueryClient} from '../../query-client';
import {server} from '../../test/server';

/** The informed-voting contract for a participant who already answered everything. */
function answeredDeck() {
  return http.get(
    new URL('/api/v1/conversations/community-strategy/informed-voting', globalThis.location.origin).toString(),
    () => HttpResponse.json({
      data: {
        slug: 'community-strategy',
        title: 'Community strategy',
        pseudonym: 'quiet-otter',
        cards: [{
          featuredStatementId: 31,
          statement: 'Regional communities should share infrastructure funding.',
          canVote: true,
          voted: true,
          arguments: {for: [], against: []},
        }],
        progress: {completed: 1, total: 1, remaining: 0, allDone: true},
        capabilities: {vote: true},
        links: {
          self: '/api/v1/conversations/community-strategy/informed-voting',
          about: '/c/community-strategy/about',
          conversation: '/c/community-strategy',
          explore: '/c/community-strategy',
          arguments: '/c/community-strategy#tab-arguments',
        },
      },
    }),
  );
}

function unansweredDeck() {
  return http.get(
    new URL('/api/v1/conversations/community-strategy/informed-voting', globalThis.location.origin).toString(),
    () => HttpResponse.json({
      data: {
        slug: 'community-strategy', title: 'Community strategy', pseudonym: 'quiet-otter',
        cards: [{
          featuredStatementId: 31,
          statement: 'Regional communities should share infrastructure funding.',
          canVote: true, voted: false, arguments: {for: [], against: []},
        }],
        progress: {completed: 0, total: 1, remaining: 1, allDone: false},
        capabilities: {vote: true},
        links: {
          self: '/api/v1/conversations/community-strategy/informed-voting',
          about: '/c/community-strategy/about', conversation: '/c/community-strategy',
          explore: '/c/community-strategy', arguments: '/c/community-strategy#tab-arguments',
        },
      },
    }),
  );
}

function renderDeck() {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={['/app/conversations/community-strategy/informed-voting']}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

test('a returning participant sees that their cards are already answered', async () => {
  // The regression: votes/terminalIds started empty and ignored card.voted, so an
  // answered deck rendered as untouched and participants voted a second time.
  server.use(answeredDeck());
  renderDeck();

  const card = await screen.findByText('Regional communities should share infrastructure funding.');
  const shell = card.closest('.p6-card');
  expect(shell).toHaveClass('p6-card--done');
  // Assert the DOM, not the stylesheet: vitest runs jsdom without CSS, so a CSS-only
  // gate would make toBeVisible() true on every card. The hidden attribute is the gate.
  expect(screen.getByText(/Already voted/)).toBeVisible();
  expect(screen.getByText(/Choosing again will replace it/)).toBeVisible();
});

test('a finished deck shows its completion panel', async () => {
  server.use(answeredDeck());
  renderDeck();

  expect(await screen.findByRole('heading', {name: "You've completed informed voting."})).toBeVisible();
});

test('an unanswered card claims nothing', async () => {
  // The gate is an attribute, not a stylesheet rule. Without this, a broken CSS selector
  // would announce "Already voted" on every untouched card and no test would notice.
  server.use(unansweredDeck());
  renderDeck();

  await screen.findByText('Regional communities should share infrastructure funding.');
  // The note is rendered but carries `hidden`; the hint is not rendered at all. Both
  // must be inert -- queryByText matches hidden nodes, so assert visibility for the
  // first and absence for the second.
  expect(screen.queryByText(/Already voted/)).not.toBeVisible();
  expect(screen.queryByText(/Choosing again will replace it/)).not.toBeInTheDocument();
});
