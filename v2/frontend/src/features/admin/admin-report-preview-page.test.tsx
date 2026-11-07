import {Suspense} from 'react';
import {QueryClientProvider} from '@tanstack/react-query';
import {render, screen, waitFor} from '@testing-library/react';
import {http, HttpResponse} from 'msw';
import {MemoryRouter, Route, Routes, useLocation} from 'react-router-dom';
import {expect, test} from 'vitest';

import type {components} from '../../api/schema';
import {AdminReportPreviewPage} from './admin-report-preview-page';
import {MessageProvider} from '../../i18n/messages';
import {createQueryClient} from '../../query-client';
import {server} from '../../test/server';
import {testMessages} from '../../test/handlers';

const PREVIEW_URL = new URL('/api/v1/admin/conversations/7/report-preview', globalThis.location.origin).toString();

const preview: components['schemas']['ResultsReport'] = {
  slug: 'community-strategy',
  title: 'Community strategy',
  publication: 'preview',
  resultsAvailable: false,
  openedAt: '2026-05-01T12:00:00Z',
  closedAt: null,
  context: {phase: 'x', status: 'provisional', method: 'x'},
  participation: {initialRound: null, informedRound: null, matchedRounds: null},
  dataAvailability: {detailedCounts: false, opinionGroups: false, personalLens: false, responseFloor: 10},
  moderation: {excludedStatements: 0, excludedParticipants: 0},
  statements: [],
  opinionGroups: [],
  viewer: {participating: false, pseudonym: null, revealState: null},
  links: {self: '/api/v1/admin/conversations/7/report-preview', conversation: '/admin/conversations/7', about: '/c/community-strategy/about'},
};

function Where() {
  return <output aria-label="location">{useLocation().pathname}</output>;
}

/** The preview route and a stand-in console page, so a test can leave and reopen it. */
function renderAt(path: string, client = createQueryClient()) {
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Suspense fallback={null}>
          <MessageProvider locale="en">
            <Routes>
              <Route path="/admin/conversations/7/report-preview" element={<AdminReportPreviewPage conversationId={7} />} />
              <Route path="*" element={<Where />} />
            </Routes>
          </MessageProvider>
        </Suspense>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

test('every open of the preview fetches it once, so reopening shows live numbers', async () => {
  let hits = 0;
  server.use(http.get(PREVIEW_URL, () => {
    hits += 1;
    return HttpResponse.json({data: preview});
  }));
  const client = createQueryClient();

  const first = renderAt('/admin/conversations/7/report-preview', client);
  expect(await screen.findByRole('note', {}, {timeout: 5000})).toBeVisible();
  first.unmount();
  renderAt('/admin/conversations/7/report-preview', client);
  expect(await screen.findByRole('note', {}, {timeout: 5000})).toBeVisible();

  expect(hits).toBe(2);
});

test('the preview names itself in the browser tab', async () => {
  server.use(http.get(PREVIEW_URL, () => HttpResponse.json({data: preview})));
  renderAt('/admin/conversations/7/report-preview');

  await screen.findByRole('note', {}, {timeout: 5000});
  await waitFor(() => expect(document.title).toContain(testMessages['report-subtitle-preview']!));
  expect(document.title).toContain('Community strategy');
});

test('once the report is published, the preview goes to the published report', async () => {
  server.use(http.get(PREVIEW_URL, () => HttpResponse.json(
    {error: {code: 'conversation_closed', message: 'The report is already published.', details: {report: '/c/community-strategy/report'}}},
    {status: 409},
  )));
  renderAt('/admin/conversations/7/report-preview');

  expect(await screen.findByLabelText('location', {}, {timeout: 5000})).toHaveTextContent('/c/community-strategy/report');
  expect(screen.queryByRole('note')).toBeNull();
});
