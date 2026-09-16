import {QueryClientProvider} from '@tanstack/react-query';
import {fireEvent, render, screen, waitFor, within} from '@testing-library/react';
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

const REVEAL_URL = new URL('/api/v1/conversations/community-strategy/identity-reveal', globalThis.location.origin).toString();

function renderReveal(state: State, ...later: State[]) {
  // Each fetch after the first serves the next state in `later`, then stays on the last one.
  const states = [state, ...later];
  let fetches = 0;
  server.use(http.get(REVEAL_URL, () => HttpResponse.json({data: reveal(states[Math.min(fetches++, states.length - 1)] ?? state)})));
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
  expect(heading).toHaveTextContent(`Permanently link ${PSEUDONYM} to your Wikimedia username?`);
  expect(screen.getByText(/You can publish that/)).toHaveTextContent(
    `You can publish that ${USERNAME} expressed opinions as ${PSEUDONYM} in this consultation process. Other pseudonyms you used elsewhere are not affected.`);
  const warning = screen.getByText('Irreversible').closest<HTMLElement>('.close-warning')!;
  expect(within(warning).getAllByRole('listitem')[0]).toHaveTextContent(
    `Your Wikimedia username (${USERNAME}) will be permanently linked to your pseudonym ${PSEUDONYM} in the exported records of this consultation.`);
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
    'Closed — linking is not possible for 30 days',
    'Linking opens — 45 days to link your Wikimedia username if you want to',
    'Linking closes — after this, you can no longer link your username to your opinions',
  ]);
  expect(document.querySelector('.reveal-deadline')).toHaveTextContent('Linking closes in 27d 02:00:00 — once you link, it is permanent and cannot be undone.');
});

test('before the window opens, the page gives the opening date inside the sentence', async () => {
  vi.setSystemTime(new Date('2026-06-20T10:00:00Z'));
  renderReveal('pending');
  await screen.findByRole('heading', {name: 'Linking has not opened yet'});

  // Catches the date leaving the sentence, or the countdown counting to the wrong boundary.
  expect(screen.getByText(/You cannot link your Wikimedia username yet/)).toHaveTextContent('You cannot link your Wikimedia username yet. You can do that from 1 Jul 2026.');
  expect(document.querySelector('.reveal-deadline')).toHaveTextContent('Linking opens in 11d 02:00:00.');
});

test('the countdown is one message, so a translation can write days its own way', async () => {
  renderAsQqx();
  renderReveal('open');
  await screen.findByRole('heading', {level: 1});

  // Catches the days and time being assembled in code, where "d" cannot be translated.
  expect(document.querySelector('.reveal-countdown')).toHaveTextContent('(reveal-tl-countdown: 27, 02:00:00)');
});

test('the deadline sentence stays in place while its clock ticks', async () => {
  renderReveal('open');
  await screen.findByRole('heading', {level: 1});
  const sentence = document.querySelector('.reveal-deadline')!;
  const clock = sentence.querySelector('.reveal-countdown')!;

  vi.setSystemTime(new Date('2026-07-19T10:00:05Z'));
  // Catches the sentence being rebuilt on every tick. It says linking cannot be undone, and
  // replacing it each second resets a screen reader's position in it and any selection.
  await waitFor(() => expect(clock).toHaveTextContent('27d 01:59:55'), {timeout: 2000});
  expect(sentence.isConnected).toBe(true);
  expect(clock.isConnected).toBe(true);
});

test('when the window closes on an open page, the countdown stops and the page reloads its state', async () => {
  renderReveal('open', 'expired');
  await screen.findByRole('heading', {name: `Permanently link ${PSEUDONYM} to your Wikimedia username?`});

  vi.setSystemTime(new Date('2026-08-15T12:00:01Z'));
  // Catches the countdown running past zero ("closes in now") and the page keeping a live
  // submit button for a window that has closed.
  expect(await screen.findByRole('heading', {name: 'Linking has closed'}, {timeout: 2000})).toBeVisible();
  expect(document.querySelector('.reveal-deadline')).toBeNull();
  expect(screen.queryByRole('button', {name: 'Yes, link my identity'})).toBeNull();
});

async function submitReveal() {
  await screen.findByRole('heading', {level: 1});
  fireEvent.click(screen.getByRole('checkbox'));
  fireEvent.click(screen.getByRole('button', {name: 'Yes, link my identity'}));
  return screen.findByRole('alert');
}

test('a refused reveal says nothing was linked', async () => {
  server.use(http.post(REVEAL_URL, () => HttpResponse.json(
    {error: {code: 'identity_reveal_unavailable', message: 'Identity reveal is not available in the current timeline state.'}},
    {status: 409})));
  renderReveal('open');

  // Catches a failed submit leaving the page silent, with the button enabled again.
  expect(await submitReveal()).toHaveTextContent('Your identity was not linked, because linking is not open.');
});

test('a reveal that fails in transit does not claim the identity is unlinked', async () => {
  server.use(http.post(REVEAL_URL, () => HttpResponse.error()));
  renderReveal('open');

  // Catches the "not linked" message after a failure where the server may already have
  // linked the identity before the response was lost.
  expect(await submitReveal()).toHaveTextContent('We could not confirm whether your identity was linked. Reload this page to see its current state.');
});
