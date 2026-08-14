import {useState, type FormEvent} from 'react';
import {useMutation, useSuspenseQuery} from '@tanstack/react-query';
import {Link} from 'react-router-dom';

import {ApiContractError} from '../../api/client';
import {
  adminTerminationQuery,
  deleteAdminConversation,
} from '../../api/queries';

export function AdminTerminationPage({conversationId, csrfToken}: {
  conversationId: number;
  csrfToken: string;
}) {
  const {data} = useSuspenseQuery(adminTerminationQuery(conversationId));
  const [confirmation, setConfirmation] = useState('');
  const mutation = useMutation({
    mutationFn: () => deleteAdminConversation(conversationId, csrfToken),
  });
  const eligible = data.deletion.state === 'eligible';
  const confirmed = confirmation === data.conversation.title;
  const error = mutation.error instanceof ApiContractError
    ? mutation.error.message
    : mutation.error ? 'The conversation could not be deleted.' : null;

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!eligible || !confirmed) return;
    if (globalThis.confirm(
      `Permanently delete “${data.conversation.title}”? This cannot be undone.`,
    )) mutation.mutate();
  }

  if (mutation.data) {
    return (
      <main className="termination-shell" id="main">
        <section className="termination-receipt" role="status">
          <p className="eyebrow">Deletion complete</p>
          <h1>Conversation deleted</h1>
          <p>The empty conversation was hidden from the voting service and removed locally.</p>
          <a href={mutation.data.links.admin}>Return to admin panel</a>
        </section>
      </main>
    );
  }

  return (
    <main className="termination-shell" id="main">
      <nav className="record-breadcrumb" aria-label="Breadcrumb">
        <Link to="/app/admin">Admin panel</Link><span>/</span>
        <Link to={data.links.lifecycle}>{data.conversation.title}</Link><span>/</span>
        <span>Delete</span>
      </nav>
      <header className="termination-heading">
        <p className="eyebrow">Permanent removal · global admin only</p>
        <h1>Delete conversation</h1>
        <p>Deletion is reserved for empty records. Conversations with votes must be archived so their deliberation history is retained.</p>
      </header>

      <section className="termination-record" data-state={data.deletion.state}>
        <div>
          <span>Record</span>
          <h2>{data.conversation.title}</h2>
          <code>{data.conversation.slug}</code>
        </div>
        <dl>
          <div><dt>Eligibility</dt><dd>{data.deletion.state.replaceAll('_', ' ')}</dd></div>
          <div><dt>Valid votes</dt><dd>{data.deletion.validVoteCount ?? 'unavailable'}</dd></div>
        </dl>
      </section>

      <section className="termination-decision" aria-labelledby="termination-decision-heading">
        <div>
          <p className="eyebrow">Live verification</p>
          <h2 id="termination-decision-heading">{eligible ? 'This record is empty' : 'Deletion is not available'}</h2>
          <p>{data.deletion.reason}</p>
          {!eligible && <Link to={data.links.lifecycle}>Return to lifecycle controls</Link>}
        </div>
        {eligible && (
          <form onSubmit={submit}>
            <label htmlFor="termination-confirmation">
              Type <strong>{data.conversation.title}</strong> to confirm
            </label>
            <input
              id="termination-confirmation"
              value={confirmation}
              autoComplete="off"
              onChange={(event) => setConfirmation(event.target.value)}
            />
            <button type="submit" disabled={!confirmed || mutation.isPending}>
              {mutation.isPending ? 'Deleting…' : 'Permanently delete conversation'}
            </button>
            <p>The server will verify the vote count again before deleting.</p>
            {error && <p className="termination-error" role="alert">{error}</p>}
          </form>
        )}
      </section>
    </main>
  );
}
