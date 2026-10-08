import {useMutation} from '@tanstack/react-query';

import type {components} from '../../api/schema';
import {putAdminStatementModeration} from '../../api/queries';
import {useMessage} from '../../i18n/messages';

type Statement = components['schemas']['AdminStatement'];
type Status = Statement['moderation'];

/** The moderation buttons of one statement row, the same on Moderation › Queue and on
 *  Content › Statements: a check to approve and a cross to hide, each icon-only and named
 *  by its words (the accessible name and the tooltip), each disabled while the statement
 *  already is in that state.
 *
 *  `withUnmoderate` adds the third position, back to unmoderated, which Statements has
 *  always offered for an approved or hidden statement; the Queue does not. */
export function StatementActions({conversationId, statement, csrfToken, withUnmoderate = false,
  onMoved, onError}: {
  conversationId: number;
  statement: Statement;
  csrfToken: string;
  withUnmoderate?: boolean;
  onMoved: (statement: Statement, status: Status) => void;
  onError: (error: Error) => void;
}) {
  const msg = useMessage();
  const mutation = useMutation({
    mutationFn: (status: Status) => putAdminStatementModeration(
      conversationId, statement.id, {status}, csrfToken,
    ),
    onSuccess: (receipt) => onMoved(statement, receipt.status),
    onError,
  });
  const actions: {status: Status; glyph: string; name: string}[] = [
    {status: 'approved', glyph: '✓', name: msg('admin-moderation-approve-statement', statement.id)},
    {status: 'hidden', glyph: '✕', name: msg('admin-moderation-hide-statement', statement.id)},
    ...(withUnmoderate && statement.moderation !== 'pending'
      ? [{status: 'pending' as const, glyph: '○', name: msg('admin-moderation-unmoderate-statement', statement.id)}]
      : []),
  ];
  return (
    <div className="admin-row__actions">
      {actions.map((action) => (
        <button
          key={action.status}
          type="button"
          className="admin-row__glyph"
          title={action.name}
          aria-label={action.name}
          disabled={mutation.isPending || statement.moderation === action.status}
          onClick={() => mutation.mutate(action.status)}
        >
          <span aria-hidden="true">{action.glyph}</span>
        </button>
      ))}
    </div>
  );
}
