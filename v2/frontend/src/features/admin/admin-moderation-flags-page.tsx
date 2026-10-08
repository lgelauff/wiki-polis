import {useCallback, useRef, useState, type FormEvent} from 'react';
import {useMutation, useQueryClient, useSuspenseQuery} from '@tanstack/react-query';

import type {components} from '../../api/schema';
import {ApiContractError} from '../../api/client';
import {
  adminFlagQueueQuery,
  adminLifecycleQuery,
  adminSettingsQuery,
  putAdminFlagResolution,
} from '../../api/queries';
import {useDateFormat} from '../../i18n/dates';
import {InternalLink} from '../../internal-link';
import {useMessage, type Message} from '../../i18n/messages';
import {AdminShell} from './admin-shell';
import {AdminTabStrip} from './admin-tab-strip';
import {moderationTabs} from './admin-moderation-tabs';
import {useRowFocus} from './admin-row-focus';
import {LegacyToast, type LegacyToastMessage} from '../legacy/legacy-toast';

type Flag = components['schemas']['AdminContentFlag'];
type Queue = components['schemas']['AdminFlagQueue'];
type Target = Flag['target']['type'];

/** Which kind of content the rows are for. The flag's target says which it is, so the two
 *  lists are the same data read two ways rather than two requests. */
type Position = Target;

function errorMessage(error: Error, msg: Message): string {
  return error instanceof ApiContractError ? error.message : msg('adminconv-command-failed');
}

/** The flagged text, on an open flag a muted "↳" to where that content is moderated, and
 *  the reason as a muted suffix: the reason qualifies the row, it is not a second field. */
function FlagText({flag, open}: {flag: Flag; open: boolean}) {
  const msg = useMessage();
  const review = msg(flag.target.type === 'statement' ? 'flags-review-statements' : 'flags-review-arguments');
  return (
    <div className="admin-row__text">
      {flag.target.text}
      {open && (
        <>
          {' '}
          <InternalLink href={flag.target.reviewHref} className="admin-row__source" title={review}
            aria-label={review}>↳</InternalLink>
        </>
      )}
      <span className="admin-row__suffix">
        {' · '}{flag.categoryLabel}{flag.detail ? ` · ${flag.detail}` : ''}
      </span>
    </div>
  );
}

/** One open flag, with one action: "Mark as handled" closes the flag, with an optional note
 *  saying what was done. What happens to the content itself is done where the "↳" leads.
 *  There is no check glyph here — a check beside a flag would read as "confirm the flag",
 *  which is the opposite of what it does. */
function FlagRow({conversationId, flag, csrfToken, onResolved, onFeedback}: {
  conversationId: number;
  flag: Flag;
  csrfToken: string;
  onResolved: (flagId: number) => void;
  onFeedback: (category: LegacyToastMessage['category'], message: string) => void;
}) {
  const msg = useMessage();
  const {date} = useDateFormat();
  const queryClient = useQueryClient();
  // Set on the click itself: `isPending` reaches the buttons a render later, and a second
  // click in between would send a second request.
  const busy = useRef(false);
  const [note, setNote] = useState('');
  const mutation = useMutation({
    mutationFn: () => putAdminFlagResolution(
      conversationId, flag.id, {resolved: true, note: note.trim() || null}, csrfToken,
    ),
    onSuccess: (receipt) => {
      onResolved(flag.id);
      queryClient.setQueryData<Queue>(
        adminFlagQueueQuery(conversationId).queryKey,
        (queue) => {
          if (!queue) return queue;
          const resolvedFlag: Flag = {...flag, status: 'resolved', resolution: receipt.resolution};
          return {
            ...queue,
            open: queue.open.filter((item) => item.id !== flag.id),
            resolved: [resolvedFlag, ...queue.resolved.filter((item) => item.id !== flag.id)],
          };
        },
      );
      onFeedback(
        receipt.changed ? 'success' : 'warning',
        receipt.changed ? msg('admin-moderation-flag-marked-handled') : msg('admin-moderation-flag-already-handled'),
      );
    },
    onError: (error: Error) => onFeedback('error', errorMessage(error, msg)),
    onSettled: () => {
      busy.current = false;
    },
  });
  function resolve(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy.current) return;
    busy.current = true;
    mutation.mutate();
  }
  return (
    <li className="admin-row" data-row-id={flag.id}>
      <FlagText flag={flag} open />
      <div className="admin-row__actions">
        {flag.flaggedAt && <span className="admin-row__time">{date(flag.flaggedAt)}</span>}
        <form className="admin-row__block-form" onSubmit={resolve}>
          <label className="admin-row__field">
            <span>{msg('admin-moderation-flag-note')}</span>
            <input type="text" name="resolution_note" value={note}
              onChange={(event) => setNote(event.target.value)} />
          </label>
          <button type="submit" className="admin-row__text-button" disabled={mutation.isPending}>
            {msg('admin-moderation-flag-handle')}
          </button>
        </form>
      </div>
    </li>
  );
}

export function AdminModerationFlagsPage({conversationId, csrfToken}: {
  conversationId: number;
  csrfToken: string;
}) {
  const msg = useMessage();
  const {date} = useDateFormat();
  const {data} = useSuspenseQuery(adminFlagQueueQuery(conversationId));
  const {data: settings} = useSuspenseQuery(adminSettingsQuery(conversationId));
  const {data: lifecycle} = useSuspenseQuery(adminLifecycleQuery(conversationId));
  const [position, setPosition] = useState<Position>('statement');
  const [toast, setToast] = useState<LegacyToastMessage | null>(null);
  const dismissToast = useCallback(() => setToast(null), []);

  function showFeedback(category: LegacyToastMessage['category'], message: string) {
    setToast({id: Date.now(), category, message});
  }

  const rows = data.open.filter((flag) => flag.target.type === position);
  const resolved = data.resolved.filter((flag) => flag.target.type === position);
  const count = (type: Target) => data.open.filter((flag) => flag.target.type === type).length;
  const {listRef, emptyRef, rowRemoved} = useRowFocus(rows.map((flag) => flag.id));

  return (
    <AdminShell
      title={msg('adminconv-doc-title', lifecycle.conversation.title)}
      data={lifecycle}
      gatingType={settings.conversation.gatingType}
      section="moderation"
      subPage={msg('admin-moderation-flags')}
      toast={<LegacyToast toast={toast} onDismiss={dismissToast} />}
    >
      <div className="admin-page">
        <h1>{msg('admin-shell-moderation')}</h1>
        <AdminTabStrip label={msg('admin-shell-moderation')}
          tabs={moderationTabs(conversationId, msg)} current="flags" />

        {/* Each position says how many open flags it holds, so flags on the other one are
            found without switching. */}
        <div className="admin-toolbar">
          <div className="admin-switch">
            {([['statement', 'adminconv-card-statements'], ['argument', 'featured-arguments-label']] as const)
              .map(([type, key]) => (
                <button key={type} type="button" className="admin-switch__position"
                  aria-pressed={position === type} onClick={() => setPosition(type)}>
                  {msg(key)}{count(type) ? ` ${count(type)}` : ''}
                </button>
              ))}
          </div>
        </div>

        {rows.length ? (
          <ul className="admin-rows" ref={listRef}>
            {rows.map((flag) => (
              <FlagRow key={flag.id} conversationId={conversationId} flag={flag}
                csrfToken={csrfToken} onResolved={rowRemoved} onFeedback={showFeedback} />
            ))}
          </ul>
        ) : (
          <p className="admin-empty" ref={emptyRef} tabIndex={-1}>{msg('flags-open-empty')}</p>
        )}

        {resolved.length > 0 && (
          <>
            <h2>{msg('admin-moderation-flags-handled-heading')}</h2>
            <ul className="admin-rows">
              {resolved.map((flag) => (
                <li className="admin-row" key={flag.id}>
                  <FlagText flag={flag} open={false} />
                  {/* When it was handled, and the note the moderator left, if any: the
                      note is theirs, so it is shown as written. */}
                  {flag.resolution?.resolvedAt && (
                    <span className="admin-row__time">
                      {msg('admin-moderation-flag-handled', date(flag.resolution.resolvedAt))}
                    </span>
                  )}
                  {flag.resolution?.note && (
                    <p className="admin-row__note">{flag.resolution.note}</p>
                  )}
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
    </AdminShell>
  );
}
