import {Suspense} from 'react';
import {QueryClientProvider} from '@tanstack/react-query';
import {fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {http, HttpResponse} from 'msw';
import {MemoryRouter} from 'react-router-dom';
import {expect, test} from 'vitest';

import type {components} from '../../api/schema';
import {AdminInvitationsPage} from './admin-invitations-page';
import {
  AdminSettingsPage,
  AdminSettingsVouchersPage,
} from './admin-settings-page';
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
  capabilities: {edit: true, switchDemo: false},
  locks: {gated: false, gatingType: false, showUsernames: false},
  links: {self: SETTINGS_URL, lifecycle: '/admin/conversations/7'},
};

/** Invitation-list access with every stored visibility value on, and the Explore flag
 *  raised, which is what locks the admission answer today. Nothing reads those values, so
 *  the page no longer offers them -- it only has to hand them back untouched. */
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

function renderPage(tab: 'basics' | 'access' = 'access') {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={[`/admin/conversations/7/settings/${tab}`]}>
        <Suspense fallback={null}>
          <MessageProvider locale="en">
            <AdminSettingsPage conversationId={7} csrfToken="test-csrf-token" tab={tab} />
          </MessageProvider>
        </Suspense>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

/** The Invitations tab is today's invitations page inside the Settings frame, so it is
 *  rendered through its own route rather than through `AdminSettingsPage`. */
function renderInvitationsPage() {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={['/admin/conversations/7/settings/invitations']}>
        <Suspense fallback={null}>
          <MessageProvider locale="en">
            <AdminInvitationsPage conversationId={7} csrfToken="test-csrf-token" />
          </MessageProvider>
        </Suspense>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

/** The tab strip, which every tab carries. */
function tabs() {
  return screen.getByRole('navigation', {name: 'Settings'});
}

test('shows who can take part as one plain-worded choice per row', async () => {
  serve(settings);
  renderPage('access');

  expect(await screen.findByRole('heading', {name: 'Settings', level: 1}, {timeout: 10_000}))
    .toBeVisible();
  const admission = screen.getByRole('group', {name: 'Who can take part'});
  expect(admission).toBeVisible();
  expect(screen.getByRole('radio', {name: 'Anyone with a Wikimedia account'})).toBeChecked();
  expect(screen.getByRole('radio', {name: /Only people on the invitation list/})).not.toBeChecked();
  expect(screen.getByRole('radio', {name: /Anyone with a voucher code/})).not.toBeChecked();
  // No internal value reaches the screen, and the combination the server refuses --
  // gated with no type -- cannot be expressed by a radio group.
  expect(screen.queryByText(/invite_only|gating type/i)).toBeNull();
  // Functionality that does not exist yet is named in prose, not mimed with a control: the
  // group offers three answers and every one of them works.
  expect(within(admission).getAllByRole('radio')).toHaveLength(3);
  expect(screen.queryByRole('radio', {name: /Wiki policy/})).toBeNull();
  const coming = screen.getByText(
    'Also coming: a policy based on wiki activity — not available yet (#406)',
  );
  expect(coming).toBeVisible();
  expect(coming.tagName).toBe('P');
  // Last on the page, after everything that works: outside the form, after the Save.
  expect(coming.closest('form')).toBeNull();
  expect(screen.getByRole('button', {name: 'Save'}).compareDocumentPosition(coming)
    & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  // The tab's one command is the console's primary button.
  expect(screen.getByRole('button', {name: 'Save'})).toHaveClass('admin-button', 'admin-button--primary');
  // The visibility answers are gone from the page altogether, and their placeholder is a
  // gated-only line, so an ungated consultation shows neither.
  expect(screen.queryByRole('group', {name: 'What people without access can see'})).toBeNull();
  expect(screen.queryByText(/choosing what people without access can see/)).toBeNull();
});

test('every tab is headed Settings, and no heading repeats the tab name', async () => {
  serve(settings);
  renderPage('basics');

  // The h1 says which section; the strip's current tab says which page of it, so no
  // heading under the strip names the tab again.
  expect(await screen.findByRole('heading', {name: 'Settings', level: 1}, {timeout: 10_000}))
    .toBeVisible();
  expect(screen.queryByRole('heading', {name: 'Basics'})).toBeNull();
  expect(within(tabs()).getByRole('link', {name: 'Basics'}))
    .toHaveAttribute('aria-current', 'page');
  // The numbered sections are the h2s, straight under the h1.
  expect(screen.getByRole('heading', {name: 'Description', level: 2})).toBeVisible();
});

test('the tab strip lists the four tabs in order and marks exactly one', async () => {
  serve(settings);
  renderPage('basics');

  await screen.findByRole('heading', {name: 'Settings', level: 1}, {timeout: 10_000});
  expect(within(tabs()).getAllByRole('link').map((link) => link.textContent))
    .toEqual(['Basics', 'Access', 'Invitations', 'Roles']);
  // The third tab is named by who-gets-in; an ungated, ungated-type consultation has the
  // invitation list, so that is the tab.
  expect(within(tabs()).getAllByRole('link').map((link) => link.getAttribute('href')))
    .toEqual([
      '/admin/conversations/7/settings/basics',
      '/admin/conversations/7/settings/access',
      '/admin/conversations/7/settings/invitations',
      '/admin/conversations/7/settings/roles',
    ]);
  const current = within(tabs()).getAllByRole('link')
    .filter((link) => link.getAttribute('aria-current') === 'page');
  expect(current).toHaveLength(1);
  expect(current[0]).toHaveTextContent('Basics');
});

test.each([
  ['invite_only', 'Invitations'],
  ['wiki_based', 'Invitations'],
  [null, 'Invitations'],
  ['voucher', 'Vouchers'],
] as const)('who-gets-in %s names the third tab %s', async (gatingType, label) => {
  serve({...settings, conversation: {
    ...settings.conversation, gated: gatingType !== null, gatingType,
    accessPolicy: gatingType === 'voucher' ? 'invite_only' : 'public',
  }});
  renderPage('basics');

  await screen.findByRole('heading', {name: 'Settings', level: 1}, {timeout: 10_000});
  expect(within(tabs()).getByRole('link', {name: label})).toBeVisible();
  const other = label === 'Vouchers' ? 'Invitations' : 'Vouchers';
  expect(within(tabs()).queryByRole('link', {name: other})).toBeNull();
  // Whichever the answer is, the strip points at the tab of this consultation's own kind.
  expect(within(tabs()).getByRole('link', {name: label})).toHaveAttribute(
    'href',
    gatingType === 'voucher'
      ? '/admin/conversations/7/settings/vouchers'
      : '/admin/conversations/7/settings/invitations',
  );
});

test('the access tab marks itself in the strip', async () => {
  serve(settings);
  renderPage('access');

  await screen.findByRole('heading', {name: 'Settings', level: 1}, {timeout: 10_000});
  expect(screen.queryByRole('heading', {name: 'Access'})).toBeNull();
  expect(within(tabs()).getByRole('link', {name: 'Access'}))
    .toHaveAttribute('aria-current', 'page');
  expect(within(tabs()).getByRole('link', {name: 'Basics'}))
    .not.toHaveAttribute('aria-current');
});

test('renders a locked admission answer as text with the reason on its lock', async () => {
  serve(lockedSettings);
  renderPage('access');

  expect(await screen.findByRole('heading', {name: 'Settings', level: 1}, {timeout: 10_000}))
    .toBeVisible();
  expect(screen.getByText('Only people on the invitation list')).toBeVisible();
  expect(screen.queryByRole('radio', {name: /Only people on the invitation list/})).toBeNull();
  expect(screen.queryByRole('group', {name: 'Who can take part'})).toBeNull();
  const lock = screen.getByRole('img', {name: 'Locked while Explore is open'});
  expect(lock).toHaveAttribute('title', 'Locked while Explore is open');
  // The visibility answers and the "how to ask for access" text are stored and read by
  // nothing, so the page no longer asks about them: no fieldset, no checkboxes, no field.
  expect(screen.queryByRole('group', {name: 'What people without access can see'})).toBeNull();
  expect(screen.queryByRole('checkbox', {name: 'The results'})).toBeNull();
  expect(screen.queryByRole('checkbox', {name: 'That this consultation exists'})).toBeNull();
  expect(screen.queryByRole('checkbox', {name: 'The introduction, phase and dates'})).toBeNull();
  expect(screen.queryByRole('checkbox', {name: /Show usernames in shared results/})).toBeNull();
  expect(screen.queryByRole('textbox', {name: 'How to ask for access'})).toBeNull();
  // What they promised is one muted line instead, beside the username-reveal one.
  const coming = screen.getByText(
    'Also coming: choosing what people without access can see, and what to tell them'
    + ' — not available yet (#405)',
  );
  expect(coming).toBeVisible();
  expect(coming.tagName).toBe('P');
  expect(screen.getByText(
    'Also coming: participants choosing to show their username — not available yet (#405)',
  )).toBeVisible();
});

test('asks once before narrowing access and saves only after Continue', async () => {
  serve(settings);
  const sent = recordPuts();
  renderPage('access');

  await screen.findByRole('heading', {name: 'Settings', level: 1}, {timeout: 10_000});
  fireEvent.click(screen.getByRole('radio', {name: /Only people on the invitation list/}));
  fireEvent.click(screen.getByRole('button', {name: 'Save'}));

  expect(screen.getByText('Some people will lose access. Continue?')).toBeVisible();
  expect(sent).toHaveLength(0);

  expect(screen.getByRole('group', {name: 'Some people will lose access. Continue?'}))
    .toHaveFocus();
  fireEvent.click(screen.getByRole('button', {name: 'Cancel'}));
  expect(screen.queryByText('Some people will lose access. Continue?')).toBeNull();
  expect(screen.getByRole('radio', {name: /Only people on the invitation list/})).toBeChecked();
  // The button that held focus is gone; focus goes back to Save, not to the page.
  expect(screen.getByRole('button', {name: 'Save'})).toHaveFocus();

  fireEvent.click(screen.getByRole('button', {name: 'Save'}));
  fireEvent.click(screen.getByRole('button', {name: 'Continue'}));

  await waitFor(() => expect(sent).toHaveLength(1));
  expect(sent[0]).toMatchObject({gated: true, gatingType: 'invite_only'});
});

test('the eligibility fields are not shown while the invitation list is the answer', async () => {
  // The server clears the eligibility pair whenever the invitation list is chosen
  // (services/admin_settings.py), so a field that save would empty is not offered.
  serve({...settings, eligibility: {
    ...settings.eligibility, configured: true, eventId: 'event-42', label: 'Active editors',
  }});
  renderPage('access');

  const eventId = await screen.findByLabelText('Eligibility event ID', {}, {timeout: 10_000});
  expect(eventId).toHaveValue('event-42');
  fireEvent.click(screen.getByRole('radio', {name: /Only people on the invitation list/}));
  expect(screen.queryByLabelText('Eligibility event ID')).toBeNull();
  expect(screen.queryByLabelText('Eligibility label')).toBeNull();
  expect(screen.queryByText(/^Eligibility (not )?configured$/)).toBeNull();
  // Back to an answer that keeps them, and they are there again, as they were.
  fireEvent.click(screen.getByRole('radio', {name: 'Anyone with a Wikimedia account'}));
  expect(screen.getByLabelText('Eligibility event ID')).toHaveValue('event-42');
});

test('a stored invitation list shows no eligibility fields', async () => {
  serve(lockedSettings);
  renderPage('access');

  await screen.findByRole('heading', {name: 'Settings', level: 1}, {timeout: 10_000});
  expect(screen.queryByLabelText('Eligibility event ID')).toBeNull();
  expect(screen.queryByLabelText('Eligibility label')).toBeNull();
});

test('names a stored wiki-activity policy in words, not by its stored value', async () => {
  serve({...lockedSettings, conversation: {
    ...lockedSettings.conversation, gatingType: 'wiki_based',
  }});
  renderPage('access');

  expect(await screen.findByText('A policy based on wiki activity', {exact: false},
    {timeout: 10_000})).toBeVisible();
  expect(screen.queryByText(/wiki_based|Wiki policy/)).toBeNull();
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
  renderPage('access');

  await screen.findByRole('heading', {name: 'Settings', level: 1}, {timeout: 10_000});
  fireEvent.click(screen.getByRole('radio', {name: 'Anyone with a Wikimedia account'}));
  fireEvent.click(screen.getByRole('button', {name: 'Save'}));

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
  renderPage('access');

  await screen.findByRole('heading', {name: 'Settings', level: 1}, {timeout: 10_000});
  fireEvent.click(screen.getByRole('radio', {name: /Anyone with a voucher code/}));
  fireEvent.click(screen.getByRole('button', {name: 'Save'}));
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
  renderPage('basics');

  await screen.findByRole('heading', {name: 'Settings', level: 1}, {timeout: 10_000});
  const title = screen.getByRole('textbox', {name: 'Title'});
  fireEvent.change(title, {target: {value: 'A retitled consultation'}});
  fireEvent.click(screen.getByRole('button', {name: 'Save'}));

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
  renderPage('access');

  await screen.findByRole('heading', {name: 'Settings', level: 1}, {timeout: 10_000});
  fireEvent.click(screen.getByRole('radio', {name: /Anyone with a voucher code/}));
  fireEvent.click(screen.getByRole('button', {name: 'Save'}));

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
  renderPage('access');

  await screen.findByRole('heading', {name: 'Settings', level: 1}, {timeout: 10_000});
  fireEvent.click(screen.getByRole('radio', {name: /Only people on the invitation list/}));
  fireEvent.click(screen.getByRole('button', {name: 'Save'}));
  expect(screen.getByText('Some people will lose access. Continue?')).toBeVisible();

  // Putting the widest answer back leaves the question with nothing left to ask about.
  fireEvent.click(screen.getByRole('radio', {name: 'Anyone with a Wikimedia account'}));
  expect(screen.queryByText('Some people will lose access. Continue?')).toBeNull();
  expect(screen.getByRole('button', {name: 'Save'})).toBeVisible();
  expect(sent).toHaveLength(0);
});

test('what is not available yet is prose, not a control that does nothing', async () => {
  // This test used to click a greyed radio and check that nothing happened. The option is
  // gone, so what is pinned now is that the "also coming" lines are inert: no role, no
  // tab stop, nothing to click, and no effect on what a save sends.
  serve({...lockedSettings, conversation: {...lockedSettings.conversation, showUsernames: true}});
  const sent = recordPuts();
  renderPage('access');

  await screen.findByRole('heading', {name: 'Settings', level: 1}, {timeout: 10_000});
  for (const note of [
    screen.getByText(
      'Also coming: choosing what people without access can see, and what to tell them'
      + ' — not available yet (#405)',
    ),
    screen.getByText(
      'Also coming: participants choosing to show their username — not available yet (#405)',
    ),
  ]) {
    expect(note).not.toHaveAttribute('tabindex');
    expect(note).not.toHaveAttribute('role');
    expect(note.querySelector('input, button, a, [role]')).toBeNull();
  }
  fireEvent.click(screen.getByRole('button', {name: 'Save'}));

  await waitFor(() => expect(sent).toHaveLength(1));
  // Every stored value behind those lines goes back exactly as it was read: the endpoint
  // takes one complete key set and would refuse the save without them, and a default would
  // quietly rewrite what an organizer set before the controls went away.
  expect(sent[0]).toMatchObject({
    announce: true, information: true, resultsShared: true, showUsernames: true,
    accessRequestText: 'Write to the organizers.',
  });
  expect(await screen.findByText('Settings saved.')).toBeVisible();
});

test('an organizer is never offered the Practice Environment', async () => {
  serve(settings);
  renderPage('basics');

  await screen.findByRole('heading', {name: 'Settings', level: 1}, {timeout: 10_000});
  expect(screen.queryByRole('combobox', {name: /^Access$/})).toBeNull();
  expect(screen.queryByRole('option', {name: 'Practice'})).toBeNull();
  expect(screen.queryByText('Practice Environment')).toBeNull();
});

test('an organizer sees a practice item as a fact with its fixed answer', async () => {
  serve({...settings, conversation: {...settings.conversation, accessPolicy: 'demo'}});
  const sent = recordPuts();
  renderPage('basics');

  await screen.findByRole('heading', {name: 'Settings', level: 1}, {timeout: 10_000});
  expect(screen.getByText('Practice Environment')).toBeVisible();
  expect(screen.getByText('Anyone, including people who are not logged in')).toBeVisible();
  // The fixed answer reads as the answer to its question, and the fact comes before it.
  expect(within(screen.getByRole('group', {name: 'Who can take part'}))
    .getByText('Anyone, including people who are not logged in')).toBeVisible();
  expect(screen.getByText('Practice Environment').compareDocumentPosition(
    screen.getByRole('group', {name: 'Who can take part'}),
  ) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  // One fixed answer: nothing to choose, so no radio and no select.
  expect(screen.queryAllByRole('radio', {name: /invitation list|voucher code/})).toHaveLength(0);
  expect(screen.queryByRole('combobox', {name: /^Access$/})).toBeNull();

  fireEvent.click(screen.getByRole('button', {name: 'Save'}));
  await waitFor(() => expect(sent).toHaveLength(1));
  expect(sent[0]).toMatchObject({accessPolicy: 'demo', gated: false, gatingType: null});
});

test('a site admin moves an item into the Practice Environment and sees its fixed answer', async () => {
  serve({...settings, capabilities: {edit: true, switchDemo: true}});
  const sent = recordPuts();
  renderPage('basics');

  const mode = await screen.findByRole('combobox', {name: /^Access$/}, {timeout: 10_000});
  expect(screen.queryByRole('radio', {name: /Only people on the invitation list/})).toBeNull();
  fireEvent.change(mode, {target: {value: 'demo'}});

  // Once Practice is selected the admission row states its one answer instead of offering
  // gates the server would refuse.
  expect(screen.getByText('Anyone, including people who are not logged in')).toBeVisible();
  expect(screen.queryByRole('radio', {name: /Only people on the invitation list/})).toBeNull();
  fireEvent.click(screen.getByRole('button', {name: 'Save'}));
  await waitFor(() => expect(sent).toHaveLength(1));
  expect(sent[0]).toMatchObject({accessPolicy: 'demo', gated: false, gatingType: null});
});

test('a site admin sees the switch, not the fact, on a practice item', async () => {
  serve({...settings, capabilities: {edit: true, switchDemo: true},
    conversation: {...settings.conversation, accessPolicy: 'demo'}});
  renderPage('basics');

  const mode = await screen.findByRole('combobox', {name: /^Access$/}, {timeout: 10_000});
  expect(mode).toHaveValue('demo');
  // The section heading is the item's own name; the fact is stated inside it, not beside it.
  expect(screen.getByRole('heading', {name: 'Practice Environment'})).toBeVisible();
  fireEvent.change(mode, {target: {value: 'public'}});
});

test('no Practice switch while Explore locks access', async () => {
  serve({...settings, capabilities: {edit: true, switchDemo: true},
    locks: {gated: true, gatingType: true, showUsernames: true}});
  renderPage('basics');

  await screen.findByRole('heading', {name: 'Settings', level: 1}, {timeout: 10_000});
  expect(screen.queryByRole('combobox', {name: /^Access$/})).toBeNull();
});

test('on Access a role that may not edit sees the values as text and no Save', async () => {
  serve({...settings, capabilities: {edit: false, switchDemo: false},
    eligibility: {...settings.eligibility, configured: true, eventId: 'event-42', label: 'Active editors'}});
  renderPage('access');

  await screen.findByRole('heading', {name: 'Settings', level: 1}, {timeout: 10_000});
  // No disabled controls and no note about the role: the values, as text.
  expect(screen.queryByRole('note')).toBeNull();
  expect(screen.queryByText(/inspect but not change/)).toBeNull();
  expect(screen.queryByRole('radio')).toBeNull();
  expect(screen.queryByRole('textbox')).toBeNull();
  expect(screen.getByText('Anyone with a Wikimedia account')).toBeVisible();
  expect(screen.getByText('event-42')).toBeVisible();
  expect(screen.queryByRole('button', {name: 'Save'})).toBeNull();
});

test('on Basics a moderator sees the settings as text and saves only the strict-moderation answer', async () => {
  // Moderators may set the moderation policy but not the settings: the settings are text,
  // so the one Save cannot take a typed title and quietly drop it.
  const policy = recordPolicyPuts();
  serve({...settings, capabilities: {edit: false, switchDemo: false}});
  const settingsPuts = recordPuts();
  renderPage('basics');

  const approval = await screen.findByRole('checkbox', {name: /Strict moderation/},
    {timeout: 10_000});
  expect(screen.queryByRole('note')).toBeNull();
  expect(screen.queryByRole('textbox')).toBeNull();
  expect(screen.queryByRole('radio')).toBeNull();
  expect(screen.getByText('Community strategy', {selector: '.settings-value'})).toBeVisible();
  // The introduction as participants see it: rendered, not its HTML source.
  expect(screen.getByText('Shape the future.', {selector: '.intro-text p'})).toBeVisible();
  expect(screen.queryByText('<p>Shape the future.</p>')).toBeNull();
  expect(screen.getByText('Medium topic')).toBeVisible();
  fireEvent.click(approval);
  fireEvent.click(screen.getByRole('button', {name: 'Save'}));

  await waitFor(() => expect(policy).toHaveLength(1));
  expect(policy[0]).toEqual({mode: 'moderate'});
  await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('Settings saved.'));
  expect(settingsPuts).toHaveLength(0);
});

test('the strict-moderation checkbox works while the statements cannot be read', async () => {
  // `capabilities.moderate` says whether the statements could be read from the voting
  // service; it does not decide whether the policy can be set. The stored mode does.
  const policy = recordPolicyPuts();
  server.use(http.get(STATEMENTS_URL, () => HttpResponse.json({data: {
    ...workspace('auto_approve'), capabilities: {moderate: false, seed: true},
    dataAvailability: {statements: false},
  }})));
  serve(settings);
  renderPage('basics');

  const approval = await screen.findByRole('checkbox', {name: /Strict moderation/},
    {timeout: 10_000});
  fireEvent.click(approval);
  fireEvent.click(screen.getByRole('button', {name: 'Save'}));
  await waitFor(() => expect(policy).toHaveLength(1));
});

test('on Basics a viewer who may not edit gets no Save while the policy is unknown', async () => {
  server.use(http.get(STATEMENTS_URL, () => HttpResponse.json({data: {
    ...workspace('moderate'),
    moderationPolicy: {mode: null, newStatements: null, available: false},
  }})));
  serve({...settings, capabilities: {edit: false, switchDemo: false}});
  renderPage('basics');

  await screen.findByRole('heading', {name: 'Moderation settings', level: 2}, {timeout: 10_000});
  expect(screen.queryByRole('checkbox')).toBeNull();
  expect(screen.queryByRole('button', {name: 'Save'})).toBeNull();
});

test('shows a refusal of the admission answer once, under the group', async () => {
  serve(settings);
  const sent = recordPuts(400, {error: {
    code: 'validation_failed',
    message: 'Check the highlighted settings.',
    details: {fields: {gatingType: ['Choose invite_only, voucher, or wiki_based.']}},
  }});
  renderPage('access');

  await screen.findByRole('heading', {name: 'Settings', level: 1}, {timeout: 10_000});
  fireEvent.click(screen.getByRole('button', {name: 'Save'}));

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
      'admin-settings-heading': 'CATALOGUE SETTINGS',
      'admin-access-heading': 'CATALOGUE ACCESS',
      'admin-access-admission-legend': 'CATALOGUE WHO TAKES PART',
      'admin-access-admission-anyone': 'CATALOGUE ANYONE',
    }),
  ));
  serve(settings);
  renderPage('access');

  expect(await screen.findByRole('heading', {name: 'CATALOGUE SETTINGS', level: 1},
    {timeout: 10_000})).toBeVisible();
  expect(screen.getByRole('group', {name: 'CATALOGUE WHO TAKES PART'})).toBeVisible();
  expect(screen.getByRole('radio', {name: 'CATALOGUE ANYONE'})).toBeChecked();
  expect(within(tabs()).getByRole('link', {name: 'CATALOGUE ACCESS'})).toBeVisible();
});

test('the eligibility fields live on Access, and Basics says nothing about them', async () => {
  serve({...settings, eligibility: {...settings.eligibility, configured: true, eventId: 'event-42'}});
  renderPage('basics');

  await screen.findByRole('heading', {name: 'Settings', level: 1}, {timeout: 10_000});
  expect(screen.queryByLabelText('Eligibility event ID')).toBeNull();
});

test('Basics carries the texts, the topic size and the CC0 line', async () => {
  serve(settings);
  renderPage('basics');

  await screen.findByRole('heading', {name: 'Settings', level: 1}, {timeout: 10_000});
  expect(screen.getByRole('textbox', {name: 'Title'})).toHaveValue('Community strategy');
  expect(screen.getByRole('radio', {name: /Medium topic/})).toBeChecked();
  expect(screen.getByRole('radio', {name: /Complex topic/})).toBeVisible();
  // Admin-written texts meant for publication are CC0, built as on the join screen.
  const licence = screen.getByText(/^Texts you write here are released into the public domain/);
  expect(licence).toBeVisible();
  const link = within(licence).getByRole('link', {name: /^CC0/});
  expect(link).toHaveAttribute('href', 'https://creativecommons.org/publicdomain/zero/1.0/');
  // The access half is on the other tab, not here.
  expect(screen.queryByRole('group', {name: 'Who can take part'})).toBeNull();
});

test('Basics names the three things that are not built yet', async () => {
  serve(settings);
  renderPage('basics');

  await screen.findByRole('heading', {name: 'Settings', level: 1}, {timeout: 10_000});
  // Scoped to the page: the console frame carries two "Also coming" lines of its own
  // (#477), both outside <main>.
  const lines = within(screen.getByRole('main')).getAllByText(/^Also coming:/);
  expect(lines).toHaveLength(3);
  expect(lines.map((line) => line.textContent)).toEqual([
    'Also coming: the language the consultation is written in — not available yet (#473)',
    'Also coming: keeping the submission form open while new statements are no longer shown'
    + ' — not available yet (#473)',
    'Also coming: publishing the moderation log — not available yet (#473)',
  ]);
  for (const line of lines) {
    // A control whose value nothing reads is not a control: muted like the frame's own
    // lines, in English, and nothing to tab into.
    expect(line).toHaveClass('admin-shell__coming');
    expect(line).toHaveAttribute('lang', 'en');
    // Not inside a control, and not itself focusable. `<main tabindex="-1">` is the frame's
    // skip target, not a control these lines live in.
    expect(line.closest('a, button')).toBeNull();
    expect(line).not.toHaveAttribute('tabindex');
    expect(line.parentElement?.closest('a, button, [tabindex]:not(main)')).toBeNull();
  }
});

const STATEMENTS_URL = new URL(
  '/api/v1/admin/conversations/7/statements', globalThis.location.origin,
).toString();
const POLICY_URL = new URL(
  '/api/v1/admin/conversations/7/statement-moderation-policy', globalThis.location.origin,
).toString();

function workspace(mode: string) {
  return {
    conversation: {id: 7, slug: 'community-strategy', title: 'Community strategy'},
    statements: {pending: [], approved: [], hidden: []},
    moderationPolicy: {
      mode, newStatements: mode === 'moderate' ? 'pending' : 'approved', available: true,
    },
    dataAvailability: {statements: true},
    seeding: {allowed: true, lockReason: null, maxStatementsPerImport: 20, maxCharactersPerStatement: 280},
    capabilities: {moderate: true, seed: true},
    links: {self: '/api/v1/admin/conversations/7/statements', lifecycle: '/admin/conversations/7'},
  };
}

/** Serves the statements workspace the Approval control reads its state from (decisions.md
 *  a), and records every moderation-policy PUT. */
function recordPolicyPuts() {
  const sent: Record<string, unknown>[] = [];
  server.use(http.get(STATEMENTS_URL, () => HttpResponse.json({data: workspace('auto_approve')})));
  server.use(http.put(POLICY_URL, async ({request}) => {
    const payload = await request.json() as Record<string, unknown>;
    sent.push(payload);
    return HttpResponse.json({data: {
      mode: payload.mode, changed: true, reconciledStatements: 0,
      workspace: workspace(String(payload.mode)),
    }});
  }));
  return sent;
}

test('Basics has one Save button, at the bottom, and the Approval section has none', async () => {
  recordPolicyPuts();
  serve(settings);
  renderPage('basics');

  await screen.findByRole('checkbox', {name: /Strict moderation/}, {timeout: 10_000});
  const buttons = within(screen.getByRole('main')).getAllByRole('button');
  expect(buttons.map((button) => button.textContent)).toEqual(['Save']);
  const save = buttons[0]!;
  // Every control on the tab is in the one form the Save submits, and none comes after it.
  const form = save.closest('form');
  expect(form).not.toBeNull();
  expect(form?.querySelectorAll('form')).toHaveLength(0);
  const main = within(screen.getByRole('main'));
  for (const control of [...main.getAllByRole('textbox'), ...main.getAllByRole('radio'),
    ...main.getAllByRole('checkbox')]) {
    expect(control.closest('form')).toBe(form);
    expect(control.compareDocumentPosition(save) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  }
  const section = screen.getByRole('region', {name: 'Moderation settings'});
  expect(within(section).queryByRole('button')).toBeNull();
});

test('the sections of Basics are headed in sentence case, with no number', async () => {
  recordPolicyPuts();
  serve(settings);
  renderPage('basics');

  const heading = await screen.findByRole('heading', {name: 'Moderation settings', level: 2},
    {timeout: 10_000});
  expect(heading.textContent).toBe('Moderation settings');
  const section = screen.getByRole('region', {name: 'Moderation settings'});
  // A section of the settings form, like the others, headed by its h2 alone.
  expect(section.parentElement).toHaveClass('settings-form');
  expect(section.firstElementChild).toBe(heading);
  for (const name of ['Description', 'Complexity tier', 'Moderation settings']) {
    expect(screen.getByRole('heading', {name, level: 2})).toBeVisible();
  }
  expect(within(screen.getByRole('main')).queryByText(/^0\d$/)).toBeNull();
});

test('changing only the checkbox sends only the policy request', async () => {
  const policy = recordPolicyPuts();
  serve(settings);
  const settingsPuts = recordPuts();
  renderPage('basics');

  const approval = await screen.findByRole('checkbox', {name: /Strict moderation/},
    {timeout: 10_000});
  expect(approval).not.toBeChecked();
  fireEvent.click(approval);
  fireEvent.click(screen.getByRole('button', {name: 'Save'}));

  await waitFor(() => expect(policy).toHaveLength(1));
  // The moderation policy is not one of the fields the settings endpoint takes, so it
  // keeps its own endpoint and its own body.
  expect(policy[0]).toEqual({mode: 'moderate'});
  await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('Settings saved.'));
  expect(settingsPuts).toHaveLength(0);
  expect(screen.getByRole('checkbox', {name: /Strict moderation/})).toBeChecked();
});

test('changing a setting and the checkbox sends both requests on the one Save', async () => {
  const policy = recordPolicyPuts();
  serve(settings);
  const settingsPuts = recordPuts();
  renderPage('basics');

  const approval = await screen.findByRole('checkbox', {name: /Strict moderation/},
    {timeout: 10_000});
  fireEvent.change(screen.getByRole('textbox', {name: 'Title'}), {target: {value: 'A new title'}});
  fireEvent.click(approval);
  fireEvent.click(screen.getByRole('button', {name: 'Save'}));

  await waitFor(() => expect(policy).toHaveLength(1));
  expect(settingsPuts).toHaveLength(1);
  expect(settingsPuts[0]).toMatchObject({title: 'A new title'});
  expect(policy[0]).toEqual({mode: 'moderate'});
  await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('Settings saved.'));
});

test('changing only a setting sends only the settings request', async () => {
  const policy = recordPolicyPuts();
  serve(settings);
  const settingsPuts = recordPuts();
  renderPage('basics');

  await screen.findByRole('checkbox', {name: /Strict moderation/}, {timeout: 10_000});
  fireEvent.change(screen.getByRole('textbox', {name: 'Title'}), {target: {value: 'A new title'}});
  fireEvent.click(screen.getByRole('button', {name: 'Save'}));

  await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('Settings saved.'));
  expect(settingsPuts).toHaveLength(1);
  expect(policy).toHaveLength(0);
});

test('a refused settings request stops the Save before the policy request', async () => {
  const policy = recordPolicyPuts();
  serve(settings);
  const settingsPuts = recordPuts(400, {error: {
    code: 'validation_failed',
    message: 'Check the highlighted settings.',
    details: {fields: {title: ['Give the consultation a title.']}},
  }});
  renderPage('basics');

  const approval = await screen.findByRole('checkbox', {name: /Strict moderation/},
    {timeout: 10_000});
  fireEvent.change(screen.getByRole('textbox', {name: 'Title'}), {target: {value: 'x'}});
  fireEvent.click(approval);
  fireEvent.click(screen.getByRole('button', {name: 'Save'}));

  await waitFor(() => expect(settingsPuts).toHaveLength(1));
  expect((await screen.findAllByText('Give the consultation a title.')).length).toBeGreaterThan(0);
  expect(policy).toHaveLength(0);
  // The unsaved answer is kept for the next attempt.
  expect(screen.getByRole('checkbox', {name: /Strict moderation/})).toBeChecked();
});

test('a refused policy request is said on the status line', async () => {
  recordPolicyPuts();
  server.use(http.put(POLICY_URL, () => HttpResponse.json(
    {error: {code: 'upstream_unavailable', message: 'The moderation baseline could not be reconciled safely.'}},
    {status: 502},
  )));
  serve(settings);
  const settingsPuts = recordPuts();
  renderPage('basics');

  const approval = await screen.findByRole('checkbox', {name: /Strict moderation/},
    {timeout: 10_000});
  fireEvent.click(approval);
  fireEvent.click(screen.getByRole('button', {name: 'Save'}));

  expect(await screen.findByRole('alert')).toHaveTextContent(
    'Could not update moderation settings. Check server logs for details.',
  );
  expect(settingsPuts).toHaveLength(0);
  expect(screen.getByRole('status')).toBeEmptyDOMElement();
});

test('a partial save says both: the settings saved, the policy not', async () => {
  recordPolicyPuts();
  server.use(http.put(POLICY_URL, () => HttpResponse.json(
    {error: {code: 'upstream_unavailable', message: 'The moderation baseline could not be reconciled safely.'}},
    {status: 502},
  )));
  serve(settings);
  const settingsPuts = recordPuts();
  renderPage('basics');

  const approval = await screen.findByRole('checkbox', {name: /Strict moderation/},
    {timeout: 10_000});
  fireEvent.change(screen.getByRole('textbox', {name: 'Title'}), {target: {value: 'A new title'}});
  fireEvent.click(approval);
  fireEvent.click(screen.getByRole('button', {name: 'Save'}));

  expect(await screen.findByRole('alert')).toHaveTextContent(
    'Could not update moderation settings. Check server logs for details.',
  );
  expect(settingsPuts).toHaveLength(1);
  expect(screen.getByRole('status')).toHaveTextContent('Settings saved.');
});

test('the Access tab has no Approval control and no Practice switch', async () => {
  serve({...settings, capabilities: {edit: true, switchDemo: true}});
  renderPage('access');

  await screen.findByRole('heading', {name: 'Settings', level: 1}, {timeout: 10_000});
  expect(screen.queryByRole('checkbox', {name: /Strict moderation/})).toBeNull();
  expect(screen.queryByRole('combobox', {name: /^Access$/})).toBeNull();
  expect(screen.queryByRole('textbox', {name: 'Title'})).toBeNull();
});

test('a practice item keeps its eligibility fields on Access, without the admission group', async () => {
  serve({...settings, conversation: {...settings.conversation, accessPolicy: 'demo'},
    eligibility: {...settings.eligibility, configured: true, eventId: 'event-42'}});
  renderPage('access');

  const eventId = await screen.findByLabelText('Eligibility event ID', {}, {timeout: 10_000});
  expect(eventId).toHaveValue('event-42');
  expect(screen.getByLabelText('Eligibility label')).toBeVisible();
  // The fixed answer is stated on Basics; here there is no question to offer.
  expect(screen.queryByRole('group', {name: 'Who can take part'})).toBeNull();
  expect(screen.queryByRole('radio')).toBeNull();
  expect(within(screen.getByRole('main')).queryByText(/^Also coming:/)).toBeNull();
});

test('saving Basics sends the Access fields back as they were loaded', async () => {
  // The endpoint takes one of three complete key sets, so a save from either tab has to
  // carry the fields the other tab owns. Last write wins, so they go back untouched.
  serve({...settings, eligibility: {...settings.eligibility, configured: true, eventId: 'event-42', label: 'Active editors'}});
  const sent = recordPuts();
  renderPage('basics');

  await screen.findByRole('heading', {name: 'Settings', level: 1}, {timeout: 10_000});
  fireEvent.change(screen.getByRole('textbox', {name: 'Title'}), {target: {value: 'A new title'}});
  fireEvent.click(screen.getByRole('button', {name: 'Save'}));

  await waitFor(() => expect(sent).toHaveLength(1));
  expect(sent[0]).toMatchObject({
    title: 'A new title',
    eligibilityEventId: 'event-42',
    eligibilityLabel: 'Active editors',
    gated: false,
    gatingType: null,
    accessPolicy: 'public',
    announce: false, information: false, resultsShared: false, showUsernames: false,
    accessRequestText: null,
  });
});

test('saving Access sends the Basics fields back as they were loaded', async () => {
  serve({...settings, eligibility: {...settings.eligibility, configured: true, eventId: 'event-42', label: 'Active editors'}});
  const sent = recordPuts();
  renderPage('access');

  await screen.findByRole('heading', {name: 'Settings', level: 1}, {timeout: 10_000});
  fireEvent.change(screen.getByLabelText('Eligibility event ID'), {target: {value: 'event-99'}});
  fireEvent.click(screen.getByRole('button', {name: 'Save'}));

  await waitFor(() => expect(sent).toHaveLength(1));
  expect(sent[0]).toMatchObject({
    eligibilityEventId: 'event-99',
    title: 'Community strategy',
    introHtml: '<p>Shape the future.</p>',
    outroHtml: '',
    accessPolicy: 'public',
    recommendationTier: 'medium',
  });
});

test('a voucher consultation can be sent to Invitations, which still says what it is', async () => {
  // `…/settings/invitations` stays routable for every gating type (#478 item 4), so a link
  // from an e-mail or an old bookmark does not land on a page that says it is the wrong
  // thing for this consultation.
  serve({...settings, conversation: {
    ...settings.conversation, gated: true, gatingType: 'voucher', accessPolicy: 'invite_only',
  }});
  renderInvitationsPage();

  await screen.findByRole('heading', {name: 'Settings', level: 1}, {timeout: 10_000});
  expect(screen.queryByRole('heading', {name: 'Invitations'})).toBeNull();
  // The strip still names the tab this consultation uses.
  expect(within(tabs()).getByRole('link', {name: 'Vouchers'}))
    .toHaveAttribute('href', '/admin/conversations/7/settings/vouchers');
});

test('the Vouchers tab is the strip and one line about what is not built yet', async () => {
  serve({...settings, conversation: {
    ...settings.conversation, gated: true, gatingType: 'voucher', accessPolicy: 'invite_only',
  }});
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={['/admin/conversations/7/settings/vouchers']}>
        <Suspense fallback={null}>
          <MessageProvider locale="en">
            <AdminSettingsVouchersPage conversationId={7} />
          </MessageProvider>
        </Suspense>
      </MemoryRouter>
    </QueryClientProvider>,
  );

  await screen.findByRole('heading', {name: 'Settings', level: 1}, {timeout: 10_000});
  expect(screen.queryByRole('heading', {name: 'Vouchers'})).toBeNull();
  expect(within(tabs()).getByRole('link', {name: 'Vouchers'}))
    .toHaveAttribute('aria-current', 'page');
  // Every voucher action is parked (#368): the page says so once instead of offering a
  // control that saves nothing.
  const lines = within(screen.getByRole('main')).getAllByText(/^Also coming:/);
  expect(lines).toHaveLength(1);
  expect(lines[0]).toHaveTextContent(
    'Also coming: generating, importing, checking and withdrawing voucher codes here'
    + ' — not available yet (#368)',
  );
  expect(lines[0]).toHaveAttribute('lang', 'en');
  expect(lines[0]).toHaveClass('admin-shell__coming');
  expect(lines[0]?.closest('a, button')).toBeNull();
  // No dead controls standing in for the missing feature.
  expect(screen.queryByRole('button', {name: /Generate|Import|Check|Withdraw/})).toBeNull();
  expect(screen.queryByRole('table')).toBeNull();
});

test.each([
  ['voucher', 'invitations', 'Vouchers'],
  ['invite_only', 'vouchers', 'Invitations'],
] as const)('a %s consultation on the %s tab still marks one tab as current', async (
  gatingType, page, label,
) => {
  // The third tab is named by this consultation's kind, while the URL may be the other
  // kind's (an old link, a changed answer). The strip still says "you are here" once.
  serve({...settings, conversation: {
    ...settings.conversation, gated: true, gatingType, accessPolicy: 'invite_only',
  }});
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={[`/admin/conversations/7/settings/${page}`]}>
        <Suspense fallback={null}>
          <MessageProvider locale="en">
            {page === 'invitations'
              ? <AdminInvitationsPage conversationId={7} csrfToken="test-csrf-token" />
              : <AdminSettingsVouchersPage conversationId={7} />}
          </MessageProvider>
        </Suspense>
      </MemoryRouter>
    </QueryClientProvider>,
  );

  await screen.findByRole('heading', {name: 'Settings', level: 1}, {timeout: 10_000});
  const current = within(tabs()).getAllByRole('link')
    .filter((link) => link.getAttribute('aria-current') === 'page');
  expect(current).toHaveLength(1);
  expect(current[0]).toHaveTextContent(label);
});
