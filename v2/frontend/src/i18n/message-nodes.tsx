import {Fragment, type ReactNode} from 'react';

/** A sentence whose parameter is an element — a router link, a bolded pseudonym — has to
 *  stay one message, or a translator cannot move the element within it. `richHtml` covers
 *  the cases that can be plain HTML; it cannot carry a React `onClick` or a router link.
 *
 *  Pass `nodeSlot(n)` as the nth parameter, then hand the resolved text to `withNodes`:
 *
 *    withNodes(msg('conv-p6-done-see', nodeSlot(0)), <InternalLink …>…</InternalLink>)
 *
 *  The call stays a literal message call with its key inline, so the key-existence guard in
 *  `tests/test_i18n.py` still sees it. */
const MARK = '\u2063';   // INVISIBLE SEPARATOR: never typed into a message, survives banana.

export function nodeSlot(index: number): string {
  return `${MARK}${index}${MARK}`;
}

export function withNodes(text: string, ...nodes: ReactNode[]): ReactNode {
  const parts = text.split(new RegExp(`${MARK}(\\d+)${MARK}`));
  // split() with a capture group alternates text, index, text, index, …
  return parts.map((part, position) => (
    position % 2 === 0
      ? (part ? <Fragment key={position}>{part}</Fragment> : null)
      : <Fragment key={position}>{nodes[Number(part)]}</Fragment>
  ));
}
