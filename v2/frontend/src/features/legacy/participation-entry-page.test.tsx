import {QueryClientProvider} from '@tanstack/react-query';
import {render, screen, within} from '@testing-library/react';
import {http, HttpResponse} from 'msw';
import {MemoryRouter} from 'react-router-dom';
import {expect, test} from 'vitest';

import {App} from '../../app';
import {createQueryClient} from '../../query-client';
import {server} from '../../test/server';
import {testMessages} from '../../test/handlers';

/** Renders the join screen through the app router with the test catalogue. */
function renderJoin() {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={['/accept/community-strategy']}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

test('the join screen renders its copy from the catalogue', async () => {
  renderJoin();
  expect(await screen.findByText(testMessages['accept-choose-pseudonym']!)).toBeVisible();
  // The consent checkbox and the licence disclosure are what the participant agrees to.
  expect(screen.getByText(testMessages['accept-consent']!)).toBeVisible();
  expect(screen.getByRole('heading', {name: testMessages['accept-licence-heading']!})).toBeVisible();
  expect(screen.getByText(testMessages['accept-privacy-summary']!)).toBeVisible();
  expect(screen.getByRole('button', {name: testMessages['accept-reroll-aria']!})).toBeVisible();
});

test('the licence sentence keeps its link inside one message', async () => {
  renderJoin();
  // accept-licence-intro is one message with the link passed in as $1. Two CC0 links render
  // on the page (this one and the shell footer's), so the query is scoped to this section.
  await screen.findByText(testMessages['accept-licence-heading']!);
  const section = document.getElementById('accept-licence-note');
  expect(section).not.toBeNull();
  const link = within(section!).getByRole('link', {name: /CC0/});
  expect(link).toHaveAttribute('href', 'https://creativecommons.org/publicdomain/zero/1.0/');
  expect(link.closest('p')?.textContent).toContain('released under');
  expect(link.closest('p')?.textContent).toContain('public domain');
});

test('the identity-reveal window reads as one sentence with both numbers', async () => {
  renderJoin();
  // accept-privacy-reveal-window is one sentence taking both numbers as parameters.
  const details = await screen.findByText(testMessages['accept-privacy-details-summary']!);
  const body = details.closest('details')?.textContent ?? '';
  expect(body).toContain('Between');
  expect(body).toContain('30');
  expect(body).toContain('60 days');
  expect(body).toContain('permanently link your username');
});

test('the invite-only page names the consultation inside one sentence', async () => {
  server.use(http.get(
    new URL('/api/v1/conversations/community-strategy/participation-entry', globalThis.location.origin).toString(),
    () => HttpResponse.json({data: {
      state: 'invite_denied',
      conversation: {id: 7, slug: 'community-strategy', title: 'Community strategy'},
      canModerate: false,
      links: {home: '/', manageInvites: null},
    }}),
  ));
  renderJoin();
  // The consultation title is organizer-authored content, passed into the sentence as $1.
  expect(await screen.findByText(/Community strategy/)).toBeVisible();
  expect(screen.getByText(/restricted to invited participants/)).toBeVisible();
});
