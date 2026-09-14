import {Suspense} from 'react';
import {QueryClientProvider} from '@tanstack/react-query';
import {render, screen, within} from '@testing-library/react';
import {http, HttpResponse} from 'msw';
import {MemoryRouter} from 'react-router-dom';
import {expect, test} from 'vitest';

import type {components} from '../../api/schema';
import {FinalReportLegacyPage} from './final-report-page';
import {MessageProvider} from '../../i18n/messages';
import {createQueryClient} from '../../query-client';
import {server} from '../../test/server';
import {testMessages} from '../../test/handlers';

/** The page takes its report as a prop, so this renders the screen itself rather than
 *  booting the whole app: only the session and the catalogue are fetched. */
const reportFixture: components['schemas']['ResultsReport'] = {
  slug: 'community-strategy',
  title: 'Community strategy',
  publication: 'final',
  resultsAvailable: true,
  openedAt: '2026-05-01T12:00:00Z',
  closedAt: '2026-07-01T12:00:00Z',
  // Deliberately unlike the catalogue's English, so a page echoing the server shows the marker.
  context: {phase: 'SERVER ENGLISH', status: 'final', method: 'SERVER ENGLISH'},
  participation: {initialRound: 25, informedRound: 22, matchedRounds: null},
  dataAvailability: {detailedCounts: true, opinionGroups: true},
  moderation: {excludedStatements: 1, excludedParticipants: 0},
  statements: [{
    featuredStatementId: 31,
    statement: 'Regional communities should share infrastructure funding.',
    initial: {counts: {agree: 12, pass: 3, disagree: 5, voters: 20}, percentages: {agree: 60, pass: 15, disagree: 25}},
    informed: {counts: {agree: 14, pass: 4, disagree: 2, voters: 20}, percentages: {agree: 70, pass: 20, disagree: 10}},
    agreementShift: 10,
    viewerChoice: null,
  }],
  opinionGroups: [{
    // Unlike the catalogue's "Group $1", so the server's label cannot pass for the mapped one.
    label: 'SERVER GROUP',
    memberCount: 11,
    positions: [{choice: 'agree', statement: 'Shared maintenance matters.', percentage: 82}],
  }],
  viewer: {participating: true, pseudonym: 'quiet-otter', revealState: 'open'},
  links: {
    self: '/api/v1/conversations/community-strategy/results',
    conversation: '/c/community-strategy',
    about: '/c/community-strategy/about',
    identityReveal: '/c/community-strategy/reveal',
  },
};

function renderReport() {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter>
        <Suspense fallback={null}>
          <MessageProvider locale="en"><FinalReportLegacyPage report={reportFixture} /></MessageProvider>
        </Suspense>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

test('renders the final report from the catalogue English', async () => {
  renderReport();

  expect(await screen.findByRole('heading', {name: 'Methodology'}, {timeout: 5000})).toBeVisible();
  expect(screen.getByRole('table', {name: 'Aggregate opinion shift per statement'})).toBeVisible();
  expect(screen.getByRole('columnheader', {name: /Shift/})).toHaveTextContent('(aggregate)');
  expect(screen.getByText('Featured statements used in informed voting: 1')).toBeVisible();
  expect(screen.getByText('1 group identified in the informed voting round')).toBeVisible();
  expect(screen.getByText('· 11 participants')).toBeVisible();
  expect(screen.getByText('Moderation applied: 1 statement excluded')).toBeVisible();
  expect(screen.getAllByText('60.0% agree · 15.0% pass · 20 votes')[0]).toBeVisible();
  expect(screen.getByText(/The identity reveal window is open/)).toHaveTextContent('quiet-otter');
  // Participant- and organizer-authored content is never routed through the catalogue.
  expect(screen.getByRole('heading', {name: 'Community strategy'})).toBeVisible();
  expect(screen.getAllByText('Regional communities should share infrastructure funding.')[0]).toBeVisible();
  expect(screen.getByText('"Shared maintenance matters."')).toBeVisible();
});

test('renders report text from the catalogue, not from source literals', async () => {
  // Non-vacuity: serve deliberately different English for keys spread across the page --
  // a heading, a table label, a parameterised count, a plural, an inline-markup paragraph
  // and an enum badge. None of these assertions can pass against a hardcoded literal.
  server.use(
    http.get(
      new URL('/api/v1/i18n/:locale', globalThis.location.origin).toString(),
      () => HttpResponse.json({
        ...testMessages,
        'report-methodology-heading': 'CATALOGUE METHOD SECTION',
        'report-table-aria': 'CATALOGUE TABLE LABEL',
        'report-featured-count': 'Featured count is $1',
        'report-groups-sub': '$1 {{PLURAL:$1|cluster|clusters}} found',
        'report-bar-label': '$1 pct agree, $2 pct pass, over $3 {{PLURAL:$3|ballot|ballots}}',
        'report-methodology-shift-body': 'Computed as <em>CATALOGUE FORMULA</em>.',
        'report-badge-agree': 'in favour',
        'report-status-final': 'CATALOGUE STATUS',
      }),
    ),
  );

  renderReport();

  expect(await screen.findByRole('heading', {name: 'CATALOGUE METHOD SECTION'}, {timeout: 5000})).toBeVisible();
  expect(screen.getByRole('table', {name: 'CATALOGUE TABLE LABEL'})).toBeVisible();
  expect(screen.getByText('Featured count is 1')).toBeVisible();
  expect(screen.getByText('1 cluster found')).toBeVisible();
  expect(screen.getAllByText('60.0 pct agree, 15.0 pct pass, over 20 ballots')[0]).toBeVisible();
  expect(screen.getByText('in favour')).toBeVisible();
  expect(screen.getByText('CATALOGUE STATUS')).toBeVisible();
  // Inline markup in a catalogue message stays markup rather than being escaped into text.
  expect(within(screen.getByText(/Computed as/)).getByText('CATALOGUE FORMULA').tagName).toBe('EM');
  expect(screen.queryByRole('heading', {name: 'Methodology'})).not.toBeInTheDocument();
});

test('the reading guide names its phase and method from the catalogue, not the server', async () => {
  renderReport();
  // Catches the payload's English phase or method reaching the page, and the wrong output's
  // definition being used for a final report.
  const guide = (await screen.findByRole('heading', {name: 'How to read this output'})).closest('.output-context')!;
  expect(guide).toHaveTextContent(`Produced from${testMessages['output-report-phase']}`);
  expect(guide).toHaveTextContent(testMessages['output-report-method']!);
  expect(guide).not.toHaveTextContent('SERVER ENGLISH');
});

test('opinion groups are numbered from the catalogue, not the server label', async () => {
  renderReport();
  // Catches the server's group label rendering in place of report-group-label.
  expect((await screen.findAllByText(/Group 1/, {selector: '.results-group-heading'}))[0]).toBeInTheDocument();
  expect(document.body.textContent).not.toContain('SERVER GROUP');
});
