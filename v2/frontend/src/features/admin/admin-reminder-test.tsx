import {useId, useState, type FormEvent} from 'react';
import {useMutation, useQuery} from '@tanstack/react-query';

import type {components} from '../../api/schema';
import {ApiContractError} from '../../api/client';
import {postReminderTestSend, reminderTestQuery} from '../../api/queries';
import {useMessage, type Message} from '../../i18n/messages';
import {useAnnounce} from './admin-announcer';

type State = components['schemas']['ReminderTestResponse']['data'];
type Request = components['schemas']['ReminderTestSendRequest'];
type Result = components['schemas']['ReminderTestSendResponse']['data'];
type Channel = Request['channel'];
type Line = {text: string; error: boolean};

function hostOf(state: State | undefined, wiki: string | null): string {
  return state?.wikis.find((row) => row.key === wiki)?.host ?? wiki ?? '';
}

/** The result, as one line of text (a status, not a box). */
function resultLine(msg: Message, result: Result, sent: Request, state: State | undefined): Line {
  const failed = (text: string) => ({text, error: true});
  if (result.outcome === 'sent') {
    const via = hostOf(state, result.sentVia);
    return {
      text: result.sentVia === sent.wiki
        ? msg('admin-reminder-test-sent', via)
        : msg('admin-reminder-test-sent-fallback', via, hostOf(state, sent.wiki)),
      error: false,
    };
  }
  if (result.outcome === 'unknown') return failed(msg('admin-reminder-test-unknown'));
  switch (result.reason) {
    case 'wiki_not_live': return {text: msg('admin-reminder-test-dry-not-live'), error: false};
    case 'no_credentials': return {text: msg('admin-reminder-test-dry-no-login'), error: false};
    case 'not_emailable': return failed(result.code === 'fallback_not_live'
      ? msg('admin-reminder-test-failed-not-emailable-here')
      : msg('admin-reminder-test-failed-not-emailable'));
    case 'nobots': return failed(msg('admin-reminder-test-failed-nobots'));
    case 'throttled': return failed(msg('admin-reminder-test-failed-throttled'));
    case 'lagged': return failed(msg('admin-reminder-test-failed-lagged'));
    case 'blocked': return failed(msg('admin-reminder-test-failed-blocked'));
    default: return failed(msg('admin-reminder-test-failed-error', result.code ?? ''));
  }
}

/** A refused request, in the console's own words rather than the server's English. */
function refusalLine(msg: Message, error: Error): Line {
  const code = error instanceof ApiContractError ? error.code : null;
  if (code === 'rate_limited') return {text: msg('admin-reminder-test-rate-limited'), error: true};
  if (code === 'recipient_not_allowed' || code === 'unknown_wiki' || code === 'unknown_channel'
      || code === 'validation_failed') {
    return {text: msg('admin-reminder-test-refused'), error: true};
  }
  return {text: msg('adminconv-command-failed'), error: true};
}

/** Super admins only (#577): one test message from the Proto bot to a configured test
 *  account, for the bot approvals (#581, #582). Folded like the other sections; the state is
 *  read only once it is opened. The send and its result live here, above the fold, so
 *  closing the section during a send loses neither. Results are spoken through the
 *  console's one announcement region (`useAnnounce`). */
export function AdminReminderTest({csrfToken}: {csrfToken: string}) {
  const msg = useMessage();
  const announce = useAnnounce();
  const [open, setOpen] = useState(false);
  const [line, setLine] = useState<Line | null>(null);
  const query = useQuery({...reminderTestQuery(), enabled: open});

  const send = useMutation({
    mutationFn: (body: Request) => postReminderTestSend(body, csrfToken),
    onMutate: () => {
      setLine(null);
      announce?.(msg('admin-reminder-test-sending'));
    },
    onSuccess: (result, body) => {
      const next = resultLine(msg, result, body, query.data);
      setLine(next);
      announce?.(next.text, next.error ? 'assertive' : 'polite');
    },
    onError: (error: Error) => {
      const next = refusalLine(msg, error);
      setLine(next);
      announce?.(next.text, 'assertive');
    },
  });

  return (
    <details className="admin-form admin-fold" open={open}
      onToggle={(event) => setOpen(event.currentTarget.open)}>
      <summary><h2>{msg('admin-reminder-test-heading')}</h2></summary>
      {open && <ReminderTestForm state={query.data} failed={query.isError}
        pending={send.isPending} line={line}
        onChange={() => setLine(null)}
        onSend={(body) => { if (!send.isPending) send.mutate(body); }} />}
    </details>
  );
}

function ReminderTestForm({state, failed, pending, line, onChange, onSend}: {
  state: State | undefined; failed: boolean; pending: boolean; line: Line | null;
  onChange: () => void; onSend: (body: Request) => void;
}) {
  const msg = useMessage();
  const noLoginId = useId();
  const [wiki, setWiki] = useState<string | null>(null);
  const [channel, setChannel] = useState<Channel>('email');
  const [recipient, setRecipient] = useState<string | null>(null);

  if (failed) return <p className="admin-error">{msg('adminconv-command-failed')}</p>;
  if (!state) return <p>{msg('common-loading')}</p>;
  if (!state.recipients.length) return <p className="admin-empty">{msg('admin-reminder-test-empty')}</p>;

  const chosenWiki = wiki ?? (state.wikis.find((row) => row.live) ?? state.wikis[0])?.key ?? '';
  // A remembered pick that the server no longer lists falls back to the first test account.
  const chosenRecipient = recipient && state.recipients.includes(recipient)
    ? recipient : state.recipients[0] ?? '';

  // Wiki-mail and talk-page posts have their own bot login; the note follows the channel.
  const loginSet = state.credentialsSet[channel];

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    onSend({wiki: chosenWiki, channel, recipient: chosenRecipient});
  }

  return (
    <form onSubmit={submit}>
      <p>{msg('admin-reminder-test-intro')}</p>
      <label className="admin-field admin-field--medium">{msg('admin-reminder-test-label-wiki')}<select value={chosenWiki} onChange={(event) => { setWiki(event.target.value); onChange(); }}>
        {state.wikis.map((row) => <option key={row.key} value={row.key}>
          {row.live ? row.host : msg('admin-reminder-test-wiki-dry', row.host)}
        </option>)}
      </select></label>
      <label className="admin-field admin-field--medium">{msg('admin-reminder-test-label-channel')}<select value={channel} onChange={(event) => { setChannel(event.target.value as Channel); onChange(); }}>
        <option value="email">{msg('admin-reminder-test-channel-email')}</option>
        <option value="talk">{msg('admin-reminder-test-channel-talk')}</option>
      </select></label>
      <label className="admin-field admin-field--medium">{msg('admin-reminder-test-label-recipient')}<select value={chosenRecipient} onChange={(event) => { setRecipient(event.target.value); onChange(); }}>
        {state.recipients.map((name) => <option key={name} value={name}>{name}</option>)}
      </select></label>
      {!loginSet && <p className="admin-empty" id={noLoginId}>{msg('admin-reminder-test-dry-no-login')}</p>}
      <div className="admin-form__actions">
        {/* aria-disabled, not disabled, so the button keeps focus during the send. */}
        <button type="submit" className="admin-button admin-button--primary" aria-disabled={pending}
          {...(loginSet ? {} : {'aria-describedby': noLoginId})}>{msg('admin-reminder-test-btn')}</button>
      </div>
      {pending && <p>{msg('admin-reminder-test-sending')}</p>}
      {line && <p className={line.error ? 'admin-error' : undefined}>{line.text}</p>}
    </form>
  );
}
