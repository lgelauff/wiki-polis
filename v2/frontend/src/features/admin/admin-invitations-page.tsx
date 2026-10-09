import {useCallback, useId, useState, type FormEvent} from 'react';
import {useMutation, useQueryClient, useSuspenseQuery} from '@tanstack/react-query';

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
import {useRowFocus} from './admin-row-focus';
import {AdminTime} from './admin-time';
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

/** What an add did, in two sentences at most: how many were added, and how many were not
 *  (already on the list, typed twice, or added by someone else at the same moment). */
function invitationOutcomeMessage(
  msg: Message,
  outcome: components['schemas']['AdminInvitationBatchReceipt']['outcome'],
): string {
  const skipped = outcome.alreadyPresent + outcome.duplicateInputs + outcome.concurrentConflicts;
  const added = msg('admin-invitations-added', outcome.added);
  return skipped ? `${added} ${msg('admin-invitations-skipped', skipped)}` : added;
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
  // The add form's result is said on its own status line; a toast is for the row action.
  const [result, setResult] = useState<{error: boolean; message: string} | null>(null);
  const [toast, setToast] = useState<LegacyToastMessage | null>(null);
  const dismissToast = useCallback(() => setToast(null), []);
  const announcer = useAnnouncer();
  // Where focus goes once a removed invitation's row has left the list: the next row's
  // Remove (the previous row's when the last went), or the empty-list line.
  const {listRef, emptyRef, rowRemoved} = useRowFocus(data.invitations.map((invitation) => invitation.id));
  const addMutation = useMutation({
    mutationFn: (usernames: string[]) => putAdminInvitations(
      conversationId, {usernames}, csrfToken,
    ),
    onSuccess: (receipt) => {
      queryClient.setQueryData<Roster>(
        adminInvitationRosterQuery(conversationId).queryKey,
        (roster) => roster ? {...roster, invitations: receipt.invitations} : roster,
      );
      setResult({error: false, message: invitationOutcomeMessage(msg, receipt.outcome)});
      setInput('');
    },
    onError: () => {
      // The list stays in the textarea: the save failed, so whoever typed it
      // still needs it to retry or to correct one name.
      setResult({error: true, message: msg('adminconv-command-failed')});
    },
  });
  const removeMutation = useMutation({
    mutationFn: (invitationId: number) => deleteAdminInvitation(
      conversationId, invitationId, csrfToken,
    ),
    onSuccess: (receipt, invitationId) => {
      rowRemoved(invitationId);
      const removed = data.invitations.find((invitation) => invitation.id === invitationId);
      if (removed) announcer.announce(msg('admin-invitations-removed', removed.username));
      queryClient.setQueryData<Roster>(
        adminInvitationRosterQuery(conversationId).queryKey,
        (roster) => roster ? {...roster, invitations: receipt.invitations} : roster,
      );
    },
    onError: () => setToast({id: Date.now(), category: 'error', message: msg('adminconv-command-failed')}),
  });

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    // One batch at a time: a second Enter or click while the first is on its way would
    // send the same names again.
    if (addMutation.isPending) return;
    const usernames = input.split('\n').map((value) => value.trim()).filter(Boolean);
    if (usernames.length) addMutation.mutate(usernames);
  }

  // "Signed in" = the invitation is bound to a Wikimedia account by user id, which
  // happens when that account logs in to the site. It says nothing about whether that
  // person has joined *this* consultation. "Not signed in yet" = no account with this
  // exact name has logged in to the site yet, so the invitation is not bound to one.
  // Invites only admit anyone while the invitation list is the answer to who gets in, so
  // only then can more be added. Otherwise one line, shown to every viewer above the form
  // and the list, says the list is not in effect and names the access policy that is (#478);
  // for an organizer the add form is greyed out, with that line as its reason. The stored
  // list stays shown either way: with its Remove buttons for an organizer, without them for
  // a moderator.
  const invitationList = settings.conversation.gatingType === 'invite_only';
  // Organizers (and site admins) manage the list; a moderator reads it: no add form and no
  // Remove at all, not greyed out (owner, 2026-10-09).
  const canManage = data.capabilities.manageInvitations;
  const unavailableId = useId();
  const headingId = useId();
  const listHeadingId = useId();
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
        {!invitationList && <p className="admin-note" id={unavailableId}>
          {msg('admin-invitations-unavailable', admissionName(msg, settings.conversation))}
        </p>}
        {canManage && <section className="admin-form" aria-labelledby={headingId}>
          <h2 id={headingId}>{msg('invites-add-heading')}</h2>
          <form onSubmit={submit}>
            <label className="admin-field admin-field--medium">
              {msg('invites-label-usernames')}
              <textarea
                name="mw_usernames"
                rows={6}
                value={input}
                disabled={!invitationList}
                aria-describedby={invitationList ? undefined : unavailableId}
                onChange={(event) => setInput(event.target.value)}
              />
            </label>
            <div className="admin-form__actions">
              <button type="submit" className="admin-button admin-button--primary" disabled={!invitationList || addMutation.isPending}
                aria-describedby={invitationList ? undefined : unavailableId}>{msg('invites-add-heading')}</button>
            </div>
            {/* The status line is always mounted, keyed per attempt, so a repeat is read again. */}
            <div role="status">
              {result && !result.error && <p className="admin-status" key={addMutation.submittedAt}>{result.message}</p>}
            </div>
            {result?.error && <p className="admin-error" role="alert">{result.message}</p>}
          </form>
        </section>}

        {/* One row per invitation: the name and whether that account has signed in to the
            site, the day it was added, and (for an organizer) Remove. Not a table: no column
            is compared. Its own heading, for every viewer: a moderator has no add form, and
            the list would otherwise be a bare list under the tab strip. Not the tab's name,
            which the frame does not repeat as a heading. */}
        <section aria-labelledby={listHeadingId}>
          <h2 id={listHeadingId}>{msg('admin-invitations-list-heading')}</h2>
          {data.invitations.length ? (
            <ul className="admin-rows" ref={listRef}>
              {data.invitations.map((invitation) => (
                <li className="admin-row" key={invitation.id} data-row-id={invitation.id}>
                  <div className="admin-row__text">
                    {invitation.username}
                    <span className="admin-row__suffix">
                      {' · '}
                      {invitation.signedIn
                        ? msg('admin-invitations-signed-in')
                        : msg('admin-invitations-not-signed-in')}
                    </span>
                  </div>
                  <div className="admin-row__counts"><AdminTime value={invitation.createdAt} /></div>
                  {canManage && <div className="admin-row__actions">
                    {/* Not red: a removed invitation can be added again. */}
                    <button
                      type="button"
                      className="admin-row__text-button"
                      // Only the row on its way out: the others stay operable, and keep focus.
                      disabled={removeMutation.isPending && removeMutation.variables === invitation.id}
                      aria-label={msg('admin-invitations-remove-aria', invitation.username)}
                      onClick={() => removeMutation.mutate(invitation.id)}
                    >
                      {msg('admin-btn-remove')}
                    </button>
                  </div>}
                </li>
              ))}
            </ul>
          ) : <p className="admin-empty" ref={emptyRef} tabIndex={-1}>{msg('invites-empty')}</p>}
        </section>
      </div>
    </AdminSettingsFrame>
  );
}
