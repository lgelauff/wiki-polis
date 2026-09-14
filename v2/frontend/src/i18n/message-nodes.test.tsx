import Banana from 'banana-i18n';
import {render} from '@testing-library/react';
import {expect, test} from 'vitest';

import {nodeSlot, withNodes} from './message-nodes';

test('an element parameter lands where the translation puts it, through banana', () => {
  // Word order is the point: the Dutch-like message moves the link to the end.
  const banana = new Banana('nl', {messages: {nl: {k: 'Zie voor de volledige vergelijking $1.'}}});
  const {container} = render(<p>{withNodes(banana.i18n('k', nodeSlot(0)), <a href="/x">het tabblad</a>)}</p>);
  expect(container.textContent).toBe('Zie voor de volledige vergelijking het tabblad.');
  expect(container.querySelector('a')?.textContent).toBe('het tabblad');
});

test('two element parameters keep their own identities when reordered', () => {
  const banana = new Banana('en', {messages: {en: {k: '$2 before $1'}}});
  const {container} = render(<p>{withNodes(banana.i18n('k', nodeSlot(0), nodeSlot(1)), <b>one</b>, <i>two</i>)}</p>);
  expect(container.innerHTML).toBe('<p><i>two</i> before <b>one</b></p>');
});

test('a qqx message shows its element parameter inside the parentheses', () => {
  // qqx renders (key: $1), so the element is substituted like any other parameter.
  const banana = new Banana('qqx', {messages: {qqx: {k: '(conv-p6-done-see: $1)'}}});
  const {container} = render(<p>{withNodes(banana.i18n('k', nodeSlot(0)), <a href="/x">link</a>)}</p>);
  expect(container.textContent).toBe('(conv-p6-done-see: link)');
});

test('an element whose slot the text lacks is appended, not dropped', () => {
  // Catches a translation that omitted $1, or a missing catalogue returning the bare key,
  // silently removing the link or name the sentence is there to show.
  const {container} = render(<p>{withNodes('conv-p6-done-see', <a href="/x">link</a>)}</p>);
  expect(container.querySelector('a')?.textContent).toBe('link');
  expect(container.textContent).toBe('conv-p6-done-see link');
});
