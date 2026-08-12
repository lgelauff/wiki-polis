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
  expect(await screen.findByRole('link', {name: 'Community strategy'}))
    .toHaveAttribute('href', '/c/community-strategy');
});
