import {Suspense} from 'react';
import {QueryClientProvider} from '@tanstack/react-query';
import {render, screen, within} from '@testing-library/react';
import {http, HttpResponse} from 'msw';
import {MemoryRouter} from 'react-router-dom';
import {expect, test, vi} from 'vitest';

import type {components} from '../../api/schema';
import {AdminLifecyclePage} from './admin-lifecycle-page';
import {MessageProvider} from '../../i18n/messages';
import {createQueryClient} from '../../query-client';
import {server} from '../../test/server';
import {testMessages} from '../../test/handlers';

type Lifecycle = components['schemas']['AdminLifecycle'];

const LIFECYCLE_URL = new URL('/api/v1/admin/conversations/7', globalThis.location.origin).toString();

/** An active consultation mid-route: one unmet readiness check, live statistics from an
 *  informed-voting round, and the advanced controls visible. Enough branches in one
 *  fixture to cover parameters, plurals, inline markup and aria labels. */
const lifecycle: Lifecycle = {
  conversation: {id: 7, slug: 'community-strategy', title: 'Community strategy', accessPolicy: 'public', status: 'active', publication: 'not_applicable', closedAt: null, identityReveal: null},
  operator: {roleLabel: 'Global admin'},
  phase: {linear: true, currentIndex: 1, activeKeys: ['submission'], steps: [
    {key: 'preparation', label: 'Preparation', effect: 'Configure and seed the conversation.', state: 'completed'},
    {key: 'submission', label: 'Explore', effect: 'Participants submit and vote on statements.', state: 'current'},
    {key: 'public_results', label: 'Report', effect: 'Prepare and publish final results.', state: 'upcoming'},
  ], transition: {source: {key: 'submission', label: 'Explore'}, target: {key: 'argument_mapping', label: 'Arguments'}, consequence: {opens: 'Argument submission', closes: 'Statement submission'}, preconditions: [
    {id: 'moderated', label: 'Every statement has been moderated', met: false, note: '3 pending'},
  ], requiresPhase6Initialization: false, showPauseGuidance: true}, phase6Setup: null, advancedControls: [
    {key: 'argument_mapping', label: 'Arguments', effect: 'x', active: false, requiresInitialization: false, initialized: true},
  ]},
  schedule: {canSchedule: false, scheduledAt: null, targetKey: null, targetLabel: null, frozen: false},
  publicationReadiness: {windowOpen: false, preconditions: []},
  statistics: {upstreamUnavailable: false, groups: [{key: 'submission', label: 'Explore', tiles: []}],
    informedVoting: {participants: 9, statementCount: 4, excludedStatementCount: 0, excludedParticipantCount: 0,
      largestShift: {text: 'Regional communities should share infrastructure funding.', shift: 12}}},
  counts: {participants: 12, invitations: 1, openFlags: 1, featuredStatements: 4},
  capabilities: {advancePhase: true, pause: true, publish: false, editSettings: true, useAdvancedPhases: true, initializePhase6: false, archive: true},
  links: {self: '/api/v1/admin/conversations/7', participantView: '/c/community-strategy', participants: '/admin/conversations/7/participants', moderation: '/admin/conversations/7/flags', invitations: '/admin/conversations/7/invites', roles: '/admin/conversations/7/roles', statements: '/admin/conversations/7/statements', featuredStatements: '/admin/conversations/7/featured', settings: '/admin/conversations/7/settings', termination: '/admin/conversations/7/termination'},
};

/** Closed and published, with the identity-reveal window open -- the danger-zone
 *  description, which is assembled from two parameterised sentences. */
const closedLifecycle: Lifecycle = {
  ...lifecycle,
  conversation: {...lifecycle.conversation, status: 'closed', publication: 'published', closedAt: '2026-07-01T12:00:00Z',
    identityReveal: {state: 'open', opensAt: '2026-07-01T12:00:00Z', closesAt: '2026-09-01T12:00:00Z', daysLeft: 30}},
  phase: {...lifecycle.phase, currentIndex: 2, activeKeys: ['public_results'], transition: null,
    steps: lifecycle.phase.steps.map((step, index) => ({...step, state: index === 2 ? 'current' : 'completed'}))},
};

/** The page takes the conversation id as a prop, so this renders the console itself
 *  rather than booting the whole app through a route -- which destabilises the
 *  neighbouring admin tests. Only the session, the catalogue and the admin payloads load. */
function renderConsole() {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter>
        <Suspense fallback={null}>
          <MessageProvider locale="en"><AdminLifecyclePage conversationId={7} csrfToken="test-csrf-token" /></MessageProvider>
        </Suspense>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function serve(payload: Lifecycle) {
  server.use(http.get(LIFECYCLE_URL, () => HttpResponse.json({data: payload})));
}

test('renders the admin console from the catalogue English', async () => {
  serve(lifecycle);
  renderConsole();

  expect(await screen.findByRole('heading', {name: 'Community strategy'}, {timeout: 10_000})).toBeVisible();
  expect(screen.getByRole('list', {name: 'Consultation phase progress'})).toBeVisible();
  expect(screen.getByText('You are in phase 2 of 3')).toBeVisible();
  expect(screen.getByRole('group', {name: 'Phase control mode'})).toBeVisible();
  expect(screen.getByText('1 readiness check still need resolving before Arguments')).toBeVisible();
  expect(screen.getByRole('button', {name: 'Move on to Arguments →'})).toBeDisabled();
  expect(screen.getByText('1 invite')).toBeVisible();
  expect(screen.getAllByText('12 participants joined').length).toBe(1);
  expect(screen.getByText('Need time to coordinate inviting people back? You can pause first.')).toBeVisible();
  // Inline markup in a catalogue message stays markup rather than being escaped into text.
  expect(within(screen.getByText(/These toggles act independently/)).getByText('Advanced.').tagName).toBe('STRONG');
  // The document title is an interface frame around an untranslated content value.
  expect(document.title).toBe('Manage Community strategy — Proto');
  // Participant- and organizer-authored content is never routed through the catalogue.
  expect(screen.getByText('Regional communities should share infrastructure funding.', {exact: false})).toBeVisible();
  expect(screen.getByText('Every statement has been moderated', {exact: false})).toBeVisible();
});

test('the settings page is reachable from the management cards', async () => {
  // The lifecycle payload has carried links.settings all along; until now no component
  // rendered it, so the page could only be opened by typing its URL.
  serve(lifecycle);
  renderConsole();

  const settings = await screen.findByRole('link', {name: /Settings/}, {timeout: 10_000});
  expect(settings).toHaveAttribute('href', '/admin/conversations/7/settings');
  expect(within(settings).getByText('Title, introduction and access')).toBeVisible();
});

test('the access policy is named in plain words, not by its stored value', async () => {
  serve({...lifecycle, conversation: {...lifecycle.conversation, accessPolicy: 'invite_only'}});
  renderConsole();

  await screen.findByRole('heading', {name: 'Community strategy'}, {timeout: 10_000});
  // The line under the title is where this PR takes the stored value off the screen. The
  // configuration select further down still carries the raw values on purpose (#465 deletes
  // that control), so the negative assertion is scoped to the subtitle, not the whole page.
  expect(document.querySelector('.console-sub')?.textContent)
    .toContain('Only people who have been given access');
  expect(document.querySelector('.console-sub')?.textContent).not.toContain('invite_only');
});

test('renders the closed-consultation description from parameterised sentences', async () => {
  serve(closedLifecycle);
  renderConsole();

  expect(await screen.findByText('Permanently closed', {exact: false}, {timeout: 10_000})).toBeVisible();
  // Two parameterised sentences joined at the sentence boundary, each reorderable inside.
  expect(document.querySelector('.danger-row-desc')?.textContent)
    .toBe('Closed 1 Jul 2026. Participants can link their Wikimedia username until 1 Sept 2026.');
  expect(screen.getByText('Published')).toBeVisible();
  expect(screen.getByText('The final aggregate report is published and participant activity is closed.')).toBeVisible();
});

test('renders console text from the catalogue, not from source literals', async () => {
  // Non-vacuity: serve deliberately different English for keys spread across the page --
  // a kicker, an aria-label, a two-parameter sentence, a plural, a parameterised button,
  // an inline-markup note, a status badge and the document title. None of these
  // assertions can pass against a hardcoded literal.
  server.use(
    http.get(
      new URL('/api/v1/i18n/:locale', globalThis.location.origin).toString(),
      () => HttpResponse.json({
        ...testMessages,
        'adminconv-phase-control': 'CATALOGUE PHASE KICKER',
        'adminconv-journey-aria': 'CATALOGUE STEPPER LABEL',
        'adminconv-you-are-in-phase': 'Step $1 of $2, catalogue-side',
        'adminconv-readiness-unmet': '$2 is blocked by $1 {{PLURAL:$1|item|items}}',
        'adminconv-invite-count': '$1 {{PLURAL:$1|pass|passes}} handed out',
        'adminconv-move-on-to': 'Advance into $1',
        'adminconv-advanced-note': '<strong>CATALOGUE WARNING</strong> use with care.',
        'adminconv-status-active': 'RUNNING',
        'adminconv-doc-title': 'Console for $1',
      }),
    ),
  );
  serve(lifecycle);
  renderConsole();

  expect(await screen.findByText('CATALOGUE PHASE KICKER', {}, {timeout: 10_000})).toBeVisible();
  expect(screen.getByRole('list', {name: 'CATALOGUE STEPPER LABEL'})).toBeVisible();
  expect(screen.getByText('Step 2 of 3, catalogue-side')).toBeVisible();
  expect(screen.getByText('Arguments is blocked by 1 item')).toBeVisible();
  expect(screen.getByText('1 pass handed out')).toBeVisible();
  expect(screen.getByRole('button', {name: 'Advance into Arguments'})).toBeInTheDocument();
  expect(within(screen.getByText(/use with care/)).getByText('CATALOGUE WARNING').tagName).toBe('STRONG');
  expect(screen.getByText('RUNNING')).toBeVisible();
  expect(document.title).toBe('Console for Community strategy');
  expect(screen.queryByText('Phase control')).not.toBeInTheDocument();
  expect(screen.queryByText('You are in phase 2 of 3')).not.toBeInTheDocument();
});

/** A transition due in thirty seconds, which is when the countdown falls back to its
 *  "under a minute" message. */
function dueShortly(): Lifecycle {
  return {...lifecycle, schedule: {canSchedule: true, scheduledAt: new Date(Date.now() + 30_000).toISOString(), targetKey: 'argument_mapping', targetLabel: 'Arguments', frozen: false}};
}

test('a transition under a minute away shows its countdown instead of blanking the console', async () => {
  // Under a minute, the countdown uses adminconv-countdown-lt1m on its own.
  serve(dueShortly());
  renderConsole();
  expect(await screen.findByText('under 1 min')).toBeVisible();
});

test('a message banana cannot parse degrades to its key, not to a blank page', async () => {
  // banana-i18n throws on a bare "<"; msg() shows the key for that message and the rest of
  // the console still renders.
  server.use(http.get(new URL('/api/v1/i18n/:locale', globalThis.location.origin).toString(),
    () => HttpResponse.json({...testMessages, 'adminconv-countdown-lt1m': '<1m'})));
  const errors = vi.spyOn(console, 'error').mockImplementation(() => {});
  serve(dueShortly());
  renderConsole();
  expect(await screen.findByText('adminconv-countdown-lt1m')).toBeVisible();
  expect(screen.getByText('Every statement has been moderated', {exact: false})).toBeVisible();
  // Reported once, though the countdown re-renders.
  expect(errors.mock.calls.filter(([message]) => String(message).includes('adminconv-countdown-lt1m'))).toHaveLength(1);
});
