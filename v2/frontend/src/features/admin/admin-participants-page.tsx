import {useCallback, useState, type FormEvent} from 'react';
import {useMutation, useQueryClient, useSuspenseQuery} from '@tanstack/react-query';
import {Link} from 'react-router-dom';

import type {components} from '../../api/schema';
import {
  adminParticipantRosterQuery,
  putAdminParticipantAccess,
} from '../../api/queries';
import {LegacyShell} from '../legacy/legacy-shell';
import {LegacyToast, type LegacyToastMessage} from '../legacy/legacy-toast';

type Participant = components['schemas']['AdminParticipant'];
type Roster = components['schemas']['AdminParticipantRoster'];

function legacyTruncate(value: string, length = 28, leeway = 5): string {
  return value.length <= length + leeway ? value : `${value.slice(0, length - 1)}…`;
}

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
        <div style={{fontSize: 13, marginBottom: '.5rem'}}>
          <strong>Banned</strong>{' '}
          {participant.access.changedAt && (
            <span className="muted">since {formatLegacyDate(participant.access.changedAt)}</span>
          )}
          {participant.access.summary && (
            <div className="muted" style={{marginTop: '.25rem'}}>{participant.access.summary}</div>
          )}
        </div>
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
  const {data} = useSuspenseQuery(adminParticipantRosterQuery(conversationId));
  const [toast, setToast] = useState<LegacyToastMessage | null>(null);
  const dismissToast = useCallback(() => setToast(null), []);
  const title = data.conversation.title;

  return (
    <LegacyShell
      headerMode="admin"
      title={`Participants — ${title} — ProtoWiki`}
      headerCrumb={(
        <nav className="header-crumb" aria-label="Admin breadcrumb">
          <span className="header-crumb-sep">/</span>
          <Link to="/admin">Admin panel</Link>
          <span className="header-crumb-sep">/</span>
          <Link to={data.links.conversation}>{legacyTruncate(title)}</Link>
          <span className="header-crumb-sep">/</span>
          <span>Participants</span>
        </nav>
      )}
      toast={<LegacyToast toast={toast} onDismiss={dismissToast} />}
    >
      <div className="container">
        <h2>Participants — {title}</h2>

        <p className="muted" style={{fontSize: 13, marginBottom: '1.5rem'}}>
          Engagement is based on meaningful actions in this conversation: statement votes,
          {' '}statement submissions, argument actions, and informed votes. Page views are not tracked.
        </p>

        {!data.dataAvailability.statementProgress && (
          <div className="landing-section" style={{marginBottom: '1.5rem'}}>
            <p className="muted" style={{fontSize: 13, marginBottom: 0}}>
              Statement vote progress is unavailable because the Polis statistics database could
              {' '}not be read. Argument counts and last engagement are shown from the local database.
            </p>
          </div>
        )}

        <table className="admin-table">
          <thead>
            <tr>
              <th>Username</th>
              <th>Statements voted</th>
              <th>Statements remaining</th>
              <th>Arguments submitted</th>
              <th>Arguments voted</th>
              <th>Last engagement</th>
              <th>Access</th>
            </tr>
          </thead>
          <tbody>
            {data.participants.map((participant) => {
              const progress = participant.statementProgress;
              const lastEngagement = formatLegacyDateTime(participant.lastEngagementAt);
              return (
                <tr key={participant.participantId}>
                  <td>{participant.username}</td>
                  <td>{progress ? `${progress.voted} / ${progress.total}` : <span className="muted">—</span>}</td>
                  <td>{progress ? progress.remaining : <span className="muted">—</span>}</td>
                  <td>{participant.arguments.submitted}</td>
                  <td>{participant.arguments.prioritized}</td>
                  <td>{lastEngagement ?? <span className="muted">No actions yet</span>}</td>
                  <td style={{minWidth: 210}}>
                    <ParticipantAccessControl
                      conversationId={conversationId}
                      participant={participant}
                      csrfToken={csrfToken}
                      setToast={setToast}
                    />
                  </td>
                </tr>
              );
            })}
            {!data.participants.length && (
              <tr><td colSpan={7} className="muted">No participants have joined yet.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </LegacyShell>
  );
}
