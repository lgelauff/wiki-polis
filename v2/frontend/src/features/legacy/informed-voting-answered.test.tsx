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
  expect(screen.getByText('Answered')).toBeVisible();
});

test('a finished deck opens on its completion panel, not on card one', async () => {
  server.use(answeredDeck());
  renderDeck();

  expect(await screen.findByRole('heading', {name: "You've completed informed voting."})).toBeVisible();
});
