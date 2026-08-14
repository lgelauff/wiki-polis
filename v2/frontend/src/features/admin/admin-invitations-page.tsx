import {useState, type FormEvent} from 'react';
import {useMutation, useQueryClient, useSuspenseQuery} from '@tanstack/react-query';
import {Link} from 'react-router-dom';

import type {components} from '../../api/schema';
import {
  adminInvitationRosterQuery,
  deleteAdminInvitation,
  putAdminInvitations,
} from '../../api/queries';

type Roster = components['schemas']['AdminInvitationRoster'];

function formatDate(value: string): string {
  return new Intl.DateTimeFormat(undefined, {dateStyle: 'medium'}).format(new Date(value));
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
  const [lastOutcome, setLastOutcome] = useState<components['schemas']['AdminInvitationBatchReceipt']['outcome'] | null>(null);
  const addMutation = useMutation({
    mutationFn: (usernames: string[]) => putAdminInvitations(
      conversationId, {usernames}, csrfToken,
    ),
    onSuccess: (receipt) => {
      queryClient.setQueryData<Roster>(
        adminInvitationRosterQuery(conversationId).queryKey,
        (roster) => roster ? {...roster, invitations: receipt.invitations} : roster,
      );
      setLastOutcome(receipt.outcome);
      setInput('');
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

  return (
    <main className="invitation-shell" id="main">
      <nav className="record-breadcrumb" aria-label="Breadcrumb">
        <Link to="/app/admin">Admin panel</Link><span>/</span>
        <a href={data.links.conversation}>{data.conversation.title}</a><span>/</span>
        <span>Invitations</span>
      </nav>
      <header className="invitation-heading">
        <div>
          <p className="eyebrow">Conversation access</p>
          <h1>Invitations</h1>
          <p>{data.conversation.title}</p>
        </div>
        <div className="invitation-policy">
          <span>Access policy</span><strong>{data.conversation.accessPolicy.replace('_', ' ')}</strong>
        </div>
      </header>
      {data.conversation.accessPolicy !== 'invite_only' && (
        <div className="admin-roster__notice" role="status">
          <strong>Invitations are inactive</strong>
          <span>They take effect only when the conversation policy is invite only.</span>
        </div>
      )}
      <section className="invitation-add" aria-labelledby="add-invitations-heading">
        <div>
          <p className="eyebrow">Bulk entry</p>
          <h2 id="add-invitations-heading">Add Wikimedia usernames</h2>
          <p>Enter one username per line. Existing and duplicate entries are safe to submit again.</p>
        </div>
        <form onSubmit={submit}>
          <label htmlFor="invitation-usernames">Wikimedia usernames</label>
          <textarea
            id="invitation-usernames"
            rows={7}
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder={'Username1\nUsername2\nUsername3'}
            disabled={addMutation.isPending}
          />
          <button type="submit" disabled={!input.trim() || addMutation.isPending}>
            {addMutation.isPending ? 'Adding…' : 'Add invitations'}
          </button>
          {addMutation.isError && <p className="command-error" role="alert">{addMutation.error.message}</p>}
          {lastOutcome && (
            <p className="invitation-outcome" role="status">
              {lastOutcome.added} added · {lastOutcome.alreadyPresent} already present · {lastOutcome.duplicateInputs} duplicate input · {lastOutcome.concurrentConflicts} concurrent
            </p>
          )}
        </form>
      </section>
      <section className="invitation-roster" aria-labelledby="invitation-roster-heading">
        <header><h2 id="invitation-roster-heading">Invited accounts</h2><span>{data.invitations.length}</span></header>
        {data.invitations.length ? (
          <ul>
            {data.invitations.map((invitation) => (
              <li key={invitation.id}>
                <strong>{invitation.username}</strong>
                <span>Added {formatDate(invitation.createdAt)}</span>
                <button
                  type="button"
                  onClick={() => removeMutation.mutate(invitation.id)}
                  disabled={removeMutation.isPending}
                >Remove {invitation.username}</button>
              </li>
            ))}
          </ul>
        ) : <p className="moderation-empty">No invitations yet.</p>}
        {removeMutation.isError && <p className="command-error" role="alert">{removeMutation.error.message}</p>}
      </section>
    </main>
  );
}
