import {useCallback, useEffect, useState, type FormEvent} from 'react';
import {useLocation} from 'react-router-dom';
import {useMutation, useQueryClient, useSuspenseQuery} from '@tanstack/react-query';

import type {components} from '../../api/schema';
import {ApiContractError} from '../../api/client';
import {
  adminLifecycleQuery,
  adminSettingsQuery,
  adminStatementWorkspaceQuery,
  postAdminSeedStatement,
  postAdminStatementImport,
  putAdminStatementMeta,
} from '../../api/queries';
import {useMessage, type Message} from '../../i18n/messages';
import {sortByBasedOn} from './admin-based-on';
import {AdminComing} from './admin-coming';
import {AdminShell} from './admin-shell';
import {useAnnouncer} from './admin-announcer';
import {useRowFocus} from './admin-row-focus';
import {StatementActions} from './admin-statement-actions';
import {StatementProvenance} from './admin-provenance';
import {AdminTabStrip} from './admin-tab-strip';
import {contentTabs} from './admin-content-tabs';
import {LegacyToast, type LegacyToastMessage} from '../legacy/legacy-toast';

type Workspace = components['schemas']['AdminStatementWorkspace'];
type Statement = components['schemas']['AdminStatement'];
type Status = Statement['moderation'];
/** One line of a form's result: said on the form's status line, under its button, as an
 *  error (role=alert) or as the outcome (role=status). Never also a toast: a form's result
 *  belongs to the form; toasts are for row actions. */
type Feedback = {id: number; error: boolean; message: string};


/** A form's result lines, at the form. */
function FormFeedback({lines}: {lines: Feedback[]}) {
  const errors = lines.filter((line) => line.error);
  const outcomes = lines.filter((line) => !line.error);
  return (
    <>
      {errors.length > 0 && <div role="alert">{errors.map((line) => (
        <p key={line.id} className="admin-error">{line.message}</p>
      ))}</div>}
      {/* Always mounted, so the region exists before its first message; each line is keyed
          by its own id, so the same outcome twice is a new line and is read again. */}
      <div role="status">{outcomes.map((line) => (
        <p key={line.id} className="admin-status">{line.message}</p>
      ))}</div>
    </>
  );
}

/** A moderation refusal in the page's words: the server's message is for developers. */
function moderationError(msg: Message, error: Error): string {
  return error instanceof ApiContractError && error.code === 'last_featured_statement_protected'
    ? msg('flash-last-featured-hide') : msg('flash-moderation-failed');
}

/** Which statements the page shows, chosen by the state switch. Approved is the default
 *  here: on the Content side the question is what the consultation says, not what is
 *  waiting, and what is waiting is Moderation's page. */
type Position = 'approved' | 'unmoderated' | 'hidden';

const POSITIONS: {id: Position; glyph: string; key: string}[] = [
  {id: 'approved', glyph: '✓', key: 'admin-moderation-state-approved'},
  {id: 'unmoderated', glyph: '○', key: 'admin-moderation-state-unmoderated'},
  {id: 'hidden', glyph: '✕', key: 'admin-moderation-state-hidden'},
];

const LIST: Record<Position, 'approved' | 'pending' | 'hidden'> = {
  approved: 'approved',
  unmoderated: 'pending',
  hidden: 'hidden',
};

/** What is said when a statement has moved to a list. */
const MOVED: Record<Status, string> = {
  approved: 'admin-moderation-statement-approved',
  hidden: 'admin-moderation-statement-hidden',
  pending: 'admin-moderation-statement-unmoderated',
};

/** "Most responses" is what a reader of the statements wants first; "Oldest first" is the order
 *  they arrived; "Based on" groups a correction under the statement it corrects, with the
 *  same function as the Moderation queue (`sortByBasedOn`). All three sort what is already
 *  loaded. */
type Sort = 'most-responses' | 'oldest' | 'based-on';

function responseTotal(statement: Statement): number {
  return statement.votes.agree + statement.votes.pass + statement.votes.disagree;
}

function sortStatements(rows: Statement[], sort: Sort): Statement[] {
  if (sort === 'based-on') return sortByBasedOn(rows);
  const byId = [...rows].sort((left, right) => left.id - right.id);
  if (sort === 'most-responses') {
    return byId.sort((left, right) => responseTotal(right) - responseTotal(left) || left.id - right.id);
  }
  return byId;
}

/** One statement as one row: a star when it is featured, the text, its number as a muted
 *  suffix (what "↳ #N", Featured's add by number and "Corrects statement #" refer to),
 *  where it came from, its votes and what can be done to it. The row's id is the target of
 *  "↳ #N" on the rows derived from it. */
function StatementRow({conversationId, statement, sourceShown, csrfToken, move, onMeta, onError}: {
  conversationId: number;
  statement: Statement;
  sourceShown: boolean;
  csrfToken: string;
  move: (statement: Statement, status: Status) => void;
  onMeta: (statement: Statement, meta: boolean) => void;
  onError: (message: string) => void;
}) {
  const msg = useMessage();
  // Once someone else has responded, a meta change is said first and confirmed (2026-11-07).
  const [confirming, setConfirming] = useState(false);
  const meta = useMutation({
    mutationFn: (acknowledgeResponses: boolean) => putAdminStatementMeta(
      conversationId, statement.id, {meta: !statement.meta, acknowledgeResponses}, csrfToken,
    ),
    onSuccess: (receipt) => {
      setConfirming(false);
      onMeta(statement, receipt.meta);
    },
    onError: (error: Error) => {
      if (error instanceof ApiContractError && error.code === 'meta_has_responses') {
        setConfirming(true);
      } else {
        setConfirming(false);
        onError(msg('adminconv-command-failed'));
      }
    },
  });
  // Seeds only (owner, 2026-09-24); a featured statement is an opinion, so it is never marked.
  const canToggle = statement.seed && (statement.meta || !statement.featured);
  const toggleLabel = statement.meta ? msg('stmts-meta-unmark') : msg('stmts-meta-mark');
  const toggle = canToggle ? (
    <button
      type="button"
      className="admin-row__text-button"
      aria-expanded={statement.hasResponses ? confirming : undefined}
      disabled={meta.isPending}
      onClick={() => {
        if (statement.hasResponses) setConfirming(true);
        else meta.mutate(false);
      }}
    >
      {toggleLabel}
    </button>
  ) : null;
  return (
    <li className="admin-row" id={`statement-${statement.id}`} data-row-id={statement.id}>
      <div className="admin-row__text">
        {statement.featured && (
          <span className="admin-row__star" title={msg('conv-arg-featured-label')}>
            <span aria-hidden="true">★ </span>
            <span className="sr-only">{msg('conv-arg-featured-label')}: </span>
          </span>
        )}
        {statement.text}
        <span className="admin-row__suffix">{` #${statement.id}`}</span>
        {statement.meta && (
          <span className="admin-row__suffix">{` · ${msg('meta-statement-label')}`}</span>
        )}
        {statement.provenance && (
          <StatementProvenance provenance={statement.provenance} linked={sourceShown} />
        )}
      </div>
      <div className="admin-row__counts">
        <span title={msg('stmts-vote-agree-title')}>{msg('stmts-vlabel-a')} {statement.votes.agree}</span>
        {' · '}
        <span title={msg('stmts-vote-pass-title')}>{msg('stmts-vlabel-p')} {statement.votes.pass}</span>
        {' · '}
        <span title={msg('stmts-vote-disagree-title')}>{msg('stmts-vlabel-d')} {statement.votes.disagree}</span>
      </div>
      <StatementActions
        statement={statement}
        conversationId={conversationId}
        csrfToken={csrfToken}
        withUnmoderate
        leading={toggle}
        onMoved={move}
        onError={(error) => onError(moderationError(msg, error))}
      />
      {confirming && (
        <div className="admin-row__note" role="alert">
          <p>{msg('stmts-meta-warn-responses', statement.id)}</p>
          <div className="admin-form__actions">
            <button type="button" className="admin-button admin-button--primary"
              disabled={meta.isPending} onClick={() => meta.mutate(true)}>{toggleLabel}</button>
            <button type="button" className="admin-button"
              onClick={() => setConfirming(false)}>{msg('common-cancel')}</button>
          </div>
        </div>
      )}
    </li>
  );
}

export function AdminStatementsPage({conversationId, csrfToken}: {
  conversationId: number;
  csrfToken: string;
}) {
  const msg = useMessage();
  const queryClient = useQueryClient();
  const options = adminStatementWorkspaceQuery(conversationId);
  const {data} = useSuspenseQuery(options);
  const {data: settings} = useSuspenseQuery(adminSettingsQuery(conversationId));
  const {data: lifecycle} = useSuspenseQuery(adminLifecycleQuery(conversationId));
  // A link to one statement (the Queue's "↳ #N") opens the page on the list that holds it.
  const {hash} = useLocation();
  const target = /^#statement-(\d+)$/.exec(hash)?.[1];
  const [position, setPosition] = useState<Position>(() => {
    const id = Number(target);
    if (data.statements.pending.some((row) => row.id === id)) return 'unmoderated';
    if (data.statements.hidden.some((row) => row.id === id)) return 'hidden';
    return 'approved';
  });
  // ...and scrolled to it: a client-side navigation does not do what a page load would.
  useEffect(() => {
    if (target) document.getElementById(`statement-${target}`)?.scrollIntoView?.({block: 'center'});
  }, [target]);
  const [sort, setSort] = useState<Sort>('most-responses');
  const [search, setSearch] = useState('');
  // Each form's result lines, said at that form.
  const [seedFeedback, setSeedFeedback] = useState<Feedback[]>([]);
  const [importFeedback, setImportFeedback] = useState<Feedback[]>([]);
  // Toasts are for the row actions only.
  const [toast, setToast] = useState<LegacyToastMessage | null>(null);
  const [seedText, setSeedText] = useState('');
  const [derivedFrom, setDerivedFrom] = useState('');
  const [seedMeta, setSeedMeta] = useState(false);
  const [importText, setImportText] = useState('');
  const dismissToast = useCallback(() => setToast(null), []);
  const announcer = useAnnouncer();

  function lines(messages: Omit<Feedback, 'id'>[]): Feedback[] {
    const timestamp = Date.now();
    return messages.map((message, index) => ({...message, id: timestamp + index}));
  }

  function showRowError(message: string) {
    setToast({id: Date.now(), category: 'error', message});
  }

  const seedMutation = useMutation({
    mutationFn: () => postAdminSeedStatement(
      conversationId,
      {text: seedText, derivedFromId: derivedFrom === '' ? null : Number(derivedFrom), isMeta: seedMeta},
      csrfToken,
    ),
    onSuccess: (receipt) => {
      let error = false;
      let message = msg('flash-seed-added');
      if (receipt.provenanceRecorded === false) {
        error = true;
        message = msg('flash-seed-added-no-link');
      } else if (receipt.metaRecorded === false) {
        error = true;
        message = msg('flash-seed-added-meta-failed', receipt.statementId ?? '');
      } else if (receipt.derivedFromId !== null) {
        message = msg('flash-seed-added-corrected', receipt.derivedFromId);
      }
      setSeedText('');
      setDerivedFrom('');
      setSeedMeta(false);
      setSeedFeedback(lines([{error, message}]));
      void queryClient.invalidateQueries({queryKey: options.queryKey});
    },
    onError: (error: Error) => {
      // The typed text stays in the form, so it can be corrected and sent again.
      if (error instanceof ApiContractError
          && error.code === 'derived_statement_not_found') {
        setSeedFeedback(lines([{error: true, message: msg('stmts-seed-corrects-not-found', derivedFrom)}]));
      } else {
        setSeedFeedback(lines([{error: true, message: msg('adminconv-command-failed')}]));
      }
    },
  });

  const importMutation = useMutation({
    mutationFn: (statements: string[]) => postAdminStatementImport(
      conversationId, {statements}, csrfToken,
    ),
    onSuccess: (receipt) => {
      const messages: Omit<Feedback, 'id'>[] = [];
      const skipped = receipt.outcome.skippedExisting;
      const failed = receipt.outcome.failedUpstream;
      if (receipt.outcome.imported) {
        messages.push({error: false, message: msg('stmts-import-imported', receipt.outcome.imported)});
      }
      if (skipped) {
        messages.push({error: false, message: msg('stmts-import-skipped', skipped)});
      }
      // A statement the voting service refused is not "skipped": it was not added, and
      // trying again may add it. It is counted on its own, and the text stays in the box.
      if (failed) {
        messages.push({error: true, message: msg('stmts-import-failed', failed)});
      }
      if (!receipt.outcome.imported && !skipped && !failed) {
        messages.push({error: true, message: msg('flash-import-no-valid-rows')});
        messages.push({error: false, message: msg('flash-import-no-result')});
      }
      if (!failed) setImportText('');
      setImportFeedback(lines(messages));
      void queryClient.invalidateQueries({queryKey: options.queryKey});
    },
    onError: () => setImportFeedback(lines([{error: true, message: msg('adminconv-command-failed')}])),
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
    setToast(null);
    // The row leaves the list when the switch is on another position; focus goes to the next
    // row and the result is said, every time, through the shell's live region.
    if (status !== LIST[position]) rowRemoved(statement.id);
    announcer.announce(msg(MOVED[status], statement.id));
  }

  function markMeta(statement: Statement, meta: boolean) {
    queryClient.setQueryData<Workspace>(options.queryKey, (workspace) => {
      if (!workspace) return workspace;
      const mark = (rows: Statement[]) => rows.map((row) => (
        row.id === statement.id ? {...row, meta} : row));
      return {...workspace, statements: {
        pending: mark(workspace.statements.pending),
        approved: mark(workspace.statements.approved),
        hidden: mark(workspace.statements.hidden),
      }};
    });
    setToast(null);
    announcer.announce(meta ? msg('flash-meta-marked', statement.id) : msg('flash-meta-unmarked', statement.id));
  }

  function submitImport(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const rows = importText.split(/\r?\n/)
      .map((text, index) => ({row: index + 1, text: text.trim()}))
      .filter(({text}) => text);
    if (rows.length > data.seeding.maxStatementsPerImport) {
      setImportFeedback(lines([{
        error: true,
        message: msg('flash-import-rejected-rows', rows.length, data.seeding.maxStatementsPerImport),
      }]));
      return;
    }
    const seen = new Set<string>();
    const errors: Omit<Feedback, 'id'>[] = [];
    rows.forEach(({row, text}) => {
      if (text.length > data.seeding.maxCharactersPerStatement) {
        errors.push({error: true, message: msg('flash-import-row-error', row,
          msg('stmts-import-too-long', text.length, data.seeding.maxCharactersPerStatement))});
      } else if (seen.has(text)) {
        errors.push({error: true, message: msg('flash-import-row-error', row, msg('stmts-import-duplicate'))});
      }
      seen.add(text);
    });
    if (errors.length) {
      setImportFeedback(lines([...errors, {
        error: true,
        message: msg('flash-import-rejected-invalid'),
      }]));
      return;
    }
    importMutation.mutate(rows.map(({text}) => text));
  }

  const needle = search.trim().toLowerCase();
  const total = data.statements.approved.length + data.statements.pending.length
    + data.statements.hidden.length;
  const inView = data.statements[LIST[position]];
  // What the list says when it is empty: that there are no statements at all, that this
  // position of the switch holds none, or that the search matched none of them.
  const emptyPosition: Record<Position, string> = {
    approved: msg('stmts-approved-empty'),
    unmoderated: msg('stmts-pending-empty'),
    hidden: msg('stmts-hidden-empty'),
  };
  let empty = msg('admin-content-no-match');
  if (total === 0) empty = msg('admin-content-empty');
  else if (inView.length === 0) empty = emptyPosition[position];
  const rows = sortStatements(
    inView.filter((statement) => needle === ''
      || statement.text.toLowerCase().includes(needle)),
    sort,
  );

  const shown = new Set(rows.map((row) => row.id));
  // Each meta statement asks every participant for one more response: said from the 4th on.
  const metaCount = [...data.statements.approved, ...data.statements.pending]
    .filter((row) => row.meta).length;
  const {listRef, emptyRef, rowRemoved} = useRowFocus(rows.map((row) => row.id));

  return (
    <AdminShell
      title={msg('adminconv-doc-title', lifecycle.conversation.title)}
      data={lifecycle}
      gatingType={settings.conversation.gatingType}
      section="content"
      subPage={msg('adminconv-card-statements')}
      toast={<LegacyToast toast={toast} onDismiss={dismissToast} />}
      announcer={announcer}
    >
      <div className="admin-page">
        <h1>{msg('admin-shell-content')}</h1>
        <AdminTabStrip label={msg('admin-content-tabs-aria')}
          tabs={contentTabs(conversationId, msg)} current="statements" />

        <div className="admin-toolbar">
          <div className="admin-switch">
            {POSITIONS.map((item) => (
              <button
                key={item.id}
                type="button"
                aria-pressed={position === item.id}
                title={msg(item.key)}
                onClick={() => setPosition(item.id)}
              >
                <span aria-hidden="true">{item.glyph}</span>
                <span className="sr-only">{msg(item.key)}</span>
                {data.statements[LIST[item.id]].length
                  ? ` ${data.statements[LIST[item.id]].length}` : ''}
              </button>
            ))}
          </div>
          <label className="admin-sort">
            {msg('admin-moderation-sort-aria')}
            <select value={sort} onChange={(event) => setSort(event.target.value as Sort)}>
              <option value="most-responses">{msg('admin-content-sort-most-responses')}</option>
              <option value="oldest">{msg('admin-moderation-sort-oldest')}</option>
              <option value="based-on">{msg('admin-moderation-sort-based-on')}</option>
            </select>
          </label>
          <label className="admin-sort">
            {msg('admin-content-search-aria')}
            <input
              type="search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </label>
        </div>

        {metaCount >= 4 && <p className="admin-status">{msg('stmts-meta-warn-count', metaCount)}</p>}

        {rows.length ? (
          <ul className="admin-rows" ref={listRef}>
            {rows.map((statement) => (
              <StatementRow
                key={statement.id}
                conversationId={conversationId}
                statement={statement}
                sourceShown={!!statement.provenance
                  && shown.has(statement.provenance.derivedFromId)}
                csrfToken={csrfToken}
                move={moveStatement}
                onMeta={markMeta}
                onError={showRowError}
              />
            ))}
          </ul>
        ) : data.dataAvailability.statements ? (
          <p className="admin-empty" ref={emptyRef} tabIndex={-1}>{empty}</p>
        ) : (
          // Lists left empty because the voting service could not be read are not an empty
          // consultation. Said once, here, where the list would be (as on the Queue).
          <p className="admin-empty" role="alert">{msg('flash-load-statements-failed')}</p>
        )}

        {/* Seeding works only during preparation or while statement submission is open;
            outside that, its two forms are not shown rather than shown locked. */}
        {data.seeding.allowed && (
          <>
            <h2>{msg('stmts-seed-heading')}</h2>
            <div className="admin-form">
              <form onSubmit={(event) => { event.preventDefault(); seedMutation.mutate(); }}>
                <input type="hidden" name="csrf_token" value={csrfToken} />
                <label className="admin-field">{msg('stmts-seed-label')}
                  <textarea
                    name="txt"
                    rows={3}
                    maxLength={280}
                    id="seed-txt"
                    required
                    aria-describedby="seed-count"
                    value={seedText}
                    onChange={(event) => setSeedText(event.target.value)}
                  />
                </label>
                <label className="admin-field admin-field--short">
                  {msg('stmts-seed-corrects-label')}
                  <input
                    type="number"
                    name="derived_from"
                    min={0}
                    className="admin-mono"
                    value={derivedFrom}
                    onChange={(event) => setDerivedFrom(event.target.value)}
                  />
                </label>
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    name="is_meta"
                    checked={seedMeta}
                    onChange={(event) => setSeedMeta(event.target.checked)}
                  />
                  {msg('stmts-seed-meta-label')}
                </label>
                <div className="admin-form__actions">
                  <button type="submit" className="admin-button admin-button--primary" disabled={seedMutation.isPending}>{msg('stmts-seed-submit')}</button>
                  <span id="seed-count" className="admin-form__count">{seedText.length} / 280</span>
                </div>
                <FormFeedback lines={seedFeedback} />
              </form>
            </div>

            <h2>{msg('stmts-import-heading')}</h2>
            <div className="admin-form">
              <form onSubmit={submitImport}>
                <input type="hidden" name="csrf_token" value={csrfToken} />
                <label className="admin-field">{msg('stmts-import-label')}
                  <textarea
                    name="statement_texts"
                    rows={8}
                    maxLength={data.seeding.maxStatementsPerImport * (data.seeding.maxCharactersPerStatement + 1)}
                    value={importText}
                    onChange={(event) => setImportText(event.target.value)}
                  />
                </label>
                <div className="admin-form__actions">
                  <button type="submit" className="admin-button admin-button--primary" disabled={importMutation.isPending}>{msg('stmts-import-submit')}</button>
                </div>
                <FormFeedback lines={importFeedback} />
              </form>
            </div>
          </>
        )}

        {/* Arguments are a page in the spec and not one here: there is no admin list endpoint
            for them yet (#473). */}
        <AdminComing what="the arguments of this consultation as a list of their own" issue={473} />

        {/* The Approval control (strict moderation) lives on Settings › Basics (#478): it is a
            setting of the consultation, not of the statement list. */}
      </div>
    </AdminShell>
  );
}
