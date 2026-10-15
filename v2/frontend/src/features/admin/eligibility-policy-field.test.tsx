import {Suspense, useState} from 'react';
import {QueryClientProvider} from '@tanstack/react-query';
import {fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {http, HttpResponse} from 'msw';
import {MemoryRouter} from 'react-router-dom';
import {expect, test} from 'vitest';

import type {components} from '../../api/schema';
import {AdminCatalogPage} from './admin-catalog-page';
import {AdminSettingsPage} from './admin-settings-page';
import {EligibilityPolicyField, ruleText, type EligibilityChoice} from './eligibility-policy-field';
import {createMessage, MessageProvider} from '../../i18n/messages';
import {createQueryClient} from '../../query-client';
import {testMessages, testPolicies} from '../../test/handlers';
import {renderAsQqx, untranslatedCopy} from '../../test/i18n';
import {server} from '../../test/server';

const POLICIES_URL = new URL('/api/v1/admin/eligibility-policies', globalThis.location.origin).toString();
const SETTINGS_URL = new URL('/api/v1/admin/conversations/7/settings', globalThis.location.origin).toString();

/** The field on its own, holding its value as a form would, with the last value shown. */
function Harness({initial}: {initial: EligibilityChoice}) {
  const [value, setValue] = useState(initial);
  return <>
    <EligibilityPolicyField value={value} onChange={setValue} />
    <output data-testid="value">{JSON.stringify(value)}</output>
  </>;
}

function renderField(initial: EligibilityChoice = {eventId: '', label: ''}, locale: 'en' | 'provider' = 'en') {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <MessageProvider {...(locale === 'provider' ? {} : {locale})}><Harness initial={initial} /></MessageProvider>
    </QueryClientProvider>,
  );
}

function current(): EligibilityChoice {
  return JSON.parse(screen.getByTestId('value').textContent!) as EligibilityChoice;
}

function optionNames() {
  return screen.getAllByRole('option').map((option) => option.textContent);
}

test('every rule canivote uses today is said in plain words', () => {
  const msg = createMessage('en', testMessages);
  expect(testPolicies.flatMap((policy) => policy.rules.map((rule) => ruleText(msg, rule)))).toEqual([
    'Has a global account',
    'Not blocked on nl.wikipedia.org',
    'First edit on nl.wikipedia.org at least 2 weeks ago',
    'More than 100 edits on nl.wikipedia.org',
    'Not in the "bot" group on de.wikipedia.org',
    'At least 200 article edits on de.wikipedia.org',
    'At least 50 article edits on de.wikipedia.org in the last 12 months',
    'Account not globally locked',
  ]);
  expect(ruleText(msg, {metric: 'time_since_registration', wiki: 'en.wikipedia.org',
    operator: 'at_least', value: {amount: 1, unit: 'months'}}))
    .toBe('Account on en.wikipedia.org created at least 1 month ago');
  expect(ruleText(msg, {metric: 'edit_count', wiki: 'en.wikipedia.org',
    within: {amount: 12, unit: 'months'}, operator: 'at_least', value: 10}))
    .toBe('At least 10 edits on en.wikipedia.org in the last 12 months');
  // A rule there are no words for yet gets none, rather than wrong ones.
  expect(ruleText(msg, {metric: 'edit_count', wiki: 'en.wikipedia.org', operator: 'at_most', value: 5})).toBeNull();
  expect(ruleText(msg, {metric: 'something_new', operator: 'is', value: 3})).toBeNull();
});

test('typing filters the list by id, title and wiki', async () => {
  renderField();
  const box = await screen.findByRole('combobox', {name: 'Eligibility policy'});

  fireEvent.change(box, {target: {value: 'nl'}});
  expect(box).toHaveAttribute('aria-expanded', 'true');
  expect(optionNames()).toEqual(['Voting eligibility on Dutch Wikipedia nlwiki-stemprocedure · nl.wikipedia.org']);
  fireEvent.change(box, {target: {value: 'GERMAN'}});
  expect(optionNames()).toEqual(['Voting eligibility on German Wikipedia dewiki-stimmberechtigung · de.wikipedia.org']);
  fireEvent.change(box, {target: {value: 'meta.wikimedia'}});
  expect(optionNames()).toEqual(['Not blocked anywhere in the movement meta-global · meta.wikimedia.org']);
  fireEvent.change(box, {target: {value: 'xyz'}});
  expect(screen.queryAllByRole('option')).toEqual([]);
  expect(screen.getByText('No policy matches')).toBeVisible();
});

test('the arrow opens the whole list in canivote\'s order, with no check first', async () => {
  renderField();
  const box = await screen.findByRole('combobox', {name: 'Eligibility policy'});

  fireEvent.keyDown(box, {key: 'ArrowDown'});
  const list = screen.getByRole('listbox', {name: 'Eligibility policy'});
  expect(list).toBeVisible();
  expect(within(list).getAllByRole('option').map((option) => option.textContent)).toEqual([
    'No eligibility check',
    'Voting eligibility on Dutch Wikipedia nlwiki-stemprocedure · nl.wikipedia.org',
    'Voting eligibility on German Wikipedia dewiki-stimmberechtigung · de.wikipedia.org',
    'Not blocked anywhere in the movement meta-global · meta.wikimedia.org',
  ]);
  expect(within(list).queryByRole('group')).toBeNull();
});

test('the highlighted option is the one Enter chooses, whatever canivote\'s order', async () => {
  // canivote sorts by id, so policies of one wiki need not be next to each other.
  const policy = (id: string, wiki: string) => ({id, title: `Policy ${id}`, wiki, rules: [], sources: []});
  server.use(http.get(POLICIES_URL, () => HttpResponse.json({data: {available: true, policies: [
    policy('a', 'nl.wikipedia.org'), policy('b', 'de.wikipedia.org'), policy('c', 'nl.wikipedia.org'),
  ]}})));
  renderField({eventId: 'c', label: 'Policy c'});
  const box = await screen.findByRole('combobox', {name: 'Eligibility policy'});

  // Reopening highlights the stored choice.
  fireEvent.keyDown(box, {key: 'ArrowDown'});
  const highlighted = () => document.getElementById(box.getAttribute('aria-activedescendant')!)!;
  expect(highlighted()).toHaveTextContent('Policy c');
  expect(highlighted()).toHaveAttribute('aria-selected', 'true');

  for (const [moves, id] of [[-1, 'b'], [-1, 'a']] as const) {
    fireEvent.keyDown(box, {key: moves < 0 ? 'ArrowUp' : 'ArrowDown'});
    expect(highlighted()).toHaveTextContent(`Policy ${id}`);
  }
  fireEvent.keyDown(box, {key: 'Enter'});
  expect(current().eventId).toBe('a');

  fireEvent.keyDown(box, {key: 'ArrowDown'});
  fireEvent.keyDown(box, {key: 'ArrowDown'});
  expect(highlighted()).toHaveTextContent('Policy b');
  fireEvent.keyDown(box, {key: 'Enter'});
  expect(current().eventId).toBe('b');
});

test('the keyboard chooses, and choosing fills the label with the policy title', async () => {
  renderField();
  const box = await screen.findByRole('combobox', {name: 'Eligibility policy'});

  fireEvent.change(box, {target: {value: 'wikipedia'}});
  fireEvent.keyDown(box, {key: 'ArrowDown'});
  expect(box).toHaveAttribute('aria-activedescendant',
    screen.getAllByRole('option')[1]!.id);
  fireEvent.keyDown(box, {key: 'Enter'});

  expect(current()).toEqual({eventId: 'dewiki-stimmberechtigung', label: 'Voting eligibility on German Wikipedia'});
  expect(box).toHaveValue('Voting eligibility on German Wikipedia');
  expect(box).toHaveAttribute('aria-expanded', 'false');
  expect(screen.getByLabelText('Eligibility label')).toHaveValue('Voting eligibility on German Wikipedia');
  // The chosen policy's rules, in words, under the field.
  expect(screen.getByRole('list', {name: 'Voting eligibility on German Wikipedia'}))
    .toHaveTextContent('At least 200 article edits on de.wikipedia.org');
});

test('typed text is never a value: Escape or leaving the field puts the choice back', async () => {
  renderField({eventId: 'meta-global', label: 'Good standing'});
  const box = await screen.findByRole('combobox', {name: 'Eligibility policy'});
  expect(box).toHaveValue('Not blocked anywhere in the movement');

  fireEvent.change(box, {target: {value: 'nlwiki-stemprocedur'}});
  fireEvent.keyDown(box, {key: 'Escape'});
  expect(box).toHaveValue('Not blocked anywhere in the movement');

  fireEvent.change(box, {target: {value: 'nlwiki-stemprocedure'}});
  fireEvent.blur(box);
  expect(box).toHaveValue('Not blocked anywhere in the movement');
  expect(current()).toEqual({eventId: 'meta-global', label: 'Good standing'});
});

test('the label follows the policy until the organizer writes their own', async () => {
  renderField({eventId: 'meta-global', label: 'Not blocked anywhere in the movement'});
  const box = await screen.findByRole('combobox', {name: 'Eligibility policy'});

  // Still the previous policy's title: replaced by the new one's.
  fireEvent.change(box, {target: {value: 'dutch'}});
  fireEvent.click(screen.getByRole('option', {name: /Dutch/}));
  expect(current().label).toBe('Voting eligibility on Dutch Wikipedia');

  // The organizer's own wording stays when the policy changes.
  fireEvent.change(screen.getByLabelText('Eligibility label'), {target: {value: 'Stemgerechtigd'}});
  fireEvent.change(box, {target: {value: 'german'}});
  fireEvent.click(screen.getByRole('option', {name: /German/}));
  expect(current()).toEqual({eventId: 'dewiki-stimmberechtigung', label: 'Stemgerechtigd'});

  // No check: no label either, and no label field.
  fireEvent.keyDown(box, {key: 'ArrowDown'});
  fireEvent.click(screen.getByRole('option', {name: 'No eligibility check'}));
  expect(current()).toEqual({eventId: '', label: ''});
  expect(screen.queryByLabelText('Eligibility label')).toBeNull();
  expect(box).toHaveValue('');
  expect(box).toHaveAttribute('placeholder', 'No eligibility check');
});

test('a removed policy\'s title is not kept as the organizer\'s label', async () => {
  // The stored policy is no longer on canivote's list, so its title cannot be told apart
  // from a label the organizer wrote: choosing another policy takes that policy's title.
  renderField({eventId: 'gone', label: 'Voting eligibility on a closed wiki'});
  const box = await screen.findByRole('combobox', {name: 'Eligibility policy'});

  fireEvent.change(box, {target: {value: 'dutch'}});
  fireEvent.click(screen.getByRole('option', {name: /Dutch/}));

  expect(current()).toEqual({eventId: 'nlwiki-stemprocedure', label: 'Voting eligibility on Dutch Wikipedia'});
});

test('a stored id canivote does not have is named and asks for a choice', async () => {
  renderField({eventId: 'typed-by-hand', label: 'Old'});
  const box = await screen.findByRole('combobox', {name: 'Eligibility policy'});

  expect(box).toHaveValue('typed-by-hand');
  const note = screen.getByText('"typed-by-hand" is not one of canivote\'s policies. Choose one from the list.');
  expect(box.getAttribute('aria-describedby')).toContain(note.id);
});

test('while canivote cannot be reached no policy can be chosen, but the check can be removed', async () => {
  server.use(http.get(POLICIES_URL, () => HttpResponse.json({data: {available: false, policies: []}})));
  renderField({eventId: 'nlwiki-stemprocedure', label: 'Stemgerechtigd'});

  const note = await screen.findByText('The list of eligibility policies cannot be loaded now.');
  const box = screen.getByRole('combobox', {name: 'Eligibility policy'});
  expect(box).toHaveValue('nlwiki-stemprocedure');
  expect(box.getAttribute('aria-describedby')).toContain(note.id);
  // The label stays editable: it is the organizer's text, not canivote's.
  expect(screen.getByLabelText('Eligibility label')).toHaveValue('Stemgerechtigd');

  fireEvent.keyDown(box, {key: 'ArrowDown'});
  expect(optionNames()).toEqual(['No eligibility check']);
  fireEvent.keyDown(box, {key: 'Enter'});
  expect(current()).toEqual({eventId: '', label: ''});
});

test('under qqx, nothing in the field is English', async () => {
  renderAsQqx();
  const {container} = renderField({eventId: 'nlwiki-stemprocedure', label: 'Stemgerechtigd'}, 'provider');

  const box = await screen.findByRole('combobox', {name: '(admin-access-policy-label)'});
  fireEvent.keyDown(box, {key: 'ArrowDown'});
  const content = testPolicies.flatMap((policy) => [policy.title, policy.id, policy.wiki]);
  expect(untranslatedCopy([container.querySelector('.policy-field')], [...content, 'Stemgerechtigd', '▾']))
    .toEqual([]);
});

// ── On the pages ──────────────────────────────────────────────────────────────

type Settings = components['schemas']['AdminSettings'];

function settingsFixture(overrides: Partial<Settings['eligibility']>, edit: boolean): Settings {
  return {
    conversation: {
      id: 7, slug: 'community-strategy', title: 'Community strategy', introHtml: '', outroHtml: '',
      accessPolicy: 'public', gated: false, gatingType: null, announce: false, information: false,
      resultsShared: false, showUsernames: false, accessRequestText: null, phaseRoute: 'default_7',
      phaseRouteLabel: 'Full consultation', polisId: 'polis-community-strategy',
    },
    recommendations: {tier: 'medium', tiers: [{key: 'medium', label: 'Medium topic', quantities: {}}]},
    eligibility: {configured: false, eventId: '', label: null, policy: null, ...overrides},
    capabilities: {edit, switchDemo: false},
    locks: {gated: true, gatingType: true, showUsernames: true},
    links: {self: SETTINGS_URL, lifecycle: '/admin/conversations/7'},
  };
}

function renderSettings() {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={['/admin/conversations/7/settings/access']}>
        <Suspense fallback={null}>
          <MessageProvider locale="en">
            <AdminSettingsPage conversationId={7} csrfToken="test-csrf-token" tab="access" />
          </MessageProvider>
        </Suspense>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

test('a moderator reads the policy, its rules and its label as text', async () => {
  server.use(http.get(SETTINGS_URL, () => HttpResponse.json({data: settingsFixture({
    configured: true, eventId: 'nlwiki-stemprocedure', label: 'Stemgerechtigd',
    policy: testPolicies[0]!,
  }, false)})));
  renderSettings();

  expect(await screen.findByText('Voting eligibility on Dutch Wikipedia', {}, {timeout: 10_000})).toBeVisible();
  expect(screen.queryByRole('combobox')).toBeNull();
  expect(screen.queryByRole('textbox')).toBeNull();
  expect(screen.getByText('Stemgerechtigd')).toBeVisible();
  expect(screen.getByRole('list', {name: 'Voting eligibility on Dutch Wikipedia'}))
    .toHaveTextContent('First edit on nl.wikipedia.org at least 2 weeks ago');
  expect(screen.getByRole('link', {name: /Policy page/}))
    .toHaveAttribute('href', 'https://nl.wikipedia.org/wiki/Wikipedia:Stemprocedure');
});

test('the policy can still be chosen once Explore has opened', async () => {
  // Not locked (owner, 2026-10-15): the admission answer locks, the policy does not.
  server.use(http.get(SETTINGS_URL, () => HttpResponse.json({data: settingsFixture({}, true)})));
  renderSettings();

  const box = await screen.findByRole('combobox', {name: 'Eligibility policy'}, {timeout: 10_000});
  expect(box).toBeEnabled();
});

test('a refused policy is said at the field', async () => {
  server.use(
    http.get(SETTINGS_URL, () => HttpResponse.json({data: settingsFixture({}, true)})),
    http.put(SETTINGS_URL, () => HttpResponse.json({error: {
      code: 'validation_failed', message: 'Check the highlighted settings.',
      details: {fields: {eligibilityEventId: ['Choose an eligibility policy from the list.']}},
    }}, {status: 400})),
  );
  renderSettings();

  const box = await screen.findByRole('combobox', {name: 'Eligibility policy'}, {timeout: 10_000});
  fireEvent.change(box, {target: {value: 'meta'}});
  fireEvent.click(screen.getByRole('option', {name: /movement/}));
  fireEvent.click(screen.getByRole('button', {name: 'Save'}));

  await waitFor(() => expect(box).toHaveAttribute('aria-invalid', 'true'));
  const error = screen.getAllByText('Choose an eligibility policy from the list.')
    .find((node) => node.classList.contains('access-field-error'))!;
  expect(box.getAttribute('aria-describedby')).toContain(error.id);
});

test('a refused policy on New consultation is announced', async () => {
  server.use(http.post(new URL('/api/v1/admin/conversations', globalThis.location.origin).toString(), () => HttpResponse.json({error: {
    code: 'validation_failed', message: 'Check the highlighted settings.',
    details: {fields: {eligibilityEventId: ['Choose an eligibility policy from the list.']}},
  }}, {status: 400})));
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={['/admin']}>
        <Suspense fallback={null}>
          <MessageProvider locale="en"><AdminCatalogPage csrfToken="test-csrf-token" /></MessageProvider>
        </Suspense>
      </MemoryRouter>
    </QueryClientProvider>,
  );

  const heading = await screen.findByRole('heading', {name: 'New consultation', level: 2}, {timeout: 10_000});
  fireEvent.click(heading.closest('summary')!);
  const form = heading.closest('details')!;
  fireEvent.change(within(form).getByLabelText(/Slug/), {target: {value: 'new-one'}});
  fireEvent.change(within(form).getByLabelText('Title'), {target: {value: 'New one'}});
  fireEvent.click(within(form).getByRole('button', {name: /Create/}));

  expect(await within(form).findByRole('alert')).toHaveTextContent('Check the highlighted settings.');
  expect(within(form).getByText('Choose an eligibility policy from the list.')).toBeVisible();
});

test('New consultation sends the chosen policy and its label', async () => {
  const sent: Record<string, unknown>[] = [];
  server.use(http.post(new URL('/api/v1/admin/conversations', globalThis.location.origin).toString(), async ({request}) => {
    sent.push(await request.json() as Record<string, unknown>);
    return HttpResponse.json({data: {conversation: {id: 9, slug: 'new-one', title: 'New one'},
      links: {manage: '/admin/conversations/9', catalog: '/api/v1/admin'}}}, {status: 201});
  }));
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={['/admin']}>
        <Suspense fallback={null}>
          <MessageProvider locale="en"><AdminCatalogPage csrfToken="test-csrf-token" /></MessageProvider>
        </Suspense>
      </MemoryRouter>
    </QueryClientProvider>,
  );

  const heading = await screen.findByRole('heading', {name: 'New consultation', level: 2}, {timeout: 10_000});
  fireEvent.click(heading.closest('summary')!);
  const form = heading.closest('details')!;
  expect(within(form).queryByLabelText('Eligibility event ID')).toBeNull();
  fireEvent.change(within(form).getByLabelText(/Slug/), {target: {value: 'new-one'}});
  fireEvent.change(within(form).getByLabelText('Title'), {target: {value: 'New one'}});
  const box = await within(form).findByRole('combobox', {name: 'Eligibility policy'});
  fireEvent.change(box, {target: {value: 'nlwiki'}});
  fireEvent.click(within(form).getByRole('option', {name: /Dutch/}));
  fireEvent.change(within(form).getByLabelText('Eligibility label'), {target: {value: 'Stemgerechtigd'}});
  fireEvent.click(within(form).getByRole('button', {name: /Create/}));

  await waitFor(() => expect(sent).toHaveLength(1));
  expect(sent[0]).toMatchObject({eligibilityEventId: 'nlwiki-stemprocedure', eligibilityLabel: 'Stemgerechtigd'});
});
