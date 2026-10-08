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
import {useMessage, type Message} from '../../i18n/messages';

type Role = 'moderator' | 'organizer';

/** A role in the console's words, the ones the top bar uses for the operator's own role. */
function roleName(msg: Message, role: string): string {
  if (role === 'moderator') return msg('admin-shell-role-moderator');
  if (role === 'organizer') return msg('admin-shell-role-organizer');
  return role;
}
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
      <section aria-labelledby="role-roster-heading">
        <h2 id="role-roster-heading">{msg('admin-roles-assigned')}{' '}<span className="admin-count">{data.assignments.length}</span></h2>
        {/* One row per person, their roles as plain words after the name. */}
        {data.assignments.length ? <ul className="admin-rows">{data.assignments.map((row) => (
          <li className="admin-row" key={row.participantId}>
            <div className="admin-row__text">
              {row.username}
              <span className="admin-row__suffix">{' · '}{row.roles.map((role) => roleName(msg, role)).join(', ')}</span>
            </div>
          </li>
        ))}</ul> : <p className="admin-empty">{msg('admin-roles-empty')}</p>}
      </section>
      {data.capabilities.manageRoles && (
        <section aria-labelledby="role-editor-heading">
          <h2 id="role-editor-heading">{msg('admin-roles-change')}</h2>
          <form onSubmit={submit}>
            <label className="admin-field admin-field--medium">{msg('admin-th-participant')}
              <select value={participantId ?? ''} onChange={(event) => selectParticipant(event.target.value)} required>
                <option value="">—</option>
                {data.candidates.map((row) => <option key={row.participantId} value={row.participantId}>{row.username}</option>)}
              </select>
            </label>
            <fieldset className="admin-choices" disabled={participantId === null || mutation.isPending}>
              <legend>{msg('admin-settings-tab-roles')}</legend>
              {data.availableRoles.map((role) => <label key={role}>
                <input type="checkbox" checked={chosen.includes(role)} onChange={() => toggle(role)} /> {roleName(msg, role)}
              </label>)}
            </fieldset>
            <div className="admin-form__actions">
              <button type="submit" className="admin-button admin-button--primary" disabled={participantId === null || mutation.isPending}>{mutation.isPending ? msg('admin-saving') : msg('admin-save')}</button>
            </div>
            {/* The roster above shows the new role set; the status line says the save went
                through, or that there was nothing to change. Always mounted, keyed per save:
                a repeat of the same result is read again. */}
            <div role="status">
              {mutation.isSuccess && <p className="admin-status" key={mutation.submittedAt}>
                {mutation.data.added.length || mutation.data.removed.length
                  ? msg('admin-settings-saved') : msg('admin-settings-unchanged')}
              </p>}
            </div>
            {/* The server's message is for developers (plan_i18n.md rule 4); the page says its own. */}
            {mutation.isError && <p className="admin-error" role="alert">{msg('adminconv-command-failed')}</p>}
          </form>
        </section>
      )}
      </div>
    </AdminSettingsFrame>
  );
}
