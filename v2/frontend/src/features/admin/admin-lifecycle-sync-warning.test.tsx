import {QueryClientProvider} from '@tanstack/react-query';
import {fireEvent, render, screen} from '@testing-library/react';
import {http, HttpResponse} from 'msw';
import {MemoryRouter} from 'react-router-dom';
import {expect, test} from 'vitest';

import {App} from '../../app';
import {createQueryClient} from '../../query-client';
import {phaseAdvanceFixture} from '../../test/handlers';
import {server} from '../../test/server';
import {phaseTransitionToast} from './admin-lifecycle-page';

const PHASE_URL = new URL(
  '/api/v1/admin/conversations/7/phase', globalThis.location.origin,
).toString();

function renderLifecycle() {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={['/app/admin/conversations/7']}><App /></MemoryRouter>
    </QueryClientProvider>,
  );
}

async function advance() {
  // The admin route module is lazily imported; a cold test file routinely needs more
  // than testing-library's 1s default before the console paints.
  await screen.findByRole('heading', {name: 'Community strategy'}, {timeout: 10_000});
  fireEvent.click(screen.getByRole('checkbox', {name: /statement set and introduction/}));
  fireEvent.click(screen.getByRole('button', {name: 'Move on to Explore →'}));
}

test('a failed Polis visibility sync reaches the operator as an alert, not a success', async () => {
  server.use(http.put(PHASE_URL, () => HttpResponse.json({
    data: phaseAdvanceFixture({visibilitySynced: false}),
  })));
  renderLifecycle();

  await advance();

  const toast = await screen.findByRole('alert');
  expect(toast).toHaveTextContent(
    'Phase moved, but updating results visibility in Polis failed.',
  );
  expect(toast).toHaveTextContent('Moved to: Explore.');
  expect(toast).toHaveClass('toast--error');
  expect(toast).not.toHaveClass('toast--success');
});

test('a healthy phase move confirms as a success toast, never an alert', async () => {
  renderLifecycle();

  await advance();

  const toast = await screen.findByText('Moved to: Explore.');
  expect(toast.closest('.toast')).toHaveClass('toast--success');
  expect(screen.queryByRole('alert')).toBeNull();
});

test('phaseTransitionToast keeps the worst severity and the server ordering', () => {
  const base = {
    sourceKey: 'preparation', targetKey: 'submission', targetLabel: 'Explore',
    phase6Created: false, phase6SyncMessage: null as string | null,
    visibilitySynced: true,
  };

  expect(phaseTransitionToast(base))
    .toEqual({category: 'success', message: 'Moved to: Explore.'});
  expect(phaseTransitionToast({...base, phase6SyncMessage: 'Seeded 3 statements.'}))
    .toEqual({category: 'success', message: 'Seeded 3 statements. Moved to: Explore.'});
  expect(phaseTransitionToast({
    ...base, phase6SyncMessage: 'Two statements failed — check manually.',
  })).toEqual({
    category: 'warning',
    message: 'Two statements failed — check manually. Moved to: Explore.',
  });
  expect(phaseTransitionToast({
    ...base, visibilitySynced: false,
    phase6SyncMessage: 'Two statements failed — check manually.',
  })).toEqual({
    category: 'error',
    message: 'Phase moved, but updating results visibility in Polis failed. '
      + 'Two statements failed — check manually. Moved to: Explore.',
  });
});
