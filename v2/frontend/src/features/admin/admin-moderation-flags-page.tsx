import {useCallback, useEffect, useRef, useState, type FormEvent} from 'react';
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
import {AdminTime} from './admin-time';
import {AdminTabStrip} from './admin-tab-strip';
import {moderationTabs} from './admin-moderation-tabs';
import {useRowFocus} from './admin-row-focus';
import {LegacyToast, type LegacyToastMessage} from '../legacy/legacy-toast';

type Flag = components['schemas']['AdminContentFlag'];
type Queue = components['schemas']['AdminFlagQueue'];
type Target = Flag['target']['type'];
type Resolution = components['schemas']['AdminContentFlag']['resolution'];

/** How long a handled flag stays where it was, its controls replaced by "Handled ✓", before
 *  it moves to the Handled list (owner, 2026-10-09). Removing the row at once slides the next
 *  flag's "Mark as handled" under the pointer, so a double click would handle two flags. */
export const FLAG_SETTLE_MS = 2000;

/** Which kind of content the rows are for. The flag's target says which it is, so the two
 *  lists are the same data read two ways rather than two requests. */
type Position = Target;

/** The start of a flagged text, to tell one row's controls from the next one's: every row
 *  has the same "Note" and "Mark as handled", so their accessible names carry this after
 *  the visible words (which stay first, as the name a voice-control user says). */
function rowExcerpt(text: string): string {
  const flat = text.replace(/\s+/g, ' ').trim();
  return flat.length > 60 ? `${flat.slice(0, 59)}…` : flat;
}

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
 *  The action itself carries no check glyph — a check beside an open flag would read as
 *  "confirm the flag", which is the opposite of what it does. Once the flag is handled, the
 *  row's controls give way to "Handled ✓" for FLAG_SETTLE_MS (owner, 2026-10-09): there the
 *  check says the flag is closed, and it is decorative (aria-hidden), the word says it. */
function FlagRow({conversationId, flag, csrfToken, settled, onHandled, onFeedback}: {
  conversationId: number;
  flag: Flag;
  csrfToken: string;
  /** Handled, and waiting out FLAG_SETTLE_MS before it moves to the Handled list. */
  settled: boolean;
  onHandled: (flag: Flag, resolution: Resolution) => void;
  onFeedback: (category: LegacyToastMessage['category'], message: string) => void;
}) {
  const msg = useMessage();
  const queryClient = useQueryClient();
  const rowRef = useRef<HTMLLIElement>(null);
  const settledRef = useRef<HTMLParagraphElement>(null);
  // Focus was on this row's controls when they were replaced: it goes to the line that
  // replaces them, so it is not dropped to the document.
  const focusSettled = useRef(false);
  useEffect(() => {
    if (settled && focusSettled.current) {
      focusSettled.current = false;
      settledRef.current?.focus();
    }
  }, [settled]);
  // Set on the click itself: `isPending` reaches the buttons a render later, and a second
  // click in between would send a second request.
  const busy = useRef(false);
  const [note, setNote] = useState('');
  const mutation = useMutation({
    mutationFn: () => putAdminFlagResolution(
      conversationId, flag.id, {resolved: true, note: note.trim() || null}, csrfToken,
    ),
    onSuccess: (receipt) => {
      const active = document.activeElement;
      focusSettled.current = !active || active === document.body
        || Boolean(rowRef.current?.contains(active));
      onHandled(flag, receipt.resolution);
      // The open-flag count is the Moderation badge in the frame's sidebar.
      void queryClient.invalidateQueries({queryKey: adminLifecycleQuery(conversationId).queryKey});
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
    <li className="admin-row" data-row-id={flag.id} ref={rowRef}>
      <FlagText flag={flag} open />
      {settled ? (
        <div className="admin-row__actions">
          <p className="admin-row__time" ref={settledRef} tabIndex={-1}>
            {msg('admin-moderation-flag-row-handled')} <span aria-hidden="true">✓</span>
          </p>
        </div>
      ) : <div className="admin-row__actions">
        {flag.flaggedAt && <span className="admin-row__time"><AdminTime value={flag.flaggedAt} /></span>}
        <form className="admin-row__block-form" onSubmit={resolve}>
          <label className="admin-row__field">
            <span>{msg('admin-moderation-flag-note')}</span>
            {' '}<span className="sr-only">{`— ${rowExcerpt(flag.target.text)}`}</span>
            <input type="text" name="resolution_note" value={note}
              onChange={(event) => setNote(event.target.value)} />
          </label>
          <button type="submit" className="admin-row__text-button" disabled={mutation.isPending}>
            {msg('admin-moderation-flag-handle')}
            {' '}<span className="sr-only">{`— ${rowExcerpt(flag.target.text)}`}</span>
          </button>
        </form>
      </div>}
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
  const {listRef, emptyRef, rowRemoved} = useRowFocus(rows.map((flag) => flag.id));
  const queryClient = useQueryClient();
  const queueKey = adminFlagQueueQuery(conversationId).queryKey;

  // Handled flags still shown in place, each with the move that takes it to the Handled
  // list; the move runs when its timer fires, or at once when the page goes away.
  const [settled, setSettled] = useState<ReadonlySet<number>>(new Set());
  const moves = useRef(new Map<number, {timer: ReturnType<typeof setTimeout>; move: () => void}>());
  // TanStack runs a mutation's onSuccess even after the row's page has gone, so a request
  // that lands after unmount must not start a timer the cleanup below will never see.
  const mounted = useRef(false);
  const move = useRef<(flag: Flag, resolution: Resolution, refocus: boolean) => void>(() => {});
  move.current = (flag, resolution, refocus) => {
    moves.current.delete(flag.id);
    // Focus follows the row only while it is still in the row (on its "Handled ✓" line);
    // someone who has moved on keeps their place.
    const active = document.activeElement;
    const row = listRef.current?.querySelector(`[data-row-id="${flag.id}"]`);
    if (refocus && (!active || active === document.body || row?.contains(active))) rowRemoved(flag.id);
    setSettled((current) => {
      const next = new Set(current);
      next.delete(flag.id);
      return next;
    });
    queryClient.setQueryData<Queue>(queueKey, (queue) => {
      if (!queue) return queue;
      const resolvedFlag: Flag = {...flag, status: 'resolved', resolution};
      return {
        ...queue,
        open: queue.open.filter((item) => item.id !== flag.id),
        resolved: [resolvedFlag, ...queue.resolved.filter((item) => item.id !== flag.id)],
      };
    });
  };
  function handled(flag: Flag, resolution: Resolution) {
    if (!mounted.current) {
      // The page has gone: nobody sees the row settle, so the flag moves to the Handled list
      // in the cache at once, and a return within the settle time finds it there.
      move.current(flag, resolution, false);
      return;
    }
    setSettled((current) => new Set(current).add(flag.id));
    const timer = setTimeout(() => move.current(flag, resolution, true), FLAG_SETTLE_MS);
    moves.current.set(flag.id, {timer, move: () => move.current(flag, resolution, false)});
  }
  useEffect(() => {
    const pending = moves.current;
    mounted.current = true;
    return () => {
      mounted.current = false;
      for (const {timer, move: run} of pending.values()) {
        clearTimeout(timer);
        run();
      }
    };
  }, []);
  // A flag waiting to move is handled already: it is not counted as open.
  const count = (type: Target) => data.open
    .filter((flag) => flag.target.type === type && !settled.has(flag.id)).length;

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
                csrfToken={csrfToken} settled={settled.has(flag.id)}
                onHandled={handled} onFeedback={showFeedback} />
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
