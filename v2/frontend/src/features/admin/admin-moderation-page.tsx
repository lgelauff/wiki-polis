import {useState, type FormEvent} from 'react';
import {useMutation, useQueryClient, useSuspenseQuery} from '@tanstack/react-query';
import {Link} from 'react-router-dom';

import type {components} from '../../api/schema';
import {adminFlagQueueQuery, putAdminFlagResolution} from '../../api/queries';

type Flag = components['schemas']['AdminContentFlag'];
type Queue = components['schemas']['AdminFlagQueue'];

function formatDate(value: string | null): string {
  if (!value) return 'Unknown';
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium', timeStyle: 'short',
  }).format(new Date(value));
}

function ResolveFlag({
  conversationId, flag, csrfToken,
}: {
  conversationId: number;
  flag: Flag;
  csrfToken: string;
}) {
  const queryClient = useQueryClient();
  const [note, setNote] = useState('');
  const mutation = useMutation({
    mutationFn: () => putAdminFlagResolution(
      conversationId, flag.id, {resolved: true, note: note || null}, csrfToken,
    ),
    onSuccess: (receipt) => {
      queryClient.setQueryData<Queue>(
        adminFlagQueueQuery(conversationId).queryKey,
        (queue) => {
          if (!queue) return queue;
          const resolvedFlag: Flag = {
            ...flag,
            status: 'resolved',
            resolution: receipt.resolution,
          };
          return {
            ...queue,
            open: queue.open.filter((item) => item.id !== flag.id),
            resolved: [resolvedFlag, ...queue.resolved.filter((item) => item.id !== flag.id)],
          };
        },
      );
      setNote('');
    },
  });

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    mutation.mutate();
  }

  return (
    <form className="moderation-resolve" onSubmit={submit}>
      <label htmlFor={`resolution-${flag.id}`}>Resolution note <span>(optional)</span></label>
      <div>
        <input
          id={`resolution-${flag.id}`}
          value={note}
          onChange={(event) => setNote(event.target.value)}
          maxLength={1000}
          disabled={mutation.isPending}
        />
        <button type="submit" disabled={mutation.isPending}>
          {mutation.isPending ? 'Resolving…' : `Resolve ${flag.target.label}`}
        </button>
      </div>
      {mutation.isError && <p role="alert">{mutation.error.message}</p>}
    </form>
  );
}

function FlagTarget({flag}: {flag: Flag}) {
  return (
    <div className="moderation-target">
      <span>{flag.target.label}</span>
      <blockquote>{flag.target.text}</blockquote>
      <Link to={flag.target.reviewHref}>Review {flag.target.type}</Link>
    </div>
  );
}

function FlagReason({flag}: {flag: Flag}) {
  return (
    <div className="moderation-reason">
      <strong>{flag.categoryLabel}</strong>
      {flag.detail && <p>{flag.detail}</p>}
    </div>
  );
}

function OpenFlags({
  flags, conversationId, csrfToken,
}: {
  flags: Flag[];
  conversationId: number;
  csrfToken: string;
}) {
  return (
    <section className="moderation-section" aria-labelledby="open-flags-heading">
      <header><h2 id="open-flags-heading">Open flags</h2><span>{flags.length}</span></header>
      {flags.length ? (
        <ul className="moderation-list">
          {flags.map((flag) => (
            <li key={flag.id}>
              <FlagTarget flag={flag} />
              <FlagReason flag={flag} />
              <div className="moderation-meta">
                <span>Flagged</span><time dateTime={flag.flaggedAt ?? undefined}>{formatDate(flag.flaggedAt)}</time>
              </div>
              <ResolveFlag conversationId={conversationId} flag={flag} csrfToken={csrfToken} />
            </li>
          ))}
        </ul>
      ) : <p className="moderation-empty">No open flags.</p>}
    </section>
  );
}

function ResolvedFlags({flags}: {flags: Flag[]}) {
  return (
    <section className="moderation-section moderation-section--resolved" aria-labelledby="resolved-flags-heading">
      <header><h2 id="resolved-flags-heading">Resolved</h2><span>{flags.length}</span></header>
      {flags.length ? (
        <ul className="moderation-list">
          {flags.map((flag) => (
            <li key={flag.id}>
              <FlagTarget flag={flag} />
              <FlagReason flag={flag} />
              <div className="moderation-resolution">
                <span>Resolved {formatDate(flag.resolution?.resolvedAt ?? null)}</span>
                {flag.resolution?.note && <p>{flag.resolution.note}</p>}
              </div>
            </li>
          ))}
        </ul>
      ) : <p className="moderation-empty">No resolved flags yet.</p>}
    </section>
  );
}

export function AdminModerationPage({
  conversationId, csrfToken,
}: {
  conversationId: number;
  csrfToken: string;
}) {
  const {data} = useSuspenseQuery(adminFlagQueueQuery(conversationId));
  return (
    <main className="moderation-shell" id="main">
      <nav className="record-breadcrumb" aria-label="Breadcrumb">
        <Link to="/app/admin">Admin panel</Link><span>/</span>
        <Link to={data.links.conversation}>{data.conversation.title}</Link><span>/</span>
        <span>Moderation queue</span>
      </nav>
      <header className="moderation-heading">
        <div>
          <p className="eyebrow">Content review</p>
          <h1>Moderation queue</h1>
          <p>Review participant reports without exposing who submitted them.</p>
        </div>
        <div className="moderation-count" aria-label={`${data.open.length} open flags`}>
          <strong>{data.open.length}</strong><span>open</span>
        </div>
      </header>
      {!data.dataAvailability.statementText && (
        <div className="admin-roster__notice" role="status">
          <strong>Some statement text is unavailable</strong>
          <span>The reports remain visible and resolvable while Polis recovers.</span>
        </div>
      )}
      <p className="moderation-privacy">
        Reporter identities are intentionally excluded. Resolving records review;
        changes to the underlying content happen in its review tool.
      </p>
      <OpenFlags flags={data.open} conversationId={conversationId} csrfToken={csrfToken} />
      <ResolvedFlags flags={data.resolved} />
    </main>
  );
}
