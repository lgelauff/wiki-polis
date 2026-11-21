import {useState, type FormEvent} from 'react';
import {useMutation} from '@tanstack/react-query';

import type {components} from '../../api/schema';
import {ApiContractError} from '../../api/client';
import {postReminderReferenceLookup} from '../../api/queries';
import {useDateFormat} from '../../i18n/dates';
import {useMessage} from '../../i18n/messages';
import {useAnnounce} from './admin-announcer';

type Result = components['schemas']['ReminderReferenceLookupResponse']['data'];
type ReminderType = Result['items'][number]['reminderType'];

const TYPE_KEY: Record<ReminderType, string> = {
  phase_opened: 'admin-reminder-reference-type-phase_opened',
  phase_closing: 'admin-reminder-reference-type-phase_closing',
  results: 'admin-reminder-reference-type-results',
};

/** Super admins only (#622): paste the reference from a Proto wiki-mail (someone may quote
 *  it on a talk page) and see what it points to. A made-up, changed or expired reference all
 *  get the same "No match", as the server answers them the same. Folded like the other
 *  sections on the page; nothing is asked of the server until a lookup is sent. */
export function AdminReminderReference({csrfToken}: {csrfToken: string}) {
  const msg = useMessage();
  const announce = useAnnounce();
  const {date} = useDateFormat();
  const [reference, setReference] = useState('');
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState<string | null>(null);

  const lookup = useMutation({
    mutationFn: (text: string) => postReminderReferenceLookup({reference: text}, csrfToken),
    onMutate: () => { setResult(null); setError(null); },
    onSuccess: (data) => {
      setResult(data);
      announce?.(data.match ? summary(data) : msg('admin-reminder-reference-no-match'));
    },
    onError: (err: Error) => {
      const code = err instanceof ApiContractError ? err.code : null;
      const text = code === 'rate_limited'
        ? msg('admin-reminder-reference-rate-limited') : msg('adminconv-command-failed');
      setError(text);
      announce?.(text, 'assertive');
    },
  });

  function summary(data: Result): string {
    const day = date(data.sendDay ?? '');
    if (data.kind === 'test_send') return msg('admin-reminder-reference-test-send', day);
    return data.username
      ? msg('admin-reminder-reference-sent-to', data.username, day)
      : msg('admin-reminder-reference-sent-to-unknown', day);
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const text = reference.trim();
    if (text && !lookup.isPending) lookup.mutate(text);
  }

  return (
    <details className="admin-form admin-fold">
      <summary><h2>{msg('admin-reminder-reference-heading')}</h2></summary>
      <form onSubmit={submit}>
        <p>{msg('admin-reminder-reference-intro')}</p>
        <label className="admin-field admin-field--medium">{msg('admin-reminder-reference-label')}<input type="text" required autoComplete="off" spellCheck={false} maxLength={2000} value={reference}
          onChange={(event) => { setReference(event.target.value); setResult(null); setError(null); }} /></label>
        <div className="admin-form__actions">
          {/* aria-disabled, not disabled, so the button keeps focus during the lookup. */}
          <button type="submit" className="admin-button admin-button--primary"
            aria-disabled={lookup.isPending}>{msg('admin-reminder-reference-btn')}</button>
        </div>
        {lookup.isPending && <p>{msg('common-loading')}</p>}
        {error && <p className="admin-error">{error}</p>}
        {result && !result.match && <p>{msg('admin-reminder-reference-no-match')}</p>}
        {result?.match && <>
          <p>{summary(result)}</p>
          {result.items.length > 0 && <ul className="admin-rows">
            {result.items.map((item, index) => <li className="admin-row" key={`${item.conversationId}-${index}`}>
              <div className="admin-row__text">{item.title}<span className="admin-row__suffix">{' · '}{msg(TYPE_KEY[item.reminderType])}</span></div>
            </li>)}
          </ul>}
        </>}
      </form>
    </details>
  );
}
