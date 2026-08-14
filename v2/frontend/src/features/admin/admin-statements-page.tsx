import {useState, type FormEvent} from 'react';
import {useMutation, useQueryClient, useSuspenseQuery} from '@tanstack/react-query';
import {Link} from 'react-router-dom';

import type {components} from '../../api/schema';
import {ApiContractError} from '../../api/client';
import {
  adminStatementWorkspaceQuery,
  postAdminStatementImport,
  putAdminStatementModerationPolicy,
  putAdminStatementModeration,
} from '../../api/queries';

type Workspace = components['schemas']['AdminStatementWorkspace'];
type Statement = components['schemas']['AdminStatement'];
type Status = Statement['moderation'];

function errorMessage(error: Error | null, fallback: string) {
  if (!error) return null;
  return error instanceof ApiContractError ? error.message : fallback;
}

function StatementRow({statement, conversationId, csrfToken, onMove}: {
  statement: Statement;
  conversationId: number;
  csrfToken: string;
  onMove: (statement: Statement, status: Status) => void;
}) {
  const mutation = useMutation({
    mutationFn: (status: Status) => putAdminStatementModeration(
      conversationId, statement.id, {status}, csrfToken,
    ),
    onSuccess: (receipt) => onMove(statement, receipt.status),
  });
  const actions = (['approved', 'pending', 'hidden'] as Status[])
    .filter((status) => status !== statement.moderation);
  return (
    <li className="statement-admin-row">
      <div className="statement-admin-row__meta">
        <code>#{statement.id}</code>
        {statement.seed && <span>seed</span>}
        {statement.featured && <span>featured</span>}
        {statement.provenance && <span>derived from #{statement.provenance.derivedFromId}</span>}
      </div>
      <p>{statement.text}</p>
      <dl aria-label={`Votes for statement ${statement.id}`}>
        <div><dt>Agree</dt><dd>{statement.votes.agree}</dd></div>
        <div><dt>Pass</dt><dd>{statement.votes.pass}</dd></div>
        <div><dt>Disagree</dt><dd>{statement.votes.disagree}</dd></div>
      </dl>
      <div className="statement-admin-row__actions">
        {actions.map((status) => (
          <button
            key={status}
            type="button"
            data-action={status}
            disabled={mutation.isPending}
            onClick={() => mutation.mutate(status)}
          >
            {status === 'approved' ? 'Approve' : status === 'hidden' ? 'Hide' : 'Move to pending'}
          </button>
        ))}
      </div>
      {mutation.error && <p className="statement-admin-error" role="alert">{
        errorMessage(mutation.error, 'Moderation could not be updated.')
      }</p>}
    </li>
  );
}

function StatementBucket({status, statements, conversationId, csrfToken, onMove}: {
  status: Status;
  statements: Statement[];
  conversationId: number;
  csrfToken: string;
  onMove: (statement: Statement, status: Status) => void;
}) {
  const labels: Record<Status, string> = {
    pending: 'Pending review', approved: 'Approved', hidden: 'Hidden',
  };
  return (
    <section className="statement-bucket" aria-labelledby={`statement-${status}-heading`}>
      <header>
        <h2 id={`statement-${status}-heading`}>{labels[status]}</h2>
        <span>{statements.length}</span>
      </header>
      {statements.length ? <ul>{statements.map((statement) => (
        <StatementRow
          key={statement.id}
          statement={statement}
          conversationId={conversationId}
          csrfToken={csrfToken}
          onMove={onMove}
        />
      ))}</ul> : <p className="statement-bucket__empty">No {labels[status].toLowerCase()} statements.</p>}
    </section>
  );
}

export function AdminStatementsPage({conversationId, csrfToken}: {
  conversationId: number;
  csrfToken: string;
}) {
  const queryClient = useQueryClient();
  const options = adminStatementWorkspaceQuery(conversationId);
  const {data} = useSuspenseQuery(options);
  const [seedText, setSeedText] = useState('');
  const [receipt, setReceipt] = useState<string | null>(null);
  const lines = seedText.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  const importMutation = useMutation({
    mutationFn: () => postAdminStatementImport(
      conversationId, {statements: lines}, csrfToken,
    ),
    onSuccess: (result) => {
      const summary = [
        `${result.outcome.imported} imported`,
        result.outcome.skippedExisting && `${result.outcome.skippedExisting} already present`,
        result.outcome.skippedDuplicateInput && `${result.outcome.skippedDuplicateInput} duplicate input`,
        result.outcome.failedUpstream && `${result.outcome.failedUpstream} failed upstream`,
      ].filter(Boolean).join(' · ');
      setReceipt(summary);
      setSeedText('');
      void queryClient.invalidateQueries({queryKey: options.queryKey});
    },
  });
  const policyMutation = useMutation({
    mutationFn: (mode: 'moderate' | 'auto_approve') => (
      putAdminStatementModerationPolicy(conversationId, {mode}, csrfToken)
    ),
    onSuccess: (result) => {
      queryClient.setQueryData<Workspace>(options.queryKey, result.workspace);
      const behavior = result.mode === 'moderate'
        ? 'Future participant statements will wait for review.'
        : 'Future participant statements will be approved automatically.';
      setReceipt(`${behavior} Existing statement decisions were preserved.${
        result.reconciledStatements
          ? ` ${result.reconciledStatements} legacy statement decision(s) were made explicit.`
          : ''
      }`);
    },
  });

  function moveStatement(statement: Statement, status: Status) {
    queryClient.setQueryData<Workspace>(options.queryKey, (workspace) => {
      if (!workspace) return workspace;
      const next = {
        pending: workspace.statements.pending.filter((row) => row.id !== statement.id),
        approved: workspace.statements.approved.filter((row) => row.id !== statement.id),
        hidden: workspace.statements.hidden.filter((row) => row.id !== statement.id),
      };
      next[status] = [...next[status], {...statement, moderation: status}];
      return {...workspace, statements: next};
    });
    setReceipt(`Statement #${statement.id} moved to ${status}.`);
  }

  function submitImport(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    importMutation.mutate();
  }

  return (
    <main className="statements-shell" id="main">
      <nav className="record-breadcrumb" aria-label="Breadcrumb">
        <a href="/admin">Admin panel</a><span>/</span>
        <Link to={data.links.lifecycle}>{data.conversation.title}</Link><span>/</span>
        <span>Statements</span>
      </nav>
      <header className="statements-heading">
        <div>
          <p className="eyebrow">Moderation workspace</p>
          <h1>Statements</h1>
          <p>Review participant proposals, inspect vote totals, and seed the voting queue.</p>
        </div>
        <dl>
          <div><dt>Pending</dt><dd>{data.statements.pending.length}</dd></div>
          <div><dt>Approved</dt><dd>{data.statements.approved.length}</dd></div>
          <div><dt>Hidden</dt><dd>{data.statements.hidden.length}</dd></div>
        </dl>
      </header>

      {!data.dataAvailability.statements && (
        <p className="statement-admin-notice" role="status">Statement data is temporarily unavailable. Moderation is disabled.</p>
      )}
      {data.moderationPolicy.available && (
        <section className="statement-admin-policy" aria-labelledby="statement-policy-heading">
          <div>
            <p className="eyebrow">Future submissions only</p>
            <h2 id="statement-policy-heading">Default moderation decision</h2>
            <p>Changing this default never changes the status or visibility of existing statements.</p>
          </div>
          <div role="group" aria-label="Default moderation decision">
            <button
              type="button"
              aria-pressed={data.moderationPolicy.mode === 'moderate'}
              disabled={policyMutation.isPending || data.moderationPolicy.mode === 'moderate'}
              onClick={() => policyMutation.mutate('moderate')}
            >Require review <span>New statements start pending</span></button>
            <button
              type="button"
              aria-pressed={data.moderationPolicy.mode === 'auto_approve'}
              disabled={policyMutation.isPending || data.moderationPolicy.mode === 'auto_approve'}
              onClick={() => policyMutation.mutate('auto_approve')}
            >Auto-approve <span>New statements start approved</span></button>
          </div>
          {policyMutation.error && <p className="statement-admin-error" role="alert">{
            errorMessage(policyMutation.error, 'The moderation policy could not be updated.')
          }</p>}
        </section>
      )}
      {receipt && <p className="lifecycle-receipt" role="status">{receipt}</p>}

      <section className="statement-import" aria-labelledby="statement-import-heading">
        <div>
          <p className="eyebrow">Approved seeds</p>
          <h2 id="statement-import-heading">Paste one statement per line</h2>
          <p>Imported statements are approved immediately. HTML and spreadsheet formula prefixes are removed server-side.</p>
          {!data.seeding.allowed && <p className="statement-admin-error">{data.seeding.lockReason}</p>}
        </div>
        {data.seeding.allowed && (
          <form onSubmit={submitImport}>
            <label htmlFor="seed-statements">Seed statements</label>
            <textarea
              id="seed-statements"
              rows={8}
              value={seedText}
              onChange={(event) => setSeedText(event.target.value)}
              placeholder={'First statement\nSecond statement\nThird statement'}
            />
            <div><span>{lines.length} / {data.seeding.maxStatementsPerImport} statements</span><span>{data.seeding.maxCharactersPerStatement} characters each</span></div>
            <button type="submit" disabled={!lines.length || lines.length > data.seeding.maxStatementsPerImport || importMutation.isPending}>
              {importMutation.isPending ? 'Importing…' : 'Import approved seeds'}
            </button>
            {importMutation.error && <p className="statement-admin-error" role="alert">{
              errorMessage(importMutation.error, 'Statements could not be imported.')
            }</p>}
          </form>
        )}
      </section>

      <div className="statement-buckets">
        {(['pending', 'approved', 'hidden'] as Status[]).map((status) => (
          <StatementBucket
            key={status}
            status={status}
            statements={data.statements[status]}
            conversationId={conversationId}
            csrfToken={csrfToken}
            onMove={moveStatement}
          />
        ))}
      </div>
    </main>
  );
}
