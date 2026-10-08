import {useState, type FormEvent} from 'react';
import {useMutation, useQueryClient, useSuspenseQuery} from '@tanstack/react-query';

import type {components} from '../../api/schema';
import {
  adminLifecycleQuery,
  adminRoleRosterQuery,
  adminSettingsQuery,
  putAdminRoles,
} from '../../api/queries';
import {AdminSettingsFrame} from './admin-settings-page';
import {useMessage} from '../../i18n/messages';

type Role = 'moderator' | 'organizer';
type Roster = components['schemas']['AdminRoleRoster'];

export function AdminRolesPage({conversationId, csrfToken}: {
  conversationId: number; csrfToken: string;
}) {
  const msg = useMessage();
  const queryClient = useQueryClient();
  const {data} = useSuspenseQuery(adminRoleRosterQuery(conversationId));
  // The console frame needs the lifecycle DTO and the settings query for the tab names.
  const {data: settings} = useSuspenseQuery(adminSettingsQuery(conversationId));
  const {data: lifecycle} = useSuspenseQuery(adminLifecycleQuery(conversationId));
  const [participantId, setParticipantId] = useState<number | null>(null);
  const assignment = data.assignments.find((row) => row.participantId === participantId);
  const [chosen, setChosen] = useState<Role[]>([]);
  const mutation = useMutation({
    mutationFn: () => putAdminRoles(conversationId, participantId!, {roles: chosen}, csrfToken),
    onSuccess: (receipt) => {
      // The operator's own role is in the frame (from the lifecycle DTO), and what Settings
      // lets them edit follows from it: both are read again.
      void queryClient.invalidateQueries({queryKey: adminLifecycleQuery(conversationId).queryKey});
      void queryClient.invalidateQueries({queryKey: adminSettingsQuery(conversationId).queryKey});
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

  // A result describes the person and roles it was saved for: another choice clears it.
  function selectParticipant(value: string) {
    mutation.reset();
    const id = value ? Number(value) : null;
    setParticipantId(id);
    const current = data.assignments.find((row) => row.participantId === id);
    setChosen((current?.roles ?? []) as Role[]);
  }
  function toggle(role: Role) {
    mutation.reset();
    setChosen((roles) => roles.includes(role)
      ? roles.filter((value) => value !== role)
      : [...roles, role]);
  }
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (participantId !== null) mutation.mutate();
  }

  return (
    <AdminSettingsFrame
      conversationId={conversationId}
      gatingType={settings.conversation.gatingType}
      lifecycle={lifecycle}
      tab="roles"
    >
      <div>
      <p>See who can moderate or organize {data.conversation.title}.</p>
      <section className="roles-roster" aria-labelledby="role-roster-heading">
        <header><h2 id="role-roster-heading">Assigned</h2><span>{data.assignments.length}</span></header>
        {data.assignments.length ? <ul>{data.assignments.map((row) => (
          <li key={row.participantId}>
            <strong>{row.username}</strong>
            <span>{row.roles.join(' + ')}</span>
          </li>
        ))}</ul> : <p className="moderation-empty">No roles assigned yet.</p>}
      </section>
      {data.capabilities.manageRoles && (
        <section className="roles-editor" aria-labelledby="role-editor-heading">
          <div><p className="eyebrow">Site admin</p><h2 id="role-editor-heading">Replace a role set</h2><p>An empty selection removes all scoped access.</p></div>
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
            {/* Always mounted, keyed per save: a repeat of the same result is read again. */}
            <div role="status">
              {mutation.isSuccess && <p key={mutation.submittedAt}>Added: {mutation.data.added.join(', ') || 'none'} · Removed: {mutation.data.removed.join(', ') || 'none'}</p>}
            </div>
            {/* The server's message is for developers (plan_i18n.md rule 4); the page says its own. */}
            {mutation.isError && <p className="admin-error" role="alert">{msg('adminconv-command-failed')}</p>}
          </form>
        </section>
      )}
      {!data.capabilities.manageRoles && <p className="roles-readonly">Only a site admin can change role assignments.</p>}
      </div>
    </AdminSettingsFrame>
  );
}
