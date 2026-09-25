import {QueryClientProvider} from '@tanstack/react-query';
import {fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {http, HttpResponse} from 'msw';
import {MemoryRouter} from 'react-router-dom';
import {expect, test} from 'vitest';

import type {components} from '../../api/schema';
import {App} from '../../app';
import {createQueryClient} from '../../query-client';
import {server} from '../../test/server';
import {testMessages} from '../../test/handlers';
import {renderAsQqx, untranslatedCopy} from '../../test/i18n';

type JoinEntry = components['schemas']['JoinParticipationEntry'];

const url = (path: string) => new URL(path, globalThis.location.origin).toString();
const ENTRY_URL = url('/api/v1/conversations/community-strategy/participation-entry');
const PARTICIPATION_URL = url('/api/v1/conversations/community-strategy/participation');
const I18N_URL = url('/api/v1/i18n/:locale');

const TITLE = 'Community strategy';
const PSEUDONYM = 'quiet-otter';
const DESCRIPTION = 'Shape the next chapter together.';

/** Markup a participant or an organizer could type into a field that reaches a `richHtml`
 *  sink. Rendered as text it is harmless; rendered as markup it is an element. */
const HOSTILE = '<img src=x onerror="alert(1)">';

/** Renders the join screen through the app router with the test catalogue. */
function renderJoin() {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={['/accept/community-strategy']}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

/** The join payload, with room for the values the organizer and the participant control. */
function serveJoinEntry(overrides: Partial<JoinEntry> = {}, conversation: Partial<JoinEntry['conversation']> = {}) {
  server.use(http.get(ENTRY_URL, () => HttpResponse.json({data: {
    state: 'join',
    conversation: {id: 7, slug: 'community-strategy', title: TITLE, descriptionHtml: `<p>${DESCRIPTION}</p>`, eligibilityLabel: null, ...conversation},
    pseudonyms: [PSEUDONYM, 'bright-fox', 'steady-heron'],
    emailable: true,
    reveal: {cooldownDays: 30, windowEndDays: 60},
    links: {home: '/', conversation: '/c/community-strategy'},
    ...overrides,
  }})));
}

/** The 403 the participation POST returns when the eligibility check refuses or cannot run.
 *  `displayMessage` carries Proto's own English diagnostic about the checker, which the page
 *  must ignore in favour of the catalogue. */
function serveEligibilityRefusal(status: 'ineligible' | 'unavailable', displayMessage: string | null = null) {
  server.use(http.post(PARTICIPATION_URL, () => HttpResponse.json({error: {
    code: status === 'unavailable' ? 'eligibility_unavailable' : 'eligibility_denied',
    message: 'Eligibility could not be confirmed.',
    details: {status, displayMessage},
  }}, {status: 403})));
}

/** Resolves once the join form is on screen. Named by element id rather than by copy,
 *  because several tests below serve a catalogue whose values are not the shipped English. */
function joinForm() {
  return waitFor(() => {
    const form = document.getElementById('accept-form');
    if (!form) throw new Error('the join form did not render');
    return form;
  });
}

/** Consents and submits, the only route to the not-eligible page. */
async function submitJoin() {
  await joinForm();
  fireEvent.click(document.getElementById('consent-check')!);
  fireEvent.click(document.getElementById('submit-btn')!);
}

test('the join screen renders its copy from the catalogue', async () => {
  renderJoin();
  expect(await screen.findByText(testMessages['accept-choose-pseudonym']!)).toBeVisible();
  // Catches the consent tick becoming optional: it is the only thing standing between a
  // participant and a CC0 release they did not agree to.
  expect(document.getElementById('consent-check')).toBeRequired();
  // Catches a key that is renamed, missing from en.json, or wired to the wrong element: the
  // page then shows the raw key or other text. The form still submits in that state, so the
  // consent text and licence heading, which the participant agrees to, are checked by name.
  expect(screen.getByText(testMessages['accept-consent']!)).toBeVisible();
  expect(screen.getByRole('heading', {name: testMessages['accept-licence-heading']!})).toBeVisible();
  expect(screen.getByText(testMessages['accept-privacy-summary']!)).toBeVisible();
  expect(screen.getByRole('button', {name: testMessages['accept-reroll-aria']!})).toBeVisible();
});

test('the licence sentence keeps its link inside one message', async () => {
  renderJoin();
  // Catches the link leaving the sentence or turning into visible markup: the message losing
  // its $1 (easy in a translation), or richHtml being swapped for plain text rendering. Scoped
  // to this section because the shell footer renders a second CC0 link.
  await screen.findByText(testMessages['accept-licence-heading']!);
  const section = document.getElementById('accept-licence-note');
  expect(section).not.toBeNull();
  const link = within(section!).getByRole('link', {name: /CC0/});
  expect(link).toHaveAttribute('href', 'https://creativecommons.org/publicdomain/zero/1.0/');
  expect(link.closest('p')?.textContent).toContain('released into the public domain (CC0');
});

test('the identity-reveal window reads as one sentence with both numbers', async () => {
  renderJoin();
  // Catches a parameter that is dropped or passed in the wrong position, and a plural unit
  // that fails to resolve. The sentence still renders in each case; only the numbers show it.
  const details = await screen.findByText(testMessages['accept-privacy-details-summary']!);
  const body = details.closest('details')?.textContent ?? '';
  expect(body).toContain('From');
  expect(body).toContain('30');
  expect(body).toContain('60 days');
  expect(body).toContain('link your Wikimedia username');
});

test('the invite-only page names the consultation inside one sentence', async () => {
  server.use(http.get(
    ENTRY_URL,
    () => HttpResponse.json({data: {
      state: 'invite_denied', viewer: 'refused', certainty: 'known', reason: 'access-invite-required',
      conversation: {id: 7, slug: 'community-strategy', title: TITLE},
      canModerate: false,
      links: {home: '/', manageInvites: null},
    }}),
  ));
  renderJoin();
  // Catches the organizer's title going missing from the sentence, e.g. $1 not being passed.
  expect(await screen.findByText(new RegExp(TITLE))).toBeVisible();
  expect(screen.getByText(/restricted to invited participants/)).toBeVisible();
});

// The message catalogue the page actually renders, rather than the English a hardcoded
// literal would render identically. A test that asserts en.json's own words passes whether
// the words come from msg() or from the source file, so these serve values no literal could
// produce and assert where each parameter lands.

test('the licence link lands where the message puts it, not where the code does', async () => {
  server.use(http.get(I18N_URL, () => HttpResponse.json({...testMessages, 'accept-licence-intro': 'BEFORE $1 AFTER'})));
  renderJoin();
  await joinForm();

  // Catches the sentence being assembled in code around a hardcoded link — text before the
  // link, text after it — which reads correctly in English and cannot be reordered in a
  // language that puts the object first.
  const section = document.getElementById('accept-licence-note')!;
  const link = within(section).getByRole('link', {name: /CC0/});
  expect(link.closest('p')!.textContent).toBe(`BEFORE ${testMessages['accept-licence-link']} ${testMessages['common-opens-in-new-tab']} AFTER`);
});

test('the reveal window puts its two day counts where the message asks for them', async () => {
  server.use(http.get(I18N_URL, () => HttpResponse.json({
    ...testMessages,
    'accept-privacy-reveal-window': 'WINDOW <strong>$2</strong> COOLDOWN <strong>$1</strong>',
  })));
  renderJoin();
  await joinForm();

  // Catches the cooldown and the window end being swapped, and either being concatenated in
  // code instead of substituted. Both are bare numbers, so in the shipped order a swap still
  // reads as a sentence while misstating when the identity-reveal window opens and closes.
  const sentence = document.querySelectorAll('.privacy-body p')[2]!;
  expect(sentence.textContent).toBe('WINDOW 60 COOLDOWN 30');
  expect([...sentence.querySelectorAll('strong')].map((node) => node.textContent)).toEqual(['60', '30']);
});

test('the submit button puts the pseudonym where the message asks for it', async () => {
  server.use(http.get(I18N_URL, () => HttpResponse.json({...testMessages, 'accept-submit': '$1 JOIN'})));
  renderJoin();
  await joinForm();

  // Catches the button label being built in code around the chosen name, which fixes the
  // name's position and leaves a translator no way to move it.
  const button = document.getElementById('submit-btn')!;
  expect(button.textContent).toBe(`${PSEUDONYM} JOIN`);
  expect(button.querySelector('#chosen-name')!.textContent).toBe(PSEUDONYM);
});

test('the not-eligible page names the requirement the organizer configured', async () => {
  serveJoinEntry({}, {eligibilityLabel: 'Extended-confirmed editors'});
  serveEligibilityRefusal('ineligible');
  renderJoin();
  await submitJoin();
  await screen.findByRole('heading', {name: testMessages['forbidden-elig-heading']!});

  // Catches the organizer's label leaving the sentence or losing its emphasis, and the
  // catalogue's fallback reason being replaced by the API's own English message.
  const requirement = screen.getByText(/eligibility requirement/);
  expect(requirement.textContent).toBe('This consultation has an eligibility requirement: Extended-confirmed editors.');
  expect(requirement.querySelector('strong')!.textContent).toBe('Extended-confirmed editors');
  expect(screen.getByText(testMessages['forbidden-elig-criteria']!)).toBeVisible();
  // Catches a tab title that is left at the shell default, or that drops the consultation.
  expect(document.title).toBe(`Not eligible — ${TITLE} — Proto`);
});

test('without a configured label the requirement sentence still ends in a full stop', async () => {
  serveJoinEntry();
  serveEligibilityRefusal('ineligible');
  renderJoin();
  await submitJoin();
  await screen.findByRole('heading', {name: testMessages['forbidden-elig-heading']!});

  // Catches the labelled sentence being reused with an empty $1, which ends the line with a
  // dangling colon. The two sentences are separate messages so each can be punctuated.
  expect(screen.getByText(/eligibility requirement/).textContent).toBe('This consultation has an eligibility requirement.');
});

test('a checker that cannot answer says so, rather than refusing the participant', async () => {
  serveJoinEntry();
  serveEligibilityRefusal('unavailable');
  renderJoin();
  await submitJoin();
  await screen.findByRole('heading', {name: testMessages['forbidden-elig-heading']!});

  // Catches the unavailable branch falling through to the criteria message, which tells an
  // eligible participant their account was rejected when the checker was merely down.
  expect(screen.getByText(testMessages['forbidden-elig-unavailable']!)).toBeVisible();
  expect(screen.queryByText(testMessages['forbidden-elig-criteria']!)).toBeNull();
});

test('the not-eligible page takes focus from the form it replaces', async () => {
  serveJoinEntry();
  serveEligibilityRefusal('ineligible');
  renderJoin();
  await submitJoin();
  const heading = await screen.findByRole('heading', {name: testMessages['forbidden-elig-heading']!});

  // Catches focus left on a submit button that no longer exists, which drops a keyboard or
  // screen-reader user at the top of the document with nothing announced.
  await waitFor(() => expect(heading).toHaveFocus());
  expect(heading).toHaveAttribute('tabindex', '-1');
});

test.each([
  ['ineligible', 'forbidden-elig-criteria'],
  ['unavailable', 'forbidden-elig-unavailable'],
] as const)(
  'a %s refusal ignores the English diagnostic the API sends alongside it',
  async (status, key) => {
    renderAsQqx();
    serveJoinEntry();
    serveEligibilityRefusal(status, 'The eligibility checker is not configured.');
    renderJoin();
    await submitJoin();
    await screen.findByRole('heading', {name: '(forbidden-elig-heading)'});

    // Catches `displayMessage` coming back: it is Proto's own English about its checker,
    // which no participant can act on and no translator ever sees.
    expect(screen.getByText(`(${key})`)).toBeVisible();
    expect(screen.queryByText(/eligibility checker/)).toBeNull();
  },
);

test.each([
  ['pseudonym_unavailable', 409, 'accept-js-taken'],
  ['validation_failed', 400, 'accept-err-join'],
  ['conflict', 409, 'accept-err-join'],
  ['rate_limited', 429, 'accept-err-join'],
  ['unauthorized', 401, 'common-err-nologin'],
] as const)(
  'a %s from the join form shows catalogue copy, not the server message',
  async (code, status, key) => {
    renderAsQqx();
    serveJoinEntry();
    server.use(http.post(PARTICIPATION_URL, () => HttpResponse.json(
      {error: {code, message: 'Server-side English that must not reach the page.'}}, {status},
    )));
    renderJoin();
    await submitJoin();

    // Catches the server's English reaching the participant under the submit button.
    expect(await screen.findByRole('alert')).toHaveTextContent(`(${key})`);
    expect(document.body).not.toHaveTextContent('Server-side English');
  },
);

test('without a confirmed email the note keeps its link inside the sentence', async () => {
  serveJoinEntry({emailable: false});
  renderJoin();
  await joinForm();

  // Catches the note being split around a hardcoded link, which pins the link to the start of
  // the sentence, and catches the checkbox still being offered for an address that cannot
  // receive anything.
  expect(screen.queryByRole('checkbox', {name: testMessages['accept-notify-email']!})).toBeNull();
  const link = screen.getByRole('link', {name: /Check your email settings on Meta-Wiki/});
  const note = link.closest('p')!;
  expect(note.textContent).toBe('Email notifications are unavailable because your Wikimedia account cannot receive email. Check your email settings on Meta-Wiki (opens in new window) and return to enable this.');
  expect(link).toHaveAttribute('href', 'https://meta.wikimedia.org/wiki/Special:Preferences#mw-prefsection-personal');
  // Catches the new tab going unannounced: the participant leaves to set an address and has
  // to come back to this form, so the page says both that it opens away and to return.
  expect(link).toHaveAttribute('target', '_blank');
  expect(link).toHaveAttribute('rel', 'noopener');
  expect(within(link).getByText(testMessages['common-opens-in-new-tab']!.trim())).toHaveClass('sr-only');
});

test('a hostile consultation title stays text on the invite-only page', async () => {
  server.use(http.get(ENTRY_URL, () => HttpResponse.json({data: {
    state: 'invite_denied', viewer: 'refused', certainty: 'known', reason: 'access-invite-required',
    conversation: {id: 7, slug: 'community-strategy', title: HOSTILE},
    canModerate: false,
    links: {home: '/', manageInvites: null},
  }})));
  renderJoin();
  const body = await screen.findByText(/restricted to invited participants/);

  // Catches escapeHtml going missing from this call site. The title is organizer-controlled
  // and the sentence is a richHtml sink, so unescaped it becomes an element in the page.
  expect(body.textContent).toContain(HOSTILE);
  expect(document.querySelector('img')).toBeNull();
});

test('hostile organizer and participant values stay text on the join and not-eligible pages', async () => {
  serveJoinEntry({pseudonyms: [HOSTILE]}, {title: HOSTILE, eligibilityLabel: HOSTILE});
  serveEligibilityRefusal('ineligible');
  renderJoin();
  await joinForm();

  // Catches escapeHtml going missing from the submit button, whose parameter is the name the
  // participant picked, and from the eligibility sentence, whose label the organizer typed.
  expect(document.getElementById('submit-btn')!.textContent).toBe(`Join consultation as ${HOSTILE} →`);
  expect(document.querySelector('img')).toBeNull();

  await submitJoin();
  await screen.findByRole('heading', {name: testMessages['forbidden-elig-heading']!});
  expect(screen.getByText(/eligibility requirement/).textContent).toBe(`This consultation has an eligibility requirement: ${HOSTILE}.`);
  expect(document.querySelector('img')).toBeNull();
});

test.each([true, false])(
  'under qqx, nothing on the join screen is English (emailable: %s)',
  async (emailable) => {
    renderAsQqx();
    serveJoinEntry({emailable});
    renderJoin();
    await joinForm();

    // Catches copy that never reached the catalogue on the screen where the participant
    // agrees to CC0 and to the username link being kept — including the branch that only a
    // participant without a confirmed wiki email address ever sees.
    const content = [TITLE, DESCRIPTION, PSEUDONYM, 'bright-fox', 'steady-heron'];
    expect(untranslatedCopy([document.querySelector('.container'), document.querySelector('.header-crumb')], content)).toEqual([]);
  },
);

test.each([
  ['invite_denied', 'access-invite-required', 'known', 'forbidden-invite-heading', true],
  ['access_lost', 'access-invite-required', 'known', 'forbidden-lost-invite-heading', true],
  ['invite_denied', 'access-not-eligible', 'known', 'forbidden-access-heading', false],
  ['access_lost', 'access-not-eligible', 'known', 'forbidden-lost-heading', false],
  ['invite_denied', 'access-could-not-confirm', 'temporary', 'forbidden-unconfirmed-heading', false],
  ['access_lost', 'access-could-not-confirm', 'inconclusive', 'forbidden-unconfirmed-heading', false],
  ['invite_denied', 'access-invite-required', 'inconclusive', 'forbidden-unconfirmed-heading', false],
] as const)(
  'a %s refusal (%s, %s) says why, in the catalogue',
  async (state, reason, certainty, heading, moderatorNote) => {
    renderAsQqx();
    server.use(http.get(ENTRY_URL, () => HttpResponse.json({data: {
      state, reason, certainty,
      viewer: state === 'access_lost' ? 'access_lost' : 'refused',
      conversation: {id: 7, slug: 'community-strategy', title: TITLE},
      canModerate: true,
      links: {home: '/', manageInvites: '/admin/conversations/7/invites'},
    }})));
    renderJoin();

    // Catches every refusal reading as a missing invitation: someone whose wiki-based access
    // lapsed, or whose check could not be decided, was told they were not on an invite list.
    await screen.findByRole('heading', {name: `(${heading})`});
    expect(untranslatedCopy([document.querySelector('.container')], [TITLE])).toEqual([]);
    // The note sends an organizer to the invite list, which only helps when an invitation is
    // what is missing.
    expect(screen.queryByText('(forbidden-invite-mod-lead)') !== null).toBe(moderatorNote);
  },
);

test('under qqx, nothing on the invite-only page is English', async () => {
  renderAsQqx();
  server.use(http.get(ENTRY_URL, () => HttpResponse.json({data: {
    state: 'invite_denied', viewer: 'refused', certainty: 'known', reason: 'access-invite-required',
    conversation: {id: 7, slug: 'community-strategy', title: TITLE},
    canModerate: true,
    links: {home: '/', manageInvites: '/admin/conversations/7/invites'},
  }})));
  renderJoin();
  await screen.findByRole('heading', {name: '(forbidden-invite-heading)'});

  // Catches hardcoded copy, including the moderator note that only an organizer who is
  // locked out of their own invite-only consultation sees.
  expect(untranslatedCopy([document.querySelector('.container')], [TITLE])).toEqual([]);
  expect(document.title).toBe('(forbidden-invite-doc-title)');
});

test.each([
  ['ineligible', 'Extended-confirmed editors'],
  ['unavailable', 'Extended-confirmed editors'],
  ['ineligible', null],
] as const)(
  'under qqx, nothing on the not-eligible page is English (%s, label: %s)',
  async (status, eligibilityLabel) => {
    renderAsQqx();
    serveJoinEntry({}, {eligibilityLabel});
    serveEligibilityRefusal(status);
    renderJoin();
    await submitJoin();
    await screen.findByRole('heading', {name: '(forbidden-elig-heading)'});

    // Catches hardcoded copy on the page a refused participant is left on, and the API's own
    // English message being rendered in place of the catalogue's reason. The unlabelled row
    // reaches the sentence shown when the organizer configured no label, which is a different
    // message from the one with the label in it.
    expect(untranslatedCopy([document.querySelector('.container')], eligibilityLabel ? [eligibilityLabel] : [])).toEqual([]);
    expect(document.title).toBe(`(forbidden-elig-doc-title: ${TITLE})`);
  },
);

function serveVoucherSession() {
  server.use(http.get(url('/api/v1/session'), () => HttpResponse.json({data: {
    state: 'voucher',
    user: null,
    capabilities: {administerSite: false},
    csrfToken: 'test-csrf-token',
    developerLogins: [],
    gitVersion: 'test-version',
    locales: {current: 'en', available: [{code: 'en', name: 'English'}]},
    links: {login: '/login', logout: '/logout'},
  }})));
}

test('a voucher account can join, without Wikimedia notification options', async () => {
  serveVoucherSession();
  serveJoinEntry({emailable: false});
  renderJoin();
  await joinForm();

  // Catches the join screen bouncing a voucher account to the Wikimedia login, and catches it
  // offering an email or talk page the account does not have.
  expect(screen.queryByRole('checkbox', {name: testMessages['accept-notify-talk']!})).toBeNull();
  expect(screen.queryByRole('heading', {name: testMessages['accept-notify-heading']!})).toBeNull();
  expect(screen.queryByRole('link', {name: /Check your email settings/})).toBeNull();
  // The header names the account kind where a username would be, and still offers log out.
  expect(screen.getByText(testMessages['base-voucher-account']!)).toBeVisible();
  expect(screen.getByRole('button', {name: testMessages['base-log-out']!})).toBeVisible();
});
