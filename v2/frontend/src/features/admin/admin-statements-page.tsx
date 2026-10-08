import {useCallback, useState, type FormEvent} from 'react';
import {useMutation, useQueryClient, useSuspenseQuery} from '@tanstack/react-query';

import type {components} from '../../api/schema';
import {ApiContractError} from '../../api/client';
import {
  adminLifecycleQuery,
  adminSettingsQuery,
  adminStatementWorkspaceQuery,
  postAdminSeedStatement,
  postAdminStatementImport,
} from '../../api/queries';
import {useMessage, type Message} from '../../i18n/messages';
import {sortByBasedOn} from './admin-based-on';
import {AdminComing} from './admin-coming';
import {AdminShell} from './admin-shell';
import {useAnnouncer} from './admin-announcer';
import {useRowFocus} from './admin-row-focus';
import {StatementActions} from './admin-statement-actions';
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

function legacyError(error: Error, fallback: string): string {
  return error instanceof ApiContractError ? error.message : fallback;
}

/** A form's result lines, at the form. */
function FormFeedback({lines}: {lines: Feedback[]}) {
  const errors = lines.filter((line) => line.error);
  const outcomes = lines.filter((line) => !line.error);
  return (
    <>
      {errors.length > 0 && <div role="alert">{errors.map((line) => (
        <p key={line.id} className="admin-error">{line.message}</p>
      ))}</div>}
      {outcomes.length > 0 && <div role="status">{outcomes.map((line) => (
        <p key={line.id} className="admin-status">{line.message}</p>
      ))}</div>}
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

/** Where a derived statement came from, in the words and format the old statement table
 *  used: "↳ #N", then each similarity score, muted. "↳ #N" jumps to the source's row when
 *  that row is in the list on screen; otherwise there is nothing to jump to and it is text. */
function StatementSource({provenance, sourceShown}: {
  provenance: NonNullable<Statement['provenance']>;
  sourceShown: boolean;
}) {
  const id = provenance.derivedFromId;
  const title = `Derived from statement #${id}. Similarity 1.00 = identical.${provenance.scores.map((score) => ` ${score.model} ${score.value.toFixed(2)}.`).join('')}`;
  const marker = (
    <>
      <span className="sr-only">derived from statement {id}</span>
      <span aria-hidden="true">{`↳ #${id}`}</span>
    </>
  );
  return (
    <span className="admin-row__source" title={title}>
      {' '}
      {sourceShown ? <a href={`#statement-${id}`}>{marker}</a> : marker}
      {provenance.scores.map((score) => (
        <span key={score.model}> · {score.model}&nbsp;{score.value.toFixed(2)}</span>
      ))}
    </span>
  );
}

/** One statement as one row: a star when it is featured, the text, its number as a muted
 *  suffix (what "↳ #N", Featured's add by number and "Corrects statement #" refer to),
 *  where it came from, its votes and what can be done to it. The row's id is the target of
 *  "↳ #N" on the rows derived from it. */
function StatementRow({conversationId, statement, sourceShown, csrfToken, move, onError}: {
  conversationId: number;
  statement: Statement;
  sourceShown: boolean;
  csrfToken: string;
  move: (statement: Statement, status: Status) => void;
  onError: (message: string) => void;
}) {
  const msg = useMessage();
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
        {statement.provenance && (
          <StatementSource provenance={statement.provenance} sourceShown={sourceShown} />
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
        onMoved={move}
        onError={(error) => onError(moderationError(msg, error))}
      />
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
  const [position, setPosition] = useState<Position>('approved');
  const [sort, setSort] = useState<Sort>('most-responses');
  const [search, setSearch] = useState('');
  // Each form's result lines, said at that form.
  const [seedFeedback, setSeedFeedback] = useState<Feedback[]>([]);
  const [importFeedback, setImportFeedback] = useState<Feedback[]>([]);
  // Toasts are for the row actions only.
  const [toast, setToast] = useState<LegacyToastMessage | null>(null);
  const [seedText, setSeedText] = useState('');
  const [derivedFrom, setDerivedFrom] = useState('');
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
      {text: seedText, derivedFromId: derivedFrom === '' ? null : Number(derivedFrom)},
      csrfToken,
    ),
    onSuccess: (receipt) => {
      let error = false;
      let message = 'Seed statement added.';
      if (receipt.provenanceRecorded === false) {
        error = true;
        message = 'Seed statement added, but the correction link could not be recorded.';
      } else if (receipt.derivedFromId !== null) {
        message = `Seed statement added (recorded as a correction of #${receipt.derivedFromId}).`;
      }
      setSeedText('');
      setDerivedFrom('');
      setSeedFeedback(lines([{error, message}]));
      void queryClient.invalidateQueries({queryKey: options.queryKey});
    },
    onError: (error: Error) => {
      // The typed text stays in the form, so it can be corrected and sent again.
      if (error instanceof ApiContractError
          && error.code === 'derived_statement_not_found') {
        setSeedFeedback(lines([{error: true, message: `Statement #${derivedFrom} was not found in this consultation — fix the "corrects" number and try again. Nothing was added.`}]));
      } else {
        setSeedFeedback(lines([{error: true, message: legacyError(error, msg('adminconv-command-failed'))}]));
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
          error: false,
          message: `${receipt.outcome.skippedExisting} statement${receipt.outcome.skippedExisting === 1 ? '' : 's'} already existed in this consultation and were skipped.`,
        });
      }
      // A statement the voting service refused is not "skipped": it was not added, and
      // trying again may add it. It is counted on its own, and the text stays in the box.
      const failed = receipt.outcome.failedUpstream;
      if (failed) {
        messages.push({
          error: true,
          message: `${failed} statement${failed === 1 ? '' : 's'} could not be added by the voting service. The text is still in the box: import it again to retry; lines already added are skipped.`,
        });
      }
      if (receipt.outcome.imported && !receipt.outcome.skippedExisting && !failed) {
        messages.push({
          error: false,
          message: `✓ ${receipt.outcome.imported} statement${receipt.outcome.imported === 1 ? '' : 's'} imported`,
        });
      } else if (receipt.outcome.imported || failed) {
        messages.push({
          error: false,
          message: `✓ ${receipt.outcome.imported} imported${receipt.outcome.skippedExisting ? ` — ⚠ ${receipt.outcome.skippedExisting} skipped` : ''}${failed ? ` — ✗ ${failed} not added` : ''}`,
        });
      } else if (receipt.outcome.skippedExisting) {
        messages.push({
          error: false,
          message: `⚠ 0 imported — ${receipt.outcome.skippedExisting} already existed in Polis`,
        });
      } else {
        messages.push({error: true, message: 'No statements were imported — there were no valid rows.'});
        messages.push({error: false, message: '⚠ 0 imported — Polis returned no result'});
      }
      if (!failed) setImportText('');
      setImportFeedback(lines(messages));
      void queryClient.invalidateQueries({queryKey: options.queryKey});
    },
    onError: (error: Error) => setImportFeedback(lines([{error: true, message: legacyError(error, msg('adminconv-command-failed'))}])),
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

  function submitImport(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const rows = importText.split(/\r?\n/)
      .map((text, index) => ({row: index + 1, text: text.trim()}))
      .filter(({text}) => text);
    if (rows.length > data.seeding.maxStatementsPerImport) {
      setImportFeedback(lines([{
        error: true,
        message: `✗ Import rejected — nothing was imported. Text import contains ${rows.length} lines, maximum is ${data.seeding.maxStatementsPerImport}. Reduce it and try again. (Parse errors may also be present — fix everything before retrying.)`,
      }]));
      return;
    }
    const seen = new Set<string>();
    const errors: Omit<Feedback, 'id'>[] = [];
    rows.forEach(({row, text}) => {
      if (text.length > data.seeding.maxCharactersPerStatement) {
        errors.push({error: true, message: `Row ${row}: text is too long (${text.length} characters; max ${data.seeding.maxCharactersPerStatement}).`});
      } else if (seen.has(text)) {
        errors.push({error: true, message: `Row ${row}: duplicate — already added from an earlier row.`});
      }
      seen.add(text);
    });
    if (errors.length) {
      setImportFeedback(lines([...errors, {
        error: true,
        message: '✗ Import rejected — nothing was added. One invalid line rejects the whole import; fix the lines listed above and try again.',
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

        <div className="landing-section" style={{marginBottom: '1.5rem'}}>
          <h2 style={{fontSize: 16, marginBottom: '.5rem'}}>How statement management works</h2>
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

        {!data.seeding.allowed ? (
          <>
            <h2>Seed statements locked</h2>
            <div className="admin-form">
              <p className="muted" style={{marginBottom: 0, fontSize: 13}}>
                {data.seeding.lockReason} Seed statements can only be added during preparation
                {' '}or while statement submission is open.
              </p>
            </div>
          </>
        ) : (
          <>
            <h2>Add seed statement</h2>
            <div className="admin-form">
              <p className="muted" style={{marginBottom: '.75rem', fontSize: 13}}>
                Adds a seed-marked statement that participants see early on.
              </p>
              <form onSubmit={(event) => { event.preventDefault(); seedMutation.mutate(); }}>
                <input type="hidden" name="csrf_token" value={csrfToken} />
                <label className="admin-field">Statement text (max 280 characters)
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
                  Corrects statement&nbsp;#&nbsp;(optional)
                  <input
                    type="number"
                    name="derived_from"
                    min={0}
                    className="admin-mono"
                    value={derivedFrom}
                    onChange={(event) => setDerivedFrom(event.target.value)}
                  />
                </label>
                <div className="admin-form__actions">
                  <button type="submit" className="admin-button admin-button--primary" disabled={seedMutation.isPending}>Add seed statement</button>
                  <span id="seed-count" className="admin-form__count">{seedText.length} / 280</span>
                </div>
                <FormFeedback lines={seedFeedback} />
              </form>
            </div>

            <h2>Import seed statements from text</h2>
            <div className="admin-form">
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
                <label className="admin-field">Statements
                  <textarea
                    name="statement_texts"
                    rows={8}
                    maxLength={data.seeding.maxStatementsPerImport * (data.seeding.maxCharactersPerStatement + 1)}
                    value={importText}
                    onChange={(event) => setImportText(event.target.value)}
                  />
                </label>
                <div className="admin-form__actions">
                  <button type="submit" className="admin-button admin-button--primary" disabled={importMutation.isPending}>Import statements</button>
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
