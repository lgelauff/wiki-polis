import {Suspense} from 'react';
import {QueryClientProvider} from '@tanstack/react-query';
import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import {http, HttpResponse} from 'msw';
import {expect, test} from 'vitest';

import type {components} from '../../api/schema';
import {AdminReminderTest} from './admin-reminder-test';
import {MessageProvider} from '../../i18n/messages';
import {createQueryClient} from '../../query-client';
import {server} from '../../test/server';

type State = components['schemas']['ReminderTestResponse']['data'];
type Sent = components['schemas']['ReminderTestSendResponse']['data'];

const STATE_URL = new URL('/api/v1/admin/reminder-test', globalThis.location.origin).toString();
const SEND_URL = new URL('/api/v1/admin/reminder-test-sends', globalThis.location.origin).toString();

const state: State = {
  wikis: [
    {key: 'metawiki', host: 'meta.wikimedia.org'},
    {key: 'nlwiki', host: 'nl.wikipedia.org'},
  ],
  recipients: ['Tester', 'Tester two'],
  credentialsSet: {email: true, talk: true},
};

const sent = (sentVia: string): Sent => ({outcome: 'sent', reason: null, code: null, sentVia});

function serve(stateData: State, reply?: () => Response | Promise<Response>, seen: unknown[] = []) {
  server.use(
    http.get(STATE_URL, () => HttpResponse.json({data: stateData})),
    http.post(SEND_URL, async ({request}) => {
      const body = await request.json() as {wiki: string};
      seen.push(body);
      return reply ? reply() : HttpResponse.json({data: sent(body.wiki)});
    }),
  );
  return seen;
}

function fold() {
  return screen.getByRole('heading', {name: 'Reminder test', level: 2}).closest('details')!;
}

function toggle(open: boolean) {
  const details = fold();
  details.open = open;
  fireEvent(details, new Event('toggle'));
}

async function renderSection() {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <Suspense fallback={null}>
        <MessageProvider locale="en"><AdminReminderTest csrfToken="test-csrf-token" /></MessageProvider>
      </Suspense>
    </QueryClientProvider>,
  );
  await screen.findByRole('heading', {name: 'Reminder test', level: 2});
  toggle(true);
}

test('lists every wiki by host, with no dry-run label, and sends to the chosen test account', async () => {
  const seen = serve(state);
  await renderSection();
  const wiki = await screen.findByRole('combobox', {name: 'Wiki'});
  expect((wiki as HTMLSelectElement).value).toBe('metawiki');
  expect(screen.getAllByRole('option', {name: /wiki/}).map((o) => o.textContent))
    .toEqual(['meta.wikimedia.org', 'nl.wikipedia.org']);
  fireEvent.change(wiki, {target: {value: 'nlwiki'}});
  fireEvent.change(screen.getByRole('combobox', {name: 'Test account'}), {target: {value: 'Tester two'}});
  fireEvent.click(screen.getByRole('button', {name: 'Send test'}));
  expect(await screen.findByText('Sent from nl.wikipedia.org.')).toBeTruthy();
  expect(seen).toEqual([{wiki: 'nlwiki', channel: 'email', recipient: 'Tester two'}]);
});

test('says when wiki-mail went out from Meta instead', async () => {
  serve(state, () => HttpResponse.json({data: sent('metawiki')}));
  await renderSection();
  fireEvent.change(await screen.findByRole('combobox', {name: 'Wiki'}), {target: {value: 'nlwiki'}});
  fireEvent.click(screen.getByRole('button', {name: 'Send test'}));
  expect(await screen.findByText(
    "Sent from meta.wikimedia.org, because this account can't receive wiki-mail on nl.wikipedia.org.",
  )).toBeTruthy();
});

test('says why a test was not sent', async () => {
  serve(state, () => HttpResponse.json({data: {
    outcome: 'failed', reason: 'not_emailable', code: null, sentVia: null,
  }}));
  await renderSection();
  fireEvent.click(await screen.findByRole('button', {name: 'Send test'}));
  expect(await screen.findByText(/can't receive wiki-mail, on this wiki or on Meta/)).toBeTruthy();
});

test('a talk page that keeps bots out is named as the reason', async () => {
  serve(state, () => HttpResponse.json({data: {outcome: 'failed', reason: 'nobots', code: null, sentVia: null}}));
  await renderSection();
  fireEvent.change(await screen.findByRole('combobox', {name: 'Channel'}), {target: {value: 'talk'}});
  fireEvent.click(screen.getByRole('button', {name: 'Send test'}));
  expect(await screen.findByText('Not sent: the talk page asks bots not to post there.')).toBeTruthy();
});

test('shows that a send is under way, and keeps its result when the section is folded', async () => {
  let release: () => void = () => {};
  const gate = new Promise<void>((resolve) => { release = resolve; });
  serve(state, async () => { await gate; return HttpResponse.json({data: sent('metawiki')}); });
  await renderSection();
  fireEvent.click(await screen.findByRole('button', {name: 'Send test'}));
  expect(await screen.findByText(/^Sending…/)).toBeTruthy();
  toggle(false);
  release();
  await waitFor(() => expect(screen.queryByText(/^Sending…/)).toBeNull());
  toggle(true);
  expect(await screen.findByText('Sent from meta.wikimedia.org.')).toBeTruthy();
});

test('changing the selection clears the previous result', async () => {
  serve(state);
  await renderSection();
  fireEvent.click(await screen.findByRole('button', {name: 'Send test'}));
  expect(await screen.findByText('Sent from meta.wikimedia.org.')).toBeTruthy();
  fireEvent.change(screen.getByRole('combobox', {name: 'Channel'}), {target: {value: 'talk'}});
  expect(screen.queryByText('Sent from meta.wikimedia.org.')).toBeNull();
});

test('a refused request is said in the console\'s own words', async () => {
  serve(state, () => HttpResponse.json({error: {
    code: 'recipient_not_allowed', message: 'Only the configured test accounts, wikis and channels can be used.',
  }}, {status: 400}));
  await renderSection();
  fireEvent.click(await screen.findByRole('button', {name: 'Send test'}));
  expect(await screen.findByText(/only the test accounts, wikis and channels set on the server/)).toBeTruthy();
});

test('too many tests in a minute are named as such', async () => {
  serve(state, () => HttpResponse.json({error: {code: 'rate_limited', message: '6 per 1 minute'}}, {status: 429}));
  await renderSection();
  fireEvent.click(await screen.findByRole('button', {name: 'Send test'}));
  expect(await screen.findByText(/too many tests in a short time/)).toBeTruthy();
});

test('without test accounts there is nothing to send to', async () => {
  serve({...state, recipients: []});
  await renderSection();
  expect(await screen.findByText(/No test accounts are set/)).toBeTruthy();
  expect(screen.queryByRole('button', {name: 'Send test'})).toBeNull();
});

test('says when the bot login for the chosen channel is not set, next to the button', async () => {
  serve({...state, credentialsSet: {email: false, talk: true}});
  await renderSection();
  const button = await screen.findByRole('button', {name: 'Send test'});
  expect(button.getAttribute('aria-describedby')).toBeTruthy();
  expect(document.getElementById(button.getAttribute('aria-describedby')!)?.textContent)
    .toMatch(/the bot's login for this channel is not set on the server/);
  fireEvent.change(screen.getByRole('combobox', {name: 'Channel'}), {target: {value: 'talk'}});
  expect(screen.queryByText(/the bot's login for this channel is not set/)).toBeNull();
  expect(button.getAttribute('aria-describedby')).toBeNull();
  fireEvent.change(screen.getByRole('combobox', {name: 'Channel'}), {target: {value: 'email'}});
  const describedBy = button.getAttribute('aria-describedby');
  expect(document.getElementById(describedBy!)?.textContent).toMatch(/login for this channel is not set/);
});

test('a plain account name instead of a bot-password name is explained', async () => {
  serve(state, () => HttpResponse.json({data: {
    outcome: 'failed', reason: 'api_error', code: 'not_a_bot_password', sentVia: null,
  }}));
  await renderSection();
  fireEvent.click(await screen.findByRole('button', {name: 'Send test'}));
  expect(await screen.findByText(/is not a bot-password name/)).toBeTruthy();
});
