import {Suspense} from 'react';
import {QueryClientProvider} from '@tanstack/react-query';
import {fireEvent, render, screen, within} from '@testing-library/react';
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
const STATEMENTS_URL = new URL('/api/v1/conversations/community-strategy/statements', globalThis.location.origin).toString();
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
 *  booting the whole app through <App/>, which destabilises the neighbouring tests. The
 *  locale is passed straight to the provider, so `qqx` is set here rather than in the URL. */
function renderWorkspace(locale = 'en') {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={['/c/community-strategy']}>
        <Suspense fallback={null}>
          <MessageProvider locale={locale}>
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
  expect(screen.getByRole('progressbar', {name: 'Statements you have responded to'}))
    .toHaveAttribute('aria-valuetext', 'You have responded to 3 of 12 statements');
  expect(screen.getByText('Unlocks after 1 more response')).toBeVisible();
  expect(screen.getByText('After you respond, you can…')).toBeVisible();
  expect(screen.getByRole('navigation', {name: 'Conversation context'})).toBeVisible();
  // Inline markup in a catalogue message stays markup rather than being escaped into text.
  const warning = screen.getByRole('alert');
  expect(within(warning).getByText('Live consultation.').tagName).toBe('STRONG');
  expect(warning).toHaveTextContent('These are active consultation processes with real responses.');
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
    'This consultation closed on 1 Jul 2026. Your responses were recorded under your pseudonym,'
    + ' and for a limited time you can choose to link your Wikimedia username to it.'
    + ' Linking cannot be undone.',
  );
  expect(document.querySelector('.reveal-callout-text')?.textContent).toBe(
    'Your participation is recorded under pseudonym quiet-otter, and you can now link your Wikimedia username to it.',
  );
  expect(document.querySelector('.reveal-deadline')?.textContent)
    .toMatch(/^Username linking closes in .+ — once you link, it is permanent and cannot be undone\.$/);
  // The counts either side of the countdown drive their own plurals independently.
  expect(screen.getByText(/Closed — you cannot link your username for 31 days/)).toBeVisible();
  expect(screen.getByText(/Opens — 1 day to link your Wikimedia username/)).toBeVisible();
  expect(screen.getByText('quiet-otter').tagName).toBe('STRONG');
});

test('a participant who has linked their identity sees no countdown', async () => {
  serve({...closedWorkspace, reveal: {...closedWorkspace.reveal!, state: 'revealed'}});
  renderWorkspace();

  await screen.findByText(/You linked your identity/, {}, {timeout: 10_000});
  // Catches a "Linking closes in …" line under the confirmation. The window's end no longer
  // concerns someone who has linked, even while a closing date is still sent.
  expect(document.querySelector('.reveal-deadline')).toBeNull();
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
  expect(screen.queryByText('Unlocks after 1 more response')).not.toBeInTheDocument();
  expect(screen.queryByText('Live consultation.')).not.toBeInTheDocument();
});

test('keeps the real-space and demo-space ballot warnings in separate messages', async () => {
  // The one string on this screen that tells a participant whether their responses count.
  // Swapping the demo message must not be able to change what the real one says.
  server.use(http.get(I18N_URL, () => HttpResponse.json({
    ...testMessages,
    'conv-space-warn-demo-label': 'CHANGED DEMO LEAD.',
    'conv-space-warn-demo-body': 'CHANGED DEMO BODY.',
  })));
  serve(workspace);
  renderWorkspace();

  const warning = await screen.findByRole('alert', {}, {timeout: 10_000});
  expect(warning).toHaveTextContent('Live consultation. These are active consultation processes with real responses.');
  expect(warning).not.toHaveTextContent('CHANGED DEMO');
});

/** English no catalogue message contains, standing in for the server's developer-facing
 *  `message`. Rule 4 of `plan_i18n.md`: the page must never show it. */
const SERVER_ENGLISH = 'Server-side English that must not reach the page.';

/** Opens the new-statement composer under qqx and submits it into an API error. */
async function submitFailingStatement(code: string, status: number) {
  serve(workspace, {
    ...explore,
    progress: {completed: 12, total: 12, remaining: 0, allDone: true},
    newStatement: {unlocked: true, unlockAfter: 4, quota: 3, used: 0, remaining: 3},
  });
  server.use(http.post(STATEMENTS_URL, () => HttpResponse.json(
    {error: {code, message: SERVER_ENGLISH}}, {status},
  )));
  renderWorkspace('qqx');

  fireEvent.click(await screen.findByRole('button', {name: /conv-triad-newstmt-title/}, {timeout: 10_000}));
  fireEvent.change(document.querySelector('.v2-composer-textarea')!, {target: {value: 'A new angle.'}});
  fireEvent.click(screen.getByRole('button', {name: '(conv-composer-submit)'}));
}

test.each([
  ['statement_quota_exceeded', 409, 'conv-err-proposal-limit'],
  ['derivative_similarity_too_low', 409, 'conv-err-similarity'],
  ['unknown_parent_statement', 400, 'conv-err-original-unavailable'],
  ['command_outcome_unknown', 502, 'conv-err-outcome-unknown'],
  ['idempotency_conflict', 409, 'conv-err-outcome-unknown'],
  ['upstream_unavailable', 502, 'conv-err-submit-statement'],
  ['validation_failed', 400, 'conv-err-submit-statement'],
  ['rate_limited', 429, 'conv-err-submit-statement'],
  ['conflict', 409, 'conv-err-submissions-closed'],
  ['forbidden', 403, 'conv-err-submissions-closed'],
  ['unauthorized', 401, 'conv-err-submit-statement'],
] as const)(
  'a %s from the statement composer shows catalogue copy, not the server message',
  async (code, status, key) => {
    await submitFailingStatement(code, status);

    // Catches the server's English reaching the participant, and a code falling to the wrong
    // message: an unknown outcome read as a plain failure invites a duplicate statement.
    const alert = await screen.findByText(`(${key})`);
    expect(alert).toHaveAttribute('role', 'alert');
    expect(document.body).not.toHaveTextContent(SERVER_ENGLISH);
  },
);

test.each([
  ['derivative_similarity_too_low', 409, 'true'],
  ['statement_quota_exceeded', 409, null],
] as const)(
  'a %s error is tied to the composer field for assistive technology',
  async (code, status, invalid) => {
    await submitFailingStatement(code, status);
    const message = await screen.findByText(/^\(conv-err-/);
    const field = document.querySelector('.v2-composer-textarea')!;

    // Catches an error a screen reader announces once and then loses: the field it is about
    // must point at it, and only a rejection of the text itself marks the text invalid.
    expect(message).toHaveAttribute('id', 'composer-newstmt-error');
    expect(message).toHaveClass('error');
    expect(field.getAttribute('aria-describedby')?.split(' ')).toEqual(['composer-newstmt-helper', 'composer-newstmt-error']);
    expect(field.getAttribute('aria-invalid')).toBe(invalid);
  },
);

test.each([
  ['not_found', 404, 'errorpage-404-title', 'errorpage-404-message'],
  ['forbidden', 403, 'conv-unavailable-heading', 'conv-unavailable-body'],
] as const)(
  'a workspace that fails with %s explains itself from the catalogue',
  async (code, status, heading, key) => {
    server.use(http.get(WORKSPACE_URL, () => HttpResponse.json(
      {error: {code, message: SERVER_ENGLISH}}, {status},
    )));
    renderWorkspace('qqx');

    // Catches the server's English under the heading, which a Dutch reader cannot read.
    // A consultation that does not exist is not "unavailable": the heading says so too.
    await screen.findByRole('heading', {name: `(${heading})`}, {timeout: 10_000});
    expect(screen.getByText(`(${key})`)).toBeVisible();
    expect(document.body).not.toHaveTextContent(SERVER_ENGLISH);
  },
);
