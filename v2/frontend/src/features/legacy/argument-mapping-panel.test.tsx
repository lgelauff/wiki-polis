import {QueryClientProvider} from '@tanstack/react-query';
import {fireEvent, render, screen, within} from '@testing-library/react';
import {http, HttpResponse} from 'msw';
import {MemoryRouter} from 'react-router-dom';
import {expect, test} from 'vitest';

import type {components} from '../../api/schema';
import {App} from '../../app';
import {ARGUMENT_MAX_CHARACTERS} from './argument-mapping-panel';
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
 *    argument the reader wrote and picked, one hidden by a moderator); its against side has
 *    no arguments yet, and prioritising there unlocks only with more than its budget of 1.
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

/** Every statement finished, as the server reports it once progress is all done. */
function doneMapping(): Mapping {
  const data = mapping({progress: {completed: 3, total: 3, allDone: true, currentFeaturedStatementId: null}});
  data.featuredStatements = data.featuredStatements.map((card) => ({
    ...card, contributionsComplete: true, complete: true,
    sides: {pro: side('skipped', {complete: true}), con: side('skipped', {complete: true})},
  }));
  return data;
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
  serve(doneMapping());
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
  // the words, which would announce "1 1 person marked this as most important".
  const own = screen.getByText(BODIES[0]!).closest('.at-card')!;
  const other = screen.getByText(BODIES[1]!).closest('.at-card')!;
  expect(own.querySelector('.argument-importance .sr-only')?.textContent).toBe('1 person marked this as most important');
  expect(other.querySelector('.argument-importance .sr-only')?.textContent).toBe('3 people marked this as most important');
  expect(own.querySelector('.importance-count')).toHaveAttribute('aria-hidden', 'true');
});

test("each side names its own threshold, and the step lines show each statement's own progress", async () => {
  serve(forSideLocked());
  renderPanel();
  await screen.findByText(STATEMENTS[0]!);

  // Catches the per-side notes being swapped, a threshold of 1 taking the plural, the four
  // step-2 numbers reaching the wrong placeholders, and a step-1 line that ignores which
  // side was handled.
  expect(document.getElementById('volnote-pro-8')?.textContent).toBe('You can mark the most important once there are more than 2 arguments in favour (2 so far).');
  expect(document.getElementById('volnote-con-8')?.textContent).toBe('You can mark the most important once there are more than 1 argument against (0 so far).');
  expect(document.getElementById('step2-sub-8')?.textContent)
    .toBe('You marked 1 of 2 in favour and 0 of 1 against. You can still change these.');
  expect(document.getElementById('step1-sub-8')?.textContent).toBe('in favour ✓ · against ✓');
  expect(document.getElementById('step1-sub-9')?.textContent).toBe('in favour ✓ · against');
});

test('progress circles and flag icons have readable names', async () => {
  serve(mapping());
  renderPanel();
  await screen.findByText(STATEMENTS[0]!);

  // Catches a circle naming the wrong state (qqx cannot see this: the state is the choice of
  // message, not a parameter), and an internal id leaking into a flag's name.
  const circles = within(document.getElementById('fs-8')!).getByRole('group', {name: 'Statement progress'});
  expect(within(circles).getAllByRole('button').map((circle) => circle.getAttribute('aria-label')))
    .toEqual(['Statement 1: in progress', 'Statement 2: arguments still to add', 'Statement 3: complete']);
  const first = document.getElementById('fs-8')!;
  expect(first.querySelector('.content-flag--corner summary')).toHaveAttribute('aria-label', 'Flag this statement for moderator review');
  expect(screen.getByText(BODIES[1]!).closest('.at-card')!.querySelector('summary')).toHaveAttribute('aria-label', 'Flag this argument for moderator review');
});

test('the argument box names the character limit it enforces', async () => {
  serve(mapping());
  renderAsQqx();
  renderPanel();
  await screen.findByText(STATEMENTS[0]!);

  // Catches the limit written into the placeholder text, or not passed to it: qqx then shows
  // no value, and every translation would keep the number after the limit changes.
  for (const [side, key] of [['pro', 'conv-arg-placeholder-for'], ['con', 'conv-arg-placeholder-against']] as const) {
    const box = document.querySelector<HTMLTextAreaElement>(`#fs-9 .contribute-wrapper[data-side="${side}"] textarea`)!;
    expect(box).toHaveAttribute('placeholder', `(${key}: ${ARGUMENT_MAX_CHARACTERS})`);
    expect(box.maxLength).toBe(ARGUMENT_MAX_CHARACTERS);
  }
});

test('each progress circle is a button that names its state and marks the shown statement', async () => {
  serve(mapping());
  renderPanel();
  await screen.findByText(STATEMENTS[0]!);

  // Catches a circle that is an image with a click handler (no keyboard, announced as a
  // picture), the drawing read out on top of the name, and the shown statement not marked.
  const circles = within(within(document.getElementById('fs-8')!).getByRole('group', {name: 'Statement progress'})).getAllByRole('button');
  expect(circles).toHaveLength(3);
  for (const circle of circles) {
    expect(circle.tagName).toBe('BUTTON');
    expect(circle).toHaveAttribute('type', 'button');
    expect(circle).not.toHaveAttribute('tabindex');
    expect(circle.querySelector('svg')).toHaveAttribute('aria-hidden', 'true');
  }
  expect(circles.map((circle) => circle.getAttribute('aria-current'))).toEqual(['step', null, null]);

  fireEvent.click(circles[1]!);
  expect(document.getElementById('fs-9')).not.toHaveClass('arg-block--hidden');
  expect(document.getElementById('fs-8')).toHaveClass('arg-block--hidden');
  const shown = within(within(document.getElementById('fs-9')!).getByRole('group', {name: 'Statement progress'})).getAllByRole('button');
  expect(shown.map((circle) => circle.getAttribute('aria-current'))).toEqual([null, 'step', null]);
});

/** The colour tokens the circles paint with, as style.css's :root defines them. jsdom applies
 *  no stylesheet and vite will not serve style.css as text to the tests, so they are copied;
 *  v2/tests/test_argument_controls_css.py checks the copy still matches style.css. */
const TOKENS: Record<string, string> = {
  '--ink': '#0c0c0e', '--surface': '#ffffff', '--pass': '#3d6dba', '--spot': '#b45309', '--blue-dark': '#2a4f8a',
};

function resolve(paint: string | null): string {
  if (!paint) throw new Error('no paint');
  const variable = /^var\((--[\w-]+)/.exec(paint)?.[1];
  const value = variable ? TOKENS[variable] : paint;
  if (!value) throw new Error(`no token for ${paint}`);
  return value;
}

function contrast(first: string, second: string): number {
  const luminance = (hex: string) => {
    const [r, g, b] = [1, 3, 5].map((at) => {
      const channel = parseInt(hex.slice(at, at + 2), 16) / 255;
      return channel <= 0.03928 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
    });
    return 0.2126 * r! + 0.7152 * g! + 0.0722 * b!;
  };
  const [light, dark] = [luminance(first), luminance(second)].sort((a, b) => b - a);
  return (light! + 0.05) / (dark! + 0.05);
}

test('the number in each progress circle meets text contrast against what is behind it', async () => {
  serve(mapping());
  renderPanel();
  await screen.findByText(STATEMENTS[0]!);

  // Catches the number on a filled circle drawn in a colour close to the fill (it was
  // --blue-dark on --spot, 1.6:1). Statement 1 is half filled, 2 empty, 3 filled. On the
  // half fill the number straddles both colours, so it needs a halo it can stand on.
  const circles = document.querySelectorAll('#fs-8 .at-circles .at-circle');
  for (const circle of circles) {
    const text = circle.querySelector('text')!;
    const half = circle.querySelector('path') !== null;
    const backing = half ? text.getAttribute('stroke') : circle.querySelector('circle')!.getAttribute('fill');
    expect(contrast(resolve(text.getAttribute('fill')), resolve(backing))).toBeGreaterThanOrEqual(4.5);
    if (half) {
      // The halo is drawn under the number and wide enough to stand on.
      expect(text).toHaveAttribute('paint-order', 'stroke');
      expect(Number(text.getAttribute('stroke-width'))).toBeGreaterThanOrEqual(2);
    }
  }
});
