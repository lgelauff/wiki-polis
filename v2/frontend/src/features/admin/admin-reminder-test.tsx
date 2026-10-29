import {useState, type FormEvent} from 'react';
import {useMutation, useQuery} from '@tanstack/react-query';

import type {components} from '../../api/schema';
import {ApiContractError} from '../../api/client';
import {postReminderTestSend, reminderTestQuery} from '../../api/queries';
import {useMessage, type Message} from '../../i18n/messages';

type Result = components['schemas']['ReminderTestSendResponse']['data'];
type Channel = components['schemas']['ReminderTestSendRequest']['channel'];

/** The result, as one line of text (a status, not a box). */
function resultText(msg: Message, result: Result): string {
  if (result.outcome === 'sent') return msg('admin-reminder-test-sent', result.sentVia ?? '');
  switch (result.reason) {
    case 'wiki_not_live': return msg('admin-reminder-test-dry-not-live');
    case 'no_credentials': return msg('admin-reminder-test-dry-no-login');
    case 'not_emailable': return msg('admin-reminder-test-failed-not-emailable');
    case 'nobots': return msg('admin-reminder-test-failed-nobots');
    case 'throttled': return msg('admin-reminder-test-failed-throttled');
    case 'blocked': return msg('admin-reminder-test-failed-blocked');
    default: return msg('admin-reminder-test-failed-error', result.code ?? '');
  }
}

/** Super admins only (#577): one test message from the Proto bot to a configured test
 *  account, for the bot approvals (#581, #582). Folded like the other sections; the state is
 *  read only once it is opened. */
export function AdminReminderTest({csrfToken}: {csrfToken: string}) {
  const msg = useMessage();
  const [open, setOpen] = useState(false);
  return (
    <details className="admin-form admin-fold" open={open}
      onToggle={(event) => setOpen(event.currentTarget.open)}>
      <summary><h2>{msg('admin-reminder-test-heading')}</h2></summary>
      {open && <ReminderTestForm csrfToken={csrfToken} />}
    </details>
  );
}

function ReminderTestForm({csrfToken}: {csrfToken: string}) {
  const msg = useMessage();
  const {data, isError} = useQuery(reminderTestQuery());
  const [wiki, setWiki] = useState<string | null>(null);
  const [channel, setChannel] = useState<Channel>('email');
  const [recipient, setRecipient] = useState<string | null>(null);
  const [result, setResult] = useState<string | null>(null);
  const [refusal, setRefusal] = useState<string | null>(null);

  const send = useMutation({
    mutationFn: (body: components['schemas']['ReminderTestSendRequest']) => (
      postReminderTestSend(body, csrfToken)
    ),
    onSuccess: (sent) => { setRefusal(null); setResult(resultText(msg, sent)); },
    onError: (error: Error) => {
      setResult(null);
      setRefusal(error instanceof ApiContractError ? error.message : msg('adminconv-command-failed'));
    },
  });

  if (isError) return <p className="admin-error" role="alert">{msg('adminconv-command-failed')}</p>;
  if (!data) return null;
  if (!data.recipients.length) return <p className="admin-empty">{msg('admin-reminder-test-empty')}</p>;

  const chosenWiki = wiki ?? (data.wikis.find((row) => row.live) ?? data.wikis[0])?.key ?? '';
  const chosenRecipient = recipient ?? data.recipients[0] ?? '';

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setResult(null);
    setRefusal(null);
    send.mutate({wiki: chosenWiki, channel, recipient: chosenRecipient});
  }

  return (
    <form onSubmit={submit}>
      <p>{msg('admin-reminder-test-intro')}</p>
      <label className="admin-field admin-field--medium">{msg('admin-reminder-test-label-wiki')}<select value={chosenWiki} onChange={(event) => setWiki(event.target.value)}>
        {data.wikis.map((row) => <option key={row.key} value={row.key}>
          {row.live ? row.host : msg('admin-reminder-test-wiki-dry', row.host)}
        </option>)}
      </select></label>
      <label className="admin-field admin-field--medium">{msg('admin-reminder-test-label-channel')}<select value={channel} onChange={(event) => setChannel(event.target.value as Channel)}>
        <option value="email">{msg('admin-reminder-test-channel-email')}</option>
        <option value="talk">{msg('admin-reminder-test-channel-talk')}</option>
      </select></label>
      <label className="admin-field admin-field--medium">{msg('admin-reminder-test-label-recipient')}<select value={chosenRecipient} onChange={(event) => setRecipient(event.target.value)}>
        {data.recipients.map((name) => <option key={name} value={name}>{name}</option>)}
      </select></label>
      {!data.credentialsSet && <p className="admin-empty">{msg('admin-reminder-test-dry-no-login')}</p>}
      <div className="admin-form__actions">
        <button type="submit" className="admin-button admin-button--primary" disabled={send.isPending}>{msg('admin-reminder-test-btn')}</button>
      </div>
      {result && <p role="status">{result}</p>}
      {refusal && <p className="admin-error" role="alert">{refusal}</p>}
    </form>
  );
}
