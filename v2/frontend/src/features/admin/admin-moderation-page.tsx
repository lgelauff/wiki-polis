import {useCallback, useState, type FormEvent} from 'react';
import {useMutation, useQueryClient, useSuspenseQuery} from '@tanstack/react-query';
import {Link} from 'react-router-dom';

import type {components} from '../../api/schema';
import {adminFlagQueueQuery, putAdminFlagResolution} from '../../api/queries';
import {LegacyShell} from '../legacy/legacy-shell';
import {LegacyToast, type LegacyToastMessage} from '../legacy/legacy-toast';

type Flag = components['schemas']['AdminContentFlag'];
type Queue = components['schemas']['AdminFlagQueue'];

function legacyTruncate(value: string, length = 28, leeway = 5): string {
  return value.length <= length + leeway ? value : `${value.slice(0, length - 1)}…`;
}

function formatLegacyDateTime(value: string | null): string {
  if (!value) return '';
  return new Date(value).toISOString().slice(0, 16).replace('T', ' ');
}

function FlagTarget({flag, includeReviewLink}: {flag: Flag; includeReviewLink: boolean}) {
  return (
    <>
      <div style={{fontSize: 12, color: 'var(--muted)', marginBottom: '.25rem'}}>
        {flag.target.label}
      </div>
      <div style={{fontSize: 13}}>{flag.target.text}</div>
      {includeReviewLink && (
        <div style={{marginTop: '.35rem', fontSize: 12}}>
          <Link to={flag.target.reviewHref}>
            {flag.target.type === 'statement' ? 'review statements' : 'review arguments'}
          </Link>
        </div>
      )}
    </>
  );
}

function FlagReason({flag}: {flag: Flag}) {
  return (
    <>
      <strong>{flag.categoryLabel}</strong>
      {(flag.detail || flag.category === 'other') && (
        <div className="muted" style={{fontSize: 12, marginTop: '.25rem'}}>
          {flag.detail || '(no explanation provided)'}
        </div>
      )}
    </>
  );
}

function ResolveFlag({
  conversationId,
  flag,
  csrfToken,
  onFeedback,
}: {
  conversationId: number;
  flag: Flag;
  csrfToken: string;
  onFeedback: (message: string, changed: boolean) => void;
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
      onFeedback(
        receipt.changed ? 'Flag marked resolved.' : 'Flag was already resolved.',
        receipt.changed,
      );
    },
  });

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    mutation.mutate();
  }

  return (
    <form onSubmit={submit}>
      <input
        type="text"
        name="resolution_note"
        value={note}
        onChange={(event) => setNote(event.target.value)}
        placeholder="Resolution note (optional)"
        style={{width: 210, marginBottom: '.35rem'}}
      />
      {' '}
      <button type="submit" className="btn-small">resolve</button>
    </form>
  );
}

export function AdminModerationPage({
  conversationId, csrfToken,
}: {
  conversationId: number;
  csrfToken: string;
}) {
  const {data} = useSuspenseQuery(adminFlagQueueQuery(conversationId));
  const [feedback, setFeedback] = useState<string | null>(null);
  const [toast, setToast] = useState<LegacyToastMessage | null>(null);
  const dismissToast = useCallback(() => setToast(null), []);
  const title = data.conversation.title;

  function showFeedback(message: string, changed: boolean) {
    setFeedback(message);
    setToast({
      id: Date.now(),
      category: changed ? 'success' : 'warning',
      message,
    });
  }

  return (
    <LegacyShell
      headerMode="admin"
      title={`Moderation queue — ${title} — ProtoWiki`}
      headerCrumb={(
        <nav className="header-crumb" aria-label="Admin breadcrumb">
          <span className="header-crumb-sep">/</span>
          <Link to="/app/admin">Admin panel</Link>
          <span className="header-crumb-sep">/</span>
          <Link to={data.links.conversation}>{legacyTruncate(title)}</Link>
          <span className="header-crumb-sep">/</span>
          <span>Moderation queue</span>
        </nav>
      )}
      toast={<LegacyToast toast={toast} onDismiss={dismissToast} />}
    >
      <div className="container">
        <h2>Moderation queue — {title}</h2>

        <div className="landing-section" style={{marginBottom: '1.5rem'}}>
          <p className="muted" style={{fontSize: 13, marginBottom: '.6rem'}}>
            Participant flags collect statements and arguments that need moderator review.
            {' '}Resolving a flag records that it was reviewed; hide or edit the underlying content
            {' '}in the statements or featured-statements tools when action is needed.
          </p>
          <p className="muted" style={{fontSize: 13, marginBottom: 0}}>
            Flagger identities are intentionally not shown here. The queue displays the target,
            {' '}reason, explanation when applicable, and timestamp.
          </p>
        </div>

        {feedback && (
          <div style={{
            background: '#f0fdf4',
            borderColor: '#86efac',
            color: '#166534',
            border: '1px solid',
            padding: '.75rem 1rem',
            borderRadius: 6,
            fontSize: 13,
            marginBottom: '1.5rem',
          }}>
            {feedback}
          </div>
        )}

        <h3 className="section-heading">
          Open flags{data.open.length ? ` (${data.open.length})` : ''}
        </h3>
        {data.open.length ? (
          <table className="admin-table" style={{marginBottom: '1.5rem'}}>
            <thead>
              <tr><th>Target</th><th>Reason</th><th>Flagged</th><th /></tr>
            </thead>
            <tbody>
              {data.open.map((flag) => (
                <tr key={flag.id}>
                  <td style={{verticalAlign: 'top'}}><FlagTarget flag={flag} includeReviewLink /></td>
                  <td style={{verticalAlign: 'top'}}><FlagReason flag={flag} /></td>
                  <td className="muted" style={{verticalAlign: 'top', whiteSpace: 'nowrap'}}>
                    {formatLegacyDateTime(flag.flaggedAt)}
                  </td>
                  <td style={{verticalAlign: 'top'}}>
                    <ResolveFlag
                      conversationId={conversationId}
                      flag={flag}
                      csrfToken={csrfToken}
                      onFeedback={showFeedback}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="muted" style={{fontSize: 14, marginBottom: '1.5rem'}}>No open flags.</p>
        )}

        <h3 className="section-heading">Resolved</h3>
        {data.resolved.length ? (
          <table className="admin-table">
            <thead><tr><th>Target</th><th>Reason</th><th>Resolved</th></tr></thead>
            <tbody>
              {data.resolved.map((flag) => (
                <tr key={flag.id}>
                  <td><FlagTarget flag={flag} includeReviewLink={false} /></td>
                  <td><FlagReason flag={flag} /></td>
                  <td className="muted" style={{whiteSpace: 'nowrap'}}>
                    {formatLegacyDateTime(flag.resolution?.resolvedAt ?? null)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="muted" style={{fontSize: 14}}>No resolved flags yet.</p>
        )}
      </div>
    </LegacyShell>
  );
}
