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

test('manages participant access in the distinct admin workspace', async () => {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={['/app/admin/conversations/7/participants']}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );

  expect(await screen.findByRole('heading', {name: 'Community strategy'})).toBeVisible();
  expect(screen.getByRole('navigation', {name: 'Workspace'})).toHaveTextContent(
    'Admin workspace',
  );
  expect(screen.getByRole('rowheader', {name: /Example editor/})).toHaveTextContent(
    'quiet-otter',
  );
  expect(screen.getByText('8 / 12')).toBeVisible();
  fireEvent.change(screen.getByLabelText('Reason (optional)'), {
    target: {value: 'Repeated disruption'},
  });
  fireEvent.click(screen.getByRole('button', {name: 'Ban Example editor'}));

  expect(await screen.findByRole('button', {
    name: 'Unban Example editor',
  })).toBeVisible();
  expect(screen.getByText('Repeated disruption')).toBeVisible();
  expect(screen.getByRole('status')).toHaveTextContent('Access updated');
});

test('resolves a privacy-safe moderation item through the typed contract', async () => {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={['/app/admin/conversations/7/moderation']}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );

  expect(await screen.findByRole('heading', {name: 'Moderation queue'})).toBeVisible();
  expect(screen.getByText('A statement containing private information.')).toBeVisible();
  expect(screen.getByText('Privacy violation')).toBeVisible();
  expect(screen.getByText(/Reporter identities are intentionally excluded/)).toBeVisible();
  fireEvent.change(screen.getByLabelText('Resolution note (optional)'), {
    target: {value: 'Removed private detail'},
  });
  fireEvent.click(screen.getByRole('button', {name: 'Resolve Statement #12'}));

  expect(await screen.findByText('No open flags.')).toBeVisible();
  expect(screen.getByText('Removed private detail')).toBeVisible();
  expect(screen.getByRole('heading', {name: 'Resolved'}).parentElement).toHaveTextContent('1');
});

test('adds and removes invitations through convergent admin commands', async () => {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={['/app/admin/conversations/7/invitations']}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );

  expect(await screen.findByRole('heading', {name: 'Invitations'})).toBeVisible();
  expect(screen.getByText('Existing editor')).toBeVisible();
  fireEvent.change(screen.getByLabelText('Wikimedia usernames'), {
    target: {value: 'New editor\nNew editor'},
  });
  fireEvent.click(screen.getByRole('button', {name: 'Add invitations'}));

  expect(await screen.findByText('New editor')).toBeVisible();
  expect(screen.getByRole('status')).toHaveTextContent('1 added');
  expect(screen.getByRole('status')).toHaveTextContent('1 duplicate input');
  fireEvent.click(screen.getByRole('button', {name: 'Remove New editor'}));
  expect(await screen.findByText('No invitations yet.')).toBeVisible();
});

test('replaces a conversation role set from the admin workspace', async () => {
  render(<QueryClientProvider client={createQueryClient()}><MemoryRouter initialEntries={['/app/admin/conversations/7/roles']}><App /></MemoryRouter></QueryClientProvider>);
  expect(await screen.findByRole('heading', {name: 'Conversation roles'})).toBeVisible();
  expect(screen.getByRole('listitem')).toHaveTextContent('Example editor');
  fireEvent.change(screen.getByLabelText('Participant'), {target: {value: '23'}});
  fireEvent.click(screen.getByRole('checkbox', {name: 'organizer'}));
  fireEvent.click(screen.getByRole('button', {name: 'Save role set'}));
  expect(await screen.findByRole('status')).toHaveTextContent('Added: organizer');
  expect(screen.getByText('moderator + organizer')).toBeVisible();
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

test('requires deliberate confirmation before permanently revealing identity', async () => {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={['/app/conversations/community-strategy/identity-reveal']}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );

  expect(await screen.findByRole('heading', {
    name: 'Choose whether to link your identity',
  })).toBeVisible();
  const submit = screen.getByRole('button', {name: 'Permanently link my identity'});
  expect(submit).toBeDisabled();

  fireEvent.click(screen.getByRole('checkbox'));
  expect(submit).toBeEnabled();
  fireEvent.click(submit);

  expect(await screen.findByRole('heading', {name: 'Identity linked'})).toBeVisible();
  expect(screen.getByRole('heading', {
    name: 'quiet-otter ↔ Example editor',
  })).toBeVisible();
  expect(screen.getByText(/public association is permanent/)).toBeVisible();
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

test('can explain a pass as confusing without changing its vote meaning', async () => {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={['/app/conversations/community-strategy/explore']}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );

  expect(await screen.findByText(/shared technical infrastructure/)).toBeVisible();
  fireEvent.click(screen.getByRole('button', {name: 'Pass'}));

  const confusing = await screen.findByRole('button', {
    name: 'The wording is confusing',
  });
  expect(confusing).toHaveAttribute('aria-pressed', 'false');
  fireEvent.click(confusing);

  expect(await screen.findByRole('button', {
    name: 'The wording is confusing', pressed: true,
  })).toBeVisible();
  expect(screen.getByRole('button', {name: 'Suggest clearer wording'})).toBeVisible();
});

test('completes informed voting through the typed replacement command', async () => {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={['/app/conversations/community-strategy/informed-voting']}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );

  expect(await screen.findByRole('heading', {
    name: 'Regional communities should share infrastructure funding.',
  })).toBeVisible();
  expect(screen.getByText(/reduces duplicated maintenance/)).toBeVisible();
  expect(screen.getByText(/independent budgets/)).toBeVisible();
  fireEvent.click(screen.getByRole('button', {name: 'Agree'}));

  expect(await screen.findByRole('heading', {
    name: 'You’ve completed informed voting.',
  })).toBeVisible();
  expect(screen.getByText(/recorded privately under/)).toHaveTextContent('quiet-otter');
  fireEvent.click(screen.getByRole('button', {name: 'Review statements'}));
  expect(await screen.findByText(/You voted/)).toHaveTextContent('agree');
});

test('renders final results with pass tallies and publication provenance', async () => {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={['/app/conversations/community-strategy/results']}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );

  expect(await screen.findByRole('heading', {name: 'Community strategy'})).toBeVisible();
  expect(screen.getByText('final')).toBeVisible();
  expect(screen.getByText(/filter was frozen at publication/)).toBeVisible();
  expect(screen.getByText('+10% agreement')).toBeVisible();
  expect(screen.getByRole('img', {
    name: 'Initial vote: 60% agree, 15% pass, 25% disagree',
  })).toBeVisible();
  expect(screen.getByRole('img', {
    name: 'Informed vote: 70% agree, 20% pass, 10% disagree',
  })).toBeVisible();
  expect(screen.getAllByText('Pass')).toHaveLength(2);
  expect(screen.getByRole('heading', {name: 'Opinion groups'})).toBeVisible();
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

test('renders explicit argument contribution states and submits through the typed API', async () => {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={['/app/conversations/community-strategy/arguments']}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );

  expect(await screen.findByRole('heading', {
    name: 'Our movement should invest more in shared technical infrastructure.',
  })).toBeVisible();
  expect(screen.getByText(/For:/).parentElement).toHaveTextContent('response needed');
  expect(screen.getByText(/Against:/).parentElement).toHaveTextContent('nothing to add');
  expect(screen.getByText(/Complete both responses/)).toBeVisible();

  fireEvent.click(screen.getByRole('button', {name: 'Add a for argument'}));
  fireEvent.change(screen.getByRole('textbox', {name: 'Your for argument'}), {
    target: {value: 'Shared maintenance reduces duplicated work.'},
  });
  fireEvent.click(screen.getByRole('button', {name: 'Submit argument'}));

  expect(await screen.findByText('Your for argument was saved.')).toBeVisible();
  expect(screen.getByRole('link', {name: 'Explore'})).toHaveAttribute(
    'href', '/app/conversations/community-strategy/explore',
  );
});

test('reports a statement through an accessible modal without edge positioning', async () => {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={['/app/conversations/community-strategy/explore']}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );

  expect(await screen.findByText(/shared technical infrastructure/)).toBeVisible();
  fireEvent.click(screen.getByRole('button', {name: 'Report concern'}));
  const dialog = screen.getByRole('dialog', {name: 'Report a concern'});
  expect(dialog).toBeVisible();
  fireEvent.change(screen.getByRole('combobox', {name: 'Reason'}), {
    target: {value: 'other'},
  });
  expect(screen.getByRole('button', {name: 'Send for review'})).toBeDisabled();
  fireEvent.change(screen.getByRole('textbox', {name: 'Details (required)'}), {
    target: {value: 'The wording could be interpreted in two incompatible ways.'},
  });
  fireEvent.click(screen.getByRole('button', {name: 'Send for review'}));

  expect(await screen.findByRole('heading', {
    name: 'Thank you for raising this concern.',
  })).toBeVisible();
});
