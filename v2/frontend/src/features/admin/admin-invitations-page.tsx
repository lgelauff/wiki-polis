import {useCallback, useEffect, useId, useRef, useState, type FormEvent} from 'react';
import {useMutation, useQueryClient, useSuspenseQuery} from '@tanstack/react-query';
import {Link} from 'react-router-dom';

import type {components} from '../../api/schema';
import {
  adminInvitationRosterQuery,
  adminLifecycleQuery,
  adminSettingsQuery,
  deleteAdminInvitation,
  putAdminInvitations,
} from '../../api/queries';
import {AdminSettingsFrame} from './admin-settings-page';
import {useAnnouncer} from './admin-announcer';
import {LegacyToast, type LegacyToastMessage} from '../legacy/legacy-toast';
import {useMessage, type Message} from '../../i18n/messages';
import {accessPolicyLabel} from '../../i18n/server-labels';

type Roster = components['schemas']['AdminInvitationRoster'];

type Settings = components['schemas']['AdminSettings'];

/** The answer to who gets in, in the words the Access tab uses for it. */
function admissionName(msg: Message, conversation: Settings['conversation']): string {
  if (conversation.accessPolicy === 'demo') return msg('admin-access-admission-practice');
  if (!conversation.gated) return msg('admin-access-admission-anyone');
  switch (conversation.gatingType) {
    case 'invite_only': return msg('admin-access-admission-invited');
    case 'voucher': return msg('admin-access-admission-voucher');
    case 'wiki_based': return msg('admin-access-admission-wiki');
    default: return accessPolicyLabel(msg, conversation.accessPolicy);
  }
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
  const msg = useMessage();
  const queryClient = useQueryClient();
  const {data} = useSuspenseQuery(adminInvitationRosterQuery(conversationId));
  // The console frame needs the lifecycle DTO and the settings query for the tab names.
  const {data: settings} = useSuspenseQuery(adminSettingsQuery(conversationId));
  const {data: lifecycle} = useSuspenseQuery(adminLifecycleQuery(conversationId));
  const [input, setInput] = useState('');
  const [toast, setToast] = useState<LegacyToastMessage | null>(null);
  const dismissToast = useCallback(() => setToast(null), []);
  const announcer = useAnnouncer();
  // Where focus goes once a removed invitation's row has left the table: the next row's
  // Remove (the previous row's when the last went), or the empty-list line.
  const rowsRef = useRef<HTMLTableSectionElement>(null);
  const emptyRef = useRef<HTMLTableCellElement>(null);
  const [focusAfterRemove, setFocusAfterRemove] = useState<{removed: number; next: number | null} | null>(null);
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
      // The list stays in the textarea: the save failed, so whoever typed it
      // still needs it to retry or to correct one name.
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
    onSuccess: (receipt, invitationId) => {
      const shown = data.invitations.map((invitation) => invitation.id);
      const index = shown.indexOf(invitationId);
      const rest = shown.filter((id) => id !== invitationId);
      setFocusAfterRemove({removed: invitationId, next: rest[index] ?? rest[index - 1] ?? null});
      const removed = data.invitations.find((invitation) => invitation.id === invitationId);
      if (removed) announcer.announce(msg('admin-invitations-removed', removed.username));
      queryClient.setQueryData<Roster>(
        adminInvitationRosterQuery(conversationId).queryKey,
        (roster) => roster ? {...roster, invitations: receipt.invitations} : roster,
      );
    },
  });
  useEffect(() => {
    if (!focusAfterRemove) return;
    if (data.invitations.some((invitation) => invitation.id === focusAfterRemove.removed)) return;
    setFocusAfterRemove(null);
    const next = focusAfterRemove.next === null ? null : rowsRef.current?.querySelector<HTMLElement>(
      `[data-row-id="${focusAfterRemove.next}"] button`,
    );
    (next ?? emptyRef.current)?.focus();
  }, [data.invitations, focusAfterRemove]);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    // One batch at a time: a second Enter or click while the first is on its way would
    // send the same names again.
    if (addMutation.isPending) return;
    const usernames = input.split('\n').map((value) => value.trim()).filter(Boolean);
    if (usernames.length) addMutation.mutate(usernames);
  }

  const title = data.conversation.title;
  const invited = data.invitations.length;
  // "Linked" = the invitation is bound to a Wikimedia account by user id, which
  // happens when that account logs in to the site. It says nothing about
  // whether that person has joined *this* consultation. "Never logged in" = no
  // account with this exact name has logged in to the site yet, so the
  // invitation is not bound to an account.
  const linked = data.invitations.filter((invitation) => invitation.signedIn).length;
  // Invites only admit anyone while the invitation list is the answer to who gets in, so
  // only then can more be added. Otherwise the form is shown greyed out, with one line
  // naming the access policy in effect as the reason (#478). The stored list stays either
  // way, with its remove buttons.
  const invitationList = settings.conversation.gatingType === 'invite_only';
  const unavailableId = useId();
  return (
    <AdminSettingsFrame
      conversationId={conversationId}
      gatingType={settings.conversation.gatingType}
      lifecycle={lifecycle}
      tab="invitations"
      toast={<LegacyToast toast={toast} onDismiss={dismissToast} />}
      announcer={announcer}
    >
      <div>
        <p>
          <Link to={`/c/${data.conversation.slug}/about`}>{title}</Link>
        </p>
        <p className="muted" style={{marginBottom: '1.25rem'}}>
          Access policy: <strong>{accessPolicyLabel(msg, data.conversation.accessPolicy)}</strong>
        </p>
        {invited > 0 && (
          <p className="muted" style={{marginBottom: '1.25rem'}}>
            {invited} invited · {linked} linked · {invited - linked} never logged in
          </p>
        )}

        <div className="edit-form">
          <h2>Add invites</h2>
          {!invitationList && <p className="muted" id={unavailableId}>
            {msg('admin-invitations-unavailable', admissionName(msg, settings.conversation))}
          </p>}
          <form onSubmit={submit}>
            <label>
              Wikimedia usernames (one per line)
              <textarea
                name="mw_usernames"
                rows={6}
                value={input}
                disabled={!invitationList}
                aria-describedby={invitationList ? undefined : unavailableId}
                onChange={(event) => setInput(event.target.value)}
                placeholder={'Username1\nUsername2\nUsername3'}
              />
            </label>
            <button type="submit" disabled={!invitationList || addMutation.isPending}
              aria-describedby={invitationList ? undefined : unavailableId}>Add</button>
          </form>
        </div>

        {/* The table scrolls inside its own box at 320px, so the page never scrolls sideways. */}
        <div className="admin-table-wrap">
          <table className="admin-table">
            <thead>
              <tr><th>Username</th><th>Status</th><th>Added</th><th /></tr>
            </thead>
            <tbody ref={rowsRef}>
              {data.invitations.map((invitation) => (
                <tr key={invitation.id} data-row-id={invitation.id}>
                  <td>{invitation.username}</td>
                  <td>{invitation.signedIn ? 'Linked' : 'Never logged in'}</td>
                  <td className="muted">{formatLegacyDate(invitation.createdAt)}</td>
                  <td>
                    <form
                      onSubmit={(event) => {
                        event.preventDefault();
                        removeMutation.mutate(invitation.id);
                      }}
                      style={{display: 'inline'}}
                    >
                      <button
                        type="submit"
                        className="btn-small btn-danger"
                        aria-label={`Remove invitation for ${invitation.username}`}
                      >
                        remove
                      </button>
                    </form>
                  </td>
                </tr>
              ))}
              {!data.invitations.length && (
                <tr><td colSpan={4} className="muted" ref={emptyRef} tabIndex={-1}>No invites yet.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </AdminSettingsFrame>
  );
}
