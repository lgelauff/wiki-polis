import {QueryClientProvider} from '@tanstack/react-query';
import {render, screen, within} from '@testing-library/react';
import {http, HttpResponse} from 'msw';
import {MemoryRouter} from 'react-router-dom';
import {expect, test} from 'vitest';

import {App} from '../../app';
import {createQueryClient} from '../../query-client';
import {server} from '../../test/server';
import {testMessages} from '../../test/handlers';

/** The join screen had no test at all before this file, which is how a page carrying the
 *  consent checkbox, the licence disclosure and the privacy summary — every word of it
 *  load-bearing — could have been rewritten without evidence that it still rendered. */
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
  // The consent checkbox and the licence disclosure are the two the participant is agreeing
  // to; if either silently failed to render, the page would still look plausible.
  expect(screen.getByText(testMessages['accept-consent']!)).toBeVisible();
  expect(screen.getByRole('heading', {name: testMessages['accept-licence-heading']!})).toBeVisible();
  expect(screen.getByText(testMessages['accept-privacy-summary']!)).toBeVisible();
  expect(screen.getByRole('button', {name: testMessages['accept-reroll-aria']!})).toBeVisible();
});

test('the licence sentence keeps its link inside one message', async () => {
  renderJoin();
  // It used to be three pieces with the CC0 link between them, which fixed the English word
  // order. One message now, with the link passed in as $1.
  // Two CC0 links render: this one and the shell's footer, both from accept-licence-link.
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
  // accept-privacy-window-a/-b/-c (now accept-privacy-reveal-window) were "Between", "and", and the rest, with the two numbers
  // interpolated between them. A translator could not reorder that.
  const details = await screen.findByText(testMessages['accept-privacy-details-summary']!);
  const body = details.closest('details')?.textContent ?? '';
  expect(body).toContain('Between');
  expect(body).toContain('30');
  expect(body).toContain('60 days');
  expect(body).toContain('permanently link your username');
});

test('the eligibility rule names what it requires, in one sentence', async () => {
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
  // The consultation title is organizer-authored and must survive untranslated, inside a
  // sentence that used to be split around it.
  expect(await screen.findByText(/Community strategy/)).toBeVisible();
  expect(screen.getByText(/restricted to invited participants/)).toBeVisible();
});
