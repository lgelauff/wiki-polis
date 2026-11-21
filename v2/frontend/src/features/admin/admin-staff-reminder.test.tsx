import {Suspense} from 'react';
import {QueryClientProvider} from '@tanstack/react-query';
import {fireEvent, render, screen, within} from '@testing-library/react';
import {http, HttpResponse} from 'msw';
import {expect, test} from 'vitest';

import type {components} from '../../api/schema';
import {AdminStaffReminder} from './admin-staff-reminder';
import {MessageProvider} from '../../i18n/messages';
import {createQueryClient} from '../../query-client';
import {server} from '../../test/server';

type State = components['schemas']['StaffReminderResponse']['data'];
type Run = components['schemas']['StaffReminderDryRunResponse']['data'];

const STATE_URL = new URL('/api/v1/admin/conversations/7/reminder-dry-run', globalThis.location.origin).toString();
const RUN_URL = new URL('/api/v1/admin/conversations/7/reminder-dry-runs', globalThis.location.origin).toString();

const state: State = {
  wiki: 'nlwiki', wikiHost: 'nl.wikipedia.org', automatedSendApproved: false,
  reminderTypes: ['phase_opened', 'phase_closing', 'results'],
  counts: {email: 2, talk: 1},
};

const run: Run = {reminderId: 3, rows: [
  {username: 'Organizer', channel: 'email', status: 'dry_run', reason: null, errorCode: null},
  {username: 'Organizer', channel: 'talk', status: 'not_sent_limit', reason: null, errorCode: null},
  {username: 'Moderator', channel: 'email', status: 'failed', reason: 'nobots', errorCode: null},
  {username: 'Site admin', channel: 'email', status: 'combined', reason: null, errorCode: null},
]};

function serve(reply: () => Response = () => HttpResponse.json({data: run}), seen: unknown[] = []) {
  server.use(
    http.get(STATE_URL, () => HttpResponse.json({data: state})),
    http.post(RUN_URL, async ({request}) => {
      seen.push(await request.json());
      return reply();
    }),
  );
  return seen;
}

async function renderOpen(stateData: State = state) {
  server.use(http.get(STATE_URL, () => HttpResponse.json({data: stateData})));
  render(
    <QueryClientProvider client={createQueryClient()}>
      <Suspense fallback={null}>
        <MessageProvider locale="en"><AdminStaffReminder conversationId={7} csrfToken="test-csrf-token" /></MessageProvider>
      </Suspense>
    </QueryClientProvider>,
  );
  const details = (await screen.findByText('Staff dry run', {selector: 'summary'})).closest('details')!;
  details.open = true;
  fireEvent(details, new Event('toggle'));
}

test('warns with the counts per channel and the bot approval before the dry run', async () => {
  serve();
  await renderOpen();
  expect(await screen.findByText('Staff who opted in: wiki-mail 2, talk page 1.')).toBeTruthy();
  expect(screen.getByText('The bot is not approved for automatic sends on nl.wikipedia.org.')).toBeTruthy();
  expect(screen.getAllByRole('option').map((o) => o.textContent))
    .toEqual(['Phase opened', 'Phase closing soon', 'Results']);
  expect(screen.queryByRole('table')).toBeNull();
});

test('runs the chosen message and lists each person and channel with what would happen', async () => {
  const seen = serve();
  await renderOpen();
  fireEvent.change(await screen.findByRole('combobox', {name: 'Message'}), {target: {value: 'results'}});
  fireEvent.click(screen.getByRole('button', {name: 'Dry run'}));
  const table = await screen.findByRole('table');
  expect(seen).toEqual([{reminderType: 'results'}]);
  const rows = within(table).getAllByRole('row').slice(1).map((row) =>
    within(row).getAllByRole('cell').map((cell) => cell.textContent));
  expect(rows).toEqual([
    ['Organizer', 'Wiki-mail', 'Would send'],
    ['Organizer', 'Talk page', 'Held back: daily limit'],
    ['Moderator', 'Wiki-mail', 'Not sent: the talk page asks bots not to post there.'],
    ['Site admin', 'Wiki-mail', 'Combined with another reminder'],
  ]);
});

test('offers no button when no staff member joined and ticked a channel', async () => {
  serve();
  await renderOpen({...state, counts: {email: 0, talk: 0}});
  expect(await screen.findByText('No staff member joined and ticked a channel.')).toBeTruthy();
  expect(screen.queryByRole('button', {name: 'Dry run'})).toBeNull();
});

test('says so when no message is due', async () => {
  serve();
  await renderOpen({...state, reminderTypes: []});
  expect(await screen.findByText('No reminder is due for this consultation now.')).toBeTruthy();
  expect(screen.queryByRole('button', {name: 'Dry run'})).toBeNull();
});

test('the fold and the button have different names, and the button points at the warning', async () => {
  serve();
  await renderOpen();
  const button = await screen.findByRole('button', {name: 'Dry run'});
  expect(screen.getByText('Staff dry run', {selector: 'summary'})).toBeTruthy();
  expect(button.getAttribute('aria-describedby')).toBeTruthy();
  expect(document.getElementById(button.getAttribute('aria-describedby')!)?.textContent)
    .toContain('Staff who opted in: wiki-mail 2, talk page 1.');
});

test('keeps each message type\'s result while another type is chosen', async () => {
  serve();
  await renderOpen();
  fireEvent.click(await screen.findByRole('button', {name: 'Dry run'}));
  expect(await screen.findByRole('table', {name: 'Phase opened'})).toBeTruthy();
  const select = screen.getByRole('combobox', {name: 'Message'});
  fireEvent.change(select, {target: {value: 'phase_closing'}});
  expect(screen.queryByRole('table')).toBeNull();
  fireEvent.change(select, {target: {value: 'phase_opened'}});
  expect(screen.getByRole('table', {name: 'Phase opened'})).toBeTruthy();
});

test.each([
  ['reminder_exists', 'Not run: this message was already recorded for this consultation today. Try again tomorrow (UTC).'],
  ['batch_busy', 'Not run: another reminder run is in progress. Try again in a few minutes.'],
  ['unknown_wiki', "Not run: the bot does not know this consultation's wiki."],
  ['not_due', 'No reminder is due for this consultation now.'],
  ['no_recipients', 'No staff member joined and ticked a channel.'],
  ['reminders_paused', 'Not run: reminders are paused on the server.'],
])('a %s refusal is shown in the console\'s words', async (code, text) => {
  serve(() => HttpResponse.json({error: {code, message: 'server text'}}, {status: 409}));
  await renderOpen();
  fireEvent.click(await screen.findByRole('button', {name: 'Dry run'}));
  expect(await screen.findByText(text)).toBeTruthy();
});
