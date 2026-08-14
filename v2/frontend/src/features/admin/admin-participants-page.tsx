import {useState, type FormEvent} from 'react';
import {useMutation, useQueryClient, useSuspenseQuery} from '@tanstack/react-query';
import {Link} from 'react-router-dom';

import type {components} from '../../api/schema';
import {
  adminParticipantRosterQuery,
  putAdminParticipantAccess,
} from '../../api/queries';

type Participant = components['schemas']['AdminParticipant'];
type Roster = components['schemas']['AdminParticipantRoster'];

function formatDate(value: string | null): string {
  if (!value) return 'No actions yet';
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value));
}

function ParticipantAccessControl({
  conversationId,
  participant,
  csrfToken,
}: {
  conversationId: number;
  participant: Participant;
  csrfToken: string;
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
    },
  });

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    mutation.mutate();
  }

  return (
    <div className="admin-access">
      <div className="admin-access__state" data-banned={participant.access.banned}>
        <span aria-hidden="true" />
        <strong>{participant.access.banned ? 'Banned' : 'Allowed'}</strong>
        {participant.access.changedAt && <small>since {formatDate(participant.access.changedAt)}</small>}
      </div>
      {participant.access.summary && <p>{participant.access.summary}</p>}
      <form onSubmit={submit}>
        <label htmlFor={`access-summary-${participant.participantId}`}>
          {desiredBanned ? 'Reason' : 'Unban note'} <span>(optional)</span>
        </label>
        <div>
          <input
            id={`access-summary-${participant.participantId}`}
            value={summary}
            onChange={(event) => setSummary(event.target.value)}
            maxLength={1000}
            disabled={mutation.isPending}
          />
          <button
            type="submit"
            className={desiredBanned ? 'admin-access__ban' : 'admin-access__allow'}
            disabled={mutation.isPending}
          >
            {mutation.isPending
              ? 'Saving…'
              : desiredBanned ? `Ban ${participant.username}` : `Unban ${participant.username}`}
          </button>
        </div>
      </form>
      {mutation.isError && <p className="admin-access__error" role="alert">{mutation.error.message}</p>}
      {mutation.isSuccess && (
        <p className="admin-access__receipt" role="status">
          Access {mutation.data.changed ? 'updated' : 'was already current'}.
        </p>
      )}
    </div>
  );
}

function Progress({participant}: {participant: Participant}) {
  const progress = participant.statementProgress;
  if (!progress) return <span className="admin-roster__unavailable">Unavailable</span>;
  return (
    <div className="admin-roster__progress">
      <strong>{progress.voted} / {progress.total}</strong>
      <span>{progress.remaining} remaining</span>
      <div aria-hidden="true">
        <i style={{width: `${progress.total ? (progress.voted / progress.total) * 100 : 0}%`}} />
      </div>
    </div>
  );
}

export function AdminParticipantsPage({
  conversationId,
  csrfToken,
}: {
  conversationId: number;
  csrfToken: string;
}) {
  const {data} = useSuspenseQuery(adminParticipantRosterQuery(conversationId));
  const bannedCount = data.participants.filter((participant) => participant.access.banned).length;

  return (
    <main className="admin-roster" id="main">
      <nav className="record-breadcrumb" aria-label="Breadcrumb">
        <Link to="/app/admin">Admin panel</Link><span>/</span>
        <Link to={data.links.conversation}>{data.conversation.title}</Link><span>/</span>
        <span>Participants</span>
      </nav>
      <header className="admin-roster__heading">
        <div>
          <p className="eyebrow">Participant operations</p>
          <h1>{data.conversation.title}</h1>
          <p>Review meaningful contribution activity and manage conversation access.</p>
        </div>
        <dl>
          <div><dt>Joined</dt><dd>{data.participants.length}</dd></div>
          <div><dt>Banned</dt><dd>{bannedCount}</dd></div>
        </dl>
      </header>

      {!data.dataAvailability.statementProgress && (
        <div className="admin-roster__notice" role="status">
          <strong>Statement progress unavailable</strong>
          <span>Argument activity and last engagement remain current.</span>
        </div>
      )}

      <div className="admin-roster__table-wrap">
        <table>
          <caption>
            Engagement counts include actions, not page views. Participant identities are
            visible here only to authorized conversation moderators.
          </caption>
          <thead>
            <tr>
              <th scope="col">Participant</th>
              <th scope="col">Statement votes</th>
              <th scope="col">Arguments</th>
              <th scope="col">Last engagement</th>
              <th scope="col">Access</th>
            </tr>
          </thead>
          <tbody>
            {data.participants.map((participant) => (
              <tr key={participant.participantId}>
                <th scope="row">
                  <strong>{participant.username}</strong>
                  <code>{participant.pseudonym}</code>
                </th>
                <td><Progress participant={participant} /></td>
                <td>
                  <dl className="admin-roster__arguments">
                    <div><dt>Submitted</dt><dd>{participant.arguments.submitted}</dd></div>
                    <div><dt>Prioritized</dt><dd>{participant.arguments.prioritized}</dd></div>
                  </dl>
                </td>
                <td><time dateTime={participant.lastEngagementAt ?? undefined}>{formatDate(participant.lastEngagementAt)}</time></td>
                <td>
                  <ParticipantAccessControl
                    conversationId={conversationId}
                    participant={participant}
                    csrfToken={csrfToken}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {data.participants.length === 0 && <p className="admin-roster__empty">No participants have joined yet.</p>}
      </div>
    </main>
  );
}
