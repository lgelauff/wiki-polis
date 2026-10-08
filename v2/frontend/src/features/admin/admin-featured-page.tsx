import {useCallback, useId, useState, type FormEvent} from 'react';
import {useMutation, useQueryClient, useSuspenseQuery} from '@tanstack/react-query';

import type {components} from '../../api/schema';
import {ApiContractError} from '../../api/client';
import {
  adminFeaturedWorkspaceQuery,
  adminLifecycleQuery,
  adminSettingsQuery,
  deleteAdminFeaturedArgument,
  deleteAdminFeaturedSelection,
  putAdminFeaturedArgument,
  putAdminFeaturedStatement,
} from '../../api/queries';
import {useMessage} from '../../i18n/messages';
import {AdminShell} from './admin-shell';
import {AdminTime} from './admin-time';
import {AdminTabStrip} from './admin-tab-strip';
import {moderationTabs} from './admin-moderation-tabs';
import {LegacyToast, type LegacyToastMessage} from '../legacy/legacy-toast';

type Workspace = components['schemas']['AdminFeaturedWorkspace'];
type Selected = components['schemas']['AdminFeaturedSelection'];
type Candidate = components['schemas']['AdminFeaturedCandidate'];
type Provenance = Selected['provenance'];

const selectLiveMessage = 'The informed opinion round is already open. This statement is added to it at once. Continue?';
const removeLiveMessage = 'The informed opinion round is already open. Removing this statement takes it out of that round at once; the responses it has are kept. Continue?';
const deleteArgumentMessage = 'Delete this argument and all its ratings? This cannot be undone.';

function errorMessage(error: Error, fallback: string): string {
  if (error instanceof ApiContractError
      && error.code === 'last_featured_statement_protected') {
    return 'Cannot remove the last featured statement while argument mapping is active. Disable the argument mapping phase first.';
  }
  return error instanceof ApiContractError ? error.message : fallback;
}

/** Where a featured statement came from, as Content › Statements says it: "↳ #N" and each
 *  similarity score, muted plain text with the explanation on hover. */
function Provenance({provenance}: {provenance: Provenance}) {
  if (!provenance) return null;
  const title = `Derived from statement #${provenance.derivedFromId}. Similarity 1.00 = identical.${provenance.scores.map((score) => ` ${score.model} ${score.value.toFixed(2)}.`).join('')}`;
  return (
    <span className="admin-row__source" title={title}>
      {' '}
      <span className="sr-only">derived from statement {provenance.derivedFromId}</span>
      <span aria-hidden="true">{`↳ #${provenance.derivedFromId}`}</span>
      {provenance.scores.map((score) => (
        <span key={score.model}> · {score.model}&nbsp;{score.value.toFixed(2)}</span>
      ))}
    </span>
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
  const msg = useMessage();
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
    <li className="admin-row">
      <div className="admin-row__text">
        <span className="admin-row__id">#{selection.statementId}</span>{' '}
        {selection.text ?? '—'}
        <Provenance provenance={selection.provenance} />
      </div>
      <div className="admin-row__actions">
        {/* Not red: a removed statement can be featured again. */}
        <button type="button" className="admin-row__text-button" disabled={remove.isPending}
          onClick={() => {
            if (!informedVotingLive || globalThis.confirm(removeLiveMessage)) remove.mutate();
          }}>
          {msg('admin-btn-remove')}
        </button>
      </div>
      {/* Its arguments, one small row each: side, text, who and when, its state in words,
          and what can be done to it. */}
      {selection.arguments.length ? (
        <ul className="admin-row__sub" aria-label={`Arguments on statement ${selection.statementId}`}>
          {selection.arguments.map((argument) => (
            <li key={argument.id}>
              <span className="admin-row__suffix">{argument.side}</span>
              <span>{argument.body}</span>
              <span className="admin-row__suffix">
                {argument.proposerPseudonym ?? '—'}
                {argument.createdAt && <>{' · '}<AdminTime value={argument.createdAt} /></>}
                {argument.hidden && <>{' · '}{msg('featured-arg-hidden')}</>}
              </span>
              <span className="admin-row__actions">
                <button type="button" className="admin-row__text-button" disabled={visibility.isPending}
                  onClick={() => visibility.mutate({id: argument.id, hidden: !argument.hidden})}>
                  {argument.hidden ? msg('featured-arg-unhide') : msg('featured-arg-hide')}
                </button>
                {/* Red and confirmed: deleting an argument and its ratings cannot be undone. */}
                <button type="button" className="admin-row__text-button admin-row__text-button--danger"
                  disabled={deletion.isPending}
                  onClick={() => {
                    if (globalThis.confirm(deleteArgumentMessage)) deletion.mutate(argument.id);
                  }}>
                  {msg('featured-arg-delete')}
                </button>
              </span>
            </li>
          ))}
        </ul>
      ) : <p className="admin-row__note admin-row__suffix">{msg('featured-no-args')}</p>}
    </li>
  );
}

function CandidateRow({candidate, pending, onConfirm}: {
  candidate: Candidate;
  pending: boolean;
  onConfirm: () => void;
}) {
  const msg = useMessage();
  return (
    <tr>
      <td className="admin-num">{candidate.statementId}</td>
      <td>
        {candidate.text}
        <Provenance provenance={candidate.provenance} />
      </td>
      {/* A seed statement is marked with a check that names itself. */}
      <td>{candidate.seed && <span title="Seed" aria-label="Seed" role="img">✓</span>}</td>
      <td className="admin-num">{candidate.votes.agree}</td>
      <td className="admin-num">{candidate.votes.disagree}</td>
      <td className="admin-num">{candidate.votes.pass}</td>
      <td className="admin-num">{candidate.votes.total}</td>
      <td>
        <button type="button" className="admin-row__text-button" disabled={pending} onClick={onConfirm}>
          {msg('featured-btn-confirm')}
        </button>
      </td>
    </tr>
  );
}

export function AdminFeaturedPage({conversationId, csrfToken}: {
  conversationId: number;
  csrfToken: string;
}) {
  const msg = useMessage();
  const queryClient = useQueryClient();
  const options = adminFeaturedWorkspaceQuery(conversationId);
  const {data} = useSuspenseQuery(options);
  const {data: settings} = useSuspenseQuery(adminSettingsQuery(conversationId));
  const {data: lifecycle} = useSuspenseQuery(adminLifecycleQuery(conversationId));
  const [manualId, setManualId] = useState('');
  // The add-by-TID form's refusal, said at its field; the row actions' refusals are toasts.
  const [manualError, setManualError] = useState<string | null>(null);
  const [toast, setToast] = useState<LegacyToastMessage | null>(null);
  const dismissToast = useCallback(() => setToast(null), []);
  const manualErrorId = useId();
  function refresh() {
    void queryClient.invalidateQueries({queryKey: options.queryKey});
  }
  function showError(message: string) {
    setToast({id: Date.now(), category: 'error', message});
  }
  const selection = useMutation({
    mutationFn: ({id, source}: {id: number; source: 'system' | 'manual'}) => (
      putAdminFeaturedStatement(conversationId, id, {source}, csrfToken)
    ),
    onSuccess: () => {
      setManualId('');
      setManualError(null);
      refresh();
    },
    onError: (error: Error, {source}) => {
      const message = errorMessage(error, 'The statement could not be selected.');
      if (source === 'manual') setManualError(message);
      else showError(message);
    },
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

  return (
    <AdminShell
      title={msg('adminconv-doc-title', lifecycle.conversation.title)}
      data={lifecycle}
      gatingType={settings.conversation.gatingType}
      section="moderation"
      subPage={msg('featured-crumb')}
      toast={<LegacyToast toast={toast} onDismiss={dismissToast} />}
    >
      <div className="admin-page">
        <h1>{msg('admin-shell-moderation')}</h1>
        <AdminTabStrip label={msg('admin-shell-moderation')}
          tabs={moderationTabs(conversationId, msg)} current="featured" />

        <p className="muted" style={{fontSize: 13, marginBottom: '1.5rem'}}>
          Featured statements appear in the argument mapping tab. Participants submit a pro and con
          {' '}argument for each, then vote on the most important arguments submitted by others.
        </p>

        <div className="landing-section" style={{marginBottom: '1.5rem'}}>
          <h2 style={{fontSize: 16, marginBottom: '.5rem'}}>How to choose featured statements</h2>
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

        <h2>Confirmed<span className="admin-count">{data.selected.length}</span></h2>
        {data.selected.length ? (
          <ul className="admin-rows">
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
          </ul>
        ) : <p className="admin-empty">{msg('featured-empty')}</p>}

        <h2>System suggestions</h2>
        {!data.dataAvailability.candidates ? (
          <p className="muted" style={{fontSize: 13, marginBottom: '1.5rem'}}>
            Not available — <code>POLIS_DATABASE_URL</code> is not configured.
            {' '}Use the manual form below to add statements by TID.
          </p>
        ) : data.candidates.length === 0 ? (
          <p className="admin-empty">{msg('featured-suggestions-empty')}</p>
        ) : (
          // A table: the response counts are compared down the columns.
          <div className="admin-table-wrap">
          <table className="admin-table">
            <thead><tr><th>TID</th><th>Text</th><th>Seed</th><th className="admin-num">Agree</th><th className="admin-num">Disagree</th><th className="admin-num">Pass</th><th className="admin-num">Responses</th><th>{msg('admin-th-actions')}</th></tr></thead>
            <tbody>
              {data.candidates.map((candidate) => (
                <CandidateRow
                  key={candidate.statementId}
                  candidate={candidate}
                  pending={selection.isPending}
                  onConfirm={() => select(candidate.statementId, 'system')}
                />
              ))}
            </tbody>
          </table>
          </div>
        )}

        <h2>Add by TID</h2>
        <div className="admin-form">
          <p className="muted" style={{fontSize: 13, marginBottom: '.75rem'}}>
            Enter the Polis statement ID (TID) to feature it directly.
          </p>
          <form onSubmit={submitManual}>
            <input type="hidden" name="csrf_token" value={csrfToken} />
            <label className="admin-field admin-field--short">Statement TID
              <input type="number" name="tid" min="0" required className="admin-mono" value={manualId}
                {...(manualError ? {'aria-invalid': true, 'aria-describedby': manualErrorId} : {})}
                onChange={(event) => setManualId(event.target.value)} />
            </label>
            {manualError && <p className="admin-error" id={manualErrorId} role="alert">{manualError}</p>}
            <div className="admin-form__actions">
              <button type="submit" className="admin-button admin-button--primary" disabled={selection.isPending}>Add</button>
            </div>
          </form>
        </div>
      </div>
    </AdminShell>
  );
}
