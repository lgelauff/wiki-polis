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

/** An element whose slot the text does not contain — a translation that dropped `$1`, or a
 *  catalogue that failed to load — is appended after the text rather than lost, because the
 *  element is often the link or the name the sentence exists to show. */
export function withNodes(text: string, ...nodes: ReactNode[]): ReactNode {
  const parts = text.split(new RegExp(`${MARK}(\\d+)${MARK}`));
  const placed = new Set<number>();
  // split() with a capture group alternates text, index, text, index, …
  const rendered = parts.map((part, position) => {
    if (position % 2 === 0) return part ? <Fragment key={position}>{part}</Fragment> : null;
    placed.add(Number(part));
    return <Fragment key={position}>{nodes[Number(part)]}</Fragment>;
  });
  const missing = nodes.map((node, index) => (placed.has(index) ? null : <Fragment key={`missing-${index}`}> {node}</Fragment>));
  return [...rendered, ...missing];
}
