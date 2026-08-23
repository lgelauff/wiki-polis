import {useCallback, useState, type FormEvent} from 'react';
import {useMutation, useQueryClient, useSuspenseQuery} from '@tanstack/react-query';
import {Link} from 'react-router-dom';

import type {components} from '../../api/schema';
import {
  adminInvitationRosterQuery,
  deleteAdminInvitation,
  putAdminInvitations,
} from '../../api/queries';
import {LegacyShell} from '../legacy/legacy-shell';
import {LegacyToast, type LegacyToastMessage} from '../legacy/legacy-toast';

type Roster = components['schemas']['AdminInvitationRoster'];

function legacyTruncate(value: string, length = 28, leeway = 5): string {
  return value.length <= length + leeway ? value : `${value.slice(0, length - 1)}…`;
}

function formatLegacyDate(value: string): string {
  return new Date(value).toISOString().slice(0, 10);
}

function invitationOutcomeMessage(
  outcome: components['schemas']['AdminInvitationBatchReceipt']['outcome'],
): string {
  const summary = [`${outcome.added} added`];
  if (outcome.alreadyPresent) summary.push(`${outcome.alreadyPresent} already present`);
  if (outcome.duplicateInputs) summary.push(`${outcome.duplicateInputs} duplicate input`);
  if (outcome.concurrentConflicts) {
    summary.push(`${outcome.concurrentConflicts} added concurrently by another moderator`);
  }
  return `Invites: ${summary.join('; ')}.`;
}

export function AdminInvitationsPage({
  conversationId, csrfToken,
}: {
  conversationId: number;
  csrfToken: string;
}) {
  const queryClient = useQueryClient();
  const {data} = useSuspenseQuery(adminInvitationRosterQuery(conversationId));
  const [input, setInput] = useState('');
  const [toast, setToast] = useState<LegacyToastMessage | null>(null);
  const dismissToast = useCallback(() => setToast(null), []);
  const addMutation = useMutation({
    mutationFn: (usernames: string[]) => putAdminInvitations(
      conversationId, {usernames}, csrfToken,
    ),
    onSuccess: (receipt) => {
      queryClient.setQueryData<Roster>(
        adminInvitationRosterQuery(conversationId).queryKey,
        (roster) => roster ? {...roster, invitations: receipt.invitations} : roster,
      );
      setToast({
        id: Date.now(),
        category: receipt.outcome.concurrentConflicts ? 'info' : 'success',
        message: invitationOutcomeMessage(receipt.outcome),
      });
      setInput('');
    },
    onError: () => {
      setInput('');
      setToast({
        id: Date.now(),
        category: 'error',
        message: "Couldn't save invites — please review the list and retry.",
      });
    },
  });
  const removeMutation = useMutation({
    mutationFn: (invitationId: number) => deleteAdminInvitation(
      conversationId, invitationId, csrfToken,
    ),
    onSuccess: (receipt) => {
      queryClient.setQueryData<Roster>(
        adminInvitationRosterQuery(conversationId).queryKey,
        (roster) => roster ? {...roster, invitations: receipt.invitations} : roster,
      );
    },
  });

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const usernames = input.split('\n').map((value) => value.trim()).filter(Boolean);
    if (usernames.length) addMutation.mutate(usernames);
  }

  const title = data.conversation.title;
  return (
    <LegacyShell
      headerMode="admin"
      title={`Invites — ${title} — ProtoWiki`}
      headerCrumb={(
        <nav className="header-crumb" aria-label="Admin breadcrumb">
          <span className="header-crumb-sep">/</span>
          <Link to="/admin">Admin panel</Link>
          <span className="header-crumb-sep">/</span>
          <Link to={data.links.conversation}>{legacyTruncate(title)}</Link>
          <span className="header-crumb-sep">/</span>
          <span>Invites</span>
        </nav>
      )}
      toast={<LegacyToast toast={toast} onDismiss={dismissToast} />}
    >
      <div className="container">
        <h2>
          Invites — <Link to={`/c/${data.conversation.slug}/about`}>{title}</Link>
        </h2>
        <p className="muted" style={{marginBottom: '1.25rem'}}>
          Access policy: <strong>{data.conversation.accessPolicy}</strong>
        </p>

        {data.conversation.accessPolicy !== 'invite_only' && (
          <div className="landing-section">
            <p className="muted">
              This conversation uses <strong>{data.conversation.accessPolicy}</strong> access.
              {' '}Invites only take effect when the policy is set to <strong>invite_only</strong>.
            </p>
          </div>
        )}

        <div className="edit-form">
          <h3>Add invites</h3>
          <form onSubmit={submit}>
            <label>
              Wikimedia usernames (one per line)
              <textarea
                name="mw_usernames"
                rows={6}
                value={input}
                onChange={(event) => setInput(event.target.value)}
                placeholder={'Username1\nUsername2\nUsername3'}
              />
            </label>
            <button type="submit">Add</button>
          </form>
        </div>

        <table className="admin-table">
          <thead>
            <tr><th>Username</th><th>Added</th><th /></tr>
          </thead>
          <tbody>
            {data.invitations.map((invitation) => (
              <tr key={invitation.id}>
                <td>{invitation.username}</td>
                <td className="muted">{formatLegacyDate(invitation.createdAt)}</td>
                <td>
                  <form
                    onSubmit={(event) => {
                      event.preventDefault();
                      removeMutation.mutate(invitation.id);
                    }}
                    style={{display: 'inline'}}
                  >
                    <button type="submit" className="btn-small btn-danger">remove</button>
                  </form>
                </td>
              </tr>
            ))}
            {!data.invitations.length && (
              <tr><td colSpan={3} className="muted">No invites yet.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </LegacyShell>
  );
}
