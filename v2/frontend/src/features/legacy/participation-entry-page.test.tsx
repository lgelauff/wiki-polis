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
  // Catches a key that is renamed, missing from en.json, or wired to the wrong element: the
  // page then shows the raw key or other text. The form still submits in that state, so the
  // consent text and licence heading, which the participant agrees to, are checked by name.
  expect(screen.getByText(testMessages['accept-consent']!)).toBeVisible();
  expect(screen.getByRole('heading', {name: testMessages['accept-licence-heading']!})).toBeVisible();
  expect(screen.getByText(testMessages['accept-privacy-summary']!)).toBeVisible();
  expect(screen.getByRole('button', {name: testMessages['accept-reroll-aria']!})).toBeVisible();
});

test('the licence sentence keeps its link inside one message', async () => {
  renderJoin();
  // Catches the link leaving the sentence or turning into visible markup: the message losing
  // its $1 (easy in a translation), or richHtml being swapped for plain text rendering. Scoped
  // to this section because the shell footer renders a second CC0 link.
  await screen.findByText(testMessages['accept-licence-heading']!);
  const section = document.getElementById('accept-licence-note');
  expect(section).not.toBeNull();
  const link = within(section!).getByRole('link', {name: /CC0/});
  expect(link).toHaveAttribute('href', 'https://creativecommons.org/publicdomain/zero/1.0/');
  expect(link.closest('p')?.textContent).toContain('released into the public domain (CC0');
});

test('the identity-reveal window reads as one sentence with both numbers', async () => {
  renderJoin();
  // Catches a parameter that is dropped or passed in the wrong position, and a plural unit
  // that fails to resolve. The sentence still renders in each case; only the numbers show it.
  const details = await screen.findByText(testMessages['accept-privacy-details-summary']!);
  const body = details.closest('details')?.textContent ?? '';
  expect(body).toContain('From');
  expect(body).toContain('30');
  expect(body).toContain('60 days');
  expect(body).toContain('link your Wikimedia username');
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
  // Catches the organizer's title going missing from the sentence, e.g. $1 not being passed.
  expect(await screen.findByText(/Community strategy/)).toBeVisible();
  expect(screen.getByText(/restricted to invited participants/)).toBeVisible();
});
