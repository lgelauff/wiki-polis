import {QueryClientProvider} from '@tanstack/react-query';
import {fireEvent, render, screen} from '@testing-library/react';
import {http, HttpResponse} from 'msw';
import {MemoryRouter} from 'react-router-dom';
import {expect, test} from 'vitest';

import type {components} from '../../api/schema';
import {App} from '../../app';
import {createQueryClient} from '../../query-client';
import {renderAsQqx, untranslatedCopy} from '../../test/i18n';
import {server} from '../../test/server';

type Results = components['schemas']['IntermediateResults'];

const STATEMENTS = ['Shared maintenance matters.', 'Centralize every budget.', 'Local autonomy matters.'];

function results(overrides: Partial<Results> = {}): Results {
  return {
    slug: 'community-strategy', title: 'Community strategy', state: 'ready', participantCount: 1, smallSample: true,
    consensus: [{choice: 'agree', statement: STATEMENTS[0]!, percentage: 82}, {choice: 'disagree', statement: STATEMENTS[1]!, percentage: 64}],
    // The server's own labels, deliberately not what the catalogue says.
    groups: [
      {label: 'SERVER GROUP A', positions: [{choice: 'agree', statement: STATEMENTS[2]!, percentage: 76}]},
      {label: 'SERVER GROUP B', positions: []},
    ],
    links: {self: '/api/v1/conversations/community-strategy/intermediate-results', conversation: '/c/community-strategy'},
    ...overrides,
  } as Results;
}

function renderResults(data: Results) {
  server.use(http.get(new URL('/api/v1/conversations/community-strategy/intermediate-results', globalThis.location.origin).toString(),
    () => HttpResponse.json({data})));
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={['/app/conversations/community-strategy/explore']}><App /></MemoryRouter>
    </QueryClientProvider>,
  );
}

/** The tab bar renders before the catalogue-driven panels; open the intermediate results tab. */
async function openResultsTab(name: string | RegExp) {
  fireEvent.click(await screen.findByRole('tab', {name}));
}

test.each([
  ['ready, small sample', results()],
  ['recomputing', results({state: 'recomputing'})],
  ['pending', results({state: 'pending', participantCount: null})],
])('under qqx, the intermediate results carry no English: %s', async (_name, data) => {
  renderAsQqx();
  renderResults(data);
  await openResultsTab('(conv-tab-results)');
  await screen.findByRole('heading', {name: /\(conv-results-heading\)/});

  // Catches hardcoded copy, the raw vote choice, and the server's group labels.
  expect(untranslatedCopy([document.querySelector('.results-section')], STATEMENTS)).toEqual([]);
});

test('groups are numbered from the catalogue, and the sample warning is one sentence', async () => {
  renderResults(results());
  await openResultsTab('Intermediate results');
  await screen.findByText('Areas of broad consensus');

  // Catches the server's label rendering instead of the catalogue's, and a group numbered
  // off by one.
  const headings = [...document.querySelectorAll('.results-group-heading')].map((node) => node.textContent);
  expect(headings).toEqual(['Group 1', 'Group 2']);
  expect(screen.getByText('2 opinion groups found')).toBeVisible();
  // Catches the count falling out of the sentence, or the plural ignoring it.
  expect(document.querySelector('.notice-low-n')?.textContent)
    .toBe('Small sample: these results are based on 1 participant. Opinion groups detected from small samples can shift substantially as more people participate — treat group boundaries with caution.');
  expect(screen.getByText('"Shared maintenance matters."')).toBeVisible();
});
