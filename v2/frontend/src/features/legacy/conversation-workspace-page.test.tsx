import {Suspense} from 'react';
import {QueryClientProvider} from '@tanstack/react-query';
import {render, screen, within} from '@testing-library/react';
import {http, HttpResponse} from 'msw';
import {MemoryRouter, Route, Routes} from 'react-router-dom';
import {expect, test} from 'vitest';

import type {components} from '../../api/schema';
import {ConversationWorkspacePage} from './conversation-workspace-page';
import {MessageProvider} from '../../i18n/messages';
import {createQueryClient} from '../../query-client';
import {server} from '../../test/server';
import {testMessages} from '../../test/handlers';

type Workspace = components['schemas']['ConversationWorkspace'];
type Explore = components['schemas']['ExploreState'];

const WORKSPACE_URL = new URL('/api/v1/conversations/community-strategy/workspace', globalThis.location.origin).toString();
const EXPLORE_URL = new URL('/api/v1/conversations/community-strategy/explore', globalThis.location.origin).toString();
const I18N_URL = new URL('/api/v1/i18n/:locale', globalThis.location.origin).toString();

/** An open real-space consultation on the voting tab, with the space warning and a
 *  scheduled phase change showing. Between them these cover plain labels, an aria-label,
 *  an aria-valuetext built from two numbers, a parameterised sentence with inline markup,
 *  and the document title. */
const workspace: Workspace = {
  slug: 'community-strategy',
  title: 'Community strategy',
  space: 'real',
  status: 'open',
  descriptionHtml: '<p>Shape the future together.</p>',
  outroHtml: null,
  viewer: {state: 'participant', pseudonym: 'quiet-otter'},
  spaceWarning: 'real',
  scheduledTransition: {at: '2026-08-02T09:30:00Z', target: 'argument_mapping', targetLabel: 'Arguments'},
  tabs: [{key: 'vote', label: 'Vote', dataHref: '/api/v1/conversations/community-strategy/explore'}],
  defaultTab: 'vote',
  reveal: null,
  statementContribution: {unlockAfter: 0, quota: 3, used: 0},
  capabilities: {participate: true, moderate: false},
  links: {
    self: '/api/v1/conversations/community-strategy/workspace',
    conversation: '/c/community-strategy',
    about: '/c/community-strategy/about',
    join: '/accept/community-strategy',
    explore: '/api/v1/conversations/community-strategy/explore',
  },
};

/** Closed, with the identity-reveal window open: the two sentences that interpolate a
 *  pseudonym and a date, plus the countdown line and its plural day counts. */
const closedWorkspace: Workspace = {
  ...workspace,
  status: 'closed',
  spaceWarning: null,
  scheduledTransition: null,
  tabs: [],
  reveal: {
    state: 'open', pseudonym: 'quiet-otter',
    closedAt: '2026-07-01T12:00:00Z', opensAt: '2026-08-01T12:00:00Z', closesAt: '2026-09-01T12:00:00Z',
    daysRemaining: 30, cooldownDays: 31, windowDays: 1, countdownTargetAt: '2126-09-01T12:00:00Z',
  },
};

const explore = {
  slug: 'community-strategy',
  title: 'Community strategy',
  pseudonym: 'quiet-otter',
  currentStatement: {id: 12, text: 'Our movement should invest more in shared technical infrastructure.', isMeta: false, isSeed: true},
  progress: {completed: 3, total: 12, remaining: 9, allDone: false},
  newStatement: {unlocked: false, unlockAfter: 4, quota: 3, used: 0, remaining: 3},
  capabilities: {vote: true, suggestWording: true, submitNewStatement: true},
  links: {
    self: '/api/v1/conversations/community-strategy/explore',
    about: '/c/community-strategy/about',
    conversation: '/c/community-strategy',
    arguments: '/c/community-strategy#tab-arguments',
  },
} as Explore;

/** The page reads its slug from the route, so this mounts just that route rather than
 *  booting the whole app through <App/>, which destabilises the neighbouring tests. */
function renderWorkspace() {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={['/c/community-strategy']}>
        <Suspense fallback={null}>
          <MessageProvider locale="en">
            <Routes><Route path="/c/:slug" element={<ConversationWorkspacePage />} /></Routes>
          </MessageProvider>
        </Suspense>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function serve(payload: Workspace, state: Explore = explore) {
  server.use(
    http.get(WORKSPACE_URL, () => HttpResponse.json({data: payload})),
    http.get(EXPLORE_URL, () => HttpResponse.json({data: state})),
  );
}

test('renders the voting workspace from the catalogue English', async () => {
  serve(workspace);
  renderWorkspace();

  expect(await screen.findByRole('button', {name: 'Agree'}, {timeout: 10_000})).toBeVisible();
  expect(screen.getByRole('button', {name: 'Disagree'})).toBeVisible();
  expect(screen.getByRole('progressbar', {name: 'Statements voted'}))
    .toHaveAttribute('aria-valuetext', '3 of 12 statements voted');
  expect(screen.getByText('Unlocks after 1 more vote')).toBeVisible();
  expect(screen.getByText('After you vote, you can…')).toBeVisible();
  expect(screen.getByRole('navigation', {name: 'Conversation context'})).toBeVisible();
  // Inline markup in a catalogue message stays markup rather than being escaped into text.
  const warning = screen.getByRole('alert');
  expect(within(warning).getByText('Live consultation.').tagName).toBe('STRONG');
  expect(warning).toHaveTextContent('These ballots are real — your votes here count.');
  // A sentence whose two values are an interface label and a <time> element.
  expect(document.querySelector('.output-context p')?.textContent)
    .toBe('Next: Arguments on 2 Aug 2026, 09:30.');
  expect(document.querySelector('.output-context time'))
    .toHaveAttribute('title', 'Shown in your local timezone');
  // The document title is an interface frame around an untranslated content value.
  expect(document.title).toBe('Community strategy — Proto');
  // Participant- and organizer-authored content is never routed through the catalogue.
  expect(document.querySelector('#statement-text')?.textContent)
    .toBe('Our movement should invest more in shared technical infrastructure.');
  expect(screen.getByText('Shape the future together.')).toBeVisible();
});

test('renders the closed workspace from parameterised sentences', async () => {
  serve(closedWorkspace);
  renderWorkspace();

  await screen.findByText(/This consultation closed on/, {}, {timeout: 10_000});
  // Each of these was a fragment joined around a value in JSX; they are single messages now.
  expect(document.querySelector('.landing-section > .muted')?.textContent).toBe(
    'This consultation closed on 1 Jul 2026. Your votes were recorded under your pseudonym;'
    + ' for a limited time you may optionally and permanently link your Wikimedia username to it.',
  );
  expect(document.querySelector('.reveal-callout-text')?.textContent).toBe(
    'The identity reveal window is open. Your participation is recorded under pseudonym quiet-otter.',
  );
  expect(document.querySelector('.reveal-deadline')?.textContent)
    .toMatch(/^Window closes in .+ — linking is permanent and cannot be undone\.$/);
  // The counts either side of the countdown drive their own plurals independently.
  expect(screen.getByText(/Closed — linking stays sealed for 31 days/)).toBeVisible();
  expect(screen.getByText(/Window opens — 1 day to optionally link/)).toBeVisible();
  expect(screen.getByText('quiet-otter').tagName).toBe('STRONG');
});

test('renders workspace text from the catalogue, not from source literals', async () => {
  // Non-vacuity: serve deliberately different English for keys covering distinct
  // mechanisms -- plain text, an aria-label, an aria-valuetext with two parameters, a
  // plural, a sentence with an interpolated value inside inline markup, and the document
  // title. None of these assertions can pass against a hardcoded literal.
  server.use(http.get(I18N_URL, () => HttpResponse.json({
    ...testMessages,
    'conv-vote-agree': 'CATALOGUE AGREE',
    'conv-crumb-aria': 'CATALOGUE BREADCRUMB',
    'conv-vote-progress-valuetext': '$1 done, $2 in all',
    'conv-newstmt-unlocks-more': 'after $1 further {{PLURAL:$1|ballot|ballots}}',
    'conv-space-warn-live-label': 'CATALOGUE LEAD.',
    'conv-scheduled-transition': 'Then <em>$1</em> at $2, catalogue-side.',
    'conv-doc-title': 'Workspace for $1',
  })));
  serve(workspace);
  renderWorkspace();

  expect(await screen.findByRole('button', {name: 'CATALOGUE AGREE'}, {timeout: 10_000})).toBeVisible();
  expect(screen.getByRole('navigation', {name: 'CATALOGUE BREADCRUMB'})).toBeVisible();
  expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuetext', '3 done, 12 in all');
  expect(screen.getByText('after 1 further ballot')).toBeVisible();
  expect(within(screen.getByRole('alert')).getByText('CATALOGUE LEAD.').tagName).toBe('STRONG');
  expect(document.querySelector('.output-context em')?.textContent).toBe('Arguments');
  expect(document.querySelector('.output-context p')?.textContent)
    .toBe('Then Arguments at 2 Aug 2026, 09:30, catalogue-side.');
  expect(document.title).toBe('Workspace for Community strategy');
  expect(screen.queryByRole('button', {name: 'Agree'})).not.toBeInTheDocument();
  expect(screen.queryByText('Unlocks after 1 more vote')).not.toBeInTheDocument();
  expect(screen.queryByText('Live consultation.')).not.toBeInTheDocument();
});

test('keeps the real-space and demo-space ballot warnings in separate messages', async () => {
  // The one string on this screen that tells a participant whether their vote counts.
  // Swapping the demo message must not be able to change what the real one says.
  server.use(http.get(I18N_URL, () => HttpResponse.json({
    ...testMessages,
    'conv-space-warn-demo-label': 'CHANGED DEMO LEAD.',
    'conv-space-warn-demo-body': 'CHANGED DEMO BODY.',
  })));
  serve(workspace);
  renderWorkspace();

  const warning = await screen.findByRole('alert', {}, {timeout: 10_000});
  expect(warning).toHaveTextContent('Live consultation. These ballots are real — your votes here count.');
  expect(warning).not.toHaveTextContent('CHANGED DEMO');
});
