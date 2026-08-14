import {QueryClientProvider} from '@tanstack/react-query';
import {render, screen, waitFor} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {expect, test} from 'vitest';

import {App} from '../../app';
import {createQueryClient} from '../../query-client';

function renderRoute(route: string) {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={[route]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

test('renders the entry fork with the legacy shell and card contract', async () => {
  renderRoute('/app/parity/fork');

  expect(await screen.findByRole('heading', {name: 'Where the community actually stands.'})).toBeVisible();
  expect(screen.getByRole('link', {name: 'ProtoWiki'})).toHaveClass('header-logo');
  expect(screen.getByRole('link', {name: /Try out the platform/})).toHaveClass('fork-card--demo');
  expect(screen.getByRole('link', {name: /Participate in real consultations/})).toHaveClass('fork-card--real');
  expect(screen.getByRole('link', {name: /Open an issue/})).toHaveAttribute('target', '_blank');
  await waitFor(() => expect(document.querySelector('link[data-react-legacy-styles]')).toBeTruthy());
});

test('renders the complete statement-writing guide', async () => {
  renderRoute('/app/parity/help/statements');

  expect(await screen.findByRole('heading', {name: 'Writing good statements'})).toBeVisible();
  expect(screen.getByText('statement guide').closest('.header-crumb')).toHaveClass('header-crumb');
  expect(screen.getByText('Make one claim.')).toBeVisible();
  expect(screen.getByRole('heading', {name: 'When to pass'})).toBeVisible();
});

test('renders the complete argument-writing guide', async () => {
  renderRoute('/app/parity/help/arguments');

  expect(await screen.findByRole('heading', {name: 'Writing good arguments'})).toBeVisible();
  expect(screen.getByText('argument guide').closest('.header-crumb')).toHaveClass('header-crumb');
  expect(screen.getByText('State the direction.')).toBeVisible();
  expect(screen.getByRole('heading', {name: 'Moderation baseline'})).toBeVisible();
});
