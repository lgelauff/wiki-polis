import {Suspense} from 'react';
import {QueryClientProvider} from '@tanstack/react-query';
import {render, screen} from '@testing-library/react';
import {http, HttpResponse} from 'msw';
import {MemoryRouter} from 'react-router-dom';
import {expect, test} from 'vitest';

import type {components} from '../../api/schema';
import {LegacyPreliminaryResultsPanel} from './preliminary-results-panel';
import {MessageProvider} from '../../i18n/messages';
import {createQueryClient} from '../../query-client';
import {server} from '../../test/server';

type Statement = components['schemas']['ResultsReport']['statements'][number];

function statement(id: number, viewerChoice: Statement['viewerChoice']): Statement {
  return {
    featuredStatementId: id, statement: `Statement ${id}`,
    initial: {counts: {agree: 1, pass: 1, disagree: 1, voters: 3}, percentages: {agree: 33, pass: 33, disagree: 34}},
    informed: {counts: {agree: 1, pass: 1, disagree: 1, voters: 3}, percentages: {agree: 33, pass: 33, disagree: 34}},
    agreementShift: 0, viewerChoice,
  };
}

test('the Yours column shows each recorded vote in the past tense, with the class that colours it', async () => {
  server.use(http.get(new URL('/api/v1/conversations/community-strategy/results', globalThis.location.origin).toString(), () => HttpResponse.json({data: {
    slug: 'community-strategy', title: 'Community strategy', publication: 'preliminary', resultsAvailable: true,
    openedAt: '2026-05-01T12:00:00Z', closedAt: null,
    context: {phase: 'Informed vote', status: 'provisional', method: 'Live comparison.'},
    participation: {initialRound: 3, informedRound: 3, matchedRounds: null},
    dataAvailability: {detailedCounts: true, opinionGroups: false},
    moderation: {excludedStatements: 0, excludedParticipants: 0},
    statements: [statement(1, 'agree'), statement(2, 'disagree'), statement(3, 'pass'), statement(4, null)],
    opinionGroups: [],
    viewer: {participating: true, pseudonym: 'quiet-otter', revealState: null},
    links: {self: '/api/v1/conversations/community-strategy/results', conversation: '/c/community-strategy', about: '/c/community-strategy/about'},
  }})));
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter>
        <Suspense fallback={null}>
          <MessageProvider locale="en"><LegacyPreliminaryResultsPanel slug="community-strategy" /></MessageProvider>
        </Suspense>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  await screen.findByRole('table');

  // Catches a choice shown as the button's present tense, the wrong choice's message, or a
  // modifier class the stylesheet does not define (it colours --agreed/--disagreed/--passed).
  const cells = [...document.querySelectorAll('tbody .p6-col-mine')].map((cell) => [cell.textContent, cell.querySelector('.p6-my-vote')?.className ?? '']);
  expect(cells).toEqual([
    ['Agreed', 'p6-my-vote p6-my-vote--agreed'],
    ['Disagreed', 'p6-my-vote p6-my-vote--disagreed'],
    ['Passed', 'p6-my-vote p6-my-vote--passed'],
    ['—', ''],
  ]);
});
