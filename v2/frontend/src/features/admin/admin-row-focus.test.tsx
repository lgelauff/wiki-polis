import {useState} from 'react';
import {fireEvent, render, screen} from '@testing-library/react';
import {expect, test} from 'vitest';

import {useRowFocus} from './admin-row-focus';

/** pr-check #540 accessibility-4: when the next row has no enabled button, only a line that
 *  takes focus (a handled flag's "Handled ✓", tabindex -1), focus goes to that line rather
 *  than dropping to the document. */

type Row = {id: number; settled: boolean};

function List({initial}: {initial: Row[]}) {
  const [rows, setRows] = useState(initial);
  const {listRef, emptyRef, rowRemoved} = useRowFocus(rows.map((row) => row.id));
  function removeFirst() {
    rowRemoved(rows[0]!.id);
    setRows(rows.slice(1));
  }
  return <>
    {/* Stands in for the action that succeeded; fireEvent does not move focus to it. */}
    <button type="button" onClick={removeFirst}>Remove first</button>
    {rows.length ? (
      <ul ref={listRef}>
        {rows.map((row) => (
          <li key={row.id} data-row-id={row.id}>
            {row.settled
              ? <p tabIndex={-1}>{`Handled ${row.id}`}</p>
              : <button type="button">{`Act ${row.id}`}</button>}
          </li>
        ))}
      </ul>
    ) : <p ref={emptyRef} tabIndex={-1}>Empty</p>}
  </>;
}

test('focus goes to the next row\'s button when it has one', () => {
  render(<List initial={[{id: 1, settled: false}, {id: 2, settled: false}]} />);
  screen.getByRole('button', {name: 'Act 1'}).focus();

  fireEvent.click(screen.getByRole('button', {name: 'Remove first'}));

  expect(screen.getByRole('button', {name: 'Act 2'})).toHaveFocus();
});

test('focus goes to the next row\'s focusable line when it has no enabled button', () => {
  render(<List initial={[{id: 1, settled: false}, {id: 2, settled: true}]} />);
  screen.getByRole('button', {name: 'Act 1'}).focus();

  fireEvent.click(screen.getByRole('button', {name: 'Remove first'}));

  expect(screen.getByText('Handled 2')).toHaveFocus();
  expect(document.activeElement).not.toBe(document.body);
});
