import {useEffect, useRef, useState, type KeyboardEvent} from 'react';
import {useMutation, useQuery, useSuspenseQuery} from '@tanstack/react-query';
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

type Workspace = components['schemas']['ConversationWorkspace'];
type WorkspaceTab = components['schemas']['ConversationWorkspaceTab']['key'];
type Explore = components['schemas']['ExploreState'];
type VoteChoice = components['schemas']['ExploreVoteRequest']['choice'];
type ComposerMode = 'suggest' | 'new' | null;
type InviteOnlyDetails = {
  title: string;
  canModerate: boolean;
  links: {home: string; invitations?: string};
};

function requiredSlug(value: string | undefined) {
  if (!value) throw new Error('Missing route parameter: slug');
  return value;
}

function inviteOnlyDetails(error: unknown): InviteOnlyDetails | null {
  if (!(error instanceof ApiContractError) || error.code !== 'invite_only') return null;
  const details = error.details as Partial<InviteOnlyDetails> | undefined;
  if (!details || typeof details.title !== 'string'
      || typeof details.canModerate !== 'boolean'
      || !details.links || typeof details.links.home !== 'string') return null;
  return details as InviteOnlyDetails;
}

function InviteOnlyPage({details}: {details: InviteOnlyDetails}) {
  return (
    <LegacyShell title="Access restricted — ProtoWiki">
      <div className="container" style={{maxWidth: 700, paddingTop: '3rem'}}>
        <h1 style={{fontSize: 24, fontWeight: 600, color: 'var(--ink)', margin: '0 0 .75rem'}}>This consultation is invite-only</h1>
        <p style={{color: 'var(--body)', fontSize: 15, lineHeight: 1.6, margin: '0 0 1.5rem'}}>
          <strong>{details.title}</strong> is restricted to invited participants. You have not been added to the invite list for this consultation.
        </p>
        {details.canModerate && details.links.invitations && (
          <div style={{background: '#f0f4ff', border: '1px solid #c7d3f5', borderRadius: 8, padding: '1rem 1.25rem', fontSize: 14, color: 'var(--ink)', lineHeight: 1.6, marginBottom: '1.5rem'}}>
            <strong>You can moderate this consultation.</strong>{' '}
            To participate as a voter, add yourself to the invite list first:{' '}
            <InternalLink href={details.links.invitations} style={{color: 'var(--accent)'}}>Manage invites →</InternalLink>
          </div>
        )}
        <InternalLink href={details.links.home} style={{fontSize: 13, color: 'var(--muted)', textDecoration: 'none'}}>← back to home</InternalLink>
      </div>
    </LegacyShell>
  );
}

function shortTitle(value: string) {
  return value.length > 40 ? `${value.slice(0, 39)}…` : value;
}

function localDateTime(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium', timeStyle: 'short',
  }).format(new Date(value));
}

function ConversationCrumb({data}: {data: Workspace}) {
  return (
    <nav className="header-crumb" aria-label="Conversation context">
      <span className="header-crumb-sep">/</span>
      <span>{shortTitle(data.title)}</span>
      <InternalLink className="header-manage-link" href={data.links.about}>About</InternalLink>
      {data.capabilities.moderate && data.links.manage && (
        <InternalLink className="header-manage-link" href={data.links.manage}>Manage</InternalLink>
      )}
    </nav>
  );
}

function SpaceWarning({space}: {space: 'real' | 'demo'}) {
  const [visible, setVisible] = useState(true);
  if (!visible) return null;
  return (
    <div className={`space-warn space-warn--${space}`} id="space-warn" role={space === 'real' ? 'alert' : 'status'}>
      <span>
        <strong>{space === 'real' ? 'Live consultation.' : 'Demo.'}</strong>{' '}
        {space === 'real'
          ? 'These ballots are real — your votes here count. Just exploring? '
          : 'These are demonstration ballots — not a real consultation. '}
        <InternalLink href="/demo">{space === 'real' ? 'Try the demo space →' : 'Browse the demo space →'}</InternalLink>
      </span>
      <button type="button" className="space-warn-ok" id="space-warn-x" onClick={() => setVisible(false)}>I understand</button>
    </div>
  );
}

function VoteChoices({disabled, onVote}: {disabled: boolean; onVote: (choice: VoteChoice) => void}) {
  return (
    <div className="vote-choice-row" id="vote-choice-row">
      <button type="button" className="vote-choice" data-type="agree" disabled={disabled} onClick={() => onVote('agree')} autoFocus><span className="vote-dot vote-dot--agree" />Agree</button>
      <button type="button" className="vote-choice" data-type="neutral" disabled={disabled} onClick={() => onVote('pass')}><span className="vote-dot vote-dot--pass" />Pass</button>
      <button type="button" className="vote-choice" data-type="disagree" disabled={disabled} onClick={() => onVote('disagree')}><span className="vote-dot vote-dot--disagree" />Disagree</button>
    </div>
  );
}

function Progress({progress}: {progress: Explore['progress']}) {
  const completed = progress.completed;
  const remaining = progress.remaining;
  return (
    <div className="vote-progress-row" id="vote-progress-row">
      <span className="vote-progress-count"><span id="votes-done" className="vote-progress-voted">{completed}</span><span className="vote-progress-sep"> / </span><span id="votes-total">{progress.total}</span>{' '}<span className="vote-progress-label">voted</span></span>
      <div className="vote-progress-bar-wrap">
        <div className="vote-progress-bar" id="vote-progress-bar" role="progressbar" aria-label="Statements voted" aria-valuemin={0} aria-valuenow={completed} aria-valuemax={progress.total} aria-valuetext={`${completed} of ${progress.total} statements voted`}>
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
  const suggest = mode === 'suggest';
  const title = suggest ? 'Suggest different wording' : 'Propose a new statement';
  const helperId = suggest ? 'composer-suggest-helper' : 'composer-newstmt-helper';
  return (
    <div id={suggest ? 'composer-suggest' : 'composer-newstmt'} className="v2-composer">
      <div className="v2-composer-header">
        <div>
          <div className="v2-composer-title" id={suggest ? 'composer-suggest-title' : 'composer-newstmt-title'}>{title}</div>
          <div className="v2-composer-helper" id={helperId}>{suggest ? 'Stays close to the same idea — just a clearer or fairer phrasing. ' : 'A different angle entirely. One claim, one sentence. Goes to moderation, then into the same pool. '}<InternalLink href="/help/statements" target="_blank" rel="noopener">Writing tips<span className="sr-only"> (opens in a new tab)</span></InternalLink></div>
        </div>
        <span className="propose-charcount"><span>{text.length}</span> / 280</span>
      </div>
      <textarea className="v2-composer-textarea" maxLength={280} aria-labelledby={suggest ? 'composer-suggest-title' : 'composer-newstmt-title'} aria-describedby={helperId} placeholder={suggest ? 'Re-confirmation every five years would balance accountability against admin burnout…' : 'A new angle on the topic…'} value={text} onChange={(event) => setText(event.target.value)} onFocus={(event) => { if (suggest) event.currentTarget.select(); }} autoFocus />
      <div className="v2-composer-footer">
        <span className="v2-composer-hint">{suggest ? 'Goes into the pool with the original' : 'A separate statement — others will vote on it too'}</span>
        <div className="v2-composer-btns">
          <button type="button" className="btn-small btn-muted" onClick={onCancel}>Cancel</button>
          <button type="button" className="propose-submit-btn" disabled={mutation.isPending || !text.trim() || (suggest && text.trim() === original.trim())} onClick={() => mutation.mutate()}>Submit &amp; next</button>
        </div>
      </div>
      {mutation.error && <p className="muted" role="alert">{mutation.error.message}</p>}
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
  const disabled = !active || allDone;
  const newStatementUnlocked = thresholdUnlocked && quotaRemaining > 0;
  const availability = !thresholdUnlocked
    ? `Unlocks after ${votesUntilUnlock} more vote${votesUntilUnlock === 1 ? '' : 's'}`
    : quotaRemaining === 0
      ? 'Limit reached'
      : `${quotaRemaining} of ${quota} remaining`;
  return (
    <div className={`v2-triad${active && !allDone ? ' v2-triad--active' : ''}${allDone ? ' v2-triad--alldone' : ''}`} id="v2-triad">
      <div className="v2-triad-label" id="v2-triad-label" aria-live="polite">{allDone ? 'Want to add something new?' : active ? 'What now?' : 'After you vote, you can…'}</div>
      <div className="v2-triad-grid" role="group" aria-labelledby="v2-triad-label">
        <button type="button" className="v2-option-card" id="triad-suggest" aria-disabled={disabled} tabIndex={0} onClick={() => !disabled && onSuggest()}>
          <div className="v2-option-top"><span className="v2-option-glyph"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M3 17l6-6 4 4 8-8" /><path d="M14 7h7v7" /></svg></span></div>
          <div className="v2-option-bottom"><div className="v2-option-title">Suggest different wording</div><div className="v2-option-sub">Same idea, clearer phrasing</div><div className="v2-option-action">Write yours →</div></div>
        </button>
        <button type="button" className={`v2-option-card${active ? ' v2-option-card--primary' : ''}`} id="triad-next" aria-disabled={disabled} tabIndex={0} onClick={() => !disabled && onNext()}>
          <div className="v2-option-top"><span className="v2-option-glyph"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M5 12h14" /><path d="M13 5l7 7-7 7" /></svg></span></div>
          <div className="v2-option-bottom"><div className="v2-option-title">Move on</div><div className="v2-option-sub">Next statement, nothing to add</div><div className="v2-option-action">Next →</div></div>
        </button>
        <button type="button" className={`v2-option-card${newStatementUnlocked ? '' : ' v2-option-card--locked'}`} id="triad-newstmt" aria-disabled={!newStatementUnlocked} tabIndex={0} aria-describedby="triad-newstmt-sub" onClick={() => newStatementUnlocked && onNew()}>
          <div className="v2-option-top"><span className="v2-option-glyph"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M12 5v14" /><path d="M5 12h14" /></svg></span>{!newStatementUnlocked && <svg className="v2-lock-icon" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#9ca3af" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><rect x="3" y="11" width="18" height="11" rx="2" /><path d="M7 11V7a5 5 0 0 1 10 0v4" /></svg>}</div>
          <div className="v2-option-bottom"><div className="v2-option-title">Propose a new statement</div><div className="v2-option-sub" id="triad-newstmt-sub">{availability}</div><div className="v2-option-action" hidden={!newStatementUnlocked}>Compose →</div></div>
        </button>
      </div>
    </div>
  );
}

function ExplorePanel({slug, csrfToken}: {slug: string; csrfToken: string}) {
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
            <LegacyContentFlag slug={slug} target={{contentType: 'statement', targetId: data.currentStatement.id}} label="this statement" csrfToken={csrfToken} corner />
            <div className="statement-card-header">
              <span className="stmt-meta-left"><span className="stmt-dot" /><span className="stmt-meta-label">STATEMENT</span></span>
              <span className="stmt-meta-right" id="stmt-right-label">private vote</span>
              {receipt && (
                <span className="voted-badge" data-type={receipt.choice === 'pass' ? 'neutral' : receipt.choice}>
                  <span className="voted-badge-check"><svg width="7" height="7" viewBox="0 0 12 12" fill="none" aria-hidden="true"><path d="M2 6.5L4.8 9L10 3.5" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg></span> YOU VOTED <span id="voted-label">{receipt.choice === 'pass' ? 'PASS' : receipt.choice.toUpperCase()}</span>
                  <button type="button" className="change-vote-btn" onClick={() => setReceipt(null)}>change</button>
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
            <span className="check-pill">✓</span><span className="propose-submitted-label">PROPOSED — heading to moderation</span>
            <button type="button" className="propose-next-btn" onClick={next}>Next statement <span aria-hidden="true">→</span></button>
          </div>
        )}
        {allDone && (
          <div id="all-done-msg" className="all-done-msg">
            <p className="all-done-label">For now, you have shared your opinion on all available statements. Please come back later for more!</p>
            {data.newStatement.unlocked && <p className="all-done-sub">If you can think of any statements that are missing from the current set, this is your chance to submit them.</p>}
          </div>
        )}
        {vote.error && <div id="conv-error" role="alert"><p className="muted">Could not submit your vote. Please try again.</p></div>}
      </div>
    </div>
  );
}

function ClosedWorkspace({data}: {data: Workspace}) {
  const reveal = data.reveal;
  return (
    <div className="landing-section">
      {reveal ? (
        <>
          <p className="muted">This consultation closed on <strong>{legacyDate(reveal.closedAt)}</strong>. Your votes were recorded under your pseudonym; for a limited time you may optionally and permanently link your Wikimedia username to it.</p>
          <RevealTimeline reveal={reveal} />
          {reveal.state === 'revealed' && <p className="muted" style={{marginTop: '.5rem', fontSize: 13}}>You linked your identity — your username is associated with pseudonym <strong>{data.viewer.pseudonym}</strong> in this consultation's records.</p>}
          {reveal.state === 'open' && <div className="reveal-callout"><p className="reveal-callout-text">The identity reveal window is open. Your participation is recorded under pseudonym <strong>{data.viewer.pseudonym}</strong>.</p><InternalLink className="reveal-callout-link" href={`/c/${data.slug}/reveal`}>Optionally link your Wikimedia username <span aria-hidden="true">→</span></InternalLink></div>}
          {reveal.state === 'pending' && <p className="muted" style={{marginTop: '.5rem', fontSize: 13}}>The window opens on {legacyDate(reveal.opensAt)} — nothing to do until then.</p>}
          {reveal.state === 'expired' && <p className="muted" style={{marginTop: '.5rem', fontSize: 13}}>The reveal window has closed. Records stay pseudonymous — identities can no longer be linked.</p>}
        </>
      ) : <p className="muted">This consultation is closed.</p>}
      {data.links.results && <p style={{marginTop: '1rem', fontSize: 14}}><InternalLink href={`/c/${data.slug}/report`}>Read the final report <span aria-hidden="true">→</span></InternalLink></p>}
    </div>
  );
}

function legacyDate(value: string) {
  const date = new Date(value);
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  return `${date.getUTCDate()} ${months[date.getUTCMonth()]} ${date.getUTCFullYear()}`;
}

function countdown(value: string) {
  const milliseconds = Date.parse(value) - Date.now();
  if (milliseconds <= 0) return 'now';
  const seconds = Math.floor(milliseconds / 1000);
  const pad = (part: number) => String(part).padStart(2, '0');
  return `${Math.floor(seconds / 86400)}d ${pad(Math.floor(seconds % 86400 / 3600))}:${pad(Math.floor(seconds % 3600 / 60))}:${pad(seconds % 60)}`;
}

function RevealTimeline({reveal}: {reveal: NonNullable<Workspace['reveal']>}) {
  const [remaining, setRemaining] = useState(
    reveal.countdownTargetAt ? countdown(reveal.countdownTargetAt) : null,
  );
  useEffect(() => {
    if (!reveal.countdownTargetAt) return;
    const update = () => setRemaining(countdown(reveal.countdownTargetAt!));
    update();
    const timer = globalThis.setInterval(update, 1000);
    return () => globalThis.clearInterval(timer);
  }, [reveal.countdownTargetAt]);
  const firstNow = reveal.state === 'pending';
  const secondNow = reveal.state === 'open' || reveal.state === 'revealed';
  const expired = reveal.state === 'expired';
  return <div className="reveal-timeline">
    <ol className="reveal-track" aria-label="Identity reveal timeline">
      <li className={`reveal-node reveal-node--done${firstNow ? ' reveal-node--now' : ''}`} {...(firstNow ? {'aria-current': 'step' as const} : {})}>
        <span className="reveal-pip" aria-hidden="true" />
        <div className="reveal-when">{legacyDate(reveal.closedAt)}</div>
        <div className="reveal-what">Closed — linking stays sealed for {reveal.cooldownDays} days <span className="sr-only">{firstNow ? '(in progress — cooldown)' : '(completed)'}</span></div>
      </li>
      <li className={`reveal-node${secondNow ? ' reveal-node--now' : expired ? ' reveal-node--done' : ''}`} {...(secondNow ? {'aria-current': 'step' as const} : {})}>
        <span className="reveal-pip" aria-hidden="true" />
        <div className="reveal-when">{legacyDate(reveal.opensAt)}</div>
        <div className="reveal-what">Window opens — {reveal.windowDays} days to optionally link your Wikimedia username <span className="sr-only">{secondNow ? '(current)' : expired ? '(completed)' : '(upcoming)'}</span></div>
      </li>
      <li className={`reveal-node${expired ? ' reveal-node--now' : ''}`} {...(expired ? {'aria-current': 'step' as const} : {})}>
        <span className="reveal-pip" aria-hidden="true" />
        <div className="reveal-when">{legacyDate(reveal.closesAt)}</div>
        <div className="reveal-what">Window closes — records stay pseudonymous permanently <span className="sr-only">{expired ? '(current)' : '(upcoming)'}</span></div>
      </li>
    </ol>
    {remaining && <p className="reveal-deadline">{reveal.state === 'pending' ? 'Reveal window opens in ' : <><strong>Window closes in</strong>{' '}</>}<strong className="reveal-countdown">{remaining}</strong>{reveal.state === 'open' && <> — linking is <strong>permanent and cannot be undone</strong></>}.</p>}
  </div>;
}

function WorkspaceBody({data, csrfToken, routeTab}: {data: Workspace; csrfToken: string; routeTab?: WorkspaceTab}) {
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
      {data.space === 'demo' && <div className="mode-lock mode-lock--demo" style={{marginBottom: '1rem'}}><span className="mode-lock-dot" aria-hidden="true" />Demonstration conversation — try the full flow. Your input is recorded here, just like a real consultation.</div>}
      {data.descriptionHtml && <div className="intro-text" dangerouslySetInnerHTML={{__html: data.descriptionHtml}} />}
      {data.scheduledTransition && <div className="landing-section output-context"><p className="muted" style={{margin: 0}}>Next: <strong>{data.scheduledTransition.targetLabel}</strong> on <time dateTime={data.scheduledTransition.at} title="Shown in your local timezone">{localDateTime(data.scheduledTransition.at)}</time>.</p></div>}
      {data.status === 'closed' ? <ClosedWorkspace data={data} /> : data.status === 'paused' ? <div className="landing-section"><p className="muted">This consultation is temporarily paused. Check back soon.</p></div> : data.tabs.length === 0 ? <div className="landing-section"><p className="muted">Nothing is available yet. Check back soon.</p></div> : (
        <>
          {data.tabs.length > 1 && <div className="tab-bar" role="tablist" onKeyDown={keyDown}>{data.tabs.map((tab, index) => <button key={tab.key} ref={(element) => { tabRefs.current[index] = element; }} id={`tab-btn-${tab.key}`} className={`tab-btn${activeTab === tab.key ? ' tab-btn--active' : ''}`} role="tab" data-tab={`tab-${tab.key}`} aria-controls={`tab-${tab.key}`} aria-selected={activeTab === tab.key} tabIndex={activeTab === tab.key ? 0 : -1} onClick={() => setActiveTab(tab.key)}>{tab.label}</button>)}</div>}
          {data.tabs.map((tab) => <div key={tab.key} id={`tab-${tab.key}`} className={`tab-panel${tab.key === 'arguments' ? ' arguments-tab' : ''}${activeTab === tab.key ? ' tab-panel--active' : ' tab-panel--hidden'}`} role="tabpanel" aria-labelledby={`tab-btn-${tab.key}`}>{activeTab === tab.key && (tab.key === 'vote' ? <ExplorePanel slug={data.slug} csrfToken={csrfToken} /> : tab.key === 'results' ? <LegacyIntermediateResultsPanel slug={data.slug} /> : tab.key === 'arguments' ? <LegacyArgumentMappingPanel slug={data.slug} csrfToken={csrfToken} /> : tab.key === 'informed-voting' ? <LegacyInformedVotingPanel workspace={data} csrfToken={csrfToken} onSelectPreliminary={() => setActiveTab('p6-results')} /> : tab.key === 'p6-results' ? <LegacyPreliminaryResultsPanel slug={data.slug} /> : <div className="landing-section"><p className="muted">{tab.label}</p></div>)}</div>)}
        </>
      )}
      {data.outroHtml && <div className="outro-text" dangerouslySetInnerHTML={{__html: data.outroHtml}} />}
    </div>
  );
}

export function ConversationWorkspacePage() {
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
  if (workspace.isPending) return <p className="loading-state" role="status">Loading conversation…</p>;
  if (workspace.error instanceof ApiContractError && workspace.error.code === 'unauthorized') {
    return <NavigationRedirect href={session.links.login} />;
  }
  const restricted = inviteOnlyDetails(workspace.error);
  if (restricted) return <InviteOnlyPage details={restricted} />;
  if (workspace.error) {
    return <LegacyShell title="Conversation unavailable — ProtoWiki"><div className="container"><div className="landing-section"><h1>Conversation unavailable</h1><p className="muted">{workspace.error.message}</p></div></div></LegacyShell>;
  }
  const data = workspace.data;
  if (data.viewer.state === 'join_required') return <NavigationRedirect href={data.links.join} />;
  return (
    <LegacyShell headerMode={data.space === 'demo' ? 'conversation-demo' : 'conversation-real'} headerCrumb={<ConversationCrumb data={data} />} title={`${data.title} — ProtoWiki`}>
      <WorkspaceBody data={data} csrfToken={session.csrfToken} {...(location.pathname.endsWith('/arguments') ? {routeTab: 'arguments' as const} : location.pathname.endsWith('/informed-voting') ? {routeTab: 'informed-voting' as const} : location.pathname.endsWith('/results') ? {routeTab: 'p6-results' as const} : {})} />
    </LegacyShell>
  );
}
