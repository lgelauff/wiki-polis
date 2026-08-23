import {QueryClientProvider} from '@tanstack/react-query';
import {http, HttpResponse} from 'msw';
import {fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {expect, test} from 'vitest';

import {App} from '../../app';
import {createQueryClient} from '../../query-client';
import {server} from '../../test/server';

/**
 * Serve a partially-voted phase 6 deck: the participant has answered the first
 * two cards in an earlier session and has seven left. No shared fixture produces
 * this state, which is why the resume defect reached production.
 */
function partiallyVotedDeck() {
  const cards = Array.from({length: 9}, (_, index) => ({
    featuredStatementId: 31 + index,
    statement: `Featured statement ${index + 1}.`,
    canVote: true,
    voted: index < 2,
    arguments: {for: [], against: []},
  }));
  server.use(
    http.get(
      new URL(
        '/api/v1/conversations/community-strategy/informed-voting',
        globalThis.location.origin,
      ).toString(),
      () => HttpResponse.json({
        data: {
          slug: 'community-strategy',
          title: 'Community strategy',
          pseudonym: 'quiet-otter',
          cards,
          progress: {completed: 2, total: 9, remaining: 7, allDone: false},
          capabilities: {vote: true},
          links: {
            self: '/api/v1/conversations/community-strategy/informed-voting',
            about: '/c/community-strategy/about',
            conversation: '/c/community-strategy',
          },
        },
      }),
    ),
  );
}

async function openInformedVoting() {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={['/app/conversations/community-strategy/explore']}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  fireEvent.click(await screen.findByRole('tab', {name: 'Informed vote'}));
}

function card(featuredStatementId: number) {
  return document.querySelector<HTMLElement>(`.p6-card[data-fs-id="${featuredStatementId}"]`);
}

test('resumes at the first unanswered card instead of restarting the deck', async () => {
  partiallyVotedDeck();
  await openInformedVoting();

  // Card 33 is the first with voted: false, so it is the one on screen.
  expect(await screen.findByText('Featured statement 3.')).toBeInTheDocument();
  expect(card(33)?.className).not.toContain('p6-card--hidden');

  // The two already answered upstream stay out of the way.
  expect(card(31)?.className).toContain('p6-card--hidden');
  expect(card(32)?.className).toContain('p6-card--hidden');
});

test('marks cards already voted upstream as done', async () => {
  partiallyVotedDeck();
  await openInformedVoting();

  await screen.findByText('Featured statement 3.');
  expect(card(31)?.className).toContain('p6-card--done');
  expect(card(32)?.className).toContain('p6-card--done');
  expect(card(33)?.className).not.toContain('p6-card--done');
});

test('does not drop back onto an answered card after leaving and returning to the tab', async () => {
  // The projection is authoritative and changes once the vote lands upstream.
  const answered = new Set<number>();
  let projectionReads = 0;
  server.use(
    http.get(
      new URL(
        '/api/v1/conversations/community-strategy/informed-voting',
        globalThis.location.origin,
      ).toString(),
      () => {
        projectionReads += 1;
        const cards = Array.from({length: 3}, (_, index) => ({
          featuredStatementId: 51 + index,
          statement: `Resumable statement ${index + 1}.`,
          canVote: true,
          voted: answered.has(51 + index),
          arguments: {for: [], against: []},
        }));
        return HttpResponse.json({
          data: {
            slug: 'community-strategy',
            title: 'Community strategy',
            pseudonym: 'quiet-otter',
            cards,
            progress: {
              completed: answered.size,
              total: 3,
              remaining: 3 - answered.size,
              allDone: answered.size === 3,
            },
            capabilities: {vote: true},
            links: {
              self: '/api/v1/conversations/community-strategy/informed-voting',
              about: '/c/community-strategy/about',
              conversation: '/c/community-strategy',
            },
          },
        });
      },
    ),
    http.put(
      new URL(
        '/api/v1/conversations/community-strategy/featured-statements/51/informed-vote',
        globalThis.location.origin,
      ).toString(),
      async ({request}) => {
        const body = await request.json() as {choice: 'agree' | 'pass' | 'disagree'};
        answered.add(51);
        return HttpResponse.json({
          data: {
            featuredStatementId: 51,
            choice: body.choice,
            links: {informedVoting: '/api/v1/conversations/community-strategy/informed-voting'},
          },
        });
      },
    ),
  );

  await openInformedVoting();
  await screen.findByText('Resumable statement 1.');

  fireEvent.click(within(card(51)!).getByRole('button', {name: 'Agree'}));
  await waitFor(() => expect(answered.has(51)).toBe(true), {timeout: 5000});

  // The vote must invalidate the projection; without that the cache keeps
  // voted:false for card 51 and the remount below reseeds onto it.
  await waitFor(() => expect(projectionReads).toBeGreaterThan(1), {timeout: 5000});

  // Leave the tab and come back — this unmounts and remounts the panel, which
  // re-runs the seeding initialisers against whatever the cache now holds.
  fireEvent.click(screen.getByRole('tab', {name: 'Vote'}));
  fireEvent.click(screen.getByRole('tab', {name: 'Informed vote'}));

  await waitFor(() => expect(card(51)?.className).toContain('p6-card--hidden'), {timeout: 5000});
  expect(card(52)?.className).not.toContain('p6-card--hidden');
});

test('shows the completion state when every card was answered upstream', async () => {
  const cards = Array.from({length: 3}, (_, index) => ({
    featuredStatementId: 41 + index,
    statement: `Answered statement ${index + 1}.`,
    canVote: true,
    voted: true,
    arguments: {for: [], against: []},
  }));
  server.use(
    http.get(
      new URL(
        '/api/v1/conversations/community-strategy/informed-voting',
        globalThis.location.origin,
      ).toString(),
      () => HttpResponse.json({
        data: {
          slug: 'community-strategy',
          title: 'Community strategy',
          pseudonym: 'quiet-otter',
          cards,
          progress: {completed: 3, total: 3, remaining: 0, allDone: true},
          capabilities: {vote: true},
          links: {
            self: '/api/v1/conversations/community-strategy/informed-voting',
            about: '/c/community-strategy/about',
            conversation: '/c/community-strategy',
          },
        },
      }),
    ),
  );
  await openInformedVoting();

  // Reported from staging: a deck with every card answered reopened on card 1
  // with three live vote buttons, above "You've completed informed voting."
  // Voting there overwrites a recorded vote.
  await waitFor(() => expect(document.querySelector('.p6-done')).not.toBeNull(), {timeout: 5000});
  expect(screen.queryByText('Answered statement 1.')).toBeNull();
  expect(document.querySelector('.p6-card')).toBeNull();
  expect(screen.queryByRole('button', {name: 'Agree'})).toBeNull();
});
