import {QueryClientProvider} from '@tanstack/react-query';
import {fireEvent, render, screen} from '@testing-library/react';
import {http, HttpResponse} from 'msw';
import {MemoryRouter} from 'react-router-dom';
import {expect, test} from 'vitest';

import type {components} from '../../api/schema';
import {App} from '../../app';
import {createQueryClient} from '../../query-client';
import {renderAsQqx, untranslatedCopy} from '../../test/i18n';
import {server} from '../../test/server';

type Card = components['schemas']['ConversationCard'];
type Output = components['schemas']['ConversationOutput'];

/** The server still sends English labels for outputs and the scheduled phase, as a fallback
 *  the SPA ignores when the catalogue has the identifier. These are deliberately unlike the
 *  catalogue's English, so a component echoing the server shows up as the wrong text. */
const SERVER_ENGLISH = 'SERVER ENGLISH';

function output(key: string, ready: boolean): Output {
  return {
    key, label: SERVER_ENGLISH, status: 'provisional', symbol: key,
    tooltip: SERVER_ENGLISH, pending: SERVER_ENGLISH, ready,
    href: ready ? `/c/community-strategy/outputs/${key}` : null,
  };
}

function card(slug: string, title: string, overrides: Partial<Card> = {}): Card {
  return {
    slug, title, relationship: 'joined', participantState: 'needs_attention',
    pseudonym: 'quiet-otter', status: 'open', closedAt: null, phases: ['submission'],
    statementsRemaining: null, scheduledTransition: null, reveal: null, outputs: [],
    capabilities: {join: false, participate: true, moderate: false},
    links: {self: `/c/${slug}`, about: `/c/${slug}/about`},
    ...overrides,
  };
}

/** One card in every state the lane can show, so a single render reaches every string. */
const TITLES = ['Community strategy', 'Movement charter', 'Grants review', 'Budget round', 'Archive policy', 'Open board', 'Moderated board'];

function everyState(authenticated = true) {
  return http.get(new URL('/api/v1/conversations', globalThis.location.origin).toString(), () => HttpResponse.json({data: {
    space: 'real',
    authenticated,
    groups: {
      needsAttention: [card('community-strategy', 'Community strategy', {
        statementsRemaining: 1,
        phases: ['informed_voting'],
        scheduledTransition: {at: '2026-10-01T12:00:00Z', target: 'informed_voting', targetLabel: SERVER_ENGLISH},
        reveal: {state: 'open', daysRemaining: 3},
        outputs: [output('initial-clustering', true), output('argument-map', false)],
      })],
      caughtUp: [card('movement-charter', 'Movement charter', {participantState: 'caught_up', statementsRemaining: 0, reveal: {state: 'pending', daysRemaining: 12}})],
      inactive: [
        card('grants-review', 'Grants review', {participantState: 'inactive', status: 'paused'}),
        card('budget-round', 'Budget round', {participantState: 'inactive', status: 'open'}),
      ],
      archived: [card('archive-policy', 'Archive policy', {
        participantState: 'archived', status: 'archived', closedAt: '2026-08-31T23:30:00Z',
        phases: ['closed'], reveal: {state: 'open', daysRemaining: 0},
      })],
      available: [card('open-board', 'Open board', {relationship: 'available', participantState: null, pseudonym: null})],
      moderating: [card('moderated-board', 'Moderated board', {relationship: 'moderating', participantState: null, status: 'archived', links: {self: '/c/moderated-board', about: '/c/moderated-board/about', admin: '/admin/conversations/9'}})],
    },
  }}));
}

function renderLane() {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={['/consultations']}><App /></MemoryRouter>
    </QueryClientProvider>,
  );
}

test('under qqx, nothing on the signed-in lane is English except the consultations', async () => {
  server.use(everyState());
  renderAsQqx();
  renderLane();
  await screen.findByRole('heading', {name: '(home-section-needs-attention)'});

  const content = [...TITLES, 'quiet-otter', 'Aug 2026', '1 Oct 2026, 12:00'];
  expect(untranslatedCopy([document.querySelector('.home-container'), document.getElementById('output-dialog')], content)).toEqual([]);
});

test('under qqx, nothing on the signed-out lane is English', async () => {
  server.use(
    everyState(false),
    http.get(new URL('/api/v1/session', globalThis.location.origin).toString(), () => HttpResponse.json({data: {
      state: 'anonymous', user: null, capabilities: {administerSite: false}, csrfToken: 'test-csrf-token',
      developerLogins: [{username: 'Dev editor', href: '/dev-login/Dev%20editor'}], gitVersion: 'test-version',
      locales: {current: 'en', available: [{code: 'en', name: 'English'}]}, links: {login: '/login', logout: '/logout'},
    }})),
  );
  renderAsQqx();
  renderLane();
  await screen.findByRole('heading', {name: '(home-open-consultations)'});

  expect(untranslatedCopy([document.querySelector('.home-container')], [...TITLES, 'Dev editor'])).toEqual([]);
});

test('a card announces its state as one label, with the count pluralised', async () => {
  server.use(everyState());
  renderLane();

  // Fragments joined in order: title, pseudonym, remaining, state. "1 statement", not "1 statements".
  expect(await screen.findByRole('link', {name: 'Community strategy — your pseudonym: quiet-otter — 1 statement to vote — continue'})).toBeVisible();
  expect(screen.getByRole('link', {name: 'Movement charter — your pseudonym: quiet-otter — caught up'})).toBeVisible();
  expect(screen.getByRole('link', {name: 'Grants review — your pseudonym: quiet-otter — inactive'})).toBeVisible();
  // The section is headed "Closed", so the card says closed too -- not the internal "archived".
  expect(screen.getByRole('link', {name: 'Archive policy — your pseudonym: quiet-otter — closed'})).toBeVisible();
});

test('output symbols and the scheduled phase read the catalogue, not the server English', async () => {
  server.use(everyState());
  renderLane();

  const pending = await screen.findByRole('button', {name: 'After Arguments phase: argument mapping'});
  expect(screen.getByRole('link', {name: 'After Explore phase: topic and participant clustering'})).toBeVisible();
  expect(screen.queryByText(SERVER_ENGLISH)).not.toBeInTheDocument();
  expect(document.body.innerHTML).not.toContain(SERVER_ENGLISH);

  fireEvent.click(pending);
  expect(screen.getByRole('dialog', {name: 'Argument map'})).toHaveTextContent(/opens when featured statements are visible/);

  const chip = screen.getByText(/^Next:/);
  expect(chip).toHaveTextContent('Next: Informed vote 1 Oct 2026, 12:00');
  expect(chip.querySelector('time')).toHaveAttribute('title', 'Shown in your local timezone');
});

test('a closed card shows its month, and the reveal chips their days', async () => {
  server.use(everyState());
  renderLane();

  await screen.findByRole('heading', {name: 'Closed'});
  // 23:30 UTC on 31 August is still August, whatever zone the reader is in.
  expect(screen.getByText('Aug 2026')).toBeVisible();
  expect(screen.getByText('Reveal window: 3d left')).toBeVisible();
  expect(screen.getByText('Reveal window: today')).toBeVisible();
  expect(screen.getByText('Reveal opens in 12d')).toBeVisible();
  expect(screen.getByText('paused')).toBeVisible();
  // An inactive consultation that is not paused is between phases.
  expect(screen.getByText('waiting')).toBeVisible();
});

test('dates follow the language the reader chose, not the browser', async () => {
  // The test runtime's own locale is en-US. Choosing Dutch must give Dutch dates even where
  // the copy around them is still English, as it is for any message not yet translated.
  server.use(everyState());
  globalThis.history.replaceState(null, '', '/?uselang=nl');
  renderLane();

  expect(await screen.findByText('aug 2026')).toBeVisible();
  expect(screen.getByText(/^Next:/)).toHaveTextContent('Next: Informed vote 1 okt 2026, 12:00');
});
