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
  counts: {participants: 12, openFlags: 1, featuredStatements: 4},
  capabilities: {advancePhase: true, pause: true, publish: false, editSettings: true, useAdvancedPhases: true, initializePhase6: false, archive: true},
  links: {self: '/api/v1/admin/conversations/7', participantView: '/c/community-strategy', moderation: '/admin/conversations/7/flags', statements: '/admin/conversations/7/statements', settings: '/admin/conversations/7/settings', termination: '/admin/conversations/7/termination'},
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

test('the page renders the console shell, not the legacy header and role bar', async () => {
  serve(lifecycle);
  const {container} = renderConsole();

  // The frame is the shell's: the sidebar landmark, the top bar and the main region all
  // come from AdminShell, so the page itself contributes only the content.
  expect(await screen.findByRole('navigation', {name: 'Admin sections'})).toBeVisible();
  expect(container.querySelector('.admin-shell')).not.toBeNull();
  expect(container.querySelectorAll('main')).toHaveLength(1);

  // The two things this issue removes, by the marks they left in the document: the legacy
  // shell's header, crumb, main and toast container, and the role bar. (The import itself
  // is a property of the diff, which the reviewer reads; its consequence is what a test
  // can see -- a class of LegacyShell on the page means the header is still in the tree.)
  for (const mark of ['.site-header', '.header-crumb', '.legacy-main', '#toast-container', '.role-bar']) {
    expect(container.querySelector(mark)).toBeNull();
  }
});

test('renders the admin console from the catalogue English', async () => {
  serve(lifecycle);
  renderConsole();

  expect(await screen.findByRole('heading', {name: 'Community strategy'}, {timeout: 10_000})).toBeVisible();
  expect(screen.getByRole('list', {name: 'Consultation phase progress'})).toBeVisible();
  expect(screen.getByText('You are in phase 2 of 3')).toBeVisible();
  expect(screen.getByRole('group', {name: 'Phase control mode'})).toBeVisible();
  expect(screen.getByText('1 readiness check still need resolving before Arguments')).toBeVisible();
  expect(screen.getByRole('button', {name: 'Move on to Arguments →'})).toBeDisabled();
  expect(screen.getByText('12 participants joined', {exact: false})).toBeVisible();
  expect(screen.getByText('Need time to coordinate inviting people back? You can pause first.')).toBeVisible();
  // Inline markup in a catalogue message stays markup rather than being escaped into text.
  expect(within(screen.getByText(/These toggles act independently/)).getByText('Advanced.').tagName).toBe('STRONG');
  // The document title is an interface frame around an untranslated content value.
  expect(document.title).toBe('Manage Community strategy — Proto');
  // Participant- and organizer-authored content is never routed through the catalogue.
  expect(screen.getByText('Regional communities should share infrastructure funding.', {exact: false})).toBeVisible();
  expect(screen.getByText('Every statement has been moderated', {exact: false})).toBeVisible();
});

test('edits no setting itself: Settings is reached from the sidebar', async () => {
  // The owner's condition: one setting, one place that edits it. The console used to carry
  // a second copy of the settings form -- title, intro, outro, the eligibility pair and the
  // complexity tier -- writing the same two endpoints the settings page writes. The
  // settings page is reached from the console sidebar, as every section is.
  serve(lifecycle);
  renderConsole();

  const sidebar = await screen.findByRole('navigation', {name: 'Admin sections'}, {timeout: 10_000});
  expect(within(sidebar).getByRole('link', {name: 'Settings'}))
    .toHaveAttribute('href', '/admin/conversations/7/settings');

  // Nothing on this page writes a setting any more. Queried by accessible name, so a
  // control that merely moved elsewhere on the page would still fail this.
  for (const name of ['Title', 'Introduction (HTML, optional)', 'Closing text (HTML, optional)',
    'Eligibility event ID', 'Eligibility label']) {
    expect(screen.queryByLabelText(name)).toBeNull();
  }
  expect(screen.queryByRole('combobox', {name: 'Complexity tier'})).toBeNull();
  expect(screen.queryByRole('button', {name: /^Save( settings)?$/})).toBeNull();
  expect(screen.queryByRole('button', {name: 'Save recommendations'})).toBeNull();

  // What stays is what the settings page does not show, plus the tier as a fact.
  expect(screen.getByText(/Route \(locked after launch\)/)).toBeVisible();
  expect(screen.getByText(/Polis ID/)).toBeVisible();
  expect(screen.getByText(/Complexity tier/)).toBeVisible();
});

const moderatorLifecycle: Lifecycle = {
  ...lifecycle,
  operator: {roleLabel: 'Moderator'},
  phase: {...lifecycle.phase, activeKeys: ['submission', 'informed_voting']},
  schedule: {canSchedule: true, scheduledAt: '2026-11-01T12:00:00Z', targetKey: 'argument_mapping', targetLabel: 'Arguments', frozen: false},
  capabilities: {advancePhase: false, pause: false, publish: false, editSettings: false, useAdvancedPhases: false, initializePhase6: false, archive: false},
};

test.each([
  ['an organizer or site admin', () => lifecycle],
  ['a moderator', () => moderatorLifecycle],
] as const)('the Overview has no Content & access block for %s; the sidebar reaches every section', async (_role, payload) => {
  // Owner, 2026-10-09: the block only repeated the sidebar and the section tab strips, and
  // once Invitations is always in the Settings strip nothing is reachable from it alone.
  serve(payload());
  renderConsole();

  const sidebar = await screen.findByRole('navigation', {name: 'Admin sections'}, {timeout: 10_000});
  expect(screen.queryByText('Content & access')).toBeNull();
  expect(document.querySelector('.manage-grid, .manage-card')).toBeNull();
  // The page's own content links to none of the pages the block's cards opened.
  const main = screen.getByRole('main');
  for (const old of ['statements', 'invites', 'featured', 'participants', 'flags', 'roles', 'settings']) {
    expect(main.querySelector(`a[href="/admin/conversations/7/${old}"]`)).toBeNull();
  }
  // Every section is one click away in the sidebar, for every role.
  expect(within(sidebar).getByRole('link', {name: 'Overview'})).toHaveAttribute('href', '/admin/conversations/7');
  expect(within(sidebar).getByRole('link', {name: 'Settings'})).toHaveAttribute('href', '/admin/conversations/7/settings');
  expect(within(sidebar).getByRole('link', {name: /^Moderation/})).toHaveAttribute('href', '/admin/conversations/7/flags');
  expect(within(sidebar).getByRole('link', {name: 'Content'})).toHaveAttribute('href', '/admin/conversations/7/statements');
});

test('a moderator sees the phase control and statistics read-only, with nothing that changes a phase', async () => {
  // Owner, 2026-10-09: moderators see the Overview, phase control and statistics included,
  // but cannot change anything there. Read-only means text, not disabled controls.
  serve(moderatorLifecycle);
  const {container} = renderConsole();

  expect(await screen.findByRole('list', {name: 'Consultation phase progress'}, {timeout: 10_000})).toBeVisible();
  expect(screen.getByText('You are in phase 2 of 3')).toBeVisible();
  expect(screen.getByText('Regional communities should share infrastructure funding.', {exact: false})).toBeVisible();
  expect(screen.getByText('Only an organizer or site admin can change phases.')).toBeVisible();

  for (const name of [/Move on/, /^Pause$/, /^Resume$/, /^Save phases$/, /^Initialise Phase 6$/, /^Set$/, /^Edit$/, /^Freeze$/, /^Advanced$/]) {
    expect(screen.queryByRole('button', {name})).toBeNull();
  }
  expect(screen.queryByRole('group', {name: 'Phase control mode'})).toBeNull();
  // Nothing operable anywhere in the phase control: no button, no checkbox, no date input.
  expect(container.querySelectorAll(
    '#phaseControl :is(button, input, select, form), .mode-guided-part :is(button, input, select, form), .mode-advanced-part',
  )).toHaveLength(0);
});

test('a moderator is told which phase comes next and when, only while a transition is scheduled', async () => {
  // Owner, 2026-10-09: for a moderator no readiness list and no "next phase" head; one plain
  // line when a transition is scheduled, in the participant notice's words.
  serve(moderatorLifecycle);
  const {container} = renderConsole();

  await screen.findByRole('list', {name: 'Consultation phase progress'}, {timeout: 10_000});
  const line = container.querySelector('.admin-scheduled-transition');
  expect(line).not.toBeNull();
  const [before] = testMessages['conv-scheduled-transition']!.split('<strong>');
  expect(line!.textContent!.startsWith(before!)).toBe(true);
  expect(line!.querySelector('strong')).toHaveTextContent(testMessages['phase-label-argument_mapping']!);
  expect(line!.querySelector('time')).toHaveAttribute('datetime', '2026-11-01T12:00:00Z');
  // Text only, and no readiness list.
  expect(line!.querySelectorAll('button, input, a')).toHaveLength(0);
  expect(screen.queryByText('Every statement has been moderated', {exact: false})).toBeNull();
});

test('a moderator sees no next-phase line when nothing is scheduled, or the schedule is frozen', async () => {
  for (const schedule of [
    {...moderatorLifecycle.schedule, scheduledAt: null, targetKey: null, targetLabel: null},
    {...moderatorLifecycle.schedule, frozen: true},
  ]) {
    serve({...moderatorLifecycle, schedule});
    const {container, unmount} = renderConsole();

    await screen.findByRole('list', {name: 'Consultation phase progress'}, {timeout: 10_000});
    expect(container.querySelector('.admin-scheduled-transition')).toBeNull();
    unmount();
  }
});
