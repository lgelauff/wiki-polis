import {Suspense} from 'react';
import {QueryClientProvider} from '@tanstack/react-query';
import {render, screen, within} from '@testing-library/react';
import {http, HttpResponse} from 'msw';
import {MemoryRouter} from 'react-router-dom';
import {expect, test} from 'vitest';

import type {components} from '../../api/schema';
import {LegacyPreliminaryResultsPanel} from './preliminary-results-panel';
import {MessageProvider} from '../../i18n/messages';
import {createQueryClient} from '../../query-client';
import {server} from '../../test/server';
import dutch from '../../../../i18n/nl.json';

type Statement = components['schemas']['ResultsReport']['statements'][number];

function statement(id: number, viewerChoice: Statement['viewerChoice']): Statement {
  return {
    featuredStatementId: id, statement: `Statement ${id}`,
    initial: {counts: {agree: 1, pass: 1, disagree: 1, voters: 3}, percentages: {agree: 33, pass: 33, disagree: 34}},
    informed: {counts: {agree: 1, pass: 1, disagree: 1, voters: 3}, percentages: {agree: 33, pass: 33, disagree: 34}},
    agreementShift: 0, viewerChoice, viewerGroupChoice: null, viewerMatchesGroup: null, personalDelta: null,
  };
}

function serveResults(statements: Statement[]) {
  server.use(http.get(new URL('/api/v1/conversations/community-strategy/results', globalThis.location.origin).toString(), () => HttpResponse.json({data: {
    slug: 'community-strategy', title: 'Community strategy', publication: 'preliminary', resultsAvailable: true,
    openedAt: '2026-05-01T12:00:00Z', closedAt: null,
    context: {phase: 'Informed vote', status: 'provisional', method: 'Live comparison.'},
    participation: {initialRound: null, informedRound: 3, matchedRounds: null},
    dataAvailability: {detailedCounts: true, opinionGroups: false, personalLens: false},
    moderation: {excludedStatements: 0, excludedParticipants: 0},
    statements,
    opinionGroups: [],
    viewer: {participating: true, pseudonym: 'quiet-otter', revealState: null},
    links: {self: '/api/v1/conversations/community-strategy/results', conversation: '/c/community-strategy', about: '/c/community-strategy/about'},
  }})));
}

function renderPanel(locale = 'en') {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter>
        <Suspense fallback={null}>
          <MessageProvider locale={locale}><LegacyPreliminaryResultsPanel slug="community-strategy" /></MessageProvider>
        </Suspense>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

test('the viewer’s own recorded vote stays labelled and styled on ranked statements', async () => {
  const tally = (agree: number, pass: number, disagree: number): NonNullable<Statement['informed']> => ({
    counts: {agree, pass, disagree, voters: agree + pass + disagree},
    percentages: {agree: agree * 5, pass: pass * 5, disagree: disagree * 5},
  });
  const rows = [
    {...statement(1, 'agree'), informed: tally(18, 0, 2)},
    {...statement(2, 'disagree'), informed: tally(16, 0, 4)},
    {...statement(3, 'pass'), informed: tally(10, 0, 10)},
    {...statement(4, null), informed: tally(10, 1, 9)},
  ];
  serveResults(rows);
  renderPanel();
  await screen.findByText('Agreed');

  const classes = [...document.querySelectorAll('.report-stmt-row .p6-my-vote')].map((badge) => badge.className);
  expect(classes).toEqual(expect.arrayContaining([
    'p6-my-vote p6-my-vote--agreed',
    'p6-my-vote p6-my-vote--disagreed',
    'p6-my-vote p6-my-vote--passed',
  ]));
  const ownVoteRows = [...document.querySelectorAll('.report-stmt-row p')]
    .filter((row) => row.textContent?.startsWith('Yours:'));
  expect(ownVoteRows.some((row) => row.querySelector('.muted')?.textContent === '—')).toBe(true);
});

test('preliminary results rank informed-vote consensus and contention without phase comparisons', async () => {
  const tallies = (agree: number, pass: number, disagree: number): NonNullable<Statement['informed']> => ({
    counts: {agree: 10, pass: 2, disagree: 8, voters: 20},
    percentages: {agree, pass, disagree},
  });
  const rows = [
    {...statement(1, null), initial: tallies(95, 0, 5), informed: tallies(10, 10, 80), agreementShift: -65},
    {...statement(2, null), initial: tallies(10, 0, 90), informed: tallies(85, 5, 10), agreementShift: 75},
    {...statement(3, null), initial: tallies(50, 0, 50), informed: tallies(45, 10, 45), agreementShift: -5},
    {...statement(4, null), initial: tallies(20, 0, 80), informed: tallies(15, 10, 75), agreementShift: -5},
  ];
  serveResults(rows);
  renderPanel();

  const highest = await screen.findByRole('heading', {name: 'Highest agreement'});
  const consensusSection = highest.closest<HTMLElement>('.report-section')!;
  expect(within(consensusSection).getByText('Statement 2')).toBeVisible();
  expect(within(consensusSection).queryByText('Statement 1')).not.toBeInTheDocument();

  const divisive = screen.getByRole('heading', {name: 'Most divisive'});
  const contentionSection = divisive.closest<HTMLElement>('.report-section')!;
  expect(within(contentionSection).getByText('Statement 3')).toBeVisible();
  expect(within(contentionSection).queryByText('Statement 2')).not.toBeInTheDocument();
  expect(screen.queryByRole('columnheader', {name: 'Initial vote'})).not.toBeInTheDocument();
  expect(screen.queryByRole('columnheader', {name: 'Shift'})).not.toBeInTheDocument();
});

test('under nl, percentages are written the Dutch way, with a decimal comma', async () => {
  // toFixed would write "62.5" whatever the language; the number, not the message, owns the %.
  server.use(http.get(new URL('/api/v1/i18n/:locale', globalThis.location.origin).toString(), () => HttpResponse.json(dutch)));
  const tally = {counts: {agree: 5, pass: 1, disagree: 2, voters: 8}, percentages: {agree: 62.5, pass: 12.5, disagree: 25}};
  serveResults([{...statement(1, null), initial: tally, informed: tally, agreementShift: -2.5}]);
  renderPanel('nl');
  await screen.findByRole('heading', {name: 'Meeste overeenstemming'});

  expect(screen.getAllByText('62,5% eens · 12,5% overgeslagen')).toHaveLength(2);
  expect(screen.getAllByTitle('Eens 62,5% · Oneens 25,0% · Overgeslagen 12,5%')).toHaveLength(2);
  expect(screen.queryByText('-2,5%')).not.toBeInTheDocument();
});
