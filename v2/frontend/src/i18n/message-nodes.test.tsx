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

test('a qqx message, which drops its parameters, renders as the bare key', () => {
  const {container} = render(<p>{withNodes('(conv-p6-done-see)', <a href="/x">link</a>)}</p>);
  expect(container.textContent).toBe('(conv-p6-done-see)');
});
