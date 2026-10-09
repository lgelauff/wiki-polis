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
import {useMessage, type Message} from '../../i18n/messages';
import {AdminShell} from './admin-shell';
import {AdminTime} from './admin-time';
import {StatementProvenance} from './admin-provenance';
import {AdminTabStrip} from './admin-tab-strip';
import {moderationTabs} from './admin-moderation-tabs';
import {LegacyToast, type LegacyToastMessage} from '../legacy/legacy-toast';

type Workspace = components['schemas']['AdminFeaturedWorkspace'];
type Selected = components['schemas']['AdminFeaturedSelection'];
type Candidate = components['schemas']['AdminFeaturedCandidate'];

/** A refusal in the page's words: the server's message is for developers (plan_i18n.md
 *  rule 4). Removing the last featured statement while argument mapping runs has its own. */
function errorMessage(msg: Message, error: Error): string {
  return error instanceof ApiContractError && error.code === 'last_featured_statement_protected'
    ? msg('flash-last-featured-remove') : msg('adminconv-command-failed');
}

/** The start of a text, to tell one row's buttons from the next one's: every row has the
 *  same Remove, Hide and Delete, so their accessible names carry this after the visible
 *  word (which stays first, as the name a voice-control user says). */
function excerpt(text: string): string {
  const flat = text.replace(/\s+/g, ' ').trim();
  return flat.length > 60 ? `${flat.slice(0, 59)}…` : flat;
}

/** What follows a row control's visible word in its accessible name. */
function RowName({children}: {children: string}) {
  return <>{' '}<span className="sr-only">{`— ${children}`}</span></>;
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
    onError: (error: Error) => showError(errorMessage(msg, error)),
  });
  const visibility = useMutation({
    mutationFn: ({id, hidden}: {id: number; hidden: boolean}) => (
      putAdminFeaturedArgument(conversationId, id, {hidden}, csrfToken)
    ),
    onSuccess: refresh,
    onError: (error: Error) => showError(errorMessage(msg, error)),
  });
  const deletion = useMutation({
    mutationFn: (id: number) => deleteAdminFeaturedArgument(
      conversationId, id, csrfToken,
    ),
    onSuccess: refresh,
    onError: (error: Error) => showError(errorMessage(msg, error)),
  });
  return (
    <li className="admin-row">
      <div className="admin-row__text">
        <span className="admin-row__id">#{selection.statementId}</span>{' '}
        {selection.text ?? '—'}
        {selection.provenance && <StatementProvenance provenance={selection.provenance} />}
      </div>
      <div className="admin-row__actions">
        {/* Not red: a removed statement can be featured again. */}
        <button type="button" className="admin-row__text-button" disabled={remove.isPending}
          onClick={() => {
            if (!informedVotingLive || globalThis.confirm(msg('featured-remove-live-confirm'))) remove.mutate();
          }}>
          {msg('admin-btn-remove')}<RowName>{`#${selection.statementId}`}</RowName>
        </button>
      </div>
      {/* Its arguments, one small row each: side, text, who and when, its state in words,
          and what can be done to it. */}
      {selection.arguments.length ? (
        <ul className="admin-row__sub" aria-label={msg('featured-arguments-label')}>
          {selection.arguments.map((argument) => (
            <li key={argument.id}>
              <span className="admin-row__suffix">
                {argument.side === 'pro' ? msg('conv-arg-col-for') : msg('conv-arg-col-against')}
              </span>
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
                  <RowName>{excerpt(argument.body)}</RowName>
                </button>
                {/* Red and confirmed: deleting an argument and its ratings cannot be undone. */}
                <button type="button" className="admin-row__text-button admin-row__text-button--danger"
                  disabled={deletion.isPending}
                  onClick={() => {
                    if (globalThis.confirm(msg('featured-arg-delete-confirm'))) deletion.mutate(argument.id);
                  }}>
                  {msg('featured-arg-delete')}<RowName>{excerpt(argument.body)}</RowName>
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
        {candidate.provenance && <StatementProvenance provenance={candidate.provenance} />}
      </td>
      {/* A seed statement is marked with a check that names itself. */}
      <td>{candidate.seed && <span title={msg('featured-th-seed')} aria-label={msg('featured-th-seed')} role="img">✓</span>}</td>
      <td className="admin-num">{candidate.votes.agree}</td>
      <td className="admin-num">{candidate.votes.disagree}</td>
      <td className="admin-num">{candidate.votes.pass}</td>
      <td className="admin-num">{candidate.votes.total}</td>
      <td>
        <button type="button" className="admin-row__text-button" disabled={pending} onClick={onConfirm}>
          {msg('featured-btn-confirm')}<RowName>{`#${candidate.statementId}`}</RowName>
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
  // The add-by-number form's refusal, said at its field; the row actions' refusals are toasts.
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
      const message = errorMessage(msg, error);
      if (source === 'manual') setManualError(message);
      else showError(message);
    },
  });
  function select(id: number, source: 'system' | 'manual') {
    if (!data.phase.informedVotingLive || globalThis.confirm(msg('featured-select-live-confirm'))) {
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

        <h2>{msg('featured-confirmed-heading')}{' '}<span className="admin-count">{data.selected.length}</span></h2>
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

        {/* Without the statistics database there are no suggestions: the section is left
            out rather than shown with a note about configuration. Adding by number still works. */}
        {data.dataAvailability.candidates && <h2>{msg('featured-suggestions-heading')}</h2>}
        {!data.dataAvailability.candidates ? null : data.candidates.length === 0 ? (
          <p className="admin-empty">{msg('featured-suggestions-empty')}</p>
        ) : (
          // A table: the response counts are compared down the columns.
          <div className="admin-table-wrap">
          <table className="admin-table">
            <thead><tr>
              <th>{msg('featured-th-number')}</th><th>{msg('featured-th-text')}</th><th>{msg('featured-th-seed')}</th>
              <th className="admin-num">{msg('featured-th-agree')}</th><th className="admin-num">{msg('featured-th-disagree')}</th>
              <th className="admin-num">{msg('conv-vote-pass')}</th><th className="admin-num">{msg('featured-th-votes')}</th>
              <th>{msg('admin-th-actions')}</th>
            </tr></thead>
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

        <h2>{msg('featured-addnumber-heading')}</h2>
        <div className="admin-form">
          <form onSubmit={submitManual}>
            <input type="hidden" name="csrf_token" value={csrfToken} />
            <label className="admin-field admin-field--short">{msg('featured-label-number')}
              <input type="number" name="tid" min="0" required className="admin-mono" value={manualId}
                {...(manualError ? {'aria-invalid': true, 'aria-describedby': manualErrorId} : {})}
                onChange={(event) => setManualId(event.target.value)} />
            </label>
            {manualError && <p className="admin-error" id={manualErrorId} role="alert">{manualError}</p>}
            <div className="admin-form__actions">
              <button type="submit" className="admin-button admin-button--primary" disabled={selection.isPending}>{msg('featured-addnumber-heading')}</button>
            </div>
          </form>
        </div>
      </div>
    </AdminShell>
  );
}
