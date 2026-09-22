import {useEffect, useRef, useState, type KeyboardEvent} from 'react';
import {useMutation, useQuery, useQueryClient, useSuspenseQuery} from '@tanstack/react-query';
import {useLocation, useParams} from 'react-router-dom';

import {ApiContractError} from '../../api/client';
import type {components} from '../../api/schema';
import {
  conversationWorkspaceQuery,
  createStatement,
  exploreStateQuery,
  putExploreVote,
  sessionQuery,
} from '../../api/queries';
import {NavigationRedirect} from './external-redirect';
import {LegacyArgumentMappingPanel} from './argument-mapping-panel';
import {LegacyInformedVotingPanel} from './informed-voting-panel';
import {LegacyPreliminaryResultsPanel} from './preliminary-results-panel';
import {LegacyIntermediateResultsPanel} from './intermediate-results-panel';
import {LegacyShell} from './legacy-shell';
import {InternalLink} from '../../internal-link';
import {LegacyContentFlag} from './legacy-content-flag';
import {RevealTimeline} from './reveal-timeline';
import {useMessage, type Message} from '../../i18n/messages';
import {phaseLabel, statementErrorCopy, tabLabel, workspaceErrorCopy} from '../../i18n/server-labels';
import {escapeHtml, richHtml} from '../../i18n/rich-html';
import {useDateFormat} from '../../i18n/dates';

type Workspace = components['schemas']['ConversationWorkspace'];
type WorkspaceTab = components['schemas']['ConversationWorkspaceTab']['key'];
type Explore = components['schemas']['ExploreState'];
type VoteChoice = components['schemas']['ExploreVoteRequest']['choice'];
type ComposerMode = 'suggest' | 'new' | null;
type InviteOnlyDetails = {
  title: string;
  slug?: string;
  gatingType?: string | null;
  reason?: string | null;
  canModerate?: boolean;
  links?: {home?: string; invitations?: string};
};

function requiredSlug(value: string | undefined) {
  if (!value) throw new Error('Missing route parameter: slug');
  return value;
}

function inviteOnlyDetails(error: unknown): InviteOnlyDetails | null {
  if (!(error instanceof ApiContractError)
      || !['access_required', 'invite_only'].includes(error.code)) return null;
  const details = error.details as Partial<InviteOnlyDetails> | undefined;
  if (!details || typeof details.title !== 'string') return null;
  return details as InviteOnlyDetails;
}

/** A voucher-gated consultation refuses in its own words, and a visitor without a
 *  voucher account is pointed at the page where a code is typed (#368). */
function VoucherRefusalPage({details}: {details: InviteOnlyDetails}) {
  const msg = useMessage();
  const title = escapeHtml(details.title);
  const copy = details.reason === 'access-voucher-other'
    ? {heading: msg('forbidden-voucher-other-heading'), body: msg('forbidden-voucher-other-body', title), entry: false}
    : details.reason === 'access-voucher-revoked'
      ? {heading: msg('forbidden-lost-voucher-heading'), body: msg('forbidden-lost-voucher-body', title), entry: false}
      : {heading: msg('forbidden-voucher-heading'), body: msg('forbidden-voucher-body', title), entry: Boolean(details.slug)};
  return (
    <LegacyShell title={msg('forbidden-invite-doc-title')}>
      <div className="container" style={{maxWidth: 700, paddingTop: '3rem'}}>
        <h1 style={{fontSize: 24, fontWeight: 600, color: 'var(--ink)', margin: '0 0 .75rem'}}>{copy.heading}</h1>
        <p
          style={{color: 'var(--body)', fontSize: 15, lineHeight: 1.6, margin: '0 0 1.5rem'}}
          dangerouslySetInnerHTML={richHtml(copy.body)}
        />
        {copy.entry && (
          <p style={{margin: '0 0 1.5rem'}}>
            {/* Served by Flask; InternalLink renders a full-page link for it. */}
            <InternalLink className="btn-primary" href={`/c/${encodeURIComponent(details.slug ?? '')}/v`}>{msg('forbidden-voucher-link')}</InternalLink>
          </p>
        )}
        <InternalLink href={details.links?.home ?? '/'} style={{fontSize: 13, color: 'var(--muted)', textDecoration: 'none'}}>{msg('forbidden-invite-back-home')}</InternalLink>
      </div>
    </LegacyShell>
  );
}

function InviteOnlyPage({details}: {details: InviteOnlyDetails}) {
  const msg = useMessage();
  if (details.gatingType === 'voucher' || details.reason === 'access-voucher-other') {
    return <VoucherRefusalPage details={details} />;
  }
  return (
    <LegacyShell title={msg('forbidden-invite-doc-title')}>
      <div className="container" style={{maxWidth: 700, paddingTop: '3rem'}}>
        <h1 style={{fontSize: 24, fontWeight: 600, color: 'var(--ink)', margin: '0 0 .75rem'}}>{msg('forbidden-invite-heading')}</h1>
        <p
          style={{color: 'var(--body)', fontSize: 15, lineHeight: 1.6, margin: '0 0 1.5rem'}}
          dangerouslySetInnerHTML={richHtml(msg('forbidden-invite-body', escapeHtml(details.title)))}
        />
        {details.canModerate && details.links?.invitations && (
          <div style={{background: '#f0f4ff', border: '1px solid #c7d3f5', borderRadius: 8, padding: '1rem 1.25rem', fontSize: 14, color: 'var(--ink)', lineHeight: 1.6, marginBottom: '1.5rem'}}>
            <strong>{msg('forbidden-invite-mod-lead')}</strong>{' '}
            {msg('forbidden-invite-mod-body')}{' '}
            <InternalLink href={details.links.invitations} style={{color: 'var(--accent)'}}>{msg('forbidden-invite-mod-link')}</InternalLink>
          </div>
        )}
        <InternalLink href={details.links?.home ?? '/'} style={{fontSize: 13, color: 'var(--muted)', textDecoration: 'none'}}>{msg('forbidden-invite-back-home')}</InternalLink>
      </div>
    </LegacyShell>
  );
}

function shortTitle(value: string) {
  return value.length > 40 ? `${value.slice(0, 39)}…` : value;
}

function ConversationCrumb({data}: {data: Workspace}) {
  const msg = useMessage();
  return (
    <nav className="header-crumb" aria-label={msg('conv-crumb-aria')}>
      <span className="header-crumb-sep">/</span>
      <span>{shortTitle(data.title)}</span>
      <InternalLink className="header-manage-link" href={data.links.about}>{msg('conv-crumb-about')}</InternalLink>
      {data.capabilities.moderate && data.links.manage && (
        <InternalLink className="header-manage-link" href={data.links.manage}>{msg('conv-crumb-manage')}</InternalLink>
      )}
    </nav>
  );
}

/** Whether the ballots a participant is about to cast count. Each variant is one whole
 *  sentence per message rather than a shared frame with a swapped word, so no translation
 *  can blur "real" into "demonstration" — the two readings never share a string. */
function SpaceWarning({space}: {space: 'real' | 'demo'}) {
  const msg = useMessage();
  const [visible, setVisible] = useState(true);
  if (!visible) return null;
  const real = space === 'real';
  return (
    <div className={`space-warn space-warn--${space}`} id="space-warn" role={real ? 'alert' : 'status'}>
      <span>
        <strong>{real ? msg('conv-space-warn-live-label') : msg('conv-space-warn-demo-label')}</strong>{' '}
        {real ? msg('conv-space-warn-live-body') : msg('conv-space-warn-demo-body')}{' '}
        <InternalLink href="/demo">{real ? msg('conv-space-warn-live-link') : msg('conv-space-warn-demo-link')}</InternalLink>
      </span>
      <button type="button" className="space-warn-ok" id="space-warn-x" onClick={() => setVisible(false)}>{msg('conv-space-warn-ok')}</button>
    </div>
  );
}

function VoteChoices({disabled, onVote}: {disabled: boolean; onVote: (choice: VoteChoice) => void}) {
  const msg = useMessage();
  return (
    <div className="vote-choice-row" id="vote-choice-row">
      <button type="button" className="vote-choice" data-type="agree" disabled={disabled} onClick={() => onVote('agree')} autoFocus><span className="vote-dot vote-dot--agree" />{msg('conv-vote-agree')}</button>
      <button type="button" className="vote-choice" data-type="neutral" disabled={disabled} onClick={() => onVote('pass')}><span className="vote-dot vote-dot--pass" />{msg('conv-vote-pass')}</button>
      <button type="button" className="vote-choice" data-type="disagree" disabled={disabled} onClick={() => onVote('disagree')}><span className="vote-dot vote-dot--disagree" />{msg('conv-vote-disagree')}</button>
    </div>
  );
}

function Progress({progress}: {progress: Explore['progress']}) {
  const msg = useMessage();
  const completed = progress.completed;
  const remaining = progress.remaining;
  return (
    <div className="vote-progress-row" id="vote-progress-row">
      <span className="vote-progress-count"><span id="votes-done" className="vote-progress-voted">{completed}</span><span className="vote-progress-sep"> / </span><span id="votes-total">{progress.total}</span>{' '}<span className="vote-progress-label">{msg('conv-vote-voted-label')}</span></span>
      <div className="vote-progress-bar-wrap">
        <div className="vote-progress-bar" id="vote-progress-bar" role="progressbar" aria-label={msg('conv-vote-progress-aria')} aria-valuemin={0} aria-valuenow={completed} aria-valuemax={progress.total} aria-valuetext={msg('conv-vote-progress-valuetext', completed, progress.total)}>
          {Array.from({length: completed}, (_, index) => <div className="vote-seg vote-seg--done" key={`done-${index}`} />)}
          {remaining > 0 && <div className="vote-seg vote-seg--current" />}
          {Array.from({length: Math.max(0, remaining - 1)}, (_, index) => <div className="vote-seg vote-seg--queued" key={`queued-${index}`} />)}
        </div>
      </div>
      <span className="vote-progress-queued" id="vote-progress-queued" />
    </div>
  );
}

function Composer({mode, data, slug, csrfToken, onCancel, onSubmitted}: {
  mode: Exclude<ComposerMode, null>;
  data: Explore;
  slug: string;
  csrfToken: string;
  onCancel: () => void;
  onSubmitted: () => void;
}) {
  const original = mode === 'suggest' ? data.currentStatement?.text ?? '' : '';
  const [text, setText] = useState(original);
  const [idempotencyKey] = useState(() => globalThis.crypto.randomUUID());
  const mutation = useMutation({
    mutationFn: () => createStatement(slug, {
      text: text.trim(),
      ...(mode === 'suggest' && data.currentStatement
        ? {derivedFromStatementId: data.currentStatement.id}
        : {}),
    }, csrfToken, idempotencyKey),
    onSuccess: onSubmitted,
  });
  const msg = useMessage();
  const suggest = mode === 'suggest';
  const title = suggest ? msg('conv-triad-suggest-title') : msg('conv-triad-newstmt-title');
  const helperId = suggest ? 'composer-suggest-helper' : 'composer-newstmt-helper';
  const errorId = suggest ? 'composer-suggest-error' : 'composer-newstmt-error';
  // Only a rewording that strayed too far is a problem with the text itself; the other
  // failures say nothing about what was typed, so they do not mark the field invalid.
  const textRejected = mutation.error instanceof ApiContractError
    && mutation.error.code === 'derivative_similarity_too_low';
  return (
    <div id={suggest ? 'composer-suggest' : 'composer-newstmt'} className="v2-composer">
      <div className="v2-composer-header">
        <div>
          <div className="v2-composer-title" id={suggest ? 'composer-suggest-title' : 'composer-newstmt-title'}>{title}</div>
          <div className="v2-composer-helper" id={helperId}>{suggest ? msg('conv-suggest-helper') : msg('conv-newstmt-helper')}{' '}<InternalLink href="/help/statements" target="_blank" rel="noopener">{msg('conv-writing-tips')}<span className="sr-only">{msg('common-opens-in-new-tab')}</span></InternalLink></div>
        </div>
        <span className="propose-charcount">{msg('conv-composer-charcount', text.length)}</span>
      </div>
      <textarea className="v2-composer-textarea" maxLength={280} aria-labelledby={suggest ? 'composer-suggest-title' : 'composer-newstmt-title'} aria-describedby={mutation.error ? `${helperId} ${errorId}` : helperId} aria-invalid={textRejected || undefined} placeholder={suggest ? msg('conv-suggest-placeholder') : msg('conv-newstmt-placeholder')} value={text} onChange={(event) => setText(event.target.value)} onFocus={(event) => { if (suggest) event.currentTarget.select(); }} autoFocus />
      <div className="v2-composer-footer">
        <span className="v2-composer-hint">{suggest ? msg('conv-suggest-hint') : msg('conv-newstmt-hint')}</span>
        <div className="v2-composer-btns">
          <button type="button" className="btn-small btn-muted" onClick={onCancel}>{msg('common-cancel')}</button>
          <button type="button" className="propose-submit-btn" disabled={mutation.isPending || !text.trim() || (suggest && text.trim() === original.trim())} onClick={() => mutation.mutate()}>{msg('conv-composer-submit')}</button>
        </div>
      </div>
      {mutation.error && <p className="error" id={errorId} role="alert">{statementErrorCopy(msg, mutation.error)}</p>}
    </div>
  );
}

function OptionTriad({active, allDone, thresholdUnlocked, quota, quotaRemaining, votesUntilUnlock, onSuggest, onNext, onNew}: {
  active: boolean;
  allDone: boolean;
  thresholdUnlocked: boolean;
  quota: number;
  quotaRemaining: number;
  votesUntilUnlock: number;
  onSuggest: () => void;
  onNext: () => void;
  onNew: () => void;
}) {
  const msg = useMessage();
  const disabled = !active || allDone;
  const newStatementUnlocked = thresholdUnlocked && quotaRemaining > 0;
  const availability = !thresholdUnlocked
    ? msg('conv-newstmt-unlocks-more', votesUntilUnlock)
    : quotaRemaining === 0
      ? msg('conv-newstmt-limit-reached')
      : msg('conv-newstmt-remaining', quotaRemaining, quota);
  return (
    <div className={`v2-triad${active && !allDone ? ' v2-triad--active' : ''}${allDone ? ' v2-triad--alldone' : ''}`} id="v2-triad">
      <div className="v2-triad-label" id="v2-triad-label" aria-live="polite">{allDone ? msg('conv-triad-alldone-label') : active ? msg('conv-triad-active-label') : msg('conv-triad-idle-label')}</div>
      <div className="v2-triad-grid" role="group" aria-labelledby="v2-triad-label">
        <button type="button" className="v2-option-card" id="triad-suggest" aria-disabled={disabled} tabIndex={0} onClick={() => !disabled && onSuggest()}>
          <div className="v2-option-top"><span className="v2-option-glyph"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M3 17l6-6 4 4 8-8" /><path d="M14 7h7v7" /></svg></span></div>
          <div className="v2-option-bottom"><div className="v2-option-title">{msg('conv-triad-suggest-title')}</div><div className="v2-option-sub">{msg('conv-triad-suggest-sub')}</div><div className="v2-option-action">{msg('conv-triad-suggest-action')}</div></div>
        </button>
        <button type="button" className={`v2-option-card${active ? ' v2-option-card--primary' : ''}`} id="triad-next" aria-disabled={disabled} tabIndex={0} onClick={() => !disabled && onNext()}>
          <div className="v2-option-top"><span className="v2-option-glyph"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M5 12h14" /><path d="M13 5l7 7-7 7" /></svg></span></div>
          <div className="v2-option-bottom"><div className="v2-option-title">{msg('conv-triad-next-title')}</div><div className="v2-option-sub">{msg('conv-triad-next-sub')}</div><div className="v2-option-action">{msg('conv-triad-next-action')}</div></div>
        </button>
        <button type="button" className={`v2-option-card${newStatementUnlocked ? '' : ' v2-option-card--locked'}`} id="triad-newstmt" aria-disabled={!newStatementUnlocked} tabIndex={0} aria-describedby="triad-newstmt-sub" onClick={() => newStatementUnlocked && onNew()}>
          <div className="v2-option-top"><span className="v2-option-glyph"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M12 5v14" /><path d="M5 12h14" /></svg></span>{!newStatementUnlocked && <svg className="v2-lock-icon" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#9ca3af" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><rect x="3" y="11" width="18" height="11" rx="2" /><path d="M7 11V7a5 5 0 0 1 10 0v4" /></svg>}</div>
          <div className="v2-option-bottom"><div className="v2-option-title">{msg('conv-triad-newstmt-title')}</div><div className="v2-option-sub" id="triad-newstmt-sub">{availability}</div><div className="v2-option-action" hidden={!newStatementUnlocked}>{msg('conv-triad-newstmt-action')}</div></div>
        </button>
      </div>
    </div>
  );
}

function ExplorePanel({slug, csrfToken}: {slug: string; csrfToken: string}) {
  const msg = useMessage();
  const {data, refetch} = useSuspenseQuery(exploreStateQuery(slug));
  const [receipt, setReceipt] = useState<components['schemas']['ExploreVoteReceipt'] | null>(null);
  const [recordedCurrentVote, setRecordedCurrentVote] = useState(false);
  const [composer, setComposer] = useState<ComposerMode>(null);
  const [submitted, setSubmitted] = useState(false);
  const vote = useMutation({
    mutationFn: (choice: VoteChoice) => {
      if (!data.currentStatement) throw new Error('There is no statement to vote on.');
      return putExploreVote(slug, data.currentStatement.id, {choice}, csrfToken);
    },
    onSuccess: (nextReceipt) => {
      setReceipt(nextReceipt);
      setRecordedCurrentVote(true);
    },
  });
  async function next() {
    setReceipt(null);
    setComposer(null);
    setSubmitted(false);
    await refetch();
    setRecordedCurrentVote(false);
  }
  const allDone = data.progress.allDone && receipt === null;
  const completed = Math.min(
    data.progress.total,
    data.progress.completed + (recordedCurrentVote ? 1 : 0),
  );
  const progress = {
    ...data.progress,
    completed,
    remaining: Math.max(0, data.progress.total - completed),
    allDone: completed >= data.progress.total,
  };
  const thresholdUnlocked = progress.allDone
    || completed >= data.newStatement.unlockAfter;
  const votesUntilUnlock = Math.max(
    0, data.newStatement.unlockAfter - completed,
  );
  useEffect(() => {
    if (!receipt || composer || submitted) return;
    document.getElementById('triad-suggest')?.focus();
  }, [composer, receipt, submitted]);
  return (
    <div className="voting-col">
      <div id="particiapi-client">
        <Progress progress={progress} />
        <p className="sr-only" id="statement-live" role="status" aria-live="polite">{data.currentStatement?.text}</p>
        {!allDone && data.currentStatement && (
          <div className={`statement-card${receipt ? ' statement-card--voted' : ''}`} id="statement-card">
            <LegacyContentFlag slug={slug} target={{contentType: 'statement', targetId: data.currentStatement.id}} csrfToken={csrfToken} corner />
            <div className="statement-card-header">
              <span className="stmt-meta-left"><span className="stmt-dot" /><span className="stmt-meta-label">{msg('conv-vote-statement-label')}</span></span>
              <span className="stmt-meta-right" id="stmt-right-label">{msg('conv-vote-private')}</span>
              {receipt && (
                <span className="voted-badge" data-type={receipt.choice === 'pass' ? 'neutral' : receipt.choice}>
                  <span className="voted-badge-check"><svg width="7" height="7" viewBox="0 0 12 12" fill="none" aria-hidden="true"><path d="M2 6.5L4.8 9L10 3.5" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg></span> <span id="voted-label">{msg('conv-vote-you-voted', receipt.choice === 'agree' ? msg('conv-vote-agree') : receipt.choice === 'disagree' ? msg('conv-vote-disagree') : msg('conv-vote-pass'))}</span>
                  <button type="button" className="change-vote-btn" onClick={() => setReceipt(null)}>{msg('conv-vote-change')}</button>
                </span>
              )}
            </div>
            {!receipt ? <p id="statement-text" className="statement-text">{data.currentStatement.text}</p> : <p id="voted-stmt-text" className="voted-stmt-text">{data.currentStatement.text}</p>}
            {!receipt && <VoteChoices disabled={vote.isPending} onVote={(choice) => vote.mutate(choice)} />}
          </div>
        )}

        {!composer && !submitted && (
          <OptionTriad active={receipt !== null || allDone} allDone={allDone} thresholdUnlocked={thresholdUnlocked} quota={data.newStatement.quota} quotaRemaining={data.newStatement.remaining} votesUntilUnlock={votesUntilUnlock} onSuggest={() => setComposer('suggest')} onNext={next} onNew={() => setComposer('new')} />
        )}
        {composer && <Composer mode={composer} data={data} slug={slug} csrfToken={csrfToken} onCancel={() => setComposer(null)} onSubmitted={() => { setComposer(null); setSubmitted(true); }} />}
        {submitted && (
          <div id="propose-submitted" className="propose-submitted" role="status">
            <span className="check-pill">✓</span><span className="propose-submitted-label">{msg('conv-proposed')}</span>
            <button type="button" className="propose-next-btn" onClick={next}>{msg('conv-propose-next')} <span aria-hidden="true">→</span></button>
          </div>
        )}
        {allDone && (
          <div id="all-done-msg" className="all-done-msg">
            <p className="all-done-label">{msg('conv-alldone-label')}</p>
            {data.newStatement.unlocked && <p className="all-done-sub">{msg('conv-alldone-sub')}</p>}
          </div>
        )}
        {vote.error && <div id="conv-error" role="alert"><p className="muted">{msg('conv-err-submit-vote')}</p></div>}
      </div>
    </div>
  );
}

function ClosedWorkspace({data}: {data: Workspace}) {
  const dates = useDateFormat();
  const msg = useMessage();
  const reveal = data.reveal;
  const queryClient = useQueryClient();
  const refreshWorkspace = () => void queryClient.invalidateQueries({queryKey: conversationWorkspaceQuery(data.slug).queryKey});
  const pseudonym = escapeHtml(data.viewer.pseudonym ?? '');
  return (
    <div className="landing-section">
      {reveal ? (
        <>
          <p className="muted" dangerouslySetInnerHTML={richHtml(msg('conv-closed-on', escapeHtml(dates.date(reveal.closedAt))))} />
          <RevealTimeline state={reveal.state} closedAt={reveal.closedAt} opensAt={reveal.opensAt} closesAt={reveal.closesAt} cooldownDays={reveal.cooldownDays} windowDays={reveal.windowDays} countdownTargetAt={reveal.countdownTargetAt} onBoundary={refreshWorkspace} />
          {reveal.state === 'revealed' && <p className="muted" style={{marginTop: '.5rem', fontSize: 13}} dangerouslySetInnerHTML={richHtml(msg('conv-revealed-text', pseudonym))} />}
          {reveal.state === 'open' && <div className="reveal-callout"><p className="reveal-callout-text" dangerouslySetInnerHTML={richHtml(msg('reveal-callout-open-text', pseudonym))} /><InternalLink className="reveal-callout-link" href={`/c/${data.slug}/reveal`}>{msg('reveal-callout-link')} <span aria-hidden="true">→</span></InternalLink></div>}
          {reveal.state === 'pending' && <p className="muted" style={{marginTop: '.5rem', fontSize: 13}}>{msg('conv-reveal-pending-opens', dates.date(reveal.opensAt))}</p>}
          {reveal.state === 'expired' && <p className="muted" style={{marginTop: '.5rem', fontSize: 13}}>{msg('conv-reveal-expired')}</p>}
        </>
      ) : <p className="muted">{msg('conv-closed-simple')}</p>}
      {data.links.results && <p style={{marginTop: '1rem', fontSize: 14}}><InternalLink href={`/c/${data.slug}/report`}>{msg('conv-read-report')} <span aria-hidden="true">→</span></InternalLink></p>}
    </div>
  );
}

/** The scheduled-transition sentence carries a <time> element whose attributes cannot come
 *  from a translated string. It is built here and passed in as one parameter, so the
 *  sentence itself stays a plain "Next: $1 on $2." frame. */
function scheduledTime(msg: Message, dateTime: (value: string) => string, at: string) {
  return `<time datetime="${escapeHtml(at)}" title="${escapeHtml(msg('conv-scheduled-tz-title'))}">${escapeHtml(dateTime(at))}</time>`;
}

function WorkspaceBody({data, csrfToken, routeTab}: {data: Workspace; csrfToken: string; routeTab?: WorkspaceTab}) {
  const msg = useMessage();
  const dates = useDateFormat();
  const hashTab = useLocation().hash.replace(/^#tab-/, '') as WorkspaceTab;
  const requestedTab = routeTab ?? hashTab;
  const [activeTab, setActiveTab] = useState<WorkspaceTab>(data.tabs.some((tab) => tab.key === requestedTab) ? requestedTab : data.defaultTab ?? 'vote');
  const tabRefs = useRef<Array<HTMLButtonElement | null>>([]);

  function keyDown(event: KeyboardEvent<HTMLDivElement>) {
    const index = data.tabs.findIndex((tab) => tab.key === activeTab);
    let next = index;
    if (event.key === 'ArrowRight') next = (index + 1) % data.tabs.length;
    else if (event.key === 'ArrowLeft') next = (index - 1 + data.tabs.length) % data.tabs.length;
    else if (event.key === 'Home') next = 0;
    else if (event.key === 'End') next = data.tabs.length - 1;
    else return;
    event.preventDefault();
    const target = data.tabs[next];
    if (!target) return;
    setActiveTab(target.key);
    tabRefs.current[next]?.focus();
  }

  return (
    <div className="container">
      <h1 className="sr-only">{data.title}</h1>
      {data.spaceWarning && <SpaceWarning space={data.spaceWarning} />}
      {data.space === 'demo' && <div className="mode-lock mode-lock--demo" style={{marginBottom: '1rem'}}><span className="mode-lock-dot" aria-hidden="true" />{msg('conv-demo-mode-lock')}</div>}
      {data.descriptionHtml && <div className="intro-text" dangerouslySetInnerHTML={{__html: data.descriptionHtml}} />}
      {data.scheduledTransition && <div className="landing-section output-context"><p className="muted" style={{margin: 0}} dangerouslySetInnerHTML={richHtml(msg('conv-scheduled-transition', escapeHtml(phaseLabel(msg, data.scheduledTransition.target, data.scheduledTransition.targetLabel)), scheduledTime(msg, dates.dateTime, data.scheduledTransition.at)))} /></div>}
      {data.status === 'closed' ? <ClosedWorkspace data={data} /> : data.status === 'paused' ? <div className="landing-section"><p className="muted">{msg('conv-paused')}</p></div> : data.tabs.length === 0 ? <div className="landing-section"><p className="muted">{msg('conv-nothing-available')}</p></div> : (
        <>
          {data.tabs.length > 1 && <div className="tab-bar" role="tablist" onKeyDown={keyDown}>{data.tabs.map((tab, index) => <button key={tab.key} ref={(element) => { tabRefs.current[index] = element; }} id={`tab-btn-${tab.key}`} className={`tab-btn${activeTab === tab.key ? ' tab-btn--active' : ''}`} role="tab" data-tab={`tab-${tab.key}`} aria-controls={`tab-${tab.key}`} aria-selected={activeTab === tab.key} tabIndex={activeTab === tab.key ? 0 : -1} onClick={() => setActiveTab(tab.key)}>{tabLabel(msg, tab.key, tab.label)}</button>)}</div>}
          {data.tabs.map((tab) => <div key={tab.key} id={`tab-${tab.key}`} className={`tab-panel${tab.key === 'arguments' ? ' arguments-tab' : ''}${activeTab === tab.key ? ' tab-panel--active' : ' tab-panel--hidden'}`} role="tabpanel" aria-labelledby={`tab-btn-${tab.key}`}>{activeTab === tab.key && (tab.key === 'vote' ? <ExplorePanel slug={data.slug} csrfToken={csrfToken} /> : tab.key === 'results' ? <LegacyIntermediateResultsPanel slug={data.slug} /> : tab.key === 'arguments' ? <LegacyArgumentMappingPanel slug={data.slug} csrfToken={csrfToken} /> : tab.key === 'informed-voting' ? <LegacyInformedVotingPanel workspace={data} csrfToken={csrfToken} onSelectPreliminary={() => setActiveTab('p6-results')} /> : tab.key === 'p6-results' ? <LegacyPreliminaryResultsPanel slug={data.slug} /> : <div className="landing-section"><p className="muted">{tabLabel(msg, tab.key, tab.label)}</p></div>)}</div>)}
        </>
      )}
      {data.outroHtml && <div className="outro-text" dangerouslySetInnerHTML={{__html: data.outroHtml}} />}
    </div>
  );
}

export function ConversationWorkspacePage() {
  const msg = useMessage();
  const slug = requiredSlug(useParams().slug);
  const location = useLocation();
  const {data: session} = useSuspenseQuery(sessionQuery());
  const workspace = useQuery(conversationWorkspaceQuery(slug));
  useEffect(() => {
    if (workspace.data?.space !== 'demo') return;
    const meta = document.createElement('meta');
    meta.name = 'robots';
    meta.content = 'noindex,nofollow';
    document.head.appendChild(meta);
    return () => meta.remove();
  }, [workspace.data?.space]);
  if (workspace.isPending) return <p className="loading-state" role="status">{msg('conv-loading')}</p>;
  if (workspace.error instanceof ApiContractError && workspace.error.code === 'unauthorized') {
    return <NavigationRedirect href={session.links.login} />;
  }
  const restricted = inviteOnlyDetails(workspace.error);
  if (restricted) return <InviteOnlyPage details={restricted} />;
  if (workspace.error) {
    return <LegacyShell title={msg('conv-unavailable-doc-title')}><div className="container"><div className="landing-section"><h1>{workspace.error instanceof ApiContractError && workspace.error.code === 'not_found' ? msg('errorpage-404-title') : msg('conv-unavailable-heading')}</h1><p className="muted">{workspaceErrorCopy(msg, workspace.error)}</p></div></div></LegacyShell>;
  }
  const data = workspace.data;
  if (data.viewer.state === 'join_required') return <NavigationRedirect href={data.links.join} />;
  return (
    <LegacyShell headerMode={data.space === 'demo' ? 'conversation-demo' : 'conversation-real'} headerCrumb={<ConversationCrumb data={data} />} title={msg('conv-doc-title', data.title)}>
      <WorkspaceBody data={data} csrfToken={session.csrfToken} {...(location.pathname.endsWith('/arguments') ? {routeTab: 'arguments' as const} : location.pathname.endsWith('/informed-voting') ? {routeTab: 'informed-voting' as const} : location.pathname.endsWith('/results') ? {routeTab: 'p6-results' as const} : {})} />
    </LegacyShell>
  );
}
