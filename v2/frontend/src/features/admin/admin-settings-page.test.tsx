import {Suspense} from 'react';
import {QueryClientProvider} from '@tanstack/react-query';
import {fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {http, HttpResponse} from 'msw';
import {MemoryRouter} from 'react-router-dom';
import {expect, test} from 'vitest';

import type {components} from '../../api/schema';
import {AdminSettingsPage} from './admin-settings-page';
import {MessageProvider} from '../../i18n/messages';
import {createQueryClient} from '../../query-client';
import {server} from '../../test/server';
import {testMessages} from '../../test/handlers';

type Settings = components['schemas']['AdminSettings'];

const SETTINGS_URL = new URL(
  '/api/v1/admin/conversations/7/settings', globalThis.location.origin,
).toString();

/** A consultation that anybody with an account can join: the widest answer, nothing
 *  locked, so every row renders as a live choice. */
const settings: Settings = {
  conversation: {
    id: 7, slug: 'community-strategy', title: 'Community strategy',
    introHtml: '<p>Shape the future.</p>', outroHtml: '', accessPolicy: 'public',
    gated: false, gatingType: null, announce: false, information: false,
    resultsShared: false, showUsernames: false, accessRequestText: null,
    phaseRoute: 'default_7', phaseRouteLabel: 'Full consultation',
    polisId: 'polis-community-strategy',
  },
  recommendations: {tier: 'medium', tiers: [
    {key: 'simple', label: 'Simple topic', quantities: {seed_statements: 5}},
    {key: 'medium', label: 'Medium topic', quantities: {seed_statements: 8}},
    {key: 'complex', label: 'Complex topic', quantities: {seed_statements: 12}},
  ]},
  eligibility: {
    configured: false, eventId: '', label: null, configurationMode: 'editable',
    note: 'Leave the event ID blank when no external eligibility check applies.',
  },
  capabilities: {edit: true},
  locks: {gated: false, gatingType: false, showUsernames: false},
  links: {self: SETTINGS_URL, lifecycle: '/admin/conversations/7'},
};

/** Invitation-list access with the three visibility answers on, and the Explore flag
 *  raised, which is what locks the admission answer today. */
const lockedSettings: Settings = {
  ...settings,
  conversation: {
    ...settings.conversation, accessPolicy: 'invite_only', gated: true,
    gatingType: 'invite_only', announce: true, information: true, resultsShared: true,
    accessRequestText: 'Write to the organizers.',
  },
  locks: {gated: true, gatingType: true, showUsernames: true},
};

function serve(payload: Settings) {
  server.use(http.get(SETTINGS_URL, () => HttpResponse.json({data: payload})));
}

/** Records every settings PUT the page makes, so "did not save yet" is an assertion
 *  about the wire rather than about the rendering. */
type ErrorBody = {error: {code: string; message: string; details?: unknown}};

function recordPuts(status = 200, body?: ErrorBody) {
  const sent: Record<string, unknown>[] = [];
  server.use(http.put(SETTINGS_URL, async ({request}) => {
    const payload = await request.json() as Record<string, unknown>;
    sent.push(payload);
    if (status !== 200) return HttpResponse.json(body, {status});
    return HttpResponse.json({data: {
      changed: true, changedFields: ['gated'],
      settings: {...settings, conversation: {...settings.conversation, ...payload}},
    }});
  }));
  return sent;
}

function renderPage() {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter>
        <Suspense fallback={null}>
          <MessageProvider locale="en">
            <AdminSettingsPage conversationId={7} csrfToken="test-csrf-token" />
          </MessageProvider>
        </Suspense>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

test('shows who can take part as one plain-worded choice per row', async () => {
  serve(settings);
  renderPage();

  expect(await screen.findByRole('heading', {name: 'Access', level: 1}, {timeout: 10_000}))
    .toBeVisible();
  const admission = screen.getByRole('group', {name: 'Who can take part'});
  expect(admission).toBeVisible();
  expect(screen.getByRole('radio', {name: 'Anyone with a Wikimedia account'})).toBeChecked();
  expect(screen.getByRole('radio', {name: /Only people on the invitation list/})).not.toBeChecked();
  expect(screen.getByRole('radio', {name: /Anyone with a voucher code/})).not.toBeChecked();
  // No internal value reaches the screen, and the combination the server refuses --
  // gated with no type -- cannot be expressed by a radio group.
  expect(screen.queryByText(/invite_only|gating type/i)).toBeNull();
  // Functionality that does not exist yet is named in prose at the foot of the group, not
  // mimed with a control: the group offers three answers and every one of them works.
  expect(within(admission).getAllByRole('radio')).toHaveLength(3);
  expect(screen.queryByRole('radio', {name: /Wiki policy/})).toBeNull();
  const coming = within(admission).getByText(
    'Also coming: a policy based on wiki activity — not available yet (#406)',
  );
  expect(coming).toBeVisible();
  expect(coming.tagName).toBe('P');
  // Inside the fieldset and last in it, so it closes the question it is about instead of
  // sitting flush against the next question's legend.
  expect(coming.parentElement).toBe(admission);
  expect(admission.lastElementChild).toBe(coming);
  // Visibility answers belong to a gated consultation only, as they do today.
  expect(screen.queryByRole('group', {name: 'What people without access can see'})).toBeNull();
});

test('renders a locked admission answer as text with the reason on its lock', async () => {
  serve(lockedSettings);
  renderPage();

  expect(await screen.findByRole('heading', {name: 'Access', level: 1}, {timeout: 10_000}))
    .toBeVisible();
  expect(screen.getByText('Only people on the invitation list')).toBeVisible();
  expect(screen.queryByRole('radio', {name: /Only people on the invitation list/})).toBeNull();
  expect(screen.queryByRole('group', {name: 'Who can take part'})).toBeNull();
  const lock = screen.getByRole('img', {name: 'Locked while Explore is open'});
  expect(lock).toHaveAttribute('title', 'Locked while Explore is open');
  // What the lock does not cover stays editable: the three visibility answers never lock.
  const visibility = screen.getByRole('group', {name: 'What people without access can see'});
  expect(visibility).toBeVisible();
  expect(screen.getByRole('checkbox', {name: 'The results'})).toBeEnabled();
  // The username-reveal option has no consumer yet, so it is named at the foot of the
  // group in prose and sent back unchanged -- not offered as a checkbox nobody can tick.
  expect(screen.queryByRole('checkbox', {name: /Show usernames in shared results/})).toBeNull();
  expect(within(visibility).getAllByRole('checkbox')).toHaveLength(3);
  const reveal = within(visibility).getByText(
    'Also coming: participants choosing to show their username — not available yet',
  );
  expect(reveal).toBeVisible();
  expect(visibility.lastElementChild).toBe(reveal);
});

test('asks once before narrowing access and saves only after Continue', async () => {
  serve(settings);
  const sent = recordPuts();
  renderPage();

  await screen.findByRole('heading', {name: 'Access', level: 1}, {timeout: 10_000});
  fireEvent.click(screen.getByRole('radio', {name: /Only people on the invitation list/}));
  fireEvent.click(screen.getByRole('button', {name: 'Save settings'}));

  expect(screen.getByText('Some people will lose access. Continue?')).toBeVisible();
  expect(sent).toHaveLength(0);

  fireEvent.click(screen.getByRole('button', {name: 'Cancel'}));
  expect(screen.queryByText('Some people will lose access. Continue?')).toBeNull();
  expect(screen.getByRole('radio', {name: /Only people on the invitation list/})).toBeChecked();

  fireEvent.click(screen.getByRole('button', {name: 'Save settings'}));
  fireEvent.click(screen.getByRole('button', {name: 'Continue'}));

  await waitFor(() => expect(sent).toHaveLength(1));
  expect(sent[0]).toMatchObject({gated: true, gatingType: 'invite_only'});
});

test('widening saves at once, without the question', async () => {
  serve({
    ...settings,
    conversation: {
      ...settings.conversation, accessPolicy: 'invite_only', gated: true,
      gatingType: 'invite_only',
    },
  });
  const sent = recordPuts();
  renderPage();

  await screen.findByRole('heading', {name: 'Access', level: 1}, {timeout: 10_000});
  fireEvent.click(screen.getByRole('radio', {name: 'Anyone with a Wikimedia account'}));
  fireEvent.click(screen.getByRole('button', {name: 'Save settings'}));

  await waitFor(() => expect(sent).toHaveLength(1));
  expect(sent[0]).toMatchObject({gated: false, gatingType: null});
  expect(screen.queryByText('Some people will lose access. Continue?')).toBeNull();
});

test('shows the server refusal beside the admission answer and keeps the input', async () => {
  serve(settings);
  const sent = recordPuts(409, {error: {
    code: 'access_settings_locked',
    message: 'Gated access settings cannot change after Explore starts.',
    details: {field: 'gated'},
  }});
  renderPage();

  await screen.findByRole('heading', {name: 'Access', level: 1}, {timeout: 10_000});
  fireEvent.click(screen.getByRole('radio', {name: /Anyone with a voucher code/}));
  fireEvent.click(screen.getByRole('button', {name: 'Save settings'}));
  fireEvent.click(screen.getByRole('button', {name: 'Continue'}));

  await waitFor(() => expect(sent).toHaveLength(1));
  // The server's own sentence, not a second copy of it in the front end.
  expect(await screen.findByText('Gated access settings cannot change after Explore starts.'))
    .toBeVisible();
  expect(screen.getByRole('radio', {name: /Anyone with a voucher code/})).toBeChecked();
});

test('maps a field refusal to its field and keeps what was typed', async () => {
  serve(settings);
  const sent = recordPuts(400, {error: {
    code: 'validation_failed',
    message: 'Check the highlighted settings.',
    details: {fields: {title: ['Write a title up to 255 characters.']}},
  }});
  renderPage();

  await screen.findByRole('heading', {name: 'Access', level: 1}, {timeout: 10_000});
  const title = screen.getByRole('textbox', {name: 'Title'});
  fireEvent.change(title, {target: {value: 'A retitled consultation'}});
  fireEvent.click(screen.getByRole('button', {name: 'Save settings'}));

  await waitFor(() => expect(sent).toHaveLength(1));
  // Once in the summary that takes focus, once beside the field it is about.
  const refusal = await screen.findAllByText('Write a title up to 255 characters.');
  expect(refusal).toHaveLength(2);
  expect(screen.getByRole('alert')).toHaveTextContent('Write a title up to 255 characters.');
  expect(title).toHaveAttribute('aria-invalid', 'true');
  expect(title).toHaveAttribute('aria-describedby', refusal[1]?.id);
  expect(title).toHaveValue('A retitled consultation');
});

test('asks before swapping one gate for another, which also takes access away', async () => {
  serve({
    ...settings,
    conversation: {
      ...settings.conversation, accessPolicy: 'invite_only', gated: true,
      gatingType: 'invite_only',
    },
  });
  const sent = recordPuts();
  renderPage();

  await screen.findByRole('heading', {name: 'Access', level: 1}, {timeout: 10_000});
  fireEvent.click(screen.getByRole('radio', {name: /Anyone with a voucher code/}));
  fireEvent.click(screen.getByRole('button', {name: 'Save settings'}));

  // Everybody on the invitation list loses access when the gate becomes a voucher.
  expect(screen.getByText('Some people will lose access. Continue?')).toBeVisible();
  expect(sent).toHaveLength(0);

  fireEvent.click(screen.getByRole('button', {name: 'Continue'}));
  await waitFor(() => expect(sent).toHaveLength(1));
  expect(sent[0]).toMatchObject({gated: true, gatingType: 'voucher'});
});

test('drops the question when the answer stops narrowing', async () => {
  serve(settings);
  const sent = recordPuts();
  renderPage();

  await screen.findByRole('heading', {name: 'Access', level: 1}, {timeout: 10_000});
  fireEvent.click(screen.getByRole('radio', {name: /Only people on the invitation list/}));
  fireEvent.click(screen.getByRole('button', {name: 'Save settings'}));
  expect(screen.getByText('Some people will lose access. Continue?')).toBeVisible();

  // Putting the widest answer back leaves the question with nothing to ask about.
  fireEvent.click(screen.getByRole('radio', {name: 'Anyone with a Wikimedia account'}));
  expect(screen.queryByText('Some people will lose access. Continue?')).toBeNull();
  expect(screen.getByRole('button', {name: 'Save settings'})).toBeVisible();
  expect(sent).toHaveLength(0);
});

test('what is not available yet is prose, not a control that does nothing', async () => {
  // This test used to click a greyed radio and check that nothing happened. The option is
  // gone, so what is pinned now is that the two "also coming" lines are inert: no role, no
  // tab stop, nothing to click, and no effect on what a save sends.
  serve({...lockedSettings, conversation: {...lockedSettings.conversation, showUsernames: true}});
  const sent = recordPuts();
  renderPage();

  await screen.findByRole('heading', {name: 'Access', level: 1}, {timeout: 10_000});
  const note = screen.getByText(
    'Also coming: participants choosing to show their username — not available yet',
  );
  expect(note).not.toHaveAttribute('tabindex');
  expect(note.querySelector('input, button, a, [role]')).toBeNull();
  fireEvent.click(screen.getByRole('button', {name: 'Save settings'}));

  await waitFor(() => expect(sent).toHaveLength(1));
  // The stored value behind the line still goes back exactly as it was read.
  expect(sent[0]).toMatchObject({showUsernames: true});
});

test('a role that may not edit gets the reason and no way to save', async () => {
  serve({...settings, capabilities: {edit: false}});
  renderPage();

  await screen.findByRole('heading', {name: 'Access', level: 1}, {timeout: 10_000});
  expect(screen.getByRole('note')).toHaveTextContent('inspect but not change');
  expect(screen.queryByRole('button', {name: 'Save settings'})).toBeNull();
});

test('shows a refusal of the admission answer once, under the group', async () => {
  serve(settings);
  const sent = recordPuts(400, {error: {
    code: 'validation_failed',
    message: 'Check the highlighted settings.',
    details: {fields: {gatingType: ['Choose invite_only, voucher, or wiki_based.']}},
  }});
  renderPage();

  await screen.findByRole('heading', {name: 'Access', level: 1}, {timeout: 10_000});
  fireEvent.click(screen.getByRole('button', {name: 'Save settings'}));

  await waitFor(() => expect(sent).toHaveLength(1));
  // Once in the summary, once under the group -- and the description the choices point at
  // is the one that is actually rendered.
  const refusal = await screen.findAllByText('Choose invite_only, voucher, or wiki_based.');
  expect(refusal).toHaveLength(2);
  const anyone = screen.getByRole('radio', {name: 'Anyone with a Wikimedia account'});
  expect(anyone).toHaveAttribute('aria-invalid', 'true');
  expect(anyone).toHaveAttribute('aria-describedby', refusal[1]?.id);
});

test('renders its labels from the catalogue, not from source literals', async () => {
  server.use(http.get(
    new URL('/api/v1/i18n/:locale', globalThis.location.origin).toString(),
    () => HttpResponse.json({
      ...testMessages,
      'admin-access-heading': 'CATALOGUE ACCESS',
      'admin-access-admission-legend': 'CATALOGUE WHO TAKES PART',
      'admin-access-admission-anyone': 'CATALOGUE ANYONE',
    }),
  ));
  serve(settings);
  renderPage();

  expect(await screen.findByRole('heading', {name: 'CATALOGUE ACCESS', level: 1}, {timeout: 10_000}))
    .toBeVisible();
  expect(screen.getByRole('group', {name: 'CATALOGUE WHO TAKES PART'})).toBeVisible();
  expect(screen.getByRole('radio', {name: 'CATALOGUE ANYONE'})).toBeChecked();
});
