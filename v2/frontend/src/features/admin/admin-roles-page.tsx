import {useState, type FormEvent} from 'react';
import {useMutation, useQueryClient, useSuspenseQuery} from '@tanstack/react-query';
import {Link} from 'react-router-dom';

import type {components} from '../../api/schema';
import {adminRoleRosterQuery, putAdminRoles} from '../../api/queries';

type Role = 'moderator' | 'organizer';
type Roster = components['schemas']['AdminRoleRoster'];

export function AdminRolesPage({conversationId, csrfToken}: {
  conversationId: number; csrfToken: string;
}) {
  const queryClient = useQueryClient();
  const {data} = useSuspenseQuery(adminRoleRosterQuery(conversationId));
  const [participantId, setParticipantId] = useState<number | null>(null);
  const assignment = data.assignments.find((row) => row.participantId === participantId);
  const [chosen, setChosen] = useState<Role[]>([]);
  const mutation = useMutation({
    mutationFn: () => putAdminRoles(conversationId, participantId!, {roles: chosen}, csrfToken),
    onSuccess: (receipt) => {
      queryClient.setQueryData<Roster>(adminRoleRosterQuery(conversationId).queryKey, (roster) => {
        if (!roster) return roster;
        const rest = roster.assignments.filter((row) => row.participantId !== receipt.participantId);
        return {
          ...roster,
          assignments: receipt.roles.length ? [...rest, {
            participantId: receipt.participantId,
            username: receipt.username,
            roles: receipt.roles,
            grantedAt: receipt.roles.map(() => new Date().toISOString()),
          }].sort((a, b) => a.username.localeCompare(b.username)) : rest,
        };
      });
    },
  });

  function selectParticipant(value: string) {
    const id = value ? Number(value) : null;
    setParticipantId(id);
    const current = data.assignments.find((row) => row.participantId === id);
    setChosen((current?.roles ?? []) as Role[]);
  }
  function toggle(role: Role) {
    setChosen((roles) => roles.includes(role)
      ? roles.filter((value) => value !== role)
      : [...roles, role]);
  }
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (participantId !== null) mutation.mutate();
  }

  return (
    <main className="roles-shell" id="main">
      <nav className="record-breadcrumb" aria-label="Breadcrumb">
        <Link to="/admin">Admin panel</Link><span>/</span>
        <Link to={data.links.conversation}>{data.conversation.title}</Link><span>/</span><span>Roles</span>
      </nav>
      <header className="roles-heading">
        <p className="eyebrow">Scoped access</p><h1>Conversation roles</h1>
        <p>See who can moderate or organize {data.conversation.title}.</p>
      </header>
      <section className="roles-roster" aria-labelledby="role-roster-heading">
        <header><h2 id="role-roster-heading">Assigned</h2><span>{data.assignments.length}</span></header>
        {data.assignments.length ? <ul>{data.assignments.map((row) => (
          <li key={row.participantId}>
            <strong>{row.username}</strong>
            <span>{row.roles.join(' + ')}</span>
          </li>
        ))}</ul> : <p className="moderation-empty">No conversation roles assigned.</p>}
      </section>
      {data.capabilities.manageRoles && (
        <section className="roles-editor" aria-labelledby="role-editor-heading">
          <div><p className="eyebrow">Global admin</p><h2 id="role-editor-heading">Replace a role set</h2><p>An empty selection removes all scoped access.</p></div>
          <form onSubmit={submit}>
            <label htmlFor="role-participant">Participant</label>
            <select id="role-participant" value={participantId ?? ''} onChange={(event) => selectParticipant(event.target.value)} required>
              <option value="">Select an account</option>
              {data.candidates.map((row) => <option key={row.participantId} value={row.participantId}>{row.username}</option>)}
            </select>
            <fieldset disabled={participantId === null || mutation.isPending}>
              <legend>Roles</legend>
              {data.availableRoles.map((role) => <label key={role}>
                <input type="checkbox" checked={chosen.includes(role)} onChange={() => toggle(role)} /> {role}
              </label>)}
            </fieldset>
            <button type="submit" disabled={participantId === null || mutation.isPending}>{mutation.isPending ? 'Saving…' : 'Save role set'}</button>
            {mutation.isSuccess && <p role="status">Added: {mutation.data.added.join(', ') || 'none'} · Removed: {mutation.data.removed.join(', ') || 'none'}</p>}
            {mutation.isError && <p className="command-error" role="alert">{mutation.error.message}</p>}
          </form>
        </section>
      )}
      {!data.capabilities.manageRoles && <p className="roles-readonly">Only a global admin can change role assignments.</p>}
    </main>
  );
}
