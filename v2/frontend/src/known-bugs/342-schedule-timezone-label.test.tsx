// Known bug: the failing tests use test.fails. When the fix lands they pass, vitest reports
// that as a failure, and the fix turns them back into plain test().
import {QueryClientProvider} from '@tanstack/react-query';
import {render, screen} from '@testing-library/react';
import {http, HttpResponse} from 'msw';
import {MemoryRouter} from 'react-router-dom';
import {expect, test} from 'vitest';

import type {components} from '../api/schema';
import {App} from '../app';
import {createQueryClient} from '../query-client';
import {server} from '../test/server';

type Card = components['schemas']['ConversationCard'];

/** The instant from the #342 report: 2026-09-05T09:43:51Z. Vitest pins TZ=UTC (vite.config.ts),
 *  so the reader's own zone and UTC coincide here and what is asserted is the presence of the
 *  LABEL, not which offset was chosen. */
const AT = '2026-09-05T09:43:51Z';

/** A timezone designator as Intl may spell it: "UTC", "GMT", "GMT+2", "Coordinated Universal
 *  Time". #270 asks that the zone be stated, not which spelling is used. */
const ZONE_LABEL = /\b(?:UTC|GMT)(?:[+-]\d{1,2})?\b|Coordinated Universal Time/;

function card(overrides: Partial<Card> = {}): Card {
  return {
    slug: 'community-strategy', title: 'Community strategy', relationship: 'joined',
    participantState: 'needs_attention', pseudonym: 'quiet-otter', status: 'open', closedAt: null,
    phases: ['informed_voting'], statementsRemaining: null,
    scheduledTransition: {at: AT, target: 'informed_voting', targetLabel: 'Informed opinion'},
    reveal: null, outputs: [], capabilities: {join: false, participate: true, moderate: false},
    links: {self: '/c/community-strategy', about: '/c/community-strategy/about'},
    ...overrides,
  } as Card;
}

function oneConversationWithASchedule() {
  return http.get(new URL('/api/v1/conversations', globalThis.location.origin).toString(), () => HttpResponse.json({data: {
    space: 'real',
    authenticated: true,
    groups: {
      needsAttention: [card()], caughtUp: [], inactive: [], archived: [], available: [], moderating: [],
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

/** The chip's <time>, once the lane has rendered. */
async function scheduledTime(): Promise<HTMLElement> {
  await screen.findByRole('heading', {name: 'Community strategy'});
  const time = document.querySelector<HTMLElement>('time[data-local-datetime]');
  if (!time) {
    throw new Error('#342: the participant home page rendered no scheduled-transition time to read');
  }
  return time;
}

test.fails('#342: a scheduled-transition time on the participant page states its timezone', async () => {
  server.use(oneConversationWithASchedule());
  renderLane();

  const time = await scheduledTime();
  // The clock time itself is still there: the fix adds a label, it does not drop the time.
  expect(time.textContent ?? '', '#342: the scheduled-transition time should still show the clock time (09:43) as well as its zone')
    .toMatch(/09:43/);
  // The label may sit inside the <time> or right beside it, in the same line of text.
  expect(time.parentElement?.textContent ?? '', '#342: the scheduled-transition time should name the timezone it is shown in, e.g. "09:43 UTC" or "09:43 GMT+2", so the participant page and the admin console do not read as two different times for one instant')
    .toMatch(ZONE_LABEL);
});

test('#342: the scheduled-transition time is still a machine-readable UTC instant', async () => {
  server.use(oneConversationWithASchedule());
  renderLane();

  const time = await scheduledTime();
  expect(time.getAttribute('datetime'), '#342: the rendered time should keep the machine-readable UTC instant in its datetime attribute')
    .not.toBeNull();
  expect(Date.parse(time.getAttribute('datetime') ?? ''), '#342: the datetime attribute should be the same instant, however it is spelled')
    .toBe(Date.parse(AT));
});
