import {useCallback, useState} from 'react';
import {useMutation, useQueryClient, useSuspenseQuery} from '@tanstack/react-query';

import type {components} from '../../api/schema';
import {
  adminFlagQueueQuery,
  adminLifecycleQuery,
  adminSettingsQuery,
  putAdminFlagResolution,
} from '../../api/queries';
import {useMessage, type Message} from '../../i18n/messages';
import {AdminShell} from './admin-shell';
import {AdminTabStrip} from './admin-tab-strip';
import {moderationTabs} from './admin-moderation-tabs';
import {LegacyToast, type LegacyToastMessage} from '../legacy/legacy-toast';

type Flag = components['schemas']['AdminContentFlag'];
type Queue = components['schemas']['AdminFlagQueue'];
type Target = Flag['target']['type'];

/** Which kind of content the rows are for. The flag's target says which it is, so the two
 *  lists are the same data read two ways rather than two requests. */
type Position = Target;

/** Both buttons resolve the flag: "Keep" says the content is fine as it stands, "Remove"
 *  says the content should go, which the moderator then does on the Queue or on Featured.
 *  There is no check glyph here — a check beside a flag would read as "confirm the flag",
 *  which is the opposite of what it does. */
function ResolveFlag({conversationId, flag, csrfToken, verb, onFeedback}: {
  conversationId: number;
  flag: Flag;
  csrfToken: string;
  verb: 'keep' | 'remove';
  onFeedback: (message: string, changed: boolean) => void;
}) {
  const msg = useMessage();
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: () => putAdminFlagResolution(
      conversationId, flag.id, {resolved: true, note: null}, csrfToken,
    ),
    onSuccess: (receipt) => {
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
      onFeedback(msg('admin-moderation-flag-marked'), receipt.changed);
    },
    onError: (error: Error) => onFeedback(error.message, false),
  });
  return (
    <button
      type="button"
      className="admin-row__text-button"
      disabled={mutation.isPending}
      onClick={() => mutation.mutate()}
    >
      {msg(verb === 'keep' ? 'admin-moderation-flag-keep' : 'admin-moderation-flag-remove')}
    </button>
  );
}

function FlagRow({conversationId, flag, csrfToken, onFeedback}: {
  conversationId: number;
  flag: Flag;
  csrfToken: string;
  onFeedback: (message: string, changed: boolean) => void;
}) {
  const msg = useMessage();
  const detail = flag.detail;
  return (
    <li className="admin-row">
      <div className="admin-row__text">
        {flag.target.text}
        {/* The reason as a muted suffix: it qualifies the row, it is not a second field. */}
        <span className="admin-row__suffix">
          {' · '}{flag.categoryLabel}{detail ? ` · ${detail}` : ''}
        </span>
      </div>
      <div className="admin-row__actions">
        <ResolveFlag conversationId={conversationId} flag={flag} csrfToken={csrfToken}
          verb="keep" onFeedback={onFeedback} />
        <ResolveFlag conversationId={conversationId} flag={flag} csrfToken={csrfToken}
          verb="remove" onFeedback={onFeedback} />
      </div>
    </li>
  );
}

export function AdminModerationFlagsPage({conversationId, csrfToken}: {
  conversationId: number;
  csrfToken: string;
}) {
  const msg = useMessage();
  const {data} = useSuspenseQuery(adminFlagQueueQuery(conversationId));
  const {data: settings} = useSuspenseQuery(adminSettingsQuery(conversationId));
  const {data: lifecycle} = useSuspenseQuery(adminLifecycleQuery(conversationId));
  const [position, setPosition] = useState<Position>('statement');
  const [toast, setToast] = useState<LegacyToastMessage | null>(null);
  const dismissToast = useCallback(() => setToast(null), []);

  function showFeedback(message: string, changed: boolean) {
    setToast({id: Date.now(), category: changed ? 'success' : 'warning', message});
  }

  const rows = data.open.filter((flag) => flag.target.type === position);

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
        <h1>{msg('admin-moderation-flags')}</h1>
        <AdminTabStrip label={msg('admin-shell-moderation')}
          tabs={moderationTabs(conversationId, msg)} current="flags" />

        <div className="admin-switch admin-switch--words">
          <button type="button" aria-pressed={position === 'statement'}
            onClick={() => setPosition('statement')}>{msg('adminconv-card-statements')}</button>
          <button type="button" aria-pressed={position === 'argument'}
            onClick={() => setPosition('argument')}>{msg('featured-arguments-label')}</button>
        </div>

        {rows.length ? (
          <ul className="admin-rows">
            {rows.map((flag) => (
              <FlagRow key={flag.id} conversationId={conversationId} flag={flag}
                csrfToken={csrfToken} onFeedback={showFeedback} />
            ))}
          </ul>
        ) : (
          <p className="admin-empty">{msg('flags-open-empty')}</p>
        )}
      </div>
    </AdminShell>
  );
}