import {useCallback, useState} from 'react';
import {useMutation, useQueryClient, useSuspenseQuery} from '@tanstack/react-query';

import type {components} from '../../api/schema';
import {
  adminLifecycleQuery,
  adminParticipantRosterQuery,
  adminSettingsQuery,
  putAdminParticipantAccess,
} from '../../api/queries';
import {useMessage} from '../../i18n/messages';
import {AdminComing} from './admin-coming';
import {AdminShell} from './admin-shell';
import {AdminTabStrip} from './admin-tab-strip';
import {moderationTabs} from './admin-moderation-tabs';
import {LegacyToast, type LegacyToastMessage} from '../legacy/legacy-toast';

type Participant = components['schemas']['AdminParticipant'];
type Roster = components['schemas']['AdminParticipantRoster'];

function formatDate(value: string): string {
  return value.slice(0, 10);
}

/** Block or unblock one person from contributing.
 *
 * The server's field is a ban and the wording is the console's own: a ban takes the ability
 * to contribute away and nothing else, and the dialog on the board says so. There is no
 * "access withdrawn" state here because the API does not return one (#473 parks it). */
function AccessControl({conversationId, participant, csrfToken, onFeedback}: {
  conversationId: number;
  participant: Participant;
  csrfToken: string;
  onFeedback: (toast: LegacyToastMessage) => void;
}) {
  const msg = useMessage();
  const queryClient = useQueryClient();
  const [summary, setSummary] = useState('');
  const desiredBanned = !participant.access.banned;
  const placeholder = msg(participant.access.banned
    ? 'participants-unban-note-ph'
    : 'participants-ban-reason-ph');
  const mutation = useMutation({
    mutationFn: () => putAdminParticipantAccess(
      conversationId, participant.participantId,
      {banned: desiredBanned, summary: summary || null}, csrfToken,
    ),
    onSuccess: (receipt) => {
      queryClient.setQueryData<Roster>(
        adminParticipantRosterQuery(conversationId).queryKey,
        (current) => current ? {
          ...current,
          participants: current.participants.map((row) => (
            row.participantId === receipt.participantId ? {
              ...row,
              access: {
                banned: receipt.banned,
                changedAt: receipt.changedAt,
                summary: receipt.banned ? receipt.summary : null,
              },
            } : row
          )),
        } : current,
      );
      setSummary('');
      // The row shows the new state in place; the toast is what a screen reader hears, and
      // what says so when the person already was in the state asked for.
      const changed = receipt.banned ? msg('flash-banned') : msg('flash-unbanned');
      const unchanged = receipt.banned
        ? msg('flash-already-banned')
        : msg('admin-moderation-person-already-allowed');
      onFeedback({
        id: Date.now(),
        category: receipt.changed ? 'success' : 'warning',
        message: receipt.changed ? changed : unchanged,
      });
    },
  });

  return (
    <form
      className="admin-row__block-form"
      onSubmit={(event) => {
        event.preventDefault();
        mutation.mutate();
      }}
    >
      <input
        type="text"
        name="summary"
        value={summary}
        onChange={(event) => setSummary(event.target.value)}
        placeholder={placeholder}
        // Every row has this field and this button: the person's name after the visible
        // words tells one row's from the next one's.
        aria-label={`${placeholder} — ${participant.pseudonym}`}
      />
      <button type="submit" className="admin-row__text-button" disabled={mutation.isPending}>
        {msg(participant.access.banned ? 'participants-btn-unban' : 'participants-btn-ban')}
        {' '}<span className="sr-only">{`— ${participant.pseudonym}`}</span>
      </button>
    </form>
  );
}

export function AdminModerationPeoplePage({conversationId, csrfToken}: {
  conversationId: number;
  csrfToken: string;
}) {
  const msg = useMessage();
  const {data} = useSuspenseQuery(adminParticipantRosterQuery(conversationId));
  const {data: settings} = useSuspenseQuery(adminSettingsQuery(conversationId));
  const {data: lifecycle} = useSuspenseQuery(adminLifecycleQuery(conversationId));
  const [toast, setToast] = useState<LegacyToastMessage | null>(null);
  const dismissToast = useCallback(() => setToast(null), []);

  return (
    <AdminShell
      title={msg('adminconv-doc-title', lifecycle.conversation.title)}
      data={lifecycle}
      gatingType={settings.conversation.gatingType}
      section="moderation"
      subPage={msg('admin-moderation-people')}
      toast={<LegacyToast toast={toast} onDismiss={dismissToast} />}
    >
      <div className="admin-page">
        <h1>{msg('admin-shell-moderation')}</h1>
        <AdminTabStrip label={msg('admin-shell-moderation')}
          tabs={moderationTabs(conversationId, msg)} current="people" />

        {data.participants.length ? (
          <ul className="admin-rows">
            {data.participants.map((participant) => (
              <li className="admin-row" key={participant.participantId}>
                <div className="admin-row__text">
                  {/* The pseudonym, never the username: moderators see people only by the
                      name they take part under (owner decision, 2026-10-08), and the roster
                      does not carry a username to a moderator-only viewer at all. */}
                  {participant.pseudonym}
                  <span className="admin-row__suffix">
                    {' · '}
                    {participant.access.banned
                      ? msg('participants-banned')
                      : msg('admin-moderation-person-active')}
                    {participant.access.banned && participant.access.changedAt
                      ? ` ${msg('participants-banned-since')} ${formatDate(participant.access.changedAt)}`
                      : ''}
                    {participant.access.banned && participant.access.summary
                      ? ` · ${participant.access.summary}`
                      : ''}
                    {participant.lastEngagementAt
                      ? ` · ${formatDate(participant.lastEngagementAt)}`
                      : ` · ${msg('participants-no-actions')}`}
                  </span>
                </div>
                <div className="admin-row__actions">
                  <AccessControl conversationId={conversationId} participant={participant}
                    csrfToken={csrfToken} onFeedback={setToast} />
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <p className="admin-empty">{msg('participants-empty')}</p>
        )}

        {/* The moderator/organizer split, progress, batch label and joined day need fields
            the roster does not return yet (#473). */}
        <AdminComing what="the moderator and organizer roles per person, and when they joined" issue={473} />
      </div>
    </AdminShell>
  );
}