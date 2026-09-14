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

const STATEMENTS = ['Our movement should invest more in shared technical infrastructure.', 'Small wikis should get translation support first.', 'Every tool should publish its source code.'];
const BODIES = ['Shared maintenance reduces duplicated work.', 'Pooled hosting lowers costs for everyone.', 'An argument a moderator hid.'];
const CONTENT = [...STATEMENTS, ...BODIES];

function item(id: number, body: string, overrides: Partial<Item> = {}): Item {
  return {id, body, own: false, selected: false, hidden: false, importanceVoteCount: 0,
    capabilities: {prioritize: true, flag: true, moderate: false}, ...overrides};
}

function side(status: 'pending' | 'submitted' | 'skipped', prioritization: Partial<Featured['sides']['pro']['prioritization']> = {}, items: Item[] = []): Featured['sides']['pro'] {
  return {
    contribution: {status, argumentId: status === 'submitted' ? 90 : null, capabilities: {submit: status !== 'submitted', skip: status === 'pending'}},
    prioritization: {available: false, requiredArgumentCount: 3, argumentCount: items.length, selectionBudget: 2, selectedCount: 0, complete: false, ...prioritization},
    arguments: items,
  };
}

/** Three statements, one per state a statement can be in:
 *  - Statement 1: both sides handled, not finished. Its for side can be prioritised (one
 *    argument the reader wrote and picked, one hidden by a moderator); its against side is
 *    one argument short of an unlock threshold of 1.
 *  - Statement 2: only the for side handled.
 *  - Statement 3: complete.
 *  The for side's budget (2) and the against side's (1) differ, so the four step-2 numbers
 *  are all distinguishable. */
function mapping(overrides: Partial<Mapping> = {}): Mapping {
  const first: Featured = {
    id: 8, statement: {id: 12, text: STATEMENTS[0]!}, contributionsComplete: true, complete: false,
    sides: {
      pro: side('submitted', {available: true, requiredArgumentCount: 3, selectedCount: 1}, [
        item(91, BODIES[0]!, {own: true, selected: true, importanceVoteCount: 1}),
        item(92, BODIES[1]!, {importanceVoteCount: 3, capabilities: {prioritize: true, flag: true, moderate: true}}),
        item(93, BODIES[2]!, {hidden: true, capabilities: {prioritize: false, flag: false, moderate: true}}),
      ]),
      con: side('skipped', {requiredArgumentCount: 2, selectionBudget: 1}),
    },
    capabilities: {flagStatement: true},
  };
  const second: Featured = {
    id: 9, statement: {id: 13, text: STATEMENTS[1]!}, contributionsComplete: false, complete: false,
    sides: {pro: side('skipped'), con: side('pending')},
    capabilities: {flagStatement: true},
  };
  const third: Featured = {
    id: 10, statement: {id: 14, text: STATEMENTS[2]!}, contributionsComplete: true, complete: true,
    sides: {pro: side('skipped', {complete: true}), con: side('skipped', {complete: true})},
    capabilities: {flagStatement: true},
  };
  return {
    conversationId: 7, slug: 'community-strategy', title: 'Community strategy', pseudonym: 'quiet-otter',
    progress: {completed: 1, total: 3, allDone: false, currentFeaturedStatementId: 8},
    featuredStatements: [first, second, third],
    capabilities: {contribute: true, prioritize: true, flag: true, moderate: true},
    links: {self: '/api/v1/conversations/community-strategy/arguments', about: '/c/community-strategy/about', conversation: '/c/community-strategy'},
    ...overrides,
  };
}

/** Statement 1's for side below its threshold too (two arguments of three needed). */
function forSideLocked(): Mapping {
  const data = mapping();
  const pro = data.featuredStatements[0]!.sides.pro;
  pro.arguments = pro.arguments.slice(0, 2).map((argument) => ({...argument, capabilities: {...argument.capabilities, prioritize: false}}));
  pro.prioritization = {...pro.prioritization, available: false, argumentCount: 2};
  return data;
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

test('under qqx, the arguments tab carries no English but participant content', async () => {
  serve(mapping());
  renderAsQqx();
  renderPanel();
  await screen.findByText(STATEMENTS[0]!);

  // Catches a hardcoded string, or English passed into a message, in what this fixture
  // renders: all three statement states (the two hidden panels included), the composer
  // states CSS switches between, the hidden-argument badge and moderator buttons, the
  // against side's threshold note, the circles, and every aria-label.
  expect(untranslatedCopy([panel()], CONTENT)).toEqual([]);
  // The orientation toggle's second label.
  fireEvent.click(within(panel()!).getByRole('button', {name: /\(conv-orient-collapse\)/}));
  expect(untranslatedCopy([panel()], CONTENT)).toEqual([]);

  // The flag form's placeholder for the "other" reason, and its thanks once sent.
  const flag = document.querySelector<HTMLDetailsElement>('#fs-8 .content-flag--corner')!;
  flag.open = true;
  fireEvent.change(within(flag).getByRole('combobox'), {target: {value: 'other'}});
  expect(untranslatedCopy([panel()], CONTENT)).toEqual([]);
  fireEvent.change(within(flag).getByRole('textbox'), {target: {value: 'Needs a look.'}});
  fireEvent.submit(flag.querySelector('form')!);
  expect(await within(flag).findByText('(conv-flag-thanks)')).toBeInTheDocument();
  expect(untranslatedCopy([panel()], [...CONTENT, 'Needs a look.'])).toEqual([]);
});

test("under qqx, the for side's threshold note and the finished tab carry no English", async () => {
  serve(forSideLocked());
  renderAsQqx();
  const {unmount} = renderPanel();
  await screen.findByText(STATEMENTS[0]!);
  expect(document.getElementById('volnote-pro-8')).not.toBeNull();
  expect(untranslatedCopy([panel()], CONTENT)).toEqual([]);
  unmount();

  // Once every statement is done, each panel header becomes a toggle with an expand and a
  // collapse name.
  serve(mapping({progress: {completed: 3, total: 3, allDone: true, currentFeaturedStatementId: null}}));
  renderPanel();
  await screen.findByText(STATEMENTS[0]!);
  expect(untranslatedCopy([panel()], CONTENT)).toEqual([]);
  fireEvent.click(document.querySelector('#fs-8 .at-head')!);
  expect(document.querySelector('#fs-8 .at-head')).toHaveAttribute('aria-label', '(conv-arg-panel-collapse-aria)');
  expect(untranslatedCopy([panel()], CONTENT)).toEqual([]);
});

test('under qqx, the empty tab and a failed save carry no English', async () => {
  serve(mapping({featuredStatements: []}));
  renderAsQqx();
  const {unmount} = renderPanel();
  expect(await screen.findByText('(conv-arg-none)')).toBeVisible();
  expect(untranslatedCopy([panel()], CONTENT)).toEqual([]);
  unmount();

  serve(mapping());
  server.use(http.put(url('/api/v1/conversations/community-strategy/featured-statements/:id/contributions/:side/skip'),
    () => HttpResponse.json({error: {code: 'upstream_unavailable', message: 'The voting service is down.'}}, {status: 502})));
  renderPanel();
  await screen.findByText(STATEMENTS[0]!);
  // Statement 2's against side is the one still pending, so its "Nothing to add" is live.
  fireEvent.click(document.querySelector('#fs-9 .contribute-wrapper[data-side="con"] .contribute-direct-skip')!);
  expect(await screen.findByText('(conv-arg-save-error)')).toBeInTheDocument();
  expect(untranslatedCopy([panel()], CONTENT)).toEqual([]);
});

test('importance counts are announced with the right plural, and the number is hidden from screen readers', async () => {
  serve(mapping());
  renderPanel();
  await screen.findByText(STATEMENTS[0]!);

  // Catches the plural ignoring the count, and the visual number being read out as well as
  // the words, which would announce "1 1 importance vote".
  const own = screen.getByText(BODIES[0]!).closest('.at-card')!;
  const other = screen.getByText(BODIES[1]!).closest('.at-card')!;
  expect(own.querySelector('.argument-importance .sr-only')?.textContent).toBe('1 importance vote');
  expect(other.querySelector('.argument-importance .sr-only')?.textContent).toBe('3 importance votes');
  expect(own.querySelector('.importance-count')).toHaveAttribute('aria-hidden', 'true');
});

test("each side names its own threshold, and the step lines show each statement's own progress", async () => {
  serve(forSideLocked());
  renderPanel();
  await screen.findByText(STATEMENTS[0]!);

  // Catches the per-side notes being swapped, a threshold of 1 taking the plural, the four
  // step-2 numbers reaching the wrong placeholders, and a step-1 line that ignores which
  // side was handled.
  expect(document.getElementById('volnote-pro-8')?.textContent).toBe('Prioritising unlocks once there are more than 2 for-arguments (2 so far).');
  expect(document.getElementById('volnote-con-8')?.textContent).toBe('Prioritising unlocks once there are more than 1 against-argument (0 so far).');
  expect(document.getElementById('step2-sub-8')?.textContent)
    .toBe('Mark the most important — 1 of 2 for, 0 of 1 against · you can still change these');
  expect(document.getElementById('step1-sub-8')?.textContent).toBe('for ✓ · against ✓');
  expect(document.getElementById('step1-sub-9')?.textContent).toBe('for ✓ · against');
});

test('progress circles and flag icons have readable names', async () => {
  serve(mapping());
  renderPanel();
  await screen.findByText(STATEMENTS[0]!);

  // Catches a circle naming the wrong state (qqx cannot see this: the state is the choice of
  // message, not a parameter), and an internal id leaking into a flag's name.
  const circles = within(document.getElementById('fs-8')!).getByRole('group', {name: 'Statement progress'});
  expect(within(circles).getAllByRole('img').map((circle) => circle.getAttribute('aria-label')))
    .toEqual(['Statement 1: in progress', 'Statement 2: not started', 'Statement 3: complete']);
  const first = document.getElementById('fs-8')!;
  expect(first.querySelector('.content-flag--corner summary')).toHaveAttribute('aria-label', 'Flag this statement for moderator review');
  expect(screen.getByText(BODIES[1]!).closest('.at-card')!.querySelector('summary')).toHaveAttribute('aria-label', 'Flag this argument for moderator review');
});
