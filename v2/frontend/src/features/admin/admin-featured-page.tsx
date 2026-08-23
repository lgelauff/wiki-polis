import {useCallback, useState, type FormEvent, type ReactNode} from 'react';
import {useMutation, useQueryClient, useSuspenseQuery} from '@tanstack/react-query';
import {Link} from 'react-router-dom';

import type {components} from '../../api/schema';
import {ApiContractError} from '../../api/client';
import {
  adminFeaturedWorkspaceQuery,
  deleteAdminFeaturedArgument,
  deleteAdminFeaturedSelection,
  putAdminFeaturedArgument,
  putAdminFeaturedStatement,
} from '../../api/queries';
import {LegacyShell} from '../legacy/legacy-shell';
import {LegacyToast, type LegacyToastMessage} from '../legacy/legacy-toast';

type Workspace = components['schemas']['AdminFeaturedWorkspace'];
type Selected = components['schemas']['AdminFeaturedSelection'];
type Candidate = components['schemas']['AdminFeaturedCandidate'];
type Provenance = Selected['provenance'];

const selectLiveMessage = 'Informed vote is already live. This statement will be seeded into that round immediately. Continue?';
const removeLiveMessage = 'Informed vote is already live. Removing this statement hides it from that round immediately (existing votes are preserved). Continue?';
const deleteArgumentMessage = 'Delete this argument and all its votes? This cannot be undone.';

function legacyTruncate(value: string, length = 28, leeway = 5): string {
  return value.length <= length + leeway ? value : `${value.slice(0, length - 1)}…`;
}

function errorMessage(error: Error, fallback: string): string {
  if (error instanceof ApiContractError
      && error.code === 'last_featured_statement_protected') {
    return 'Cannot remove the last featured statement while argument mapping is active. Disable the argument mapping phase first.';
  }
  return error instanceof ApiContractError ? error.message : fallback;
}

function feedbackStyle() {
  return {
    background: '#fef2f2',
    borderColor: '#fca5a5',
    color: '#991b1b',
    border: '1px solid',
    padding: '.75rem 1rem',
    borderRadius: 6,
    fontSize: 13,
    marginBottom: '1.5rem',
  };
}

function ProvenanceBadge({provenance}: {provenance: Provenance}) {
  if (!provenance) return null;
  const title = `Derived from statement #${provenance.derivedFromId}. Similarity 1.00 = identical.${provenance.scores.map((score) => ` ${score.model} ${score.value.toFixed(2)}.`).join('')}`;
  return (
    <span className="prov-badge" title={title}>
      <span className="sr-only">derived from statement {provenance.derivedFromId}, </span>
      ↳ #{provenance.derivedFromId}
      {provenance.scores.map((score) => (
        <span key={score.model}> · {score.model}&nbsp;{score.value.toFixed(2)}</span>
      ))}
    </span>
  );
}

function InlineForm({children, className, onSubmit}: {
  children: ReactNode;
  className?: string;
  onSubmit: () => void;
}) {
  return (
    <form
      className={className}
      style={{display: 'inline', flexShrink: 0}}
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit();
      }}
    >
      {children}
    </form>
  );
}

function SelectedRow({
  selection,
  conversationId,
  csrfToken,
  informedVotingLive,
  refresh,
  showError,
}: {
  selection: Selected;
  conversationId: number;
  csrfToken: string;
  informedVotingLive: boolean;
  refresh: () => void;
  showError: (message: string) => void;
}) {
  const remove = useMutation({
    mutationFn: () => deleteAdminFeaturedSelection(
      conversationId, selection.featuredId, csrfToken,
    ),
    onSuccess: refresh,
    onError: (error: Error) => showError(errorMessage(
      error, 'The featured statement could not be removed.',
    )),
  });
  const visibility = useMutation({
    mutationFn: ({id, hidden}: {id: number; hidden: boolean}) => (
      putAdminFeaturedArgument(conversationId, id, {hidden}, csrfToken)
    ),
    onSuccess: refresh,
    onError: (error: Error) => showError(errorMessage(
      error, 'The argument moderation state could not be updated.',
    )),
  });
  const deletion = useMutation({
    mutationFn: (id: number) => deleteAdminFeaturedArgument(
      conversationId, id, csrfToken,
    ),
    onSuccess: refresh,
    onError: (error: Error) => showError(errorMessage(
      error, 'The argument could not be deleted.',
    )),
  });
  return (
    <tr>
      <td style={{whiteSpace: 'nowrap', verticalAlign: 'top'}}>{selection.statementId}</td>
      <td style={{fontSize: 13, verticalAlign: 'top'}}>
        <div style={{marginBottom: '.5rem'}}>{selection.text ?? '—'}</div>
        {selection.provenance && (
          <div style={{marginBottom: '.5rem'}}>
            <ProvenanceBadge provenance={selection.provenance} />
          </div>
        )}
        <div style={{borderTop: '1px solid var(--hairline)', paddingTop: '.4rem', marginTop: '.1rem'}}>
          <span style={{fontSize: 11, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.06em'}}>Arguments</span>
          {selection.arguments.length ? selection.arguments.map((argument) => (
            <div key={argument.id} style={{display: 'flex', flexWrap: 'wrap', alignItems: 'baseline', gap: 6, marginTop: 4, fontSize: 12}}>
              <span style={{color: 'var(--muted)', minWidth: '2rem', flexShrink: 0}}>{argument.side}</span>
              {argument.hidden && <span style={{background: '#fef3c7', color: '#92400e', border: '1px solid #f59e0b', borderRadius: 999, padding: '1px 6px', fontSize: 11}}>hidden</span>}
              <span style={{flex: 1, minWidth: 120, color: 'var(--body)'}}>{argument.body}</span>
              <span style={{color: 'var(--muted)', whiteSpace: 'nowrap'}}>{argument.proposerPseudonym ?? '—'}</span>
              <span style={{color: 'var(--muted)', whiteSpace: 'nowrap'}}>{argument.createdAt?.slice(0, 10) ?? ''}</span>
              <InlineForm onSubmit={() => visibility.mutate({id: argument.id, hidden: !argument.hidden})}>
                <input type="hidden" name="csrf_token" value={csrfToken} />
                <input type="hidden" name="hidden" value={argument.hidden ? '0' : '1'} />
                <button type="submit" className="btn-small" disabled={visibility.isPending}>{argument.hidden ? 'unhide' : 'hide'}</button>
              </InlineForm>
              <InlineForm onSubmit={() => {
                if (globalThis.confirm(deleteArgumentMessage)) deletion.mutate(argument.id);
              }}>
                <input type="hidden" name="csrf_token" value={csrfToken} />
                <button type="submit" className="btn-small btn-danger" disabled={deletion.isPending}>delete</button>
              </InlineForm>
            </div>
          )) : <p style={{fontSize: 12, color: 'var(--body)', margin: '4px 0 0'}}>no arguments yet</p>}
        </div>
      </td>
      <td style={{verticalAlign: 'top'}}>
        <InlineForm onSubmit={() => {
          if (!informedVotingLive || globalThis.confirm(removeLiveMessage)) remove.mutate();
        }}>
          <input type="hidden" name="csrf_token" value={csrfToken} />
          <button type="submit" className="btn-small btn-danger" disabled={remove.isPending}>remove</button>
        </InlineForm>
      </td>
    </tr>
  );
}

function CandidateRow({candidate, csrfToken, pending, onConfirm}: {
  candidate: Candidate;
  csrfToken: string;
  pending: boolean;
  onConfirm: () => void;
}) {
  return (
    <tr>
      <td>{candidate.statementId}</td>
      <td style={{fontSize: 13}}>
        {candidate.text}
        {candidate.provenance && <div style={{marginTop: '.35rem'}}><ProvenanceBadge provenance={candidate.provenance} /></div>}
      </td>
      <td>{candidate.seed ? '✓' : ''}</td>
      <td>{candidate.votes.agree}</td>
      <td>{candidate.votes.disagree}</td>
      <td>{candidate.votes.pass}</td>
      <td>{candidate.votes.total}</td>
      <td>
        <InlineForm onSubmit={onConfirm}>
          <input type="hidden" name="csrf_token" value={csrfToken} />
          <input type="hidden" name="tid" value={candidate.statementId} />
          <input type="hidden" name="system_suggested" value="1" />
          <button type="submit" className="btn-small" disabled={pending}>confirm</button>
        </InlineForm>
      </td>
    </tr>
  );
}

export function AdminFeaturedPage({conversationId, csrfToken}: {
  conversationId: number;
  csrfToken: string;
}) {
  const queryClient = useQueryClient();
  const options = adminFeaturedWorkspaceQuery(conversationId);
  const {data} = useSuspenseQuery(options);
  const [manualId, setManualId] = useState('');
  const [feedback, setFeedback] = useState<string | null>(null);
  const [toast, setToast] = useState<LegacyToastMessage | null>(null);
  const dismissToast = useCallback(() => setToast(null), []);
  function refresh() {
    setFeedback(null);
    void queryClient.invalidateQueries({queryKey: options.queryKey});
  }
  function showError(message: string) {
    globalThis.scrollTo(0, 0);
    setFeedback(message);
    setToast({id: Date.now(), category: 'error', message});
  }
  const selection = useMutation({
    mutationFn: ({id, source}: {id: number; source: 'system' | 'manual'}) => (
      putAdminFeaturedStatement(conversationId, id, {source}, csrfToken)
    ),
    onSuccess: () => {
      setManualId('');
      refresh();
    },
    onError: (error: Error) => showError(errorMessage(
      error, 'The statement could not be selected.',
    )),
  });
  function select(id: number, source: 'system' | 'manual') {
    if (!data.phase.informedVotingLive || globalThis.confirm(selectLiveMessage)) {
      selection.mutate({id, source});
    }
  }
  function submitManual(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const id = Number(manualId);
    if (Number.isInteger(id) && id >= 0) select(id, 'manual');
  }

  const title = data.conversation.title;
  return (
    <LegacyShell
      headerMode="admin"
      title={`Featured statements — ${title} — ProtoWiki`}
      headerCrumb={(
        <nav className="header-crumb" aria-label="Admin breadcrumb">
          <span className="header-crumb-sep">/</span>
          <Link to="/admin">Admin panel</Link>
          <span className="header-crumb-sep">/</span>
          <Link to={data.links.lifecycle}>{legacyTruncate(title)}</Link>
          <span className="header-crumb-sep">/</span>
          <span>Featured</span>
        </nav>
      )}
      toast={<LegacyToast toast={toast} onDismiss={dismissToast} />}
    >
      <div className="container">
        <h2>Featured statements — {title}</h2>

        <p className="muted" style={{fontSize: 13, marginBottom: '1.5rem'}}>
          Featured statements appear in the argument mapping tab. Participants submit a pro and con
          {' '}argument for each, then vote on the most important arguments submitted by others.
        </p>

        <div className="landing-section" style={{marginBottom: '1.5rem'}}>
          <h3 style={{fontSize: 16, marginBottom: '.5rem'}}>How to choose featured statements</h3>
          <p className="muted" style={{fontSize: 13, marginBottom: '.6rem'}}>
            Featured statements are the representative set that carries the rest of the consultation:
            {' '}they become the prompts for argument mapping and are seeded into informed voting.
            {' '}Aim for a balanced set across the main viewpoints, not only the most popular statements.
          </p>
          <ul style={{fontSize: 13, paddingLeft: '1.25rem', marginBottom: '.6rem'}}>
            <li>Use roughly 15 statements as a working target, then adjust for topic complexity.</li>
            <li>Prefer statements with enough votes to indicate signal, while preserving minority viewpoints.</li>
            <li>Once argument mapping begins, treat the selected set as locked; changing it later can confuse participants and downstream Phase 6 seeding.</li>
          </ul>
          <p className="muted" style={{fontSize: 13, marginBottom: 0}}>
            System suggestions are ranked candidates from the Polis data. Manual TID adds are for
            {' '}known statements that should be included even if they are not surfaced by the suggestion query.
            {' '}Arguments are visible by default; hide individual arguments here when they need moderation,
            {' '}and unhide them after review.
          </p>
        </div>

        {feedback && <div style={feedbackStyle()}>{feedback}</div>}

        <h3 className="section-heading">Confirmed ({data.selected.length})</h3>
        {data.selected.length ? (
          <table className="admin-table" style={{marginBottom: '1.5rem'}}>
            <thead><tr><th>TID</th><th>Statement</th><th /></tr></thead>
            <tbody>
              {data.selected.map((row) => (
                <SelectedRow
                  key={row.featuredId}
                  selection={row}
                  conversationId={conversationId}
                  csrfToken={csrfToken}
                  informedVotingLive={data.phase.informedVotingLive}
                  refresh={refresh}
                  showError={showError}
                />
              ))}
            </tbody>
          </table>
        ) : <p className="muted" style={{fontSize: 14, marginBottom: '1.5rem'}}>No featured statements yet.</p>}

        <h3 className="section-heading">System suggestions</h3>
        {!data.dataAvailability.candidates ? (
          <p className="muted" style={{fontSize: 13, marginBottom: '1.5rem'}}>
            Not available — <code>POLIS_DATABASE_URL</code> is not configured.
            {' '}Use the manual form below to add statements by TID.
          </p>
        ) : data.candidates.length === 0 ? (
          <p className="muted" style={{fontSize: 13, marginBottom: '1.5rem'}}>
            No unconfirmed candidates. All available statements are already featured,
            {' '}or there are no statements yet.
          </p>
        ) : (
          <table className="admin-table" style={{marginBottom: '1.5rem'}}>
            <thead><tr><th>TID</th><th>Text</th><th>Seed</th><th>Agree</th><th>Disagree</th><th>Pass</th><th>Votes</th><th /></tr></thead>
            <tbody>
              {data.candidates.map((candidate) => (
                <CandidateRow
                  key={candidate.statementId}
                  candidate={candidate}
                  csrfToken={csrfToken}
                  pending={selection.isPending}
                  onConfirm={() => select(candidate.statementId, 'system')}
                />
              ))}
            </tbody>
          </table>
        )}

        <h3 className="section-heading">Add by TID</h3>
        <div className="edit-form">
          <p className="muted" style={{fontSize: 13, marginBottom: '.75rem'}}>
            Enter the Polis statement ID (TID) to feature it directly.
          </p>
          <form onSubmit={submitManual}>
            <input type="hidden" name="csrf_token" value={csrfToken} />
            <div className="edit-row-fields">
              <label>Statement TID
                <input type="number" name="tid" min="0" required style={{width: 100}} value={manualId} onChange={(event) => setManualId(event.target.value)} />
              </label>
            </div>
            <button type="submit" disabled={selection.isPending}>Add</button>
          </form>
        </div>
      </div>
    </LegacyShell>
  );
}
