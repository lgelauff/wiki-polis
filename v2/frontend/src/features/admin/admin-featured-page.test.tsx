import {Suspense} from 'react';
import {QueryClientProvider} from '@tanstack/react-query';
import {render, screen, within} from '@testing-library/react';
import {http, HttpResponse} from 'msw';
import {MemoryRouter} from 'react-router-dom';
import {expect, test} from 'vitest';

import type {components} from '../../api/schema';
import {AdminFeaturedPage} from './admin-featured-page';
import {MessageProvider} from '../../i18n/messages';
import {createQueryClient} from '../../query-client';
import {server} from '../../test/server';

type Workspace = components['schemas']['AdminFeaturedWorkspace'];
type Candidate = components['schemas']['AdminFeaturedCandidate'];

const FEATURED_URL = new URL(
  '/api/v1/admin/conversations/7/featured-statements', globalThis.location.origin,
).toString();

const candidate = (votes: Candidate['votes']): Candidate => ({
  statementId: 42,
  text: 'A representative statement',
  seed: true,
  provenance: null,
  votes,
});

const workspace = (candidates: Candidate[]): Workspace => ({
  conversation: {id: 7, slug: 'community-strategy', title: 'Community strategy'},
  selected: [],
  candidates,
  dataAvailability: {candidates: true},
  phase: {argumentMappingActive: false, informedVotingLive: false},
  guidance: {recommendedCount: 15, note: 'Choose across viewpoints.'},
  capabilities: {manage: true},
  links: {self: FEATURED_URL, lifecycle: '/admin/conversations/7/lifecycle'},
});

function serve(payload: Workspace) {
  server.use(http.get(FEATURED_URL, () => HttpResponse.json({data: payload})));
}

function renderPage() {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter>
        <Suspense fallback={null}>
          <MessageProvider locale="en">
            <AdminFeaturedPage conversationId={7} csrfToken="test-csrf-token" />
          </MessageProvider>
        </Suspense>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

test('shows the actual agreement percentage and defines its denominator', async () => {
  serve(workspace([candidate({
    agree: 3, pass: 2, disagree: 1, total: 6, agreementPercent: 75,
  })]));
  renderPage();

  const row = await screen.findByRole('row', {name: /A representative statement/});
  expect(within(row).getByRole('cell', {name: '75.0%'})).toBeVisible();
  expect(screen.getByText(
    'Agreement is the percentage of agree votes among agree and disagree votes; pass votes are excluded.',
  )).toBeVisible();
  expect(screen.getByRole('columnheader', {name: 'Agreement (%)'})).toBeVisible();
});

test('shows no agreement percentage when a candidate has only pass votes', async () => {
  serve(workspace([candidate({
    agree: 0, pass: 4, disagree: 0, total: 4, agreementPercent: null,
  })]));
  renderPage();

  const row = await screen.findByRole('row', {name: /A representative statement/});
  expect(within(row).getByRole('cell', {name: '—'})).toBeVisible();
});
