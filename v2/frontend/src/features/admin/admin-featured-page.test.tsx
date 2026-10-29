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
  guidance: {recommendedCount: 15, note: 'Choose across viewpoints.', agreementFloor: 10, agreementMarkShare: 0.7},
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
  const cell = within(row).getAllByRole('cell')[column];
  if (!cell) throw new Error('no Agreement cell in the candidate row');
  return cell;
}

test('the server\'s share is shown as a whole percentage, and the note is tied to the table', async () => {
  renderAsQqx();
  serve(workspace([candidate({agree: 13, pass: 2, disagree: 7, total: 22, agreementPercent: 65, agreementMarked: false})]));
  renderPage();

  const cell = await agreementCell();
  expect(cell).toHaveTextContent(/^65\s?%$/);
  expect(within(cell).queryByRole('img')).toBeNull();
  const note = screen.getByText('(featured-agreement-note: 10)');
  expect(screen.getByRole('table')).toHaveAttribute('aria-describedby', note.id);
});

test('a share at or above the mark share carries a mark that names itself', async () => {
  renderAsQqx();
  serve(workspace([candidate({agree: 15, pass: 2, disagree: 5, total: 22, agreementPercent: 75, agreementMarked: true})]));
  renderPage();

  const cell = await agreementCell();
  expect(within(cell).getByRole('img', {name: /^\(featured-agreement-mark: 70\s?%\)$/})).toBeVisible();
});

test('a share the server withheld says so, with the floor it sent', async () => {
  renderAsQqx();
  serve(workspace([candidate({agree: 6, pass: 9, disagree: 3, total: 18, agreementPercent: null, agreementMarked: false})]));
  renderPage();

  const cell = await agreementCell();
  expect(cell).toHaveTextContent('(featured-agreement-few: 10)');
  expect(within(cell).queryByRole('img')).toBeNull();
});
