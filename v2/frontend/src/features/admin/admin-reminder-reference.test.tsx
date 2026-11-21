import {Suspense} from 'react';
import {QueryClientProvider} from '@tanstack/react-query';
import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import {http, HttpResponse} from 'msw';
import {expect, test} from 'vitest';

import type {components} from '../../api/schema';
import {AdminReminderReference} from './admin-reminder-reference';
import {MessageProvider} from '../../i18n/messages';
import {createQueryClient} from '../../query-client';
import {server} from '../../test/server';

type Result = components['schemas']['ReminderReferenceLookupResponse']['data'];

const URL_ = new URL('/api/v1/admin/reminder-reference-lookups', globalThis.location.origin).toString();
const NO_MATCH: Result = {match: false, kind: null, username: null, sendDay: null, items: []};

function serve(reply: (reference: string) => Result | Response, seen: {body: unknown; csrf: string | null}[] = []) {
  server.use(http.post(URL_, async ({request}) => {
    const body = await request.json() as {reference: string};
    seen.push({body, csrf: request.headers.get('X-CSRFToken')});
    const answer = reply(body.reference);
    return answer instanceof Response ? answer : HttpResponse.json({data: answer});
  }));
  return seen;
}

async function renderSection() {
  const view = render(
    <QueryClientProvider client={createQueryClient()}>
      <Suspense fallback={null}>
        <MessageProvider locale="en"><AdminReminderReference csrfToken="test-csrf-token" /></MessageProvider>
      </Suspense>
    </QueryClientProvider>,
  );
  const heading = await screen.findByRole('heading', {name: 'Reference lookup', level: 2});
  const details = heading.closest('details')!;
  details.open = true;
  fireEvent(details, new Event('toggle'));
  return view;
}

function lookUp(text: string) {
  fireEvent.change(screen.getByRole('textbox'), {target: {value: text}});
  fireEvent.click(screen.getByRole('button'));
}

test('sends the pasted reference with the CSRF token and shows who and what it points to', async () => {
  const seen = serve(() => ({
    match: true, kind: 'reminder', username: 'Example user', sendDay: '2026-11-02',
    items: [
      {conversationId: 1, title: 'Library hours', reminderType: 'phase_opened'},
      {conversationId: 2, title: 'Park plan', reminderType: 'phase_closing'},
    ],
  }));
  await renderSection();
  lookUp('  Proto K7 ABCDEFGHI-JKLMNOPQR-STUVWXYZ  ');
  await screen.findByText(/Example user/);
  expect(seen).toEqual([{body: {reference: 'Proto K7 ABCDEFGHI-JKLMNOPQR-STUVWXYZ'}, csrf: 'test-csrf-token'}]);
  const rows = screen.getAllByRole('listitem').map((row) => row.textContent);
  expect(rows).toHaveLength(2);
  expect(rows[0]).toContain('Library hours');
  expect(rows[1]).toContain('Park plan');
});

test('an unlinked delivery and a test send show no username', async () => {
  const answers: Result[] = [
    {match: true, kind: 'reminder', username: null, sendDay: '2026-11-02',
      items: [{conversationId: 1, title: 'Library hours', reminderType: 'results'}]},
    {match: true, kind: 'test_send', username: null, sendDay: '2026-11-02', items: []},
  ];
  serve(() => answers.shift()!);
  const view = await renderSection();
  lookUp('first');
  await screen.findByRole('listitem');
  lookUp('second');
  await waitFor(() => expect(screen.queryByRole('listitem')).toBeNull());
  expect(view.container.textContent).not.toContain('null');
});

test('every reference without a match gets the same answer', async () => {
  serve(() => NO_MATCH);
  const view = await renderSection();
  const shown: string[] = [];
  for (const text of ['Proto K1 ABCDEFGHI-JKLMNOPQR-STUVWXYZ', 'Proto K2 altered', 'expired']) {
    lookUp(text);
    await waitFor(() => expect(view.container.querySelector('form > p:last-child')?.textContent)
      .not.toBe(''));
    await waitFor(() => expect(screen.queryByText('Loading…')).toBeNull());
    shown.push(view.container.querySelector('form > p:last-child')!.textContent!);
  }
  expect(new Set(shown).size).toBe(1);
  expect(screen.queryByRole('listitem')).toBeNull();
});

test('a refused lookup shows an error, not a result', async () => {
  serve(() => HttpResponse.json({error: {code: 'forbidden', message: 'No'}}, {status: 403}));
  const view = await renderSection();
  lookUp('Proto K1 ABCDEFGHI-JKLMNOPQR-STUVWXYZ');
  await waitFor(() => expect(view.container.querySelector('.admin-error')).not.toBeNull());
  expect(screen.queryByRole('listitem')).toBeNull();
});
