import {useCallback, useState, type FormEvent} from 'react';
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
import {contentTabs} from './admin-content-tabs';
import {LegacyToast, type LegacyToastMessage} from '../legacy/legacy-toast';

type Participant = components['schemas']['AdminParticipant'];
type Roster = components['schemas']['AdminParticipantRoster'];

function formatLegacyDate(value: string): string {
  return new Date(value).toISOString().slice(0, 10);
}

function formatLegacyDateTime(value: string | null): string | null {
  if (!value) return null;
  return new Date(value).toISOString().slice(0, 16).replace('T', ' ');
}

function ParticipantAccessControl({
  conversationId,
  participant,
  csrfToken,
  setToast,
}: {
  conversationId: number;
  participant: Participant;
  csrfToken: string;
  setToast: (toast: LegacyToastMessage) => void;
}) {
  const queryClient = useQueryClient();
  const [summary, setSummary] = useState('');
  const desiredBanned = !participant.access.banned;
  const mutation = useMutation({
    mutationFn: () => putAdminParticipantAccess(
      conversationId,
      participant.participantId,
      {banned: desiredBanned, summary: summary || null},
      csrfToken,
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
      const changedMessage = receipt.banned
        ? 'Participant banned from this conversation.'
        : 'Participant unbanned from this conversation.';
      const unchangedMessage = receipt.banned
        ? 'Participant is already banned from this conversation.'
        : 'Participant is already allowed in this conversation.';
      setToast({
        id: Date.now(),
        category: receipt.changed ? 'success' : 'warning',
        message: receipt.changed ? changedMessage : unchangedMessage,
      });
    },
  });

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    mutation.mutate();
  }

  if (participant.access.banned) {
    return (
      <>
        {/* "Banned since …" is said once, beside the name. */}
        {participant.access.summary && (
          <div className="muted" style={{fontSize: 13, marginBottom: '.5rem'}}>{participant.access.summary}</div>
        )}
        <form onSubmit={submit}>
          <input
            type="text"
            name="summary"
            value={summary}
            onChange={(event) => setSummary(event.target.value)}
            placeholder="Unban note (optional)"
            style={{width: '100%', marginBottom: '.35rem'}}
          />
          <button type="submit" className="btn-small btn-approve">unban</button>
        </form>
      </>
    );
  }

  return (
    <form onSubmit={submit}>
      <input
        type="text"
        name="summary"
        value={summary}
        onChange={(event) => setSummary(event.target.value)}
        placeholder="Reason (optional)"
        style={{width: '100%', marginBottom: '.35rem'}}
      />
      <button type="submit" className="btn-small btn-danger">ban</button>
    </form>
  );
}

export function AdminParticipantsPage({
  conversationId,
  csrfToken,
}: {
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
      section="content"
      subPage={msg('adminconv-card-participants')}
      toast={<LegacyToast toast={toast} onDismiss={dismissToast} />}
    >
      <div className="admin-page">
        <h1>{msg('admin-shell-content')}</h1>
        <AdminTabStrip label={msg('admin-content-tabs-aria')}
          tabs={contentTabs(conversationId, msg)} current="participants" />

        <p className="admin-note">{msg('participants-intro')}</p>

        {!data.dataAvailability.statementProgress && (
          <p className="admin-note">{msg('participants-progress-unavailable')}</p>
        )}

        {data.participants.length ? (
          <ul className="admin-rows">
            {data.participants.map((participant) => {
              const progress = participant.statementProgress;
              const lastEngagement = formatLegacyDateTime(participant.lastEngagementAt);
              return (
                <li className="admin-row" key={participant.participantId}>
                  <div className="admin-row__text">
                    {participant.username}
                    {participant.access.banned && (
                      <span className="admin-row__suffix">
                        {' · '}{msg('participants-banned')}
                        {participant.access.changedAt
                          && ` ${msg('participants-banned-since')} ${formatLegacyDate(participant.access.changedAt)}`}
                      </span>
                    )}
                  </div>
                  {/* Today's columns, as facts about the person: progress and the argument
                      counts are what the roster returns, in the words the page already used. */}
                  <dl className="admin-row__facts">
                    <div>
                      <dt>{msg('participants-th-voted')}</dt>
                      <dd>{progress ? `${progress.voted} / ${progress.total}` : '—'}</dd>
                    </div>
                    <div>
                      <dt>{msg('participants-th-remaining')}</dt>
                      <dd>{progress ? progress.remaining : '—'}</dd>
                    </div>
                    <div>
                      <dt>{msg('participants-th-args-submitted')}</dt>
                      <dd>{participant.arguments.submitted}</dd>
                    </div>
                    <div>
                      <dt>{msg('participants-th-args-voted')}</dt>
                      <dd>{participant.arguments.prioritized}</dd>
                    </div>
                    <div>
                      <dt>{msg('participants-th-last-engagement')}</dt>
                      <dd>{lastEngagement ?? msg('participants-no-actions')}</dd>
                    </div>
                  </dl>
                  <div className="admin-row__actions">
                    <ParticipantAccessControl
                      conversationId={conversationId}
                      participant={participant}
                      csrfToken={csrfToken}
                      setToast={setToast}
                    />
                  </div>
                </li>
              );
            })}
          </ul>
        ) : (
          <p className="admin-empty">{msg('participants-empty')}</p>
        )}

        {/* The spec splits this page into a moderator's columns and an organizer's and adds
            the batch label and the joined day. The roster carries none of those fields yet. */}
        <p className="admin-shell__coming" lang="en">Also coming: the moderator and organizer roles per person, their batch, and the day they joined — not available yet (#473)</p>
      </div>
    </AdminShell>
  );
}
