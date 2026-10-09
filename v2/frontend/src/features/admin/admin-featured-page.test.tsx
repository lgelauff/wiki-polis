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
import {renderAsQqx} from '../../test/i18n';
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

/** The locale is left to the provider, so that `renderAsQqx()` renders message keys. */
function renderPage() {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter>
        <Suspense fallback={null}>
          <MessageProvider>
            <AdminFeaturedPage conversationId={7} csrfToken="test-csrf-token" />
          </MessageProvider>
        </Suspense>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

async function agreementCell() {
  const row = await screen.findByRole('row', {name: /A representative statement/});
  const header = screen.getByRole('columnheader', {name: '(featured-th-agreement)'});
  const column = [...header.parentElement!.children].indexOf(header);
  return within(row).getAllByRole('cell')[column];
}

test('the agreement share is shown as a whole percentage, with the column defined', async () => {
  renderAsQqx();
  serve(workspace([candidate({agree: 15, pass: 2, disagree: 5, total: 22, agreementPercent: 75})]));
  renderPage();

  expect(await agreementCell()).toHaveTextContent(/^75\s?%$/);
  expect(screen.getByText('(featured-agreement-note)')).toBeVisible();
});

test('below ten agree and disagree responses the share is withheld', async () => {
  renderAsQqx();
  serve(workspace([candidate({agree: 6, pass: 9, disagree: 3, total: 18, agreementPercent: 66.7})]));
  renderPage();

  expect(await agreementCell()).toHaveTextContent('(featured-agreement-few: 10)');
});

test('a candidate with only pass responses has no share either', async () => {
  renderAsQqx();
  serve(workspace([candidate({agree: 0, pass: 4, disagree: 0, total: 4, agreementPercent: null})]));
  renderPage();

  expect(await agreementCell()).toHaveTextContent('(featured-agreement-few: 10)');
});
