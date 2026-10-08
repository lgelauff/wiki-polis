import {useState} from 'react';
import {useMutation, useQueryClient} from '@tanstack/react-query';

import type {components} from '../../api/schema';
import {adminParticipantRosterQuery, putAdminParticipantAccess} from '../../api/queries';
import {useMessage} from '../../i18n/messages';
import type {LegacyToastMessage} from '../legacy/legacy-toast';

type Participant = components['schemas']['AdminParticipant'];
type Roster = components['schemas']['AdminParticipantRoster'];

/** Block or unblock one person from contributing.
 *
 * The server's field is a ban and the wording is the console's own: a ban takes the ability
 * to contribute away and nothing else, and the dialog on the board says so. There is no
 * "access withdrawn" state here because the API does not return one (#473 parks it).
 *
 * One component for Moderation › People and Content › Participants, so the same action is
 * drawn the same way on both: a labelled note field and a text button. The new state shows
 * in the row; the toast is what a screen reader hears.
 *
 * Every row has this field and this button, so `name` -- the person as their row shows
 * them, the pseudonym unless the page says otherwise -- follows the visible words in both
 * accessible names, to tell one row's controls from the next one's. */
export function PersonAccessControl({conversationId, participant, csrfToken, onFeedback, name}: {
  conversationId: number;
  participant: Participant;
  name?: string | undefined;
  csrfToken: string;
  onFeedback: (toast: LegacyToastMessage) => void;
}) {
  const msg = useMessage();
  const queryClient = useQueryClient();
  const [summary, setSummary] = useState('');
  const desiredBanned = !participant.access.banned;
  // The field's own label, beside it: an example in the field would vanish as you type.
  const label = msg(participant.access.banned
    ? 'participants-unban-note-ph'
    : 'participants-ban-reason-ph');
  const mutation = useMutation({
    mutationFn: () => putAdminParticipantAccess(
      conversationId, participant.participantId,
      {banned: desiredBanned, summary: summary || null}, csrfToken,
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
      // The row shows the new state in place; the toast is what a screen reader hears, and
      // what says so when the person already was in the state asked for.
      const changed = receipt.banned ? msg('flash-banned') : msg('flash-unbanned');
      const unchanged = receipt.banned
        ? msg('flash-already-banned')
        : msg('admin-moderation-person-already-allowed');
      onFeedback({
        id: Date.now(),
        category: receipt.changed ? 'success' : 'warning',
        message: receipt.changed ? changed : unchanged,
      });
    },
    onError: () => onFeedback({id: Date.now(), category: 'error', message: msg('adminconv-command-failed')}),
  });

  return (
    <form
      className="admin-row__block-form"
      onSubmit={(event) => {
        event.preventDefault();
        mutation.mutate();
      }}
    >
      <label className="admin-row__field">
        <span>{label}</span>
        {' '}<span className="sr-only">{`— ${name ?? participant.pseudonym}`}</span>
        <input
          type="text"
          name="summary"
          value={summary}
          onChange={(event) => setSummary(event.target.value)}
        />
      </label>
      <button type="submit" className="admin-row__text-button" disabled={mutation.isPending}>
        {msg(participant.access.banned ? 'participants-btn-unban' : 'participants-btn-ban')}
        {' '}<span className="sr-only">{`— ${name ?? participant.pseudonym}`}</span>
      </button>
    </form>
  );
}
