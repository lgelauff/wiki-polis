import {QueryClientProvider} from '@tanstack/react-query';
import {render, screen} from '@testing-library/react';
import {http, HttpResponse} from 'msw';
import {MemoryRouter} from 'react-router-dom';
import {expect, test} from 'vitest';

import {App} from '../../app';
import {createQueryClient} from '../../query-client';
import {renderAsQqx, untranslatedCopy} from '../../test/i18n';
import {server} from '../../test/server';
import {testMessages} from '../../test/handlers';

function renderRoute(route: string) {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={[route]}><App /></MemoryRouter>
    </QueryClientProvider>,
  );
}

test('renders the legacy conversation record from the typed about contract', async () => {
  renderRoute('/app/conversations/community-strategy/about');

  expect(await screen.findByRole('heading', {name: 'About Community strategy'})).toBeVisible();
  expect(screen.getByText('Shape the next chapter together.')).toBeVisible();
  expect(screen.getByText('quiet-otter')).toBeVisible();
  expect(screen.getByText('2 new statements suggested')).toBeVisible();
  // Output names come from the catalogue by key ("report"), not from the payload's label.
  const outputs = [...document.querySelectorAll('.landing-section li')].map((node) => node.textContent);
  expect(outputs).toContain('Report — pending');
  expect(screen.getByRole('link', {name: 'Moderation log (1)'})).toHaveAttribute(
    'href', '/c/community-strategy/moderation-log',
  );
});

test('renders the public moderation accountability table', async () => {
  renderRoute('/app/parity/conversations/community-strategy/moderation-log');

  expect(await screen.findByRole('heading', {name: 'Moderation log — Community strategy'})).toBeVisible();
  expect(screen.getByRole('columnheader', {name: 'Pseudonym'})).toBeVisible();
  // Catches the timestamp shown as the server's raw UTC string instead of a date in the
  // reader's language (en formats as en-GB; vite.config.ts pins the test timezone to UTC),
  // and the machine-readable value dropping out of the <time> element.
  const when = [...document.querySelectorAll('tbody tr td:first-child time')];
  expect(when.map((node) => [node.getAttribute('datetime'), node.textContent])).toEqual([
    ['2026-08-14T09:30:00Z', '14 Aug 2026, 09:30'],
    ['2026-08-13T08:15:00Z', '13 Aug 2026, 08:15'],
  ]);
  expect(screen.getByText('quiet-otter')).toBeVisible();
  expect(screen.getByText('patient-fox')).toBeVisible();
});

test('renders the exact argument-map output content and navigation', async () => {
  renderRoute('/app/parity/conversations/community-strategy/outputs/argument-map');

  expect(await screen.findByRole('heading', {name: 'Argument map'})).toBeVisible();
  expect(screen.getByRole('heading', {name: 'How to read this output'})).toBeVisible();
  expect(screen.getByRole('heading', {name: 'Featured statements and arguments'})).toBeVisible();
  expect(screen.getByRole('link', {name: /Open the current Arguments tab/})).toHaveAttribute(
    'href', '/c/community-strategy#tab-arguments',
  );
  // Catches the page keeping the default "Proto" tab title, which names neither the output nor
  // the consultation, and the breadcrumb losing its labelled navigation landmark.
  expect(document.title).toBe('Argument map — Community strategy — Proto');
  expect(screen.getByRole('navigation', {name: 'Conversation context'})).toHaveTextContent('Community strategy/Argument map');
});

test('renders the pending output state from the typed contract', async () => {
  renderRoute('/app/parity/conversations/community-strategy/outputs/initial-clustering');

  // The status is a lowercase message; the capital letter comes from CSS on .output-status-value.
  expect(await screen.findByText('provisional · pending', {selector: '.output-status-value'})).toBeVisible();
  expect(screen.getByText('Detailed clustering visuals are still to be developed.')).toBeVisible();
});

const url = (path: string) => new URL(path, globalThis.location.origin).toString();

test('under qqx, the About page carries no English but the consultation and the pseudonym', async () => {
  server.use(http.get(url('/api/v1/conversations/community-strategy/about'), () => HttpResponse.json({data: {
    conversationId: 7, slug: 'community-strategy', title: 'Community strategy', space: 'real',
    descriptionHtml: null, outroHtml: null, status: 'paused',
    phases: [{key: 'submission', label: 'SERVER ENGLISH'}, {key: 'argument_mapping', label: 'SERVER ENGLISH'}],
    scheduledTransition: {at: '2026-10-01T12:00:00Z', target: 'informed_voting', targetLabel: 'SERVER ENGLISH'},
    pseudonym: 'quiet-otter',
    statistics: {participants: null, statementVotes: null, statements: 1, arguments: 0, argumentContributors: 1},
    personal: {statementsSuggested: 1, statementVotes: null, statementVotesAvailable: false, argumentsAdded: 1, argumentsRated: 0},
    outputs: [
      {key: 'report', label: 'SERVER ENGLISH', status: 'final', symbol: 'report', tooltip: 'SERVER ENGLISH', pending: 'SERVER ENGLISH', ready: false, href: null},
      {key: 'argument-map', label: 'SERVER ENGLISH', status: 'provisional', symbol: 'argument-map', tooltip: 'SERVER ENGLISH', pending: 'SERVER ENGLISH', ready: true, href: '/c/community-strategy/outputs/argument-map'},
    ],
    moderation: {eventCount: 0, href: '/c/community-strategy/moderation-log'},
    capabilities: {participate: true, moderate: false},
    links: {self: '/api/v1/conversations/community-strategy/about', conversation: '/c/community-strategy'},
  }})));
  renderAsQqx();
  renderRoute('/app/conversations/community-strategy/about');
  await screen.findByRole('heading', {name: '(about-heading: Community strategy)'});

  // Catches hardcoded copy and any server label (phase, output, scheduled phase) rendered
  // as sent: the fixture's labels are all "SERVER ENGLISH", so one reaching the page shows.
  const page = document.querySelector('.container');
  expect(untranslatedCopy([page], ['Community strategy', 'quiet-otter', '1 Oct 2026, 12:00'])).toEqual([]);
  expect(document.title).toBe('(about-doc-title: Community strategy)');
});

test('the About page maps the scheduled phase and output names from their identifiers', async () => {
  const response = await fetch(url('/api/v1/conversations/community-strategy/about'));
  const {data} = await response.json() as {data: Record<string, unknown>};
  server.use(http.get(url('/api/v1/conversations/community-strategy/about'), () => HttpResponse.json({data: {
    ...data,
    phases: [{key: 'submission', label: 'SERVER PHASE'}],
    scheduledTransition: {at: '2026-10-01T12:00:00Z', target: 'informed_voting', targetLabel: 'SERVER PHASE'},
    statistics: {participants: null, statementVotes: 1, statements: 2, arguments: 3, argumentContributors: 4},
    outputs: [{key: 'report', label: 'SERVER OUTPUT', status: 'final', symbol: 'report', tooltip: '', pending: '', ready: false, href: null}],
  }})));
  renderRoute('/app/conversations/community-strategy/about');
  await screen.findByRole('heading', {name: 'About Community strategy'});

  // Catches the payload's English labels reaching the page: every label in this fixture is a
  // marker the catalogue does not contain.
  expect(document.body.textContent).not.toContain('SERVER');
  const next = document.querySelector('time[datetime="2026-10-01T12:00:00Z"]')!.closest('p')!;
  expect(next).toHaveTextContent('Next: Informed vote on 1 Oct 2026, 12:00.');
  expect(screen.getByText(/^Current phase:/).closest('p')).toHaveTextContent('Current phase: Explore');
  const outputs = [...document.querySelectorAll('.landing-section li')].map((node) => node.textContent);
  expect(outputs.at(-1)).toBe('Report — pending');
  // An unknown statistic shows a dash, announced as "unknown", with its unit in the plural.
  expect(document.querySelector('.stat-row > span')!.textContent).toBe('—unknownparticipants');
});

test('the output page maps its phase and status from identifiers', async () => {
  server.use(
    http.get(url('/api/v1/conversations/:slug/outputs/:outputKey'), () => HttpResponse.json({data: {
      slug: 'community-strategy', title: 'Community strategy',
      output: {key: 'initial-clustering', label: 'SERVER LABEL', phase: 'SERVER PHASE', status: 'provisional', ready: false, method: 'SERVER METHOD', pending: 'SERVER PENDING'},
      links: {self: '', conversation: '/c/community-strategy', about: '/c/community-strategy/about'},
    }})),
    // The status identifier and its English are the same word, so the catalogue value is
    // changed here to tell a mapped status from the raw one.
    http.get(url('/api/v1/i18n/:locale'), () => HttpResponse.json({...testMessages, 'output-status-provisional': 'provisional-from-catalogue'})),
  );
  renderRoute('/app/parity/conversations/community-strategy/outputs/initial-clustering');
  await screen.findByRole('heading', {name: 'Initial clustering'});

  // Catches the payload's phase, method or status reaching the eyebrow or the reading guide.
  expect(document.body.textContent).not.toContain('SERVER');
  expect(document.querySelector('.output-page-header .results-label')).toHaveTextContent('Explore output');
  expect(document.querySelector('.output-status-value')).toHaveTextContent('provisional-from-catalogue · pending');
});

test('the About page pluralises each statistic by its own number', async () => {
  const response = await fetch(url('/api/v1/conversations/community-strategy/about'));
  const {data} = await response.json() as {data: {statistics: Record<string, number>}};
  server.use(http.get(url('/api/v1/conversations/community-strategy/about'), () => HttpResponse.json({data: {
    ...data, statistics: {...data.statistics, arguments: 1, argumentContributors: 1},
  }})));
  renderRoute('/app/conversations/community-strategy/about');
  await screen.findByRole('heading', {name: 'About Community strategy'});

  // Catches a unit that ignores its count: each label must agree with the number above it,
  // and 1 takes the singular.
  const stats = [...document.querySelectorAll('.stat-row > span')].map((node) => node.textContent);
  expect(stats).toEqual(['24participants', '312statement votes', '42statements', '1argument', '1argument contributor']);
  expect(screen.getByText('1 argument added')).toBeVisible();
  expect(screen.getByText('3 arguments rated')).toBeVisible();
});

test('under qqx, the moderation log carries no English but pseudonyms and moderators', async () => {
  renderAsQqx();
  renderRoute('/app/parity/conversations/community-strategy/moderation-log');
  await screen.findByRole('heading', {name: '(modlog-heading: Community strategy)'});

  // Catches the action and scope values ("Banned", "conversation") reaching the table as the
  // server sends them. The allowed content is the fixture's data: title, pseudonyms, moderator
  // usernames, and the two timestamps as the en-GB date format writes them.
  expect(untranslatedCopy([document.querySelector('.container')], [
    'Community strategy', 'quiet-otter', 'patient-fox', 'adminuser', 'mod-kestrel', '14 Aug 2026, 09:30', '13 Aug 2026, 08:15',
  ])).toEqual([]);
});

test('the moderation log names each action from the catalogue', async () => {
  renderRoute('/app/parity/conversations/community-strategy/moderation-log');
  await screen.findByRole('heading', {name: 'Moderation log — Community strategy'});

  // Catches the two actions being mapped the wrong way round.
  const rows = [...document.querySelectorAll('tbody tr')].map((row) => [row.children[1]?.textContent, row.children[2]?.textContent]);
  expect(rows).toEqual([['Banned', 'quiet-otter'], ['Unbanned', 'patient-fox']]);
});

test.each(['initial-clustering', 'argument-map', 'preliminary-results', 'report', 'dataset'])(
  'under qqx, the %s output page carries no English', async (key) => {
    renderAsQqx();
    renderRoute(`/app/parity/conversations/community-strategy/outputs/${key}`);
    await screen.findByRole('heading', {name: /\(output-.*-label\)/});

    // Catches hardcoded copy and the payload's English phase, method, status or pending text.
    expect(untranslatedCopy([document.querySelector('.container')], ['Community strategy'])).toEqual([]);
    // Catches an English tab title, or one naming the output from the payload's label.
    expect(document.title).toBe(`(output-doc-title: (output-${key}-label), Community strategy)`);
  },
);
