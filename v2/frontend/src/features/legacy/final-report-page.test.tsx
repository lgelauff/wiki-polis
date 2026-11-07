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
import dutch from '../../../../i18n/nl.json';

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
  dataAvailability: {detailedCounts: true, opinionGroups: true, personalLens: false, responseFloor: 10},
  moderation: {excludedStatements: 1, excludedParticipants: 0},
  statements: [{
    featuredStatementId: 31,
    statement: 'Regional communities should share infrastructure funding.',
    initial: {counts: {agree: 12, pass: 3, disagree: 5, voters: 20}, percentages: {agree: 60, pass: 15, disagree: 25}, belowFloor: false},
    informed: {counts: {agree: 14, pass: 4, disagree: 2, voters: 20}, percentages: {agree: 70, pass: 20, disagree: 10}, belowFloor: false},
    agreementShift: 10,
    viewerChoice: null,
    viewerGroupChoice: null,
    viewerMatchesGroup: null,
    personalDelta: null,
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

function renderReport(report = reportFixture, locale = 'en') {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter>
        <Suspense fallback={null}>
          <MessageProvider locale={locale}><FinalReportLegacyPage report={report} /></MessageProvider>
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
  expect(screen.getByText('Featured statements in the informed opinion round: 1')).toBeVisible();
  expect(screen.getByText('1 group found in the informed opinion round')).toBeVisible();
  expect(screen.getByText('· 11 participants')).toBeVisible();
  expect(screen.getByText('Moderation applied: 1 statement excluded')).toBeVisible();
  expect(screen.getAllByText('60% agree · 15% pass · 20 responses')[0]).toBeVisible();
  expect(screen.getByText(/Your participation is recorded under pseudonym/)).toHaveTextContent('quiet-otter');
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
        'report-bar-label': '$1 in favour, $2 abstaining, over $3 {{PLURAL:$3|ballot|ballots}}',
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
  expect(screen.getAllByText('60% in favour, 15% abstaining, over 20 ballots')[0]).toBeVisible();
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
  expect(guide).toHaveTextContent(`Produced in${testMessages['output-report-phase']}`);
  expect(guide).toHaveTextContent(testMessages['output-report-method']!);
  expect(guide).not.toHaveTextContent('SERVER ENGLISH');
});

test('opinion groups are numbered from the catalogue, not the server label', async () => {
  renderReport();
  // Catches the server's group label rendering in place of report-group-label.
  expect((await screen.findAllByText(/Group 1/, {selector: '.results-group-heading'}))[0]).toBeInTheDocument();
  expect(document.body.textContent).not.toContain('SERVER GROUP');
});

test('under nl, the whole percentages from the server are written the Dutch way', async () => {
  // The server rounds once to whole percent (#233); the page adds no decimals of its own.
  server.use(http.get(new URL('/api/v1/i18n/:locale', globalThis.location.origin).toString(), () => HttpResponse.json(dutch)));
  const first = reportFixture.statements[0]!;
  renderReport({
    ...reportFixture,
    statements: [{...first, initial: {counts: first.initial!.counts, percentages: {agree: 63, pass: 15, disagree: 22}, belowFloor: false}, agreementShift: 8}],
  }, 'nl');

  expect((await screen.findAllByText('63% eens · 15% overgeslagen · 20 antwoorden', {}, {timeout: 5000}))[0]).toBeVisible();
  expect(screen.getAllByTitle('Eens 63% · Oneens 22% · Overgeslagen 15%')[0]).toBeInTheDocument();
  expect(screen.getByText('+8%')).toBeVisible();
  expect(screen.getByText('82%')).toBeVisible();
});

test('a tally the server withheld shows "fewer than" and no bar or number', async () => {
  const first = reportFixture.statements[0]!;
  const withheld = {counts: null, percentages: null, belowFloor: true};
  renderReport({...reportFixture, statements: [{...first, initial: withheld, informed: withheld, agreementShift: null}]});

  const table = await screen.findByRole('table', {name: 'Aggregate opinion shift per statement'}, {timeout: 5000});
  expect(within(table).getAllByText('fewer than 10 responses')).toHaveLength(2);
  expect(table.querySelector('.p6-vote-bar')).toBeNull();
  expect(table).not.toHaveTextContent('%');
});

test('the public view shows percentages without the number of responses', async () => {
  const first = reportFixture.statements[0]!;
  renderReport({
    ...reportFixture,
    statements: [{...first, initial: {...first.initial!, counts: null}, informed: {...first.informed!, counts: null}}],
    opinionGroups: [],
    viewer: {participating: false, pseudonym: null, revealState: null},
  });

  expect((await screen.findAllByText('60% agree · 15% pass', {}, {timeout: 5000}))[0]).toBeVisible();
  expect(document.body.textContent).not.toMatch(/\d+ responses/);
});

const previewFixture: components['schemas']['ResultsReport'] = {
  ...reportFixture,
  publication: 'preview',
  closedAt: null,
  context: {...reportFixture.context, status: 'provisional'},
  viewer: {participating: false, pseudonym: null, revealState: null},
  links: {...reportFixture.links, conversation: '/admin/conversations/7'},
};

test('a site admin preview is marked as unpublished and never as final', async () => {
  renderReport(previewFixture);

  const banner = await screen.findByRole('note', {}, {timeout: 5000});
  expect(banner).toHaveTextContent(stripTags(testMessages['report-preview-banner']!));
  expect(document.querySelector('.report-badge--preview')).toHaveTextContent(testMessages['report-badge-preview']!);
  expect(screen.getByText(testMessages['report-subtitle-preview']!)).toBeVisible();
  expect(screen.getByText(testMessages['report-status-preview']!)).toBeVisible();
  expect(screen.getByText(testMessages['report-method-preview']!)).toBeVisible();
  for (const key of ['report-badge-final', 'report-status-final', 'report-subtitle', 'output-report-method'] as const) {
    expect(screen.queryByText(testMessages[key]!)).toBeNull();
  }
  // The back link returns to the admin console, where the preview was opened.
  expect(screen.getByRole('link', {name: /Community strategy/})).toHaveAttribute('href', '/admin/conversations/7');
});

test('a preview with no informed opinion results yet shows the empty state under the banner', async () => {
  renderReport({...previewFixture, resultsAvailable: false, statements: [], opinionGroups: []});

  expect(await screen.findByRole('note', {}, {timeout: 5000})).toBeVisible();
  expect(screen.getByText(testMessages['report-no-results']!)).toBeVisible();
});

test('the published report carries no preview banner', async () => {
  renderReport();

  expect(await screen.findByRole('heading', {name: 'Methodology'}, {timeout: 5000})).toBeVisible();
  expect(screen.queryByRole('note')).toBeNull();
  expect(document.querySelector('.report-badge--preview')).toBeNull();
});

function stripTags(html: string) {
  return html.replace(/<[^>]+>/g, '');
}
