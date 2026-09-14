import {QueryClientProvider} from '@tanstack/react-query';
import {render, screen, within} from '@testing-library/react';
import {http, HttpResponse} from 'msw';
import {MemoryRouter} from 'react-router-dom';
import {afterEach, beforeEach, expect, test, vi} from 'vitest';

import type {components} from '../../api/schema';
import {App} from '../../app';
import {createQueryClient} from '../../query-client';
import {renderAsQqx, untranslatedCopy} from '../../test/i18n';
import {server} from '../../test/server';

type Reveal = components['schemas']['IdentityReveal'];
type State = Reveal['state'];

const USERNAME = 'Example editor';
const PSEUDONYM = 'quiet-otter';

function reveal(state: State): Reveal {
  return {
    slug: 'community-strategy', title: 'Community strategy', state, pseudonym: PSEUDONYM,
    wikimediaUsername: USERNAME, publicUsername: state === 'revealed' ? USERNAME : null,
    timeline: {
      closedAt: '2026-06-01T12:00:00Z', opensAt: '2026-07-01T12:00:00Z', closesAt: '2026-08-15T12:00:00Z',
      nextBoundaryAt: state === 'pending' ? '2026-07-01T12:00:00Z' : state === 'open' ? '2026-08-15T12:00:00Z' : null,
      daysRemaining: 12,
    },
    capabilities: {revealIdentity: state === 'open'},
    links: {self: '/api/v1/conversations/community-strategy/identity-reveal', conversation: '/c/community-strategy', about: '/c/community-strategy/about'},
  };
}

function renderReveal(state: State) {
  server.use(http.get(new URL('/api/v1/conversations/community-strategy/identity-reveal', globalThis.location.origin).toString(),
    () => HttpResponse.json({data: reveal(state)})));
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={['/c/community-strategy/reveal']}><App /></MemoryRouter>
    </QueryClientProvider>,
  );
}

// A fixed clock, so the countdown text is stable: 27 days, 2 hours before the window closes.
beforeEach(() => {
  vi.useFakeTimers({toFake: ['Date']});
  vi.setSystemTime(new Date('2026-07-19T10:00:00Z'));
});
afterEach(() => vi.useRealTimers());

test.each(['pending', 'open', 'revealed', 'expired'] as const)(
  'under qqx, the %s identity-reveal page carries no English but the identities and dates',
  async (state) => {
    renderAsQqx();
    renderReveal(state);
    await screen.findByRole('heading', {level: 1});

    // Catches hardcoded copy on a page whose every sentence is a privacy commitment,
    // including the timeline, the warning list and the consent label.
    const content = [USERNAME, PSEUDONYM, 'Community strategy', '1 Jun 2026', '1 Jul 2026', '15 Aug 2026'];
    expect(untranslatedCopy([document.querySelector('.container'), document.querySelector('.header-crumb')], content)).toEqual([]);
  },
);

test('the open window names the username and the pseudonym in the right places', async () => {
  renderReveal('open');
  const heading = await screen.findByRole('heading', {level: 1});

  // Catches the two identities swapping places. Both are plain strings of the same kind, so
  // a swapped parameter would still read as a sentence -- and would misstate what is published.
  expect(heading).toHaveTextContent(`Permanently link ${PSEUDONYM} to your wiki name?`);
  expect(screen.getByText(/You may optionally publish that/)).toHaveTextContent(
    `You may optionally publish that ${USERNAME} voted as ${PSEUDONYM} in this conversation. Other pseudonyms you used elsewhere are unaffected.`);
  const warning = screen.getByText('Irreversible').closest<HTMLElement>('.close-warning')!;
  expect(within(warning).getAllByRole('listitem')[0]).toHaveTextContent(
    `Your Wikimedia username (${USERNAME}) will be permanently associated with your pseudonym ${PSEUDONYM} in exported records for this consultation.`);
  expect(screen.getByRole('checkbox')).toBeRequired();
  expect(screen.getByRole('checkbox').closest('label')).toHaveTextContent(
    `I understand this is irreversible. Link my Wikimedia username (${USERNAME}) to my pseudonym (${PSEUDONYM}).`);
});

test('the timeline counts its own days and the deadline sentence carries the countdown', async () => {
  renderReveal('open');
  await screen.findByRole('heading', {level: 1});

  // Catches the day counts or the countdown falling out of their sentences, or the window's
  // length being computed between the wrong two dates: the cooldown is 30 days, the window 45.
  const steps = [...document.querySelectorAll('.reveal-what')].map((node) => node.firstChild?.textContent);
  expect(steps).toEqual([
    'Closed — linking stays sealed for 30 days',
    'Window opens — 45 days to optionally link your Wikimedia username',
    'Window closes — records stay pseudonymous permanently',
  ]);
  expect(document.querySelector('.reveal-deadline')).toHaveTextContent('Window closes in 27d 02:00:00 — linking is permanent and cannot be undone.');
});

test('before the window opens, the page gives the opening date inside the sentence', async () => {
  renderReveal('pending');
  await screen.findByRole('heading', {name: 'Reveal window not yet open'});

  // Catches the date leaving the sentence, or the wrong boundary being shown.
  expect(screen.getByText(/has not opened yet/)).toHaveTextContent('The identity reveal window has not opened yet. It will open on 1 Jul 2026.');
  expect(document.querySelector('.reveal-deadline')).toHaveTextContent('Reveal window opens in');
});
