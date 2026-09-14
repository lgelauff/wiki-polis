import {QueryClientProvider} from '@tanstack/react-query';
import {fireEvent, render, screen, within} from '@testing-library/react';
import {http, HttpResponse} from 'msw';
import {MemoryRouter} from 'react-router-dom';
import {expect, test} from 'vitest';

import type {components} from '../../api/schema';
import {App} from '../../app';
import {createQueryClient} from '../../query-client';
import {renderAsQqx, untranslatedCopy} from '../../test/i18n';
import {server} from '../../test/server';

type Mapping = components['schemas']['ArgumentMapping'];
type Featured = components['schemas']['ArgumentFeaturedStatement'];
type Item = components['schemas']['ArgumentItem'];

const url = (path: string) => new URL(path, globalThis.location.origin).toString();

const STATEMENTS = ['Our movement should invest more in shared technical infrastructure.', 'Small wikis should get translation support first.'];
const BODIES = ['Shared maintenance reduces duplicated work.', 'Pooled hosting lowers costs for everyone.', 'An argument a moderator hid.'];
const CONTENT = [...STATEMENTS, ...BODIES];

function item(id: number, body: string, overrides: Partial<Item> = {}): Item {
  return {id, body, own: false, selected: false, hidden: false, importanceVoteCount: 0,
    capabilities: {prioritize: true, flag: true, moderate: false}, ...overrides};
}

/** Statement 1 has both sides handled: for-arguments to prioritise (one the reader wrote and
 *  picked, one hidden by a moderator), and an against side still short of the unlock
 *  threshold. Statement 2 is untouched. Together they reach every state the panel draws. */
function mapping(overrides: Partial<Mapping> = {}): Mapping {
  const first: Featured = {
    id: 8, statement: {id: 12, text: STATEMENTS[0]!}, contributionsComplete: true, complete: true,
    sides: {
      pro: {
        contribution: {status: 'submitted', argumentId: 91, capabilities: {submit: false, skip: false}},
        prioritization: {available: true, requiredArgumentCount: 2, argumentCount: 3, selectionBudget: 2, selectedCount: 1, complete: false},
        arguments: [
          item(91, BODIES[0]!, {own: true, selected: true, importanceVoteCount: 1}),
          item(92, BODIES[1]!, {importanceVoteCount: 3, capabilities: {prioritize: true, flag: true, moderate: true}}),
          item(93, BODIES[2]!, {hidden: true, capabilities: {prioritize: false, flag: false, moderate: true}}),
        ],
      },
      con: {
        contribution: {status: 'skipped', argumentId: null, capabilities: {submit: true, skip: false}},
        prioritization: {available: false, requiredArgumentCount: 3, argumentCount: 0, selectionBudget: 2, selectedCount: 0, complete: false},
        arguments: [],
      },
    },
    capabilities: {flagStatement: true},
  };
  const second: Featured = {
    id: 9, statement: {id: 13, text: STATEMENTS[1]!}, contributionsComplete: false, complete: false,
    sides: {
      pro: {contribution: {status: 'pending', argumentId: null, capabilities: {submit: true, skip: true}},
        prioritization: {available: false, requiredArgumentCount: 3, argumentCount: 0, selectionBudget: 2, selectedCount: 0, complete: false}, arguments: []},
      con: {contribution: {status: 'pending', argumentId: null, capabilities: {submit: true, skip: true}},
        prioritization: {available: false, requiredArgumentCount: 3, argumentCount: 0, selectionBudget: 2, selectedCount: 0, complete: false}, arguments: []},
    },
    capabilities: {flagStatement: true},
  };
  return {
    conversationId: 7, slug: 'community-strategy', title: 'Community strategy', pseudonym: 'quiet-otter',
    progress: {completed: 1, total: 2, allDone: true, currentFeaturedStatementId: 8},
    featuredStatements: [first, second],
    capabilities: {contribute: true, prioritize: true, flag: true, moderate: true},
    links: {self: '/api/v1/conversations/community-strategy/arguments', about: '/c/community-strategy/about', conversation: '/c/community-strategy'},
    ...overrides,
  };
}

function serve(data: Mapping) {
  server.use(http.get(url('/api/v1/conversations/community-strategy/arguments'), () => HttpResponse.json({data})));
}

function renderPanel() {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={['/app/conversations/community-strategy/arguments']}><App /></MemoryRouter>
    </QueryClientProvider>,
  );
}

const panel = () => document.getElementById('tab-arguments');

test('under qqx, every state of the arguments tab carries no English but participant content', async () => {
  serve(mapping());
  renderAsQqx();
  renderPanel();
  await screen.findByText(STATEMENTS[0]!);

  // Catches a string left hardcoded in any state the fixture reaches, including the ones
  // behind `hidden`, CSS-switched composer states, the flag form, and aria-labels.
  expect(untranslatedCopy([panel()], CONTENT)).toEqual([]);
  // The orientation toggle has two labels; reach the second one too.
  fireEvent.click(within(panel()!).getByRole('button', {name: /\(conv-orient-collapse\)/}));
  expect(untranslatedCopy([panel()], CONTENT)).toEqual([]);

  // The flag form swaps its placeholder for the "other" reason, and thanks the reporter once
  // sent; both only render after interaction.
  const flag = document.querySelector<HTMLDetailsElement>('#fs-8 .content-flag--corner')!;
  flag.open = true;
  fireEvent.change(within(flag).getByRole('combobox'), {target: {value: 'other'}});
  expect(untranslatedCopy([panel()], CONTENT)).toEqual([]);
  fireEvent.change(within(flag).getByRole('textbox'), {target: {value: 'Needs a look.'}});
  fireEvent.submit(flag.querySelector('form')!);
  expect(await within(flag).findByText('(conv-flag-thanks)')).toBeInTheDocument();
  expect(untranslatedCopy([panel()], [...CONTENT, 'Needs a look.'])).toEqual([]);
});

test('under qqx, the empty tab and a failed save carry no English', async () => {
  serve(mapping({featuredStatements: []}));
  renderAsQqx();
  const {unmount} = renderPanel();
  expect(await screen.findByText('(conv-arg-none)')).toBeVisible();
  expect(untranslatedCopy([panel()], CONTENT)).toEqual([]);
  unmount();

  serve(mapping({progress: {completed: 0, total: 2, allDone: false, currentFeaturedStatementId: 9}}));
  server.use(http.put(url('/api/v1/conversations/community-strategy/featured-statements/:id/contributions/:side/skip'),
    () => HttpResponse.json({error: {code: 'upstream_unavailable', message: 'The voting service is down.'}}, {status: 502})));
  renderPanel();
  await screen.findByText(STATEMENTS[0]!);
  fireEvent.click(screen.getAllByRole('button', {name: '(conv-arg-nothing)'})[0]!);
  expect(await screen.findByText('(conv-arg-save-error)')).toBeInTheDocument();
  expect(untranslatedCopy([panel()], CONTENT)).toEqual([]);
});

test('importance counts are announced with the right plural', async () => {
  serve(mapping());
  renderPanel();
  await screen.findByText(STATEMENTS[0]!);

  // Catches the count and its noun drifting apart: the number is visual, the words are
  // screen-reader only, and a wrong plural form reads "1 importance votes".
  const own = screen.getByText(BODIES[0]!).closest('.at-card')!;
  const other = screen.getByText(BODIES[1]!).closest('.at-card')!;
  expect(own.querySelector('.argument-importance .sr-only')?.textContent).toBe('1 importance vote');
  expect(other.querySelector('.argument-importance .sr-only')?.textContent).toBe('3 importance votes');
});

test('each side names its own threshold note, and the step counts land in their slots', async () => {
  const data = mapping();
  // Both sides below their unlock threshold, so both notes render.
  data.featuredStatements[0]!.sides.pro.prioritization = {...data.featuredStatements[0]!.sides.pro.prioritization, available: false};
  serve(data);
  renderPanel();
  await screen.findByText(STATEMENTS[0]!);

  // Catches the per-side message being swapped, or the four step-2 numbers reaching the
  // wrong placeholders: the English would still read naturally with the numbers misplaced.
  const first = document.getElementById('fs-8')!;
  expect(first.querySelector('#volnote-pro-8')?.textContent).toBe('Prioritising unlocks once there are more than 2 for-arguments (3 so far).');
  expect(first.querySelector('#volnote-con-8')?.textContent).toBe('Prioritising unlocks once there are more than 2 against-arguments (0 so far).');
  expect(first.querySelector('#step2-sub-8')?.textContent)
    .toBe('Mark the most important — 1 of 2 for, 0 of 2 against · you can still change these');
  expect(first.querySelector('#step1-sub-8')?.textContent).toBe('for ✓ · against ✓');
  expect(document.querySelector('#step1-sub-9')?.textContent).toBe('for · against');
});

test('progress circles and flag icons have readable names', async () => {
  serve(mapping());
  renderPanel();
  await screen.findByText(STATEMENTS[0]!);

  // Catches the state identifier ("none", "half") reaching a screen reader instead of words,
  // and an internal id leaking into the flag's name ("Flag statement-8 for …").
  const circles = within(document.getElementById('fs-8')!).getByRole('group', {name: 'Statement progress'});
  expect(within(circles).getByRole('img', {name: 'Statement 1: complete'})).toBeInTheDocument();
  expect(within(circles).getByRole('img', {name: 'Statement 2: not started'})).toBeInTheDocument();
  const first = document.getElementById('fs-8')!;
  expect(first.querySelector('.content-flag--corner summary')).toHaveAttribute('aria-label', 'Flag this statement for moderator review');
  expect(screen.getByText(BODIES[1]!).closest('.at-card')!.querySelector('summary')).toHaveAttribute('aria-label', 'Flag this argument for moderator review');
});
