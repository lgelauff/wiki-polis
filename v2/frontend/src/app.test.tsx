import {QueryClientProvider} from '@tanstack/react-query';
import {fireEvent, render, screen} from '@testing-library/react';
import {http, HttpResponse} from 'msw';
import {MemoryRouter} from 'react-router-dom';
import {expect, test} from 'vitest';

import {App} from './app';
import {createQueryClient} from './query-client';
import {server} from './test/server';

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

test('joins a conversation through the typed command', async () => {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={['/app/conversations/community-strategy/join']}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );

  expect(await screen.findByRole('heading', {name: 'Community strategy'})).toBeVisible();
  fireEvent.click(await screen.findByRole('button', {name: 'Join conversation'}));

  expect(await screen.findByText(/You’ll participate as/)).toBeVisible();
  expect(screen.getByRole('link', {name: 'Enter the conversation'}))
    .toHaveAttribute('href', '/c/community-strategy');
});

test('votes in Explore through the wiki-polis API contract', async () => {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={['/app/conversations/community-strategy/explore']}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );

  expect(await screen.findByText(/shared technical infrastructure/)).toBeVisible();
  fireEvent.click(screen.getByRole('button', {name: 'Agree'}));

  expect(await screen.findByText(/You voted/)).toHaveTextContent('agree');
  expect(screen.getByRole('button', {name: 'Next statement'})).toBeVisible();
});

test('submits clearer wording through the idempotent statement contract', async () => {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={['/app/conversations/community-strategy/explore']}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );

  expect(await screen.findByText(/shared technical infrastructure/)).toBeVisible();
  fireEvent.click(screen.getByRole('button', {name: 'Pass'}));
  fireEvent.click(await screen.findByRole('button', {name: 'Suggest clearer wording'}));

  const text = screen.getByRole('textbox', {name: 'Statement text'});
  expect(text).toHaveValue('Our movement should invest more in shared technical infrastructure.');
  fireEvent.change(text, {target: {value: 'Invest together in shared technical infrastructure.'}});
  fireEvent.click(screen.getByRole('button', {name: 'Submit clearer wording'}));

  expect(await screen.findByRole('heading', {
    name: 'Your clearer wording is now available to participants.',
  })).toBeVisible();
  expect(screen.getByText(/linked to the original wording/)).toBeVisible();
});

test('submits a new statement from the Explore loop', async () => {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={['/app/conversations/community-strategy/explore']}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );

  expect(await screen.findByText(/shared technical infrastructure/)).toBeVisible();
  fireEvent.click(screen.getByRole('button', {name: 'Agree'}));
  fireEvent.click(await screen.findByRole('button', {name: 'Add a new statement'}));
  fireEvent.change(screen.getByRole('textbox', {name: 'Statement text'}), {
    target: {value: 'Regional communities should share maintenance funding.'},
  });
  fireEvent.click(screen.getByRole('button', {name: 'Submit statement'}));

  expect(await screen.findByRole('heading', {
    name: 'Your statement is now available to participants.',
  })).toBeVisible();
  expect(screen.getByText(/2 new-statement slots remaining/)).toBeVisible();
});

test('freezes a statement attempt when the upstream outcome is unknown', async () => {
  server.use(http.post(
    new URL('/api/v1/conversations/community-strategy/statements', globalThis.location.origin).toString(),
    ({request}) => {
      expect(request.headers.get('Idempotency-Key')).toMatch(/^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$/);
      expect(request.headers.get('X-CSRFToken')).toBe('test-csrf-token');
      return HttpResponse.json({
        error: {
          code: 'command_outcome_unknown',
          message: 'The statement may have reached the voting service. Do not retry with a new key.',
        },
      }, {status: 502});
    },
  ));
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={['/app/conversations/community-strategy/explore']}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );

  expect(await screen.findByText(/shared technical infrastructure/)).toBeVisible();
  fireEvent.click(screen.getByRole('button', {name: 'Pass'}));
  fireEvent.click(await screen.findByRole('button', {name: 'Add a new statement'}));
  fireEvent.change(screen.getByRole('textbox', {name: 'Statement text'}), {
    target: {value: 'A statement with an uncertain outcome.'},
  });
  fireEvent.click(screen.getByRole('button', {name: 'Submit statement'}));

  expect(await screen.findByRole('alert')).toHaveTextContent('Contact a moderator');
  expect(screen.getByRole('textbox', {name: 'Statement text'})).toBeDisabled();
  expect(screen.getByRole('button', {name: 'Submit statement'})).toBeDisabled();
});
