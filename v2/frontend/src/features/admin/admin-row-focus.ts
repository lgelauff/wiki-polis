import {useEffect, useRef} from 'react';

/** Where focus goes when an action takes a row off a list.
 *
 *  The button that was pressed leaves the page with its row, and focus would fall back to the
 *  document. It goes to the next row's first action instead (the previous row's when the last
 *  row went), or to the list's empty-state line when nothing is left, so a keyboard or screen
 *  reader user carries on where they were. `ids` is the list as shown; the page calls
 *  `rowRemoved` when an action succeeds, and focus moves once the row is off the screen. */
export function useRowFocus(ids: number[]) {
  const listRef = useRef<HTMLUListElement>(null);
  const emptyRef = useRef<HTMLParagraphElement>(null);
  const shown = useRef(ids);
  const pending = useRef<{removed: number; next: number | null} | null>(null);

  useEffect(() => {
    shown.current = ids;
    const target = pending.current;
    if (!target || ids.includes(target.removed)) return;
    pending.current = null;
    const next = target.next === null ? null : listRef.current?.querySelector<HTMLElement>(
      `[data-row-id="${target.next}"] button:not(:disabled)`,
    );
    (next ?? emptyRef.current)?.focus();
  });

  function rowRemoved(removed: number) {
    const index = shown.current.indexOf(removed);
    if (index < 0) return;
    const rest = shown.current.filter((id) => id !== removed);
    pending.current = {removed, next: rest[index] ?? rest[index - 1] ?? null};
  }

  return {listRef, emptyRef, rowRemoved};
}
