import {useCallback, useState} from 'react';
import {useMutation, useQueryClient, useSuspenseQuery} from '@tanstack/react-query';

import type {components} from '../../api/schema';
import {ApiContractError} from '../../api/client';
import {
  adminLifecycleQuery,
  adminSettingsQuery,
  adminStatementWorkspaceQuery,
  putAdminStatementModeration,
} from '../../api/queries';
import {InternalLink} from '../../internal-link';
import {useMessage, type Message} from '../../i18n/messages';
import {sortByBasedOn} from './admin-based-on';
import {AdminComing} from './admin-coming';
import {AdminShell} from './admin-shell';
import {useAnnouncer} from './admin-announcer';
import {AdminTabStrip, type SectionTab} from './admin-tab-strip';
import {moderationTabs} from './admin-moderation-tabs';
import {useRowFocus} from './admin-row-focus';
import {LegacyToast, type LegacyToastMessage} from '../legacy/legacy-toast';

type Statement = components['schemas']['AdminStatement'];
type Workspace = components['schemas']['AdminStatementWorkspace'];
type Status = Statement['moderation'];

/** The three positions of the queue's state switch: which statements it shows. The glyph
 *  is the state itself (✓ approved, ○ waiting, ✕ hidden), so it names itself on hover and
 *  to a screen reader rather than reading as a bare symbol. */
type Position = 'approved' | 'unmoderated' | 'hidden';

const POSITIONS: {id: Position; glyph: string; key: string}[] = [
  {id: 'approved', glyph: '✓', key: 'admin-moderation-state-approved'},
  {id: 'unmoderated', glyph: '○', key: 'admin-moderation-state-unmoderated'},
  {id: 'hidden', glyph: '✕', key: 'admin-moderation-state-hidden'},
];

/** Which workspace list each position shows. "Unmoderated" is the pending list: a statement
 *  nobody has looked at yet. */
const LIST: Record<Position, 'approved' | 'pending' | 'hidden'> = {
  approved: 'approved',
  unmoderated: 'pending',
  hidden: 'hidden',
};

const EMPTY: Record<Position, string> = {
  approved: 'stmts-approved-empty',
  unmoderated: 'admin-moderation-queue-empty',
  hidden: 'stmts-hidden-empty',
};

/** "Oldest first" works the queue in the order statements arrived; "Based on" groups a
 *  correction under the statement it corrects (`sortByBasedOn`). Both sort what is already
 *  loaded; nothing is refetched. */
type Sort = 'oldest' | 'based-on';

function sortStatements(rows: Statement[], sort: Sort): Statement[] {
  if (sort === 'based-on') return sortByBasedOn(rows);
  return [...rows].sort((left, right) => left.id - right.id);
}

function errorMessage(error: Error, msg: Message): string {
  return error instanceof ApiContractError ? error.message : msg('adminconv-command-failed');
}

/** One statement as one row: the text, its number, where it came from, and what can be
 *  done to it.
 *
 *  The number is a muted suffix, not a column of its own: it is how a moderator refers to a
 *  statement ("↳ #12", Featured's add by number), and it is in the accessible name of each
 *  action, so the visible "#12" is also what a voice-control user says. Approve and Hide
 *  are icon-only (a check and a cross) because they are the two ends of one decision and
 *  the same two words on every row are noise; the words live in the accessible name and in
 *  the tooltip. */
function QueueRow({conversationId, statement, csrfToken, move, onError}: {
  conversationId: number;
  statement: Statement;
  csrfToken: string;
  move: (statement: Statement, status: Status) => void;
  onError: (message: string) => void;
}) {
  const msg = useMessage();
  const mutation = useMutation({
    mutationFn: (status: Status) => putAdminStatementModeration(
      conversationId, statement.id, {status}, csrfToken,
    ),
    onSuccess: (receipt) => move(statement, receipt.status),
    onError: (error: Error) => onError(errorMessage(error, msg)),
  });
  const source = statement.provenance;
  return (
    <li className="admin-row" data-row-id={statement.id}>
      <div className="admin-row__text">
        {statement.text}
        <span className="admin-row__suffix">{` #${statement.id}`}</span>
        {source && (
          <InternalLink href={`/admin/conversations/${conversationId}/content/statements`}
            className="admin-row__source">{`↳ #${source.derivedFromId}`}</InternalLink>
        )}
      </div>
      <div className="admin-row__actions">
        <button
          type="button"
          className="admin-row__glyph"
          title={msg('admin-moderation-approve-statement', statement.id)}
          aria-label={msg('admin-moderation-approve-statement', statement.id)}
          disabled={mutation.isPending || statement.moderation === 'approved'}
          onClick={() => mutation.mutate('approved')}
        >
          <span aria-hidden="true">✓</span>
        </button>
        <button
          type="button"
          className="admin-row__glyph"
          title={msg('admin-moderation-hide-statement', statement.id)}
          aria-label={msg('admin-moderation-hide-statement', statement.id)}
          disabled={mutation.isPending || statement.moderation === 'hidden'}
          onClick={() => mutation.mutate('hidden')}
        >
          <span aria-hidden="true">✕</span>
        </button>
      </div>
    </li>
  );
}

export function AdminModerationQueuePage({conversationId, csrfToken}: {
  conversationId: number;
  csrfToken: string;
}) {
  const msg = useMessage();
  const queryClient = useQueryClient();
  const options = adminStatementWorkspaceQuery(conversationId);
  const {data} = useSuspenseQuery(options);
  const {data: settings} = useSuspenseQuery(adminSettingsQuery(conversationId));
  const {data: lifecycle} = useSuspenseQuery(adminLifecycleQuery(conversationId));
  const [position, setPosition] = useState<Position>('unmoderated');
  const [sort, setSort] = useState<Sort>('oldest');
  const [toast, setToast] = useState<LegacyToastMessage | null>(null);
  const dismissToast = useCallback(() => setToast(null), []);
  const announcer = useAnnouncer();
  const tabs: SectionTab[] = moderationTabs(conversationId, msg);
  const rows = sortStatements(data.statements[LIST[position]], sort);
  const {listRef, emptyRef, rowRemoved} = useRowFocus(rows.map((row) => row.id));

  function notify(category: LegacyToastMessage['category'], message: string) {
    setToast({id: Date.now(), category, message});
  }

  function move(statement: Statement, status: Status) {
    if (status !== LIST[position]) rowRemoved(statement.id);
    // The row leaves the list (or its glyph greys out); this says what happened, and is
    // said again when the next statement gets the same answer.
    if (status === 'approved') announcer.announce(msg('admin-moderation-statement-approved', statement.id));
    if (status === 'hidden') announcer.announce(msg('admin-moderation-statement-hidden', statement.id));
    // The receipt names the new state, so the row moves between the lists rather than
    // refetching: the queue keeps its scroll position and its sort while a moderator works.
    queryClient.setQueryData<Workspace>(options.queryKey, (workspace) => {
      if (!workspace) return workspace;
      const lists = {
        pending: workspace.statements.pending.filter((row) => row.id !== statement.id),
        approved: workspace.statements.approved.filter((row) => row.id !== statement.id),
        hidden: workspace.statements.hidden.filter((row) => row.id !== statement.id),
      };
      lists[status] = [...lists[status], {...statement, moderation: status}];
      return {...workspace, statements: lists};
    });
  }


  return (
    <AdminShell
      title={msg('adminconv-doc-title', lifecycle.conversation.title)}
      data={lifecycle}
      gatingType={settings.conversation.gatingType}
      section="moderation"
      subPage={msg('admin-moderation-queue')}
      toast={<LegacyToast toast={toast} onDismiss={dismissToast} />}
      announcer={announcer}
    >
      <div className="admin-page">
        <h1>{msg('admin-shell-moderation')}</h1>
        <AdminTabStrip label={msg('admin-shell-moderation')} tabs={tabs} current="queue" />

        <div className="admin-toolbar">
          {/* Not a labelled group: the three positions are three toggle buttons, each
              naming itself, so there is no group question for a screen reader to ask. */}
          <div className="admin-switch">
            {POSITIONS.map((item) => (
              <button
                key={item.id}
                type="button"
                className="admin-switch__position"
                aria-pressed={position === item.id}
                title={msg(item.key)}
                onClick={() => setPosition(item.id)}
              >
                <span aria-hidden="true">{item.glyph}</span>
                <span className="sr-only">{msg(item.key)}</span>
              </button>
            ))}
          </div>
          <label className="admin-sort">
            {msg('admin-moderation-sort-aria')}
            <select value={sort} onChange={(event) => setSort(event.target.value as Sort)}>
              <option value="oldest">{msg('admin-moderation-sort-oldest')}</option>
              <option value="based-on">{msg('admin-moderation-sort-based-on')}</option>
            </select>
          </label>
        </div>

        {/* The workspace answers 200 with empty lists when the voting service could not be
            read; that is not an empty queue, so it says what the Statements page says. */}
        {!data.dataAvailability.statements ? (
          <p className="admin-empty" role="alert">{msg('flash-load-statements-failed')}</p>
        ) : rows.length ? (
          <ul className="admin-rows" ref={listRef}>
            {rows.map((statement) => (
              <QueueRow
                key={statement.id}
                conversationId={conversationId}
                statement={statement}
                csrfToken={csrfToken}
                move={move}
                onError={(message) => notify('error', message)}
              />
            ))}
          </ul>
        ) : (
          // Each position says what it is empty of: nothing waiting is not the same news as
          // nothing approved.
          <p className="admin-empty" ref={emptyRef} tabIndex={-1}>{msg(EMPTY[position])}</p>
        )}

        {/* The waiting time on each row would need a timestamp the statements endpoint does
            not return today; the moderation log would carry it, once it exists (#473). */}
        <AdminComing what="how long each statement has been waiting" issue={473} />
      </div>
    </AdminShell>
  );
}