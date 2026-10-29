import {Suspense} from 'react';
import {QueryClientProvider} from '@tanstack/react-query';
import {fireEvent, render, screen} from '@testing-library/react';
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
    {key: 'metawiki', host: 'meta.wikimedia.org', live: false},
    {key: 'nlwiki', host: 'nl.wikipedia.org', live: true},
  ],
  recipients: ['Tester', 'Tester two'],
  credentialsSet: true,
};

function serve(stateData: State, sent?: Sent, seen: unknown[] = []) {
  server.use(
    http.get(STATE_URL, () => HttpResponse.json({data: stateData})),
    http.post(SEND_URL, async ({request}) => {
      seen.push(await request.json());
      return HttpResponse.json({data: sent});
    }),
  );
  return seen;
}

async function renderSection() {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <Suspense fallback={null}>
        <MessageProvider locale="en"><AdminReminderTest csrfToken="test-csrf-token" /></MessageProvider>
      </Suspense>
    </QueryClientProvider>,
  );
  const fold = (await screen.findByRole('heading', {name: 'Reminder test', level: 2})).closest('details')!;
  fold.open = true;
  fireEvent(fold, new Event('toggle'));
}

test('defaults to a live wiki and sends to the chosen test account', async () => {
  const seen = serve(state, {outcome: 'sent', reason: null, code: null, sentVia: 'metawiki'});
  await renderSection();
  const wiki = await screen.findByRole('combobox', {name: 'Wiki'});
  expect((wiki as HTMLSelectElement).value).toBe('nlwiki');
  expect(screen.getByRole('option', {name: 'meta.wikimedia.org (dry run)'})).toBeTruthy();
  fireEvent.change(screen.getByRole('combobox', {name: 'Test account'}), {target: {value: 'Tester two'}});
  fireEvent.click(screen.getByRole('button', {name: 'Send test'}));
  expect((await screen.findByRole('status')).textContent).toBe('Sent from metawiki.');
  expect(seen).toEqual([{wiki: 'nlwiki', channel: 'email', recipient: 'Tester two'}]);
});

test('says why a test was not sent', async () => {
  serve(state, {outcome: 'failed', reason: 'nobots', code: null, sentVia: null});
  await renderSection();
  fireEvent.change(await screen.findByRole('combobox', {name: 'Channel'}), {target: {value: 'talk'}});
  fireEvent.click(screen.getByRole('button', {name: 'Send test'}));
  expect((await screen.findByRole('status')).textContent).toBe(
    'Not sent: the talk page asks bots not to post there.',
  );
});

test('without test accounts there is nothing to send to', async () => {
  serve({...state, recipients: []});
  await renderSection();
  expect(await screen.findByText(/No test accounts are set/)).toBeTruthy();
  expect(screen.queryByRole('button', {name: 'Send test'})).toBeNull();
});

test('says when the bot login is not set', async () => {
  serve({...state, credentialsSet: false});
  await renderSection();
  expect(await screen.findByText(/the bot's login is not set on the server/)).toBeTruthy();
});
