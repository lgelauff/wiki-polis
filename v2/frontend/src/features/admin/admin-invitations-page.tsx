import {useCallback, useId, useState, type FormEvent} from 'react';
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

function invitationOutcomeMessage(
  outcome: components['schemas']['AdminInvitationBatchReceipt']['outcome'],
): string {
  const summary = [`${outcome.added} added`];
  if (outcome.alreadyPresent) summary.push(`${outcome.alreadyPresent} already present`);
  if (outcome.duplicateInputs) summary.push(`${outcome.duplicateInputs} duplicate input`);
  if (outcome.concurrentConflicts) {
    summary.push(`${outcome.concurrentConflicts} added concurrently by another moderator`);
  }
  return `Invitations: ${summary.join('; ')}.`;
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
      setResult({error: false, message: invitationOutcomeMessage(receipt.outcome)});
      setInput('');
    },
    onError: () => {
      // The list stays in the textarea: the save failed, so whoever typed it
      // still needs it to retry or to correct one name.
      setResult({error: true, message: "Couldn't save invitations — please review the list and retry."});
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

  const title = data.conversation.title;
  // "Signed in" = the invitation is bound to a Wikimedia account by user id, which
  // happens when that account logs in to the site. It says nothing about whether that
  // person has joined *this* consultation. "Not signed in yet" = no account with this
  // exact name has logged in to the site yet, so the invitation is not bound to one.
  // Invites only admit anyone while the invitation list is the answer to who gets in, so
  // only then can more be added. Otherwise the form is shown greyed out, with one line
  // naming the access policy in effect as the reason (#478). The stored list stays either
  // way, with its remove buttons.
  const invitationList = settings.conversation.gatingType === 'invite_only';
  const unavailableId = useId();
  const headingId = useId();
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
        <section className="admin-form" aria-labelledby={headingId}>
          <h2 id={headingId}>{msg('invites-add-heading')}</h2>
          {!invitationList && <p className="admin-note" id={unavailableId}>
            {msg('admin-invitations-unavailable', admissionName(msg, settings.conversation))}
          </p>}
          <form onSubmit={submit}>
            <label className="admin-field admin-field--medium">
              Wikimedia usernames (one per line)
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
                aria-describedby={invitationList ? undefined : unavailableId}>Add</button>
            </div>
            {/* The status line is always mounted, keyed per attempt, so a repeat is read again. */}
            <div role="status">
              {result && !result.error && <p className="admin-status" key={addMutation.submittedAt}>{result.message}</p>}
            </div>
            {result?.error && <p className="admin-error" role="alert">{result.message}</p>}
          </form>
        </section>

        {/* One row per invitation: the name and whether that account has signed in to the
            site, the day it was added, and Remove. Not a table: no column is compared. */}
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
                <div className="admin-row__actions">
                  {/* Not red: a removed invitation can be added again. */}
                  <button
                    type="button"
                    className="admin-row__text-button"
                    // Only the row on its way out: the others stay operable, and keep focus.
                    disabled={removeMutation.isPending && removeMutation.variables === invitation.id}
                    aria-label={`Remove invitation for ${invitation.username}`}
                    onClick={() => removeMutation.mutate(invitation.id)}
                  >
                    {msg('admin-btn-remove')}
                  </button>
                </div>
              </li>
            ))}
          </ul>
        ) : <p className="admin-empty" ref={emptyRef} tabIndex={-1}>{msg('invites-empty')}</p>}
      </div>
    </AdminSettingsFrame>
  );
}
