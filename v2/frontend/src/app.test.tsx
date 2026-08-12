import {QueryClientProvider} from '@tanstack/react-query';
import {render, screen} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {expect, test} from 'vitest';

import {App} from './app';
import {createQueryClient} from './query-client';

test('renders a conversation lane from the API contract', async () => {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={['/app/real']}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );

  expect(screen.getByRole('status')).toHaveTextContent('Loading conversations');
  expect(await screen.findByRole('heading', {name: 'See where you stand.'})).toBeVisible();
  expect(await screen.findByRole('link', {name: 'Community strategy'}))
    .toHaveAttribute('href', '/c/community-strategy');
});

test('renders a conversation record from the generated API contract', async () => {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={['/app/conversations/community-strategy/about']}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );

  expect(await screen.findByRole('heading', {name: 'Community strategy'})).toBeVisible();
  expect(screen.getByText('Shape the next chapter together.')).toBeVisible();
  expect(screen.getByText('quiet-otter')).toBeVisible();
  expect(screen.getByRole('heading', {name: 'Your contribution'})).toBeVisible();
  expect(screen.getByRole('link', {name: 'Continue participating'}))
    .toHaveAttribute('href', '/c/community-strategy');
});
