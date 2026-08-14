import {useCallback, useState, type FormEvent} from 'react';
import {useMutation, useQueryClient, useSuspenseQuery} from '@tanstack/react-query';
import {Link} from 'react-router-dom';

import type {components} from '../../api/schema';
import {ApiContractError} from '../../api/client';
import {
  adminStatementWorkspaceQuery,
  postAdminSeedStatement,
  postAdminStatementImport,
  putAdminStatementModeration,
  putAdminStatementModerationPolicy,
} from '../../api/queries';
import {LegacyShell} from '../legacy/legacy-shell';
import {LegacyToast, type LegacyToastMessage} from '../legacy/legacy-toast';

type Workspace = components['schemas']['AdminStatementWorkspace'];
type Statement = components['schemas']['AdminStatement'];
type Status = Statement['moderation'];
type Feedback = LegacyToastMessage;

function legacyTruncate(value: string, length = 28, leeway = 5): string {
  return value.length <= length + leeway ? value : `${value.slice(0, length - 1)}…`;
}

function legacyError(error: Error, fallback: string): string {
  return error instanceof ApiContractError ? error.message : fallback;
}

function feedbackStyle(category: Feedback['category']) {
  const error = category === 'error' || category === 'import_row_error';
  const warning = category === 'warning';
  return {
    background: error ? '#fef2f2' : warning ? '#fffbeb' : '#f0fdf4',
    borderColor: error ? '#fca5a5' : warning ? '#fcd34d' : '#86efac',
    color: error ? '#991b1b' : warning ? '#92400e' : '#166534',
    border: '1px solid',
    padding: '.75rem 1rem',
    borderRadius: 6,
    fontSize: 13,
    marginBottom: '1.5rem',
  };
}

function StatementIdentity({statement}: {statement: Statement}) {
  const provenance = statement.provenance;
  const scores = provenance?.scores ?? [];
  const title = provenance
    ? `Derived from statement #${provenance.derivedFromId}. Similarity 1.00 = identical.${scores.map((score) => ` ${score.model} ${score.value.toFixed(2)}.`).join('')}`
    : undefined;
  return (
    <td className="muted">
      {statement.id}{statement.featured && ' ★'}
      {provenance && (
        <><br /><span className="prov-badge" title={title}>
          <span className="sr-only">derived from statement {provenance.derivedFromId}, </span>
          ↳ #{provenance.derivedFromId}
          {scores.map((score) => (
            <span key={score.model}> · {score.model}&nbsp;{score.value.toFixed(2)}</span>
          ))}
        </span></>
      )}
    </td>
  );
}

function VoteCounts({statement}: {statement: Statement}) {
  return (
    <td className="stmt-votes">
      <span className="vcount vcount--agree" title="Agree votes"><span className="vlabel">A</span> {statement.votes.agree}</span>
      <span className="vcount vcount--pass" title="Pass votes"><span className="vlabel">P</span> {statement.votes.pass}</span>
      <span className="vcount vcount--disagree" title="Disagree votes"><span className="vlabel">D</span> {statement.votes.disagree}</span>
    </td>
  );
}

const actions: Record<Status, {status: Status; label: string; className?: string}[]> = {
  pending: [
    {status: 'approved', label: 'approve', className: 'btn-approve'},
    {status: 'hidden', label: 'hide', className: 'btn-danger'},
  ],
  approved: [
    {status: 'hidden', label: 'hide', className: 'btn-danger'},
    {status: 'pending', label: 'pending'},
  ],
  hidden: [
    {status: 'approved', label: 'approve', className: 'btn-approve'},
    {status: 'pending', label: 'pending'},
  ],
};

function StatementActions({
  statement, conversationId, csrfToken, onMove, onError,
}: {
  statement: Statement;
  conversationId: number;
  csrfToken: string;
  onMove: (statement: Statement, status: Status) => void;
  onError: (message: string) => void;
}) {
  const mutation = useMutation({
    mutationFn: (status: Status) => putAdminStatementModeration(
      conversationId, statement.id, {status}, csrfToken,
    ),
    onSuccess: (receipt) => onMove(statement, receipt.status),
    onError: (error: Error) => {
      if (error instanceof ApiContractError
          && error.code === 'last_featured_statement_protected') {
        onError('Cannot hide or move the last featured statement to pending while argument mapping is active. Disable the argument mapping phase first.');
      } else {
        onError('Moderation action failed. Check server logs for details.');
      }
    },
  });
  return (
    <td className="stmt-actions">
      {actions[statement.moderation].map((action) => (
        <form
          key={action.status}
          style={{display: 'inline'}}
          onSubmit={(event) => {
            event.preventDefault();
            mutation.mutate(action.status);
          }}
        >
          <input type="hidden" name="csrf_token" value={csrfToken} />
          <input type="hidden" name="mod" value={{approved: 1, pending: 0, hidden: -1}[action.status]} />
          <button
            type="submit"
            className={`btn-small${action.className ? ` ${action.className}` : ''}`}
            disabled={mutation.isPending}
          >{action.label}</button>
        </form>
      ))}
    </td>
  );
}

function StatementTable({
  status, statements, conversationId, csrfToken, onMove, onError,
}: {
  status: Status;
  statements: Statement[];
  conversationId: number;
  csrfToken: string;
  onMove: (statement: Statement, status: Status) => void;
  onError: (message: string) => void;
}) {
  const labels: Record<Status, string> = {
    pending: 'Pending review', approved: 'Approved', hidden: 'Hidden',
  };
  const empty: Record<Status, string> = {
    pending: 'No statements awaiting review.',
    approved: 'No approved statements.',
    hidden: 'No hidden statements.',
  };
  return (
    <>
      <h3 className="section-heading">
        {labels[status]}
        {!!statements.length && <span className="stmt-count">{statements.length}</span>}
      </h3>
      {!statements.length ? (
        <p className="muted" style={{marginBottom: '1.5rem'}}>{empty[status]}</p>
      ) : (
        <table className="admin-table stmt-table">
          <thead><tr><th>#</th><th>Text</th><th>Votes</th><th /></tr></thead>
          <tbody>
            {statements.map((statement) => (
              <tr key={statement.id}>
                {status === 'hidden'
                  ? <td className="muted">{statement.id}</td>
                  : <StatementIdentity statement={statement} />}
                <td className="stmt-text">{statement.text}</td>
                <VoteCounts statement={statement} />
                <StatementActions
                  statement={statement}
                  conversationId={conversationId}
                  csrfToken={csrfToken}
                  onMove={onMove}
                  onError={onError}
                />
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}

export function AdminStatementsPage({conversationId, csrfToken}: {
  conversationId: number;
  csrfToken: string;
}) {
  const queryClient = useQueryClient();
  const options = adminStatementWorkspaceQuery(conversationId);
  const {data} = useSuspenseQuery(options);
  const [feedback, setFeedback] = useState<Feedback[]>([]);
  const [toast, setToast] = useState<LegacyToastMessage | null>(null);
  const [seedText, setSeedText] = useState('');
  const [derivedFrom, setDerivedFrom] = useState('');
  const [importText, setImportText] = useState('');
  const [strictModeration, setStrictModeration] = useState(
    data.moderationPolicy.mode === 'moderate',
  );
  const dismissToast = useCallback(() => setToast(null), []);

  function showFeedback(messages: Omit<Feedback, 'id'>[]) {
    const timestamp = Date.now();
    const next = messages.map((message, index) => ({...message, id: timestamp + index}));
    setFeedback(next);
    setToast(next.at(-1) ?? null);
  }

  function showError(message: string) {
    showFeedback([{category: 'error', message}]);
  }

  const seedMutation = useMutation({
    mutationFn: () => postAdminSeedStatement(
      conversationId,
      {text: seedText, derivedFromId: derivedFrom === '' ? null : Number(derivedFrom)},
      csrfToken,
    ),
    onSuccess: (receipt) => {
      let category: Feedback['category'] = 'success';
      let message = 'Seed statement added.';
      if (receipt.provenanceRecorded === false) {
        category = 'warning';
        message = 'Seed statement added, but the correction link could not be recorded.';
      } else if (receipt.derivedFromId !== null) {
        message = `Seed statement added (recorded as a correction of #${receipt.derivedFromId}).`;
      }
      setSeedText('');
      setDerivedFrom('');
      showFeedback([{category, message}]);
      void queryClient.invalidateQueries({queryKey: options.queryKey});
    },
    onError: (error: Error) => {
      if (error instanceof ApiContractError
          && error.code === 'derived_statement_not_found') {
        showError(`Statement #${derivedFrom} was not found in this conversation — fix the "corrects" number and try again. Nothing was added.`);
      } else {
        showError(legacyError(error, 'The voting service is unavailable.'));
      }
    },
  });

  const importMutation = useMutation({
    mutationFn: (statements: string[]) => postAdminStatementImport(
      conversationId, {statements}, csrfToken,
    ),
    onSuccess: (receipt) => {
      const messages: Omit<Feedback, 'id'>[] = [];
      if (receipt.outcome.skippedExisting) {
        messages.push({
          category: 'warning',
          message: `${receipt.outcome.skippedExisting} statement${receipt.outcome.skippedExisting === 1 ? '' : 's'} already existed in this conversation and were skipped.`,
        });
      }
      if (receipt.outcome.imported && !receipt.outcome.skippedExisting
          && !receipt.outcome.failedUpstream) {
        messages.push({
          category: 'import_result',
          message: `✓ ${receipt.outcome.imported} statement${receipt.outcome.imported === 1 ? '' : 's'} imported`,
        });
      } else if (receipt.outcome.imported) {
        messages.push({
          category: 'import_result',
          message: `✓ ${receipt.outcome.imported} imported — ⚠ ${receipt.outcome.skippedExisting + receipt.outcome.failedUpstream} skipped`,
        });
      } else if (receipt.outcome.skippedExisting) {
        messages.push({
          category: 'import_result',
          message: `⚠ 0 imported — ${receipt.outcome.skippedExisting} already existed in Polis`,
        });
      } else {
        messages.push({category: 'warning', message: 'No statements were imported — there were no valid rows.'});
        messages.push({category: 'import_result', message: '⚠ 0 imported — Polis returned no result'});
      }
      setImportText('');
      showFeedback(messages);
      void queryClient.invalidateQueries({queryKey: options.queryKey});
    },
    onError: (error: Error) => showError(legacyError(error, 'The voting service is unavailable.')),
  });

  const policyMutation = useMutation({
    mutationFn: () => putAdminStatementModerationPolicy(
      conversationId,
      {mode: strictModeration ? 'moderate' : 'auto_approve'},
      csrfToken,
    ),
    onSuccess: (receipt) => {
      queryClient.setQueryData<Workspace>(options.queryKey, receipt.workspace);
      setStrictModeration(receipt.mode === 'moderate');
      setFeedback([]);
      setToast(null);
    },
    onError: (error: Error) => {
      if (error instanceof ApiContractError && error.code === 'verification_unavailable') {
        showError('Could not verify the current moderation state. Try again later.');
      } else if (error instanceof ApiContractError && error.code === 'upstream_unavailable') {
        showError('Could not update moderation settings. Check server logs for details.');
      } else if (error instanceof ApiContractError && error.code === 'command_outcome_unknown') {
        showError('The voting service may have been updated, but the local policy could not be saved. Do not retry until a site admin checks it.');
      } else {
        showError('Could not save the moderation policy. Try again later.');
      }
    },
  });

  function moveStatement(statement: Statement, status: Status) {
    queryClient.setQueryData<Workspace>(options.queryKey, (workspace) => {
      if (!workspace) return workspace;
      const statements = {
        pending: workspace.statements.pending.filter((row) => row.id !== statement.id),
        approved: workspace.statements.approved.filter((row) => row.id !== statement.id),
        hidden: workspace.statements.hidden.filter((row) => row.id !== statement.id),
      };
      statements[status] = [...statements[status], {...statement, moderation: status}];
      return {...workspace, statements};
    });
    setFeedback([]);
    setToast(null);
  }

  function submitImport(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const rows = importText.split(/\r?\n/)
      .map((text, index) => ({row: index + 1, text: text.trim()}))
      .filter(({text}) => text);
    if (rows.length > data.seeding.maxStatementsPerImport) {
      showFeedback([{
        category: 'import_result',
        message: `✗ Import rejected — nothing was imported. Text import contains ${rows.length} lines, maximum is ${data.seeding.maxStatementsPerImport}. Reduce it and try again. (Parse errors may also be present — fix everything before retrying.)`,
      }]);
      return;
    }
    const seen = new Set<string>();
    const errors: Omit<Feedback, 'id'>[] = [];
    rows.forEach(({row, text}) => {
      if (text.length > data.seeding.maxCharactersPerStatement) {
        errors.push({category: 'import_row_error', message: `Row ${row}: text is too long (${text.length} characters; max ${data.seeding.maxCharactersPerStatement}).`});
      } else if (seen.has(text)) {
        errors.push({category: 'import_row_error', message: `Row ${row}: duplicate — already added from an earlier row.`});
      }
      seen.add(text);
    });
    if (errors.length) {
      showFeedback([...errors, {
        category: 'import_result',
        message: '✗ Import rejected — nothing was added. One invalid line rejects the whole import; fix the lines listed above and try again.',
      }]);
      return;
    }
    importMutation.mutate(rows.map(({text}) => text));
  }

  const title = data.conversation.title;
  return (
    <LegacyShell
      headerMode="admin"
      title={`Statements — ${title} — ProtoWiki`}
      headerCrumb={(
        <nav className="header-crumb" aria-label="Admin breadcrumb">
          <span className="header-crumb-sep">/</span>
          <Link to="/app/admin">Admin panel</Link>
          <span className="header-crumb-sep">/</span>
          <Link to={data.links.lifecycle}>{legacyTruncate(title)}</Link>
          <span className="header-crumb-sep">/</span>
          <span>Statements</span>
        </nav>
      )}
      toast={<LegacyToast toast={toast} onDismiss={dismissToast} />}
    >
      <div className="container">
        <h2>Statements — {title}</h2>

        <div className="landing-section" style={{marginBottom: '1.5rem'}}>
          <h3 style={{fontSize: 16, marginBottom: '.5rem'}}>How statement management works</h3>
          <p className="muted" style={{fontSize: 13, marginBottom: '.6rem'}}>
            Pending statements are held for moderator review. Approve makes a statement visible
            {' '}for participant voting, hide removes it from participant voting, and pending returns
            {' '}an approved or hidden statement to the review queue.
          </p>
          <ul style={{fontSize: 13, paddingLeft: '1.25rem', marginBottom: '.6rem'}}>
            <li>Vote counts show <strong>A</strong>gree · <strong>P</strong>ass · <strong>D</strong>isagree totals from Polis when the statistics database is available.</li>
            <li>Seed statements come from moderator entry or imports; participant-submitted statements appear in the same moderation lists.</li>
            <li>A star marks statements already selected as featured. A correction marker links derived statements back to the original TID.</li>
            <li>Seed entry and imports are available only during preparation or open statement submission.</li>
          </ul>
          <p className="muted" style={{fontSize: 13, marginBottom: 0}}>
            The text import strips spreadsheet formula prefixes, removes HTML, rejects invalid
            {' '}rows as a batch, and skips statements already present in the conversation.
          </p>
        </div>

        {!data.dataAvailability.statements && (
          <div style={feedbackStyle('error')}>Could not load statements. Check server logs.</div>
        )}
        {feedback.map((message) => (
          <div key={message.id} style={feedbackStyle(message.category)}>{message.message}</div>
        ))}

        {!data.seeding.allowed ? (
          <>
            <h3 className="section-heading">Seed statements locked</h3>
            <div className="edit-form">
              <p className="muted" style={{marginBottom: 0, fontSize: 13}}>
                {data.seeding.lockReason} Seed statements can only be added during preparation
                {' '}or while statement submission is open.
              </p>
            </div>
          </>
        ) : (
          <>
            <h3 className="section-heading">Add seed statement</h3>
            <div className="edit-form">
              <p className="muted" style={{marginBottom: '.75rem', fontSize: 13}}>
                Adds a statement that immediately appears in the vote view for all participants.
                {' '}Statements added here appear as regular participant statements (not seed-marked).
              </p>
              <form onSubmit={(event) => { event.preventDefault(); seedMutation.mutate(); }}>
                <input type="hidden" name="csrf_token" value={csrfToken} />
                <label>Statement text (max 280 characters)
                  <textarea
                    name="txt"
                    rows={3}
                    maxLength={280}
                    id="seed-txt"
                    required
                    placeholder="Enter a statement participants will vote on…"
                    value={seedText}
                    onChange={(event) => setSeedText(event.target.value)}
                  />
                </label>
                <label className="muted" style={{display: 'block', marginTop: '.5rem', fontSize: 13}}>
                  Corrects statement&nbsp;#&nbsp;(optional)
                  <input
                    type="number"
                    name="derived_from"
                    min={0}
                    style={{width: '6rem'}}
                    title="If this is a corrected/derived version of an existing statement, enter its #id so the link is recorded (#143)."
                    value={derivedFrom}
                    onChange={(event) => setDerivedFrom(event.target.value)}
                  />
                </label>
                <div style={{display: 'flex', alignItems: 'center', gap: '1rem', marginTop: '.5rem'}}>
                  <button type="submit" disabled={seedMutation.isPending}>Add seed statement</button>
                  <span id="seed-count" className="muted" style={{fontSize: 12}}>{seedText.length} / 280</span>
                </div>
              </form>
            </div>

            <h3 className="section-heading">Import seed statements from text</h3>
            <div className="edit-form">
              <p className="muted" style={{marginBottom: '.75rem', fontSize: 13}}>
                Paste one statement per line. Blank lines are ignored. Maximum {data.seeding.maxStatementsPerImport}
                {' '}statements per import and {data.seeding.maxCharactersPerStatement} characters per statement.
              </p>
              <p className="muted" style={{marginBottom: '.75rem', fontSize: 13}}>
                All-or-nothing: if any line is invalid (too long, duplicated within your paste, or
                {' '}over the limit) nothing is imported and the offending lines are listed. Lines
                {' '}identical to an existing statement are skipped automatically — the rest still import.
              </p>
              <form onSubmit={submitImport}>
                <input type="hidden" name="csrf_token" value={csrfToken} />
                <label>Statements
                  <textarea
                    name="statement_texts"
                    rows={8}
                    maxLength={data.seeding.maxStatementsPerImport * (data.seeding.maxCharactersPerStatement + 1)}
                    placeholder={'First statement\nSecond statement\nThird statement'}
                    value={importText}
                    onChange={(event) => setImportText(event.target.value)}
                  />
                </label>
                <div style={{marginTop: '.75rem', display: 'flex', alignItems: 'center', gap: '1rem', flexWrap: 'wrap'}}>
                  <button type="submit" disabled={importMutation.isPending}>Import statements</button>
                </div>
              </form>
            </div>
          </>
        )}

        <h3 className="section-heading">Moderation settings</h3>
        <div className="edit-form" style={{marginBottom: '2rem'}}>
          <form onSubmit={(event) => { event.preventDefault(); policyMutation.mutate(); }}>
            <input type="hidden" name="csrf_token" value={csrfToken} />
            <label className="checkbox-label" style={{fontWeight: 'normal', color: 'var(--text)'}}>
              <input
                type="checkbox"
                name="strict_moderation"
                value="1"
                checked={strictModeration}
                onChange={(event) => setStrictModeration(event.target.checked)}
              />
              Strict moderation — new participant statements must be approved before others can vote on them
            </label>
            <div style={{marginTop: '.75rem'}}>
              <button type="submit" className="btn-small" disabled={policyMutation.isPending}>Save</button>
            </div>
          </form>
        </div>

        {(['pending', 'approved', 'hidden'] as Status[]).map((status) => (
          <StatementTable
            key={status}
            status={status}
            statements={data.statements[status]}
            conversationId={conversationId}
            csrfToken={csrfToken}
            onMove={moveStatement}
            onError={showError}
          />
        ))}
      </div>
    </LegacyShell>
  );
}
