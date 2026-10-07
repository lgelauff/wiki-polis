import {useState} from 'react';
import {useMutation, useQueryClient, useSuspenseQuery} from '@tanstack/react-query';

import type {components} from '../../api/schema';
import {
  adminLifecycleQuery,
  adminParticipantRosterQuery,
  adminSettingsQuery,
  putAdminParticipantAccess,
} from '../../api/queries';
import {useMessage} from '../../i18n/messages';
import {AdminShell} from './admin-shell';
import {AdminTabStrip} from './admin-tab-strip';
import {moderationTabs} from './admin-moderation-tabs';

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
function AccessControl({conversationId, participant, csrfToken}: {
  conversationId: number;
  participant: Participant;
  csrfToken: string;
}) {
  const msg = useMessage();
  const queryClient = useQueryClient();
  const [summary, setSummary] = useState('');
  const desiredBanned = !participant.access.banned;
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
      // No toast: the row says the new state in place (its state word and its button both
      // change), which is the whole of what happened.
      setSummary('');
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
        type="hidden"
        name="csrf_token"
        value={csrfToken}
      />
      <input
        type="text"
        name="summary"
        value={summary}
        onChange={(event) => setSummary(event.target.value)}
        placeholder={msg(participant.access.banned
          ? 'participants-unban-note-ph'
          : 'participants-ban-reason-ph')}
      />
      <button type="submit" className="admin-row__text-button" disabled={mutation.isPending}>
        {msg(participant.access.banned ? 'participants-btn-unban' : 'participants-btn-ban')}
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

  return (
    <AdminShell
      title={msg('adminconv-doc-title', lifecycle.conversation.title)}
      data={lifecycle}
      gatingType={settings.conversation.gatingType}
      section="moderation"
      subPage={msg('admin-moderation-people')}
    >
      <div className="admin-page">
        <h1>{msg('admin-moderation-people')}</h1>
        <AdminTabStrip label={msg('admin-shell-moderation')}
          tabs={moderationTabs(conversationId, msg)} current="people" />

        {data.participants.length ? (
          <ul className="admin-rows">
            {data.participants.map((participant) => (
              <li className="admin-row" key={participant.participantId}>
                <div className="admin-row__text">
                  {participant.pseudonym}
                  <span className="admin-row__suffix">
                    {' · '}
                    {participant.access.banned
                      ? msg('participants-banned')
                      : msg('admin-moderation-person-active')}
                    {participant.lastEngagementAt
                      ? ` · ${formatDate(participant.lastEngagementAt)}`
                      : ` · ${msg('participants-no-actions')}`}
                    {participant.access.changedAt
                      ? ` · ${msg('participants-banned-since')} ${formatDate(participant.access.changedAt)}`
                      : ''}
                  </span>
                </div>
                <div className="admin-row__actions">
                  <AccessControl conversationId={conversationId} participant={participant}
                    csrfToken={csrfToken} />
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <p className="admin-empty">{msg('participants-empty')}</p>
        )}

        {/* The moderator/organizer split, progress, batch label and joined day need fields
            the roster does not return yet (#473). */}
        <p className="admin-coming" lang="en">Also coming: the moderator and organizer roles per person, and when they joined — not available yet (#473)</p>
      </div>
    </AdminShell>
  );
}