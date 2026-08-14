import {QueryClientProvider} from '@tanstack/react-query';
import {render, screen} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {expect, test} from 'vitest';

import {App} from '../../app';
import {createQueryClient} from '../../query-client';

function renderRoute(route: string) {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={[route]}><App /></MemoryRouter>
    </QueryClientProvider>,
  );
}

test('renders the public moderation accountability table', async () => {
  renderRoute('/app/parity/conversations/community-strategy/moderation-log');

  expect(await screen.findByRole('heading', {name: 'Moderation log — Community strategy'})).toBeVisible();
  expect(screen.getByRole('columnheader', {name: 'Pseudonym'})).toBeVisible();
  expect(screen.getByText('2026-08-14 09:30')).toBeVisible();
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
});

test('renders the pending output state from the typed contract', async () => {
  renderRoute('/app/parity/conversations/community-strategy/outputs/initial-clustering');

  expect(await screen.findByText('Provisional · pending')).toBeVisible();
  expect(screen.getByText('Detailed clustering visuals are still to be developed.')).toBeVisible();
});
