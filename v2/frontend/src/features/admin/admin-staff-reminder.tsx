import {useId, useState, type FormEvent} from 'react';
import {useMutation, useQuery} from '@tanstack/react-query';

import type {components} from '../../api/schema';
import {ApiContractError} from '../../api/client';
import {postStaffReminderDryRun, staffReminderQuery} from '../../api/queries';
import {useMessage, type Message} from '../../i18n/messages';
import {useAnnounce} from './admin-announcer';

type ReminderType = components['schemas']['StaffReminderType'];
type Run = components['schemas']['StaffReminderDryRunResponse']['data'];
type Row = Run['rows'][number];

const TYPE_LABEL = {
  phase_opened: 'admin-staff-reminder-type-phase-opened',
  phase_closing: 'admin-staff-reminder-type-phase-closing',
  results: 'admin-staff-reminder-type-results',
} as const;

function channelLabel(msg: Message, channel: Row['channel']): string {
  return msg(channel === 'email' ? 'admin-reminder-test-channel-email' : 'admin-reminder-test-channel-talk');
}

/** What happened to one person on one channel, as plain text. */
export function outcomeText(msg: Message, row: Row): string {
  switch (row.status) {
    case 'dry_run': return msg('admin-staff-reminder-outcome-dry-run');
    // Not possible in a dry run; the live send (step 2) gives it its own text.
    case 'sent': return row.status;
    case 'combined': return msg('admin-staff-reminder-outcome-combined');
    case 'not_sent_limit': return msg('admin-staff-reminder-outcome-limit');
    case 'skipped_expired': return msg('admin-staff-reminder-outcome-expired');
    case 'skipped_optout': return msg('admin-staff-reminder-outcome-optout');
    case 'pending': return msg('admin-staff-reminder-outcome-pending');
    case 'failed': break;
  }
  switch (row.reason) {
    case 'not_emailable': return msg('admin-reminder-test-failed-not-emailable');
    case 'nobots': return msg('admin-reminder-test-failed-nobots');
    case 'throttled': return msg('admin-reminder-test-failed-throttled');
    case 'lagged': return msg('admin-reminder-test-failed-lagged');
    case 'blocked': return msg('admin-reminder-test-failed-blocked');
    case 'outcome_unknown': return msg('admin-reminder-test-unknown');
    default: return msg('admin-reminder-test-failed-error', row.errorCode ?? row.reason ?? '');
  }
}

function refusal(msg: Message, error: Error): string {
  const code = error instanceof ApiContractError ? error.code : null;
  switch (code) {
    case 'reminder_exists': return msg('admin-staff-reminder-exists');
    case 'reminders_paused': return msg('admin-staff-reminder-paused');
    case 'batch_busy': return msg('admin-staff-reminder-busy');
    case 'unknown_wiki': return msg('admin-staff-reminder-unknown-wiki');
    case 'not_due': return msg('admin-staff-reminder-not-due');
    case 'no_recipients': return msg('admin-staff-reminder-empty');
    default: return msg('adminconv-command-failed');
  }
}

/** Super admins only (#576, step 1): a dry run of one reminder to this consultation's staff
 *  (organizers, moderators and super admins who joined and ticked a channel). Nothing is
 *  sent. Folded; the state is read only once it is opened. The page shows it to site
 *  admins only, and the server refuses everyone else. Each message can run once a day, so
 *  its result is kept per message type while the page is open. */
export function AdminStaffReminder({conversationId, csrfToken}: {conversationId: number; csrfToken: string}) {
  const msg = useMessage();
  const announce = useAnnounce();
  const describedBy = useId();
  const [open, setOpen] = useState(false);
  const [chosen, setChosen] = useState<ReminderType | null>(null);
  const [runs, setRuns] = useState<Partial<Record<ReminderType, Run>>>({});
  const [error, setError] = useState<{type: ReminderType; text: string} | null>(null);
  const query = useQuery({...staffReminderQuery(conversationId), enabled: open});

  const dryRun = useMutation({
    mutationFn: (reminderType: ReminderType) =>
      postStaffReminderDryRun(conversationId, {reminderType}, csrfToken),
    onMutate: () => { setError(null); announce?.(msg('admin-staff-reminder-running')); },
    onSuccess: (result, reminderType) => {
      setRuns((current) => ({...current, [reminderType]: result}));
      announce?.(msg('admin-staff-reminder-done', result.rows.length));
    },
    onError: (failure: Error, reminderType) => {
      const text = refusal(msg, failure);
      setError({type: reminderType, text});
      announce?.(text, 'assertive');
      // The counts or the due messages may have changed since the section was opened.
      void query.refetch();
    },
  });

  const state = query.data;
  const type = state && chosen && state.reminderTypes.includes(chosen) ? chosen : state?.reminderTypes[0];
  const run = type ? runs[type] : undefined;
  const reachesNobody = state ? state.counts.email + state.counts.talk === 0 : false;

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (type && !dryRun.isPending) dryRun.mutate(type);
  }

  return <div className="console-section">
    <div className="console-section-label">{msg('admin-staff-reminder-heading')}</div>
    <details className="phase-advanced" open={open} onToggle={(event) => setOpen(event.currentTarget.open)}>
      <summary>{msg('admin-staff-reminder-summary')}</summary>
      {open && (query.isError ? <p className="admin-error">{msg('adminconv-command-failed')}</p>
        : !state ? <p className="muted">{msg('common-loading')}</p>
        : !type ? <p className="muted" style={{fontSize: 13}}>{msg('admin-staff-reminder-not-due')}</p>
        : <form style={{marginTop: '.75rem'}} onSubmit={submit}>
          <div className="edit-row-fields"><label>{msg('admin-staff-reminder-label-type')}<select value={type} onChange={(event) => setChosen(event.target.value as ReminderType)}>
            {state.reminderTypes.map((key) => <option key={key} value={key}>{msg(TYPE_LABEL[key])}</option>)}
          </select></label></div>
          <div id={describedBy}>
            <p style={{fontSize: 13, margin: '.5rem 0'}}>{msg('admin-staff-reminder-counts', state.counts.email, state.counts.talk)}</p>
            <p style={{fontSize: 13, margin: '.5rem 0'}}>{msg(state.automatedSendApproved ? 'admin-staff-reminder-approved' : 'admin-staff-reminder-not-approved', state.wikiHost ?? state.wiki)}</p>
          </div>
          {reachesNobody ? <p className="muted" style={{fontSize: 13}}>{msg('admin-staff-reminder-empty')}</p>
            // aria-disabled, not disabled, so the button keeps focus during the run.
            : <button type="submit" aria-disabled={dryRun.isPending} aria-describedby={describedBy}>{msg('admin-staff-reminder-btn')}</button>}
          {error?.type === type && <p className="admin-error">{error.text}</p>}
          {run && (run.rows.length === 0 ? <p className="muted" style={{fontSize: 13}}>{msg('admin-staff-reminder-empty')}</p>
            : <table className="admin-table" style={{marginTop: '.75rem'}} aria-label={msg(TYPE_LABEL[type])}>
              <thead><tr>
                <th scope="col">{msg('admin-th-username')}</th>
                <th scope="col">{msg('admin-reminder-test-label-channel')}</th>
                <th scope="col">{msg('admin-th-status')}</th>
              </tr></thead>
              <tbody>{run.rows.map((row) => <tr key={`${row.username ?? ''}-${row.channel}`}>
                <td>{row.username}</td><td>{channelLabel(msg, row.channel)}</td><td>{outcomeText(msg, row)}</td>
              </tr>)}</tbody>
            </table>)}
        </form>)}
    </details>
  </div>;
}
